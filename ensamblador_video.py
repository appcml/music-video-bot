#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensamblador_video.py - Bot simple: Imágenes + Audio = Video
Versión corregida para MoviePy 2.x
"""

import os
import re
import json
import random
import math
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import numpy as np

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
IMAGENES_DIR = 'mis_imagenes'
OUTPUT_DIR = 'output'
VIDEO_ANCHO = 1080
VIDEO_ALTO = 1920
VIDEO_FPS = 30

PALETAS = {
    'oscuro': {'acento':(224,224,224),'texto':(255,255,255),'fondo':(10,10,10)},
    'luminoso': {'acento':(45,45,45), 'texto':(26,26,26), 'fondo':(245,245,240)},
    'neon': {'acento':(127,119,221),'texto':(255,255,255),'fondo':(5,5,16)},
    'natural': {'acento':(93,202,165), 'texto':(232,245,224),'fondo':(26,36,16)},
    'vintage': {'acento':(239,159,39), 'texto':(245,232,208),'fondo':(42,31,20)},
    'pastel': {'acento':(212,83,126), 'texto':(61,26,42), 'fondo':(250,240,245)},
}

def log(msg, tipo='info'):
    iconos = {'info':'ℹ️','ok':'✅','error':'❌','warn':'⚠️','video':'🎬','img':'🖼️','music':'🎵'}
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {iconos.get(tipo,'ℹ️')} {msg}")

def escalar_9_16(img):
    target = VIDEO_ALTO / VIDEO_ANCHO
    ratio = img.height / img.width
    if ratio > target:
        nw, nh = VIDEO_ANCHO, int(VIDEO_ANCHO * ratio)
    else:
        nw, nh = int(VIDEO_ALTO / ratio), VIDEO_ALTO
    img = img.resize((nw, nh), Image.LANCZOS)
    x = (nw - VIDEO_ANCHO) // 2
    y = (nh - VIDEO_ALTO) // 2
    return img.crop((x, y, x + VIDEO_ANCHO, y + VIDEO_ALTO))

def ken_burns(img, progreso, direccion='derecha'):
    p = math.sin(progreso * math.pi / 2)
    zoom = 1.0 + 0.08 * p
    w, h = img.size
    nw, nh = int(w * zoom), int(h * zoom)
    iz = img.resize((nw, nh), Image.BILINEAR)
    dirs = {
        'derecha': (int((nw - w) * p), (nh - h) // 2),
        'izquierda': (int((nw - w) * (1 - p)), (nh - h) // 2),
        'arriba': ((nw - w) // 2, int((nh - h) * p)),
        'abajo': ((nw - w) // 2, int((nh - h) * (1 - p)))
    }
    x, y = dirs.get(direccion, ((nw - w) // 2, (nh - h) // 2))
    return iz.crop((max(0, x), max(0, y), max(0, x) + w, max(0, y) + h))

def transicion_fade(i1, i2, alpha):
    a2 = alpha * alpha * (3 - 2 * alpha)
    if i1.size != i2.size:
        i2 = i2.resize(i1.size, Image.BILINEAR)
    return Image.blend(i1, i2, a2)

def transicion_slide(i1, i2, alpha, direccion='izquierda'):
    a2 = alpha * alpha * (3 - 2 * alpha)
    w, h = i1.size
    if i2.size != (w, h):
        i2 = i2.resize((w, h), Image.BILINEAR)
    resultado = Image.new('RGB', (w, h))
    if direccion == 'izquierda':
        offset = int(w * a2)
        resultado.paste(i1.crop((offset, 0, w, h)), (0, 0))
        resultado.paste(i2.crop((0, 0, w - offset, h)), (w - offset, 0))
    elif direccion == 'derecha':
        offset = int(w * a2)
        resultado.paste(i1.crop((0, 0, w - offset, h)), (offset, 0))
        resultado.paste(i2.crop((offset, 0, w, h)), (0, 0))
    elif direccion == 'arriba':
        offset = int(h * a2)
        resultado.paste(i1.crop((0, offset, w, h)), (0, 0))
        resultado.paste(i2.crop((0, 0, w, h - offset)), (0, h - offset))
    else:  # abajo
        offset = int(h * a2)
        resultado.paste(i1.crop((0, 0, w, h - offset)), (0, offset))
        resultado.paste(i2.crop((0, h - offset, w, h)), (0, 0))
    return resultado

def texto_overlay(frame, texto_principal, texto_secundario, palette_key, idx, total):
    pk = palette_key.lower()
    pal = PALETAS.get(pk, PALETAS['oscuro'])
    w, h = frame.size
    
    try:
        ft = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        fa = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
        fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except:
        ft = fa = fs = ImageFont.load_default()

    # Gradiente oscuro abajo
    ov = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(ov)
    for yo in range(400):
        al = int(180 * (yo / 400))
        od.line([(0, h - 400 + yo), (w, h - 400 + yo)], fill=(0, 0, 0, al))
    
    frame = frame.convert('RGBA')
    frame = Image.alpha_composite(frame, ov).convert('RGB')
    draw = ImageDraw.Draw(frame)

    # Texto principal
    y = h - 320
    draw.text((50, y), texto_principal[:50], font=ft, fill=pal['texto'])
    draw.text((50, y + 80), texto_secundario[:40], font=fa, fill=pal['acento'])
    draw.text((w - 120, 40), f"{idx + 1}/{total}", font=fs, fill=pal['texto'])
    
    return frame

def main():
    print("\n" + "=" * 60)
    print("🎬 ENSAMBLADOR DE VIDEO - Modo Prueba")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    # 1. Detectar imágenes y audio
    exts_img = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    exts_audio = {'.mp3', '.wav', '.m4a', '.flac', '.aac'}
    
    imagenes = []
    audio_path = None
    
    if not os.path.exists(IMAGENES_DIR):
        log(f"ERROR: No existe carpeta {IMAGENES_DIR}", 'error')
        return False
    
    for f in sorted(Path(IMAGENES_DIR).iterdir()):
        if f.name == '.gitkeep':
            continue
        if f.suffix.lower() in exts_img:
            imagenes.append(str(f))
            log(f"📸 {f.name}", 'img')
        elif f.suffix.lower() in exts_audio and not audio_path:
            audio_path = str(f)
            log(f"🎵 Audio: {f.name}", 'music')
    
    if not imagenes:
        log("ERROR: No hay imágenes en mis_imagenes/", 'error')
        return False
    
    if not audio_path:
        log("ERROR: No hay audio en mis_imagenes/", 'error')
        return False
    
    log(f"Modo: RÁPIDO — {len(imagenes)} imgs + 1 audio", 'ok')
    
    # 2. Cargar config (opcional)
    config = {}
    if os.path.exists('config_cancion.json'):
        try:
            with open('config_cancion.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
        except:
            pass
    
    palette = config.get('palette', 'Oscuro')
    song_name = config.get('song_name', 'Video')
    artist = config.get('artist', '')
    
    # 3. Procesar imágenes
    log("Procesando imágenes...", 'info')
    imgs_pil = []
    for p in imagenes:
        try:
            img = Image.open(p).convert('RGB')
            img = escalar_9_16(img)
            imgs_pil.append(img)
        except Exception as e:
            log(f"Error cargando {p}: {e}", 'warn')
    
    if not imgs_pil:
        log("No se pudieron cargar imágenes", 'error')
        return False
    
    log(f"Imágenes procesadas: {len(imgs_pil)}", 'ok')
    
    # 4. Importar MoviePy (compatible con v1.x y v2.x)
    log("Importando MoviePy...", 'info')
    try:
        from moviepy.editor import ImageSequenceClip, AudioFileClip
        log("MoviePy v1.x detectado", 'ok')
    except ImportError:
        try:
            from moviepy import ImageSequenceClip, AudioFileClip
            log("MoviePy v2.x detectado", 'ok')
        except ImportError as e:
            log(f"ERROR: No se pudo importar MoviePy: {e}", 'error')
            return False
    
    # 5. Calcular duración del audio
    try:
        audio_clip = AudioFileClip(audio_path)
        duracion_audio = audio_clip.duration
        audio_clip.close()
    except Exception as e:
        log(f"Error leyendo audio: {e}", 'error')
        return False
    
    log(f"Duración audio: {duracion_audio:.1f}s", 'info')
    
    # Segundos por imagen
    spi = duracion_audio / len(imgs_pil)
    log(f"Segundos por imagen: {spi:.1f}s", 'info')
    
    # Frames por imagen
    FI = int(VIDEO_FPS * spi)
    FT = int(VIDEO_FPS * 0.6)  # Frames de transición
    
    # 6. Generar frames
    log("Generando frames...", 'video')
    
    efectos = ['derecha', 'izquierda', 'arriba', 'abajo']
    transiciones = ['fade', 'izquierda', 'derecha', 'arriba', 'abajo']
    random.shuffle(efectos)
    
    frames = []
    total_imgs = len(imgs_pil)
    
    for i in range(total_imgs):
        img = imgs_pil[i]
        efecto = efectos[i % len(efectos)]
        
        # Frames estáticos + Ken Burns
        for f in range(FI - FT):
            p = f / max(FI - FT - 1, 1)
            frame = ken_burns(img, p, efecto)
            frame = texto_overlay(frame, song_name, artist, palette, i, total_imgs)
            frames.append(np.array(frame))
        
        # Frames de transición (excepto última imagen)
        if i < total_imgs - 1:
            next_img = imgs_pil[i + 1]
            trans = transiciones[i % len(transiciones)]
            for f in range(FT):
                alpha = f / max(FT - 1, 1)
                if trans == 'fade':
                    frame = transicion_fade(img, next_img, alpha)
                else:
                    frame = transicion_slide(img, next_img, alpha, trans)
                frame = texto_overlay(frame, song_name, artist, palette, i, total_imgs)
                frames.append(np.array(frame))
    
    # Últimos frames de la última imagen
    ultima = imgs_pil[-1]
    for f in range(FT):
        p = f / max(FT - 1, 1)
        frame = ken_burns(ultima, p, efectos[-1])
        frame = texto_overlay(frame, song_name, artist, palette, total_imgs - 1, total_imgs)
        frames.append(np.array(frame))
    
    log(f"Total frames generados: {len(frames)}", 'ok')
    
    # 7. Ensamblar video
    log("Ensamblando video...", 'video')
    
    clip = ImageSequenceClip(frames, fps=VIDEO_FPS)
    
    # Añadir audio
    try:
        audio = AudioFileClip(audio_path)
        if audio.duration > clip.duration:
            audio = audio.subclip(0, clip.duration)
        clip = clip.set_audio(audio)
        log("Audio añadido correctamente", 'ok')
    except Exception as e:
        log(f"Error con audio: {e}", 'warn')
    
    # Exportar
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    nombre = re.sub(r'[^\w\s-]', '', song_name).strip().replace(' ', '_')[:40]
    out = f"{OUTPUT_DIR}/{nombre}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp4"
    
    log("Renderizando... (puede tardar varios minutos)", 'video')
    
    clip.write_videofile(
        out,
        codec='libx264',
        audio_codec='aac',
        preset='ultrafast',
        ffmpeg_params=['-crf', '28', '-profile:v', 'baseline', '-level', '3.0'],
        logger=None,
        threads=4
    )
    
    dur_real = clip.duration
    clip.close()
    
    mb = os.path.getsize(out) / (1024 * 1024)
    log(f"✅ VIDEO LISTO: {out} ({mb:.1f}MB, {dur_real:.0f}s)", 'ok')
    
    print(f"\n{'=' * 60}\n✅ {out}\n{'=' * 60}\n")
    return True

if __name__ == "__main__":
    try:
        ok = main()
        exit(0 if ok else 1)
    except Exception as e:
        log(f"Error crítico: {e}", 'error')
        import traceback
        traceback.print_exc()
        exit(1)
