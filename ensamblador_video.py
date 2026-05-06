#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ensamblador_video.py - Bot: Imágenes + Audio = Video
Versión 2.0 — Ken Burns real + crossfade + pipeline optimizado
"""

import os
import re
import json
import numpy as np
from datetime import datetime
from pathlib import Path

# MoviePy imports con fallback para v1.x y v2.x
try:
    from moviepy.editor import (
        ImageClip, AudioFileClip, concatenate_videoclips,
        CompositeVideoClip, VideoClip
    )
    MOVIEPY_V1 = True
except ImportError:
    from moviepy import (
        ImageClip, AudioFileClip, concatenate_videoclips,
        CompositeVideoClip, VideoClip
    )
    MOVIEPY_V1 = False

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
IMAGENES_DIR = 'mis_imagenes'
OUTPUT_DIR   = 'output'
VIDEO_ANCHO  = 1080
VIDEO_ALTO   = 1920
VIDEO_FPS    = 24

# Duración mínima por imagen (segundos)
DUR_MIN_IMG  = 4.0
# Máximo zoom Ken Burns (5% = sutil, 10% = notable)
ZOOM_MAX     = 0.07
# Duración del crossfade entre imágenes (segundos)
DUR_FADE     = 1.2

PALETAS = {
    'oscuro':    {'acento': (224, 224, 224), 'texto': (255, 255, 255), 'fondo': (10,  10,  10)},
    'luminoso':  {'acento': (45,  45,  45),  'texto': (26,  26,  26),  'fondo': (245, 245, 240)},
    'neon':      {'acento': (127, 119, 221), 'texto': (255, 255, 255), 'fondo': (5,   5,   16)},
    'natural':   {'acento': (93,  202, 165), 'texto': (232, 245, 224), 'fondo': (26,  36,  16)},
    'vintage':   {'acento': (239, 159, 39),  'texto': (245, 232, 208), 'fondo': (42,  31,  20)},
    'pastel':    {'acento': (212, 83,  126), 'texto': (61,  26,  42),  'fondo': (250, 240, 245)},
}

# ──────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────
def log(msg, tipo='info'):
    iconos = {'info': 'ℹ️', 'ok': '✅', 'error': '❌', 'warn': '⚠️',
              'video': '🎬', 'img': '🖼️', 'music': '🎵'}
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {iconos.get(tipo, 'ℹ️')} {msg}")


def preparar_imagen(ruta_img):
    """
    Carga, recorta y devuelve un ndarray numpy listo para MoviePy.
    Sin guardar temporales a disco → más rápido y menos I/O.
    """
    try:
        img = Image.open(ruta_img).convert('RGB')
        # Para Ken Burns necesitamos un canvas más grande que el frame final.
        # Usamos 1 + ZOOM_MAX como factor de escala base.
        factor  = 1.0 + ZOOM_MAX + 0.03          # margen extra para no ver bordes
        tw      = int(VIDEO_ANCHO * factor)
        th      = int(VIDEO_ALTO  * factor)

        # Escalar manteniendo relación de aspecto para cubrir el canvas grande
        ratio_t = th / tw
        ratio_i = img.height / img.width
        if ratio_i > ratio_t:
            nw, nh = tw, int(tw * ratio_i)
        else:
            nw, nh = int(th / ratio_i), th

        img = img.resize((nw, nh), Image.LANCZOS)
        # Centrar y recortar al canvas grande
        x = (nw - tw) // 2
        y = (nh - th) // 2
        img = img.crop((x, y, x + tw, y + th))
        return np.array(img), tw, th
    except Exception as e:
        log(f"Error en {ruta_img}: {e}", 'error')
        return None, 0, 0


def make_ken_burns_clip(arr, canvas_w, canvas_h, duracion, direccion='in'):
    """
    Genera un ImageClip animado con efecto Ken Burns (zoom suave).
    direccion='in'  → zoom hacia adentro (imagen crece levemente)
    direccion='out' → zoom hacia afuera (imagen se aleja levemente)
    """
    fw, fh = VIDEO_ANCHO, VIDEO_ALTO

    def make_frame(t):
        progress = t / duracion if duracion > 0 else 0
        if direccion == 'in':
            zoom = 1.0 + ZOOM_MAX * progress        # crece de 1.0 a 1+ZOOM_MAX
        else:
            zoom = (1.0 + ZOOM_MAX) - ZOOM_MAX * progress  # decrece

        # Tamaño del recorte en el canvas grande
        cw = int(canvas_w / zoom)
        ch = int(canvas_h / zoom)

        # Centrar el recorte
        x0 = (canvas_w - cw) // 2
        y0 = (canvas_h - ch) // 2
        x1, y1 = x0 + cw, y0 + ch

        # Recortar y escalar a resolución final
        patch = arr[y0:y1, x0:x1]
        frame = np.array(
            Image.fromarray(patch).resize((fw, fh), Image.BILINEAR)
        )
        return frame

    clip = VideoClip(make_frame, duration=duracion)
    clip = clip.set_fps(VIDEO_FPS)
    return clip


def crear_overlay_np(song_name, artist, palette_key, idx, total):
    """
    Crea el overlay de texto como ndarray RGBA.
    Se hace una sola vez por imagen (no por frame).
    """
    pk  = palette_key.lower()
    pal = PALETAS.get(pk, PALETAS['oscuro'])
    w, h = VIDEO_ANCHO, VIDEO_ALTO

    img  = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Cargar fuentes
    try:
        font_bold  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 62)
        font_reg   = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      42)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",      28)
    except Exception:
        font_bold = font_reg = font_small = ImageFont.load_default()

    # Gradiente oscuro en la parte inferior (para legibilidad)
    grad_h = 380
    for yo in range(grad_h):
        alpha = int(190 * (yo / grad_h) ** 1.5)   # curva suave
        draw.line([(0, h - grad_h + yo), (w, h - grad_h + yo)],
                  fill=(0, 0, 0, alpha))

    # Línea decorativa de acento
    r, g, b = pal['acento']
    draw.rectangle([(48, h - 295), (8, h - 145)], fill=(r, g, b, 220))

    # Texto: nombre de canción (máx 2 líneas)
    nombre_lines = _wrap_text(song_name, 28)[:2]
    y_txt = h - 290
    for linea in nombre_lines:
        draw.text((68, y_txt), linea, font=font_bold,
                  fill=pal['texto'] + (255,))
        y_txt += 72

    # Artista
    if artist:
        draw.text((68, y_txt + 4), artist[:38], font=font_reg,
                  fill=pal['acento'] + (220,))

    # Contador de imagen (esquina superior derecha)
    draw.text((w - 115, 36), f"{idx + 1}/{total}", font=font_small,
              fill=pal['texto'] + (180,))

    return np.array(img)


def _wrap_text(texto, max_chars):
    """Divide texto en líneas de máx max_chars caracteres."""
    palabras = texto.split()
    lineas, actual = [], ''
    for p in palabras:
        if len(actual) + len(p) + 1 <= max_chars:
            actual = (actual + ' ' + p).strip()
        else:
            if actual:
                lineas.append(actual)
            actual = p
    if actual:
        lineas.append(actual)
    return lineas or ['']


# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def main():
    print("\n" + "=" * 60)
    print("🎬 ENSAMBLADOR DE VIDEO v2.0 — Ken Burns + Crossfade")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    # ── 1. Detectar archivos ──────────────────────────────────
    exts_img   = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    exts_audio = {'.mp3', '.wav', '.m4a', '.flac', '.aac'}

    imagenes   = []
    audio_path = None

    if not os.path.exists(IMAGENES_DIR):
        log(f"No existe carpeta '{IMAGENES_DIR}'", 'error')
        return False

    for f in sorted(Path(IMAGENES_DIR).iterdir()):
        if f.name.startswith('.'):
            continue
        if f.suffix.lower() in exts_img:
            imagenes.append(str(f))
            log(f"{f.name}", 'img')
        elif f.suffix.lower() in exts_audio and not audio_path:
            audio_path = str(f)
            log(f"Audio: {f.name}", 'music')

    if not imagenes:
        log("No hay imágenes en mis_imagenes/", 'error')
        return False
    if not audio_path:
        log("No hay audio en mis_imagenes/", 'error')
        return False

    log(f"{len(imagenes)} imágenes + audio detectados", 'ok')

    # ── 2. Leer config ────────────────────────────────────────
    config    = {}
    if os.path.exists('config_cancion.json'):
        try:
            with open('config_cancion.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception:
            pass

    palette   = config.get('palette',   'Oscuro')
    song_name = config.get('song_name', 'Video')
    artist    = config.get('artist',    '')

    log(f"Canción: {song_name} | Artista: {artist} | Paleta: {palette}", 'info')

    # ── 3. Cargar audio ───────────────────────────────────────
    try:
        audio           = AudioFileClip(audio_path)
        duracion_total  = audio.duration
        log(f"Duración audio: {duracion_total:.1f}s", 'ok')
    except Exception as e:
        log(f"Error cargando audio: {e}", 'error')
        return False

    # ── 4. Calcular tiempos ───────────────────────────────────
    n_imgs          = len(imagenes)
    # Duración neta por imagen (sin contar el solapamiento del fade)
    # total = n * dur_img - (n-1) * DUR_FADE  →  dur_img = (total + (n-1)*DUR_FADE) / n
    dur_img         = max(DUR_MIN_IMG,
                          (duracion_total + (n_imgs - 1) * DUR_FADE) / n_imgs)
    dur_fade        = min(DUR_FADE, dur_img * 0.25)

    log(f"Duración por imagen: {dur_img:.1f}s | Fade: {dur_fade:.1f}s", 'info')

    # ── 5. Preparar imágenes (numpy, en RAM) ──────────────────
    log("Cargando y preparando imágenes...", 'info')
    datos_imgs = []
    for p in imagenes:
        arr, cw, ch = preparar_imagen(p)
        if arr is not None:
            datos_imgs.append((arr, cw, ch))
            log(f"  ✓ {Path(p).name}", 'img')

    if not datos_imgs:
        log("No se pudieron procesar imágenes", 'error')
        return False

    n_imgs = len(datos_imgs)

    # ── 6. Crear clips Ken Burns + overlay ───────────────────
    log("Generando clips Ken Burns...", 'video')
    clips_kb = []
    direcciones = ['in', 'out']  # alternar para variedad

    for i, (arr, cw, ch) in enumerate(datos_imgs):
        dir_kb = direcciones[i % 2]
        kb     = make_ken_burns_clip(arr, cw, ch, dur_img, dir_kb)

        # Overlay estático convertido a clip
        overlay_np = crear_overlay_np(song_name, artist, palette, i, n_imgs)
        overlay    = ImageClip(overlay_np, ismask=False, duration=dur_img)

        comp = CompositeVideoClip([kb, overlay], size=(VIDEO_ANCHO, VIDEO_ALTO))
        clips_kb.append(comp)

    # ── 7. Encadenar con crossfade ────────────────────────────
    log("Aplicando crossfade entre clips...", 'video')

    # Añadir crossfadein a todos excepto el primero
    clips_con_fade = [clips_kb[0]]
    for clip in clips_kb[1:]:
        clips_con_fade.append(clip.crossfadein(dur_fade))

    # Calcular start times para que los fades se superpongan
    starts = [0]
    for i in range(1, n_imgs):
        starts.append(starts[i - 1] + dur_img - dur_fade)

    # Componer todo en un solo clip de duración total real
    duracion_real = starts[-1] + dur_img
    clips_con_start = [
        c.set_start(s) for c, s in zip(clips_con_fade, starts)
    ]
    video_final = CompositeVideoClip(clips_con_start,
                                     size=(VIDEO_ANCHO, VIDEO_ALTO),
                                     use_bgclip=True)
    video_final = video_final.set_duration(min(duracion_real, duracion_total))

    # ── 8. Añadir audio ───────────────────────────────────────
    if audio.duration > video_final.duration:
        audio = audio.subclip(0, video_final.duration)
    video_final = video_final.set_audio(audio)

    # ── 9. Exportar ───────────────────────────────────────────
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    nombre_limpio = re.sub(r'[^\w\s-]', '', song_name).strip().replace(' ', '_')[:40]
    out_path = f"{OUTPUT_DIR}/{nombre_limpio}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp4"

    log(f"Renderizando → {out_path}", 'video')

    video_final.write_videofile(
        out_path,
        fps=VIDEO_FPS,
        codec='libx264',
        audio_codec='aac',
        preset='faster',                      # más rápido que 'ultrafast' con mejor calidad
        ffmpeg_params=[
            '-crf', '26',                     # calidad equilibrada (menor = mejor)
            '-profile:v', 'baseline',
            '-level', '3.1',
            '-pix_fmt', 'yuv420p',            # compatibilidad máxima
        ],
        logger=None,
        threads=4,
        write_logfile=False,
    )

    # Liberar memoria
    video_final.close()
    audio.close()

    mb = os.path.getsize(out_path) / (1024 * 1024)
    log(f"VIDEO LISTO: {out_path} ({mb:.1f} MB, {video_final.duration:.0f}s)", 'ok')
    print(f"\n{'=' * 60}\n✅  {out_path}\n{'=' * 60}\n")
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
