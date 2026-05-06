#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensamblador_video.py - Bot simple: Imágenes + Audio = Video
Version optimizada para GitHub Actions (bajo consumo de RAM)
"""

import os
import re
import json
import random
from datetime import datetime
from pathlib import Path

# MoviePy imports con fallback para v1.x y v2.x
try:
    from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, TextClip
except ImportError:
    from moviepy import ImageClip, AudioFileClip, concatenate_videoclips, CompositeVideoClip, TextClip

from PIL import Image, ImageDraw, ImageFont

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
IMAGENES_DIR = 'mis_imagenes'
OUTPUT_DIR = 'output'
VIDEO_ANCHO = 1080
VIDEO_ALTO = 1920
VIDEO_FPS = 24

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

def escalar_9_16(ruta_img):
    """Procesa imagen y la guarda optimizada para video vertical"""
    try:
        img = Image.open(ruta_img).convert('RGB')
        target_ratio = VIDEO_ALTO / VIDEO_ANCHO
        ratio = img.height / img.width
        
        if ratio > target_ratio:
            nw, nh = VIDEO_ANCHO, int(VIDEO_ANCHO * ratio)
        else:
            nw, nh = int(VIDEO_ALTO / ratio), VIDEO_ALTO
        
        img = img.resize((nw, nh), Image.LANCZOS)
        x = (nw - VIDEO_ANCHO) // 2
        y = (nh - VIDEO_ALTO) // 2
        img = img.crop((x, y, x + VIDEO_ANCHO, y + VIDEO_ALTO))
        
        # Guardar temporal optimizada
        tmp_path = f"/tmp/ensamblador_{os.path.basename(ruta_img)}"
        img.save(tmp_path, 'JPEG', quality=85, optimize=True)
        return tmp_path
    except Exception as e:
        log(f"Error procesando {ruta_img}: {e}", 'error')
        return None

def crear_texto_overlay(texto, subtitulo, palette_key, idx, total):
    """Crea imagen PNG con texto para overlay"""
    pk = palette_key.lower()
    pal = PALETAS.get(pk, PALETAS['oscuro'])
    w, h = VIDEO_ANCHO, VIDEO_ALTO
    
    # Crear imagen transparente
    img = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    
    try:
        ft = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        fa = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
        fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
    except:
        ft = fa = fs = ImageFont.load_default()
    
    # Gradiente oscuro abajo
    for yo in range(350):
        al = int(160 * (yo / 350))
        draw.line([(0, h - 350 + yo), (w, h - 350 + yo)], fill=(0, 0, 0, al))
    
    # Textos
    y = h - 300
    draw.text((50, y), texto[:50], font=ft, fill=pal['texto'] + (255,))
    draw.text((50, y + 80), subtitulo[:40], font=fa, fill=pal['acento'] + (255,))
    draw.text((w - 120, 40), f"{idx + 1}/{total}", font=fs, fill=pal['texto'] + (255,))
    
    tmp_path = f"/tmp/overlay_{idx}.png"
    img.save(tmp_path, 'PNG')
    return tmp_path

def main():
    print("\n" + "=" * 60)
    print("🎬 ENSAMBLADOR DE VIDEO - Version Optimizada")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    # 1. Detectar archivos
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
        log("ERROR: No hay imagenes", 'error')
        return False
    if not audio_path:
        log("ERROR: No hay audio", 'error')
        return False
    
    log(f"Listo: {len(imagenes)} imgs + 1 audio", 'ok')
    
    # 2. Config
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
    
    # 3. Procesar imagenes
    log("Optimizando imagenes...", 'info')
    imgs_procesadas = []
    for p in imagenes:
        tmp = escalar_9_16(p)
        if tmp:
            imgs_procesadas.append(tmp)
    
    if not imgs_procesadas:
        log("No se pudieron procesar imagenes", 'error')
        return False
    
    log(f"Imagenes OK: {len(imgs_procesadas)}", 'ok')
    
    # 4. Cargar audio y calcular duracion
    try:
        audio = AudioFileClip(audio_path)
        duracion_total = audio.duration
        log(f"Audio: {duracion_total:.1f}s", 'ok')
    except Exception as e:
        log(f"Error audio: {e}", 'error')
        return False
    
    # 5. Calcular duracion por imagen
    n_imgs = len(imgs_procesadas)
    duracion_por_img = duracion_total / n_imgs
    duracion_transicion = min(1.5, duracion_por_img * 0.2)  # 20% o max 1.5s
    duracion_visible = duracion_por_img - duracion_transicion
    
    log(f"Cada imagen: {duracion_visible:.1f}s + transicion {duracion_transicion:.1f}s", 'info')
    
    # 6. Crear clips de video
    log("Creando clips de video...", 'video')
    
    clips_finales = []
    efectos = ['derecha', 'izquierda', 'arriba', 'abajo']
    
    for i, img_path in enumerate(imgs_procesadas):
        efecto = efectos[i % len(efectos)]
        
        # Clip principal con zoom sutil (simulando Ken Burns con resize)
        clip_img = ImageClip(img_path, duration=duracion_visible)
        
        # Aplicar zoom sutil
        def make_zoom(t):
            # Zoom del 1.0 al 1.05 durante la duracion
            progress = t / duracion_visible if duracion_visible > 0 else 0
            zoom = 1.0 + (0.05 * progress)
            return zoom
        
        # No aplicamos zoom complejo para evitar problemas de memoria
        # Solo usamos la imagen estatica con duracion correcta
        
        # Overlay de texto
        overlay_path = crear_texto_overlay(song_name, artist, palette, i, n_imgs)
        overlay_clip = ImageClip(overlay_path, duration=duracion_visible)
        
        # Componer imagen + texto
        video_clip = CompositeVideoClip([clip_img, overlay_clip], size=(VIDEO_ANCHO, VIDEO_ALTO))
        
        clips_finales.append(video_clip)
        
        # Transicion (excepto ultima)
        if i < n_imgs - 1:
            next_img = imgs_procesadas[i + 1]
            # Clip de transicion: fade out de actual, fade in de siguiente
            trans_clip = ImageClip(next_img, duration=duracion_transicion)
            trans_overlay = ImageClip(
                crear_texto_overlay(song_name, artist, palette, i + 1, n_imgs),
                duration=duracion_transicion
            )
            trans_composite = CompositeVideoClip([trans_clip, trans_overlay], size=(VIDEO_ANCHO, VIDEO_ALTO))
            trans_composite = trans_composite.crossfadein(duracion_transicion)
            
            clips_finales.append(trans_composite)
    
    # 7. Concatenar todo
    log("Concatenando clips...", 'video')
    video_final = concatenate_videoclips(clips_finales, method="compose")
    
    # Ajustar duracion exacta al audio
    if video_final.duration > duracion_total:
        video_final = video_final.subclip(0, duracion_total)
    
    # Añadir audio
    if audio.duration > video_final.duration:
        audio = audio.subclip(0, video_final.duration)
    video_final = video_final.set_audio(audio)
    
    # 8. Exportar
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    nombre = re.sub(r'[^\w\s-]', '', song_name).strip().replace(' ', '_')[:40]
    out = f"{OUTPUT_DIR}/{nombre}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp4"
    
    log("Renderizando video...", 'video')
    
    video_final.write_videofile(
        out,
        fps=VIDEO_FPS,
        codec='libx264',
        audio_codec='aac',
        preset='ultrafast',
        ffmpeg_params=['-crf', '30', '-profile:v', 'baseline', '-level', '3.0'],
        logger=None,
        threads=4
    )
    
    dur_real = video_final.duration
    video_final.close()
    audio.close()
    
    # Limpiar temporales
    for p in imgs_procesadas:
        try:
            if os.path.exists(p):
                os.remove(p)
        except:
            pass
    
    mb = os.path.getsize(out) / (1024 * 1024)
    log(f"✅ VIDEO LISTO: {out} ({mb:.1f}MB, {dur_real:.0f}s)", 'ok')
    
    print(f"\n{'=' * 60}\n✅ {out}\n{'=' * 60}\n")
    return True

if __name__ == "__main__":
    try:
        ok = main()
        exit(0 if ok else 1)
    except Exception as e:
        log(f"Error critico: {e}", 'error')
        import traceback
        traceback.print_exc()
        exit(1)
