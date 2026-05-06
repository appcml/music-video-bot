#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
music_video_bot.py — Generador Automático de Videos Musicales
Repositorio: appcml/music-video-bot

FLUJO:
  1. Lee config_cancion.json (generado por el formulario)
  2. Busca la letra en Genius / AZLyrics / scraping
  3. Sintetiza concepto visual con Gemini/OpenRouter
  4. Recopila imágenes del usuario + genera con IA (Pollinations)
  5. Aplica filtros de color según paleta elegida
  6. Ensambla video vertical 9:16 con el audio real
  7. Guarda en output/ con nombre de la canción
  8. Actualiza proyectos.json (memoria)
"""

import os, re, json, random, hashlib, asyncio, textwrap, time, subprocess
import requests
from datetime import datetime
from urllib.parse import quote_plus
from pathlib import Path
from difflib import SequenceMatcher

# ──────────────────────────────────────────────
# CONFIGURACIÓN
# ──────────────────────────────────────────────
GENIUS_TOKEN      = os.getenv('GENIUS_TOKEN', '')
GEMINI_API_KEY    = os.getenv('GEMINI_API_KEY', '')
OPENROUTER_API_KEY= os.getenv('OPENROUTER_API_KEY', '')
PIXABAY_API_KEY   = os.getenv('PIXABAY_API_KEY', '')
PEXELS_API_KEY    = os.getenv('PEXELS_API_KEY', '')

CONFIG_PATH       = 'config_cancion.json'
PROYECTOS_PATH    = 'proyectos/proyectos.json'
MIS_IMAGENES_DIR  = 'mis_imagenes'
OUTPUT_DIR        = 'output'

VIDEO_ANCHO = 1080
VIDEO_ALTO  = 1920
VIDEO_FPS   = 24

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# Paletas de color por estilo
PALETAS = {
    'oscuro':    {'fondo': '#0a0a0a', 'acento': '#e0e0e0', 'texto': '#ffffff', 'filtro': 'oscuro'},
    'luminoso':  {'fondo': '#f5f5f0', 'acento': '#2d2d2d', 'texto': '#1a1a1a', 'filtro': 'ninguno'},
    'neon':      {'fondo': '#050510', 'acento': '#7F77DD', 'texto': '#ffffff', 'filtro': 'neon'},
    'natural':   {'fondo': '#1a2410', 'acento': '#5DCAA5', 'texto': '#e8f5e0', 'filtro': 'calido'},
    'vintage':   {'fondo': '#2a1f14', 'acento': '#EF9F27', 'texto': '#f5e8d0', 'filtro': 'vintage'},
    'pastel':    {'fondo': '#faf0f5', 'acento': '#D4537E', 'texto': '#3d1a2a', 'filtro': 'suave'},
}

def log(msg, tipo='info'):
    iconos = {'info':'ℹ️','ok':'✅','error':'❌','warn':'⚠️','debug':'🔍','video':'🎬','img':'🖼️','ia':'🤖','music':'🎵'}
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {iconos.get(tipo,'ℹ️')} {msg}")

# ──────────────────────────────────────────────
# UTILIDADES
# ──────────────────────────────────────────────
def cargar_json(ruta, default=None):
    default = default or {}
    if os.path.exists(ruta):
        try:
            with open(ruta, 'r', encoding='utf-8') as f:
                c = f.read().strip()
                return json.loads(c) if c else default.copy()
        except:
            pass
    return default.copy()

def guardar_json(ruta, datos):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)
    os.replace(tmp, ruta)

def generar_hash(texto):
    return hashlib.md5(texto.encode()).hexdigest()[:10]

def limpiar_nombre_archivo(nombre):
    return re.sub(r'[^\w\s-]', '', nombre).strip().replace(' ', '_')[:50]

# ──────────────────────────────────────────────
# PASO 1: LEER CONFIGURACIÓN
# ──────────────────────────────────────────────
def leer_config():
    if not os.path.exists(CONFIG_PATH):
        log(f"No se encontró {CONFIG_PATH}", 'error')
        return None
    config = cargar_json(CONFIG_PATH)
    log(f"Canción: '{config.get('song_name')}' — {config.get('artist')}", 'music')
    log(f"Géneros: {config.get('genres', 'no especificado')}", 'debug')
    log(f"Paleta: {config.get('palette','oscuro')} | Transición: {config.get('transition','Ken Burns')}", 'debug')
    return config

# ──────────────────────────────────────────────
# PASO 2: BUSCAR LETRA
# ──────────────────────────────────────────────
def buscar_letra_genius(song_name, artist):
    if not GENIUS_TOKEN:
        return None
    try:
        r = requests.get(
            'https://api.genius.com/search',
            headers={'Authorization': f'Bearer {GENIUS_TOKEN}'},
            params={'q': f'{song_name} {artist}'},
            timeout=15
        ).json()
        hits = r.get('response', {}).get('hits', [])
        if not hits:
            return None
        url = hits[0]['result']['url']
        log(f"Genius: encontrada en {url}", 'debug')
        return scrape_letra(url)
    except Exception as e:
        log(f"Genius error: {e}", 'debug')
        return None

def scrape_letra(url):
    try:
        from bs4 import BeautifulSoup
        r = requests.get(url, headers=HEADERS, timeout=20)
        s = BeautifulSoup(r.content, 'html.parser')
        # Genius usa contenedores data-lyrics-container
        containers = s.find_all('div', {'data-lyrics-container': 'true'})
        if containers:
            lines = []
            for c in containers:
                for br in c.find_all('br'):
                    br.replace_with('\n')
                lines.append(c.get_text())
            return '\n'.join(lines).strip()
        # Fallback genérico
        for div in s.find_all('div', class_=lambda x: x and 'lyrics' in x.lower()):
            texto = div.get_text('\n').strip()
            if len(texto) > 100:
                return texto
    except Exception as e:
        log(f"Scrape letra error: {e}", 'debug')
    return None

def buscar_letra_azlyrics(song_name, artist):
    try:
        from bs4 import BeautifulSoup
        artist_clean = re.sub(r'[^a-z0-9]', '', artist.lower())
        song_clean   = re.sub(r'[^a-z0-9]', '', song_name.lower())
        url = f"https://www.azlyrics.com/lyrics/{artist_clean}/{song_clean}.html"
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.status_code != 200:
            return None
        s = BeautifulSoup(r.content, 'html.parser')
        divs = s.find_all('div', class_=False, id=False)
        for div in divs:
            texto = div.get_text('\n').strip()
            if len(texto) > 200 and '\n' in texto:
                return texto
    except Exception as e:
        log(f"AZLyrics error: {e}", 'debug')
    return None

def buscar_letra_spotify_link(spotify_link):
    """Intenta extraer letra desde el link de Spotify vía scraping de metadatos."""
    if not spotify_link:
        return None
    try:
        from bs4 import BeautifulSoup
        r = requests.get(spotify_link, headers=HEADERS, timeout=20)
        s = BeautifulSoup(r.content, 'html.parser')
        # Extraer título y artista de los metadatos
        title = s.find('meta', property='og:title')
        if title:
            return title.get('content', '')
    except:
        pass
    return None

def obtener_letra(config):
    song_name = config.get('song_name', '')
    artist    = config.get('artist', '')
    log(f"🎵 Buscando letra de '{song_name}' — {artist}", 'music')

    # Cascada: Genius → AZLyrics → sin letra
    letra = buscar_letra_genius(song_name, artist)
    if letra and len(letra) > 50:
        log(f"Letra encontrada en Genius ({len(letra)} chars)", 'ok')
        return letra

    letra = buscar_letra_azlyrics(song_name, artist)
    if letra and len(letra) > 50:
        log(f"Letra encontrada en AZLyrics ({len(letra)} chars)", 'ok')
        return letra

    log("Letra no encontrada — se usará descripción de la canción", 'warn')
    return config.get('song_desc', '')

# ──────────────────────────────────────────────
# PASO 3: SÍNTESIS VISUAL CON IA
# ──────────────────────────────────────────────
PROMPT_VISUAL = """Eres un director de arte para videos musicales verticales (9:16) para Spotify y Reels.

CANCIÓN: "{song_name}" — {artist}
GÉNEROS: {genres}
DESCRIPCIÓN: {song_desc}
ESTILO ELEGIDO: {yt_ref}
PALETA: {palette}
LETRA (fragmento):
{letra}

Genera un concepto visual detallado para el video. RESPONDE SOLO EN JSON sin markdown:
{{
  "concepto": "Descripción del concepto visual en 2-3 oraciones",
  "mood": "Una palabra que define el mood visual",
  "queries_imagenes": [
    "query en inglés muy específico para imagen 1",
    "query en inglés muy específico para imagen 2",
    "query en inglés muy específico para imagen 3",
    "query en inglés muy específico para imagen 4",
    "query en inglés muy específico para imagen 5",
    "query en inglés muy específico para imagen 6"
  ],
  "prompts_ia": [
    "prompt detallado para generar imagen IA 1 — debe ser visual, sin texto, fotorealista",
    "prompt detallado para generar imagen IA 2",
    "prompt detallado para generar imagen IA 3",
    "prompt detallado para generar imagen IA 4"
  ],
  "texto_pantalla": "Texto exacto que aparecerá en el video (nombre canción + artista)",
  "hashtags": "#hashtag1 #hashtag2 #hashtag3 #hashtag4 #hashtag5"
}}"""

def sintetizar_concepto_gemini(config, letra):
    if not GEMINI_API_KEY:
        return None
    prompt = PROMPT_VISUAL.format(
        song_name=config.get('song_name',''),
        artist=config.get('artist',''),
        genres=config.get('genres',''),
        song_desc=config.get('song_desc',''),
        yt_ref=config.get('yt_ref','auto'),
        palette=config.get('palette','oscuro'),
        letra=letra[:2000],
    )
    try:
        r = requests.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.8, "maxOutputTokens": 1500}},
            timeout=45
        ).json()
        texto = r['candidates'][0]['content']['parts'][0]['text']
        texto = re.sub(r'```json\s*|\s*```', '', texto).strip()
        resultado = json.loads(texto)
        log("IA: concepto visual generado con Gemini", 'ia')
        return resultado
    except Exception as e:
        log(f"Gemini error: {e}", 'debug')
        return None

def sintetizar_concepto_openrouter(config, letra):
    if not OPENROUTER_API_KEY:
        return None
    prompt = PROMPT_VISUAL.format(
        song_name=config.get('song_name',''),
        artist=config.get('artist',''),
        genres=config.get('genres',''),
        song_desc=config.get('song_desc',''),
        yt_ref=config.get('yt_ref','auto'),
        palette=config.get('palette','oscuro'),
        letra=letra[:2000],
    )
    try:
        r = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization": f"Bearer {OPENROUTER_API_KEY}", "Content-Type": "application/json"},
            json={"model": "mistralai/mistral-7b-instruct:free",
                  "messages": [{"role": "user", "content": prompt}],
                  "max_tokens": 1500},
            timeout=45
        ).json()
        texto = r['choices'][0]['message']['content']
        texto = re.sub(r'```json\s*|\s*```', '', texto).strip()
        resultado = json.loads(texto)
        log("IA: concepto visual generado con OpenRouter", 'ia')
        return resultado
    except Exception as e:
        log(f"OpenRouter error: {e}", 'debug')
        return None

def sintetizar_concepto_fallback(config, letra):
    song_name = config.get('song_name', '')
    artist    = config.get('artist', '')
    genres    = config.get('genres', 'pop')
    palette   = config.get('palette', 'oscuro')
    genre1    = genres.split(',')[0].strip().lower()

    queries_map = {
        'balada':     ['romantic couple silhouette night', 'melancholy rain city lights', 'lonely person window rain', 'emotional portrait soft light', 'broken heart abstract', 'city night bokeh lights'],
        'urbano':     ['urban city night aesthetic', 'street graffiti neon', 'city skyline night', 'urban fashion portrait', 'street photography city', 'rooftop city view'],
        'electrónica':['abstract neon light trails', 'futuristic digital art', 'neon city cyberpunk', 'abstract waves colorful', 'digital art purple', 'futuristic landscape'],
        'indie':      ['aesthetic film photography', 'vintage polaroid nature', 'film grain portrait sunlight', 'golden hour landscape', 'vintage cafe aesthetic', 'sunflower field film'],
        'r&b':        ['sensual portrait studio light', 'golden hour silhouette', 'moody portrait warm light', 'luxury aesthetic bedroom', 'soft aesthetic candles', 'portrait warm tones'],
    }
    queries = queries_map.get(genre1, ['aesthetic music background', 'moody portrait cinematic', 'city lights night bokeh', 'abstract art colorful', 'nature landscape cinematic', 'sunset silhouette'])

    return {
        'concepto': f"Video cinematográfico para '{song_name}' con estética {palette} que captura la esencia {genre1}.",
        'mood': genre1,
        'queries_imagenes': queries,
        'prompts_ia': [
            f"cinematic {genre1} music video aesthetic, {palette} tones, no text, photorealistic",
            f"moody portrait {genre1} style, atmospheric lighting, vertical composition",
            f"abstract {palette} background music video aesthetic, artistic",
            f"cityscape night {genre1} aesthetic vertical photo",
        ],
        'texto_pantalla': f"{song_name}\n{artist}",
        'hashtags': f"#{artist.replace(' ','')} #{song_name.replace(' ','')} #NuevaMusica #Spotify #Musica",
    }

def obtener_concepto_visual(config, letra):
    log("🤖 Generando concepto visual...", 'ia')
    concepto = sintetizar_concepto_gemini(config, letra)
    if not concepto:
        concepto = sintetizar_concepto_openrouter(config, letra)
    if not concepto:
        concepto = sintetizar_concepto_fallback(config, letra)
    log(f"Concepto: {concepto.get('concepto','')[:80]}", 'ok')
    return concepto

# ──────────────────────────────────────────────
# PASO 4: RECOPILACIÓN DE IMÁGENES
# ──────────────────────────────────────────────
def cargar_mis_imagenes():
    """Carga las imágenes subidas por el usuario en mis_imagenes/."""
    paths = []
    if not os.path.exists(MIS_IMAGENES_DIR):
        return paths
    exts = {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}
    for f in Path(MIS_IMAGENES_DIR).iterdir():
        if f.suffix.lower() in exts and f.name != '.gitkeep':
            paths.append(str(f))
    log(f"Mis imágenes: {len(paths)} encontradas", 'img')
    return paths

def descargar_imagen(url, idx, prefix='img'):
    try:
        from PIL import Image
        from io import BytesIO
        r = requests.get(url, headers=HEADERS, timeout=25, stream=True)
        if r.status_code != 200:
            return None
        if 'image' not in r.headers.get('content-type', ''):
            return None
        data = r.content
        if len(data) < 5000:
            return None
        img = Image.open(BytesIO(data)).convert('RGB')
        if img.size[0] < 300 or img.size[1] < 200:
            return None
        # Escalar a 9:16
        img = escalar_9_16(img)
        p = f'/tmp/mvbot_{prefix}_{idx}_{generar_hash(url)}.jpg'
        img.save(p, 'JPEG', quality=92)
        return p
    except Exception as e:
        log(f"Error descargando {url[:50]}: {e}", 'debug')
        return None

def escalar_9_16(img):
    from PIL import Image
    target_ratio = VIDEO_ALTO / VIDEO_ANCHO
    img_ratio    = img.height / img.width
    if img_ratio > target_ratio:
        nw = VIDEO_ANCHO
        nh = int(VIDEO_ANCHO * img_ratio)
    else:
        nh = VIDEO_ALTO
        nw = int(VIDEO_ALTO / img_ratio)
    img = img.resize((nw, nh), Image.LANCZOS)
    x = (nw - VIDEO_ANCHO) // 2
    y = (nh - VIDEO_ALTO)  // 2
    return img.crop((x, y, x + VIDEO_ANCHO, y + VIDEO_ALTO))

def buscar_pixabay(query, n=6):
    if not PIXABAY_API_KEY:
        return []
    try:
        r = requests.get(
            "https://pixabay.com/api/",
            params={'key': PIXABAY_API_KEY, 'q': query[:100],
                    'image_type': 'photo', 'orientation': 'vertical',
                    'min_width': 600, 'per_page': n, 'safesearch': 'true'},
            timeout=15
        ).json()
        return [h['largeImageURL'] for h in r.get('hits', [])]
    except:
        return []

def buscar_pexels(query, n=6):
    if not PEXELS_API_KEY:
        return []
    try:
        r = requests.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": PEXELS_API_KEY},
            params={'query': query[:100], 'orientation': 'portrait', 'per_page': n},
            timeout=15
        ).json()
        return [p['src']['large'] for p in r.get('photos', [])]
    except:
        return []

def generar_imagen_pollinations(prompt, idx, song_name):
    try:
        from PIL import Image
        from io import BytesIO
        import urllib.parse
        prompt_clean = re.sub(r'[^\w\s,.-]', ' ', prompt)[:200]
        seed = abs(hash(song_name + str(idx))) % 99999
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt_clean)}?width=1080&height=1920&seed={seed}&nologo=true&model=flux"
        r = requests.get(url, headers=HEADERS, timeout=90)
        if r.status_code == 200 and 'image' in r.headers.get('content-type', ''):
            img = Image.open(BytesIO(r.content)).convert('RGB')
            if img.size[0] >= 400:
                p = f'/tmp/mvbot_ia_{idx}_{generar_hash(song_name)}.jpg'
                img.save(p, 'JPEG', quality=90)
                log(f"IA imagen {idx+1} generada: {img.size}", 'ok')
                return p
    except Exception as e:
        log(f"Pollinations error: {e}", 'debug')
    return None

def procesar_imagen_usuario(path_original, idx):
    """Escala imagen del usuario a 9:16."""
    try:
        from PIL import Image
        img = Image.open(path_original).convert('RGB')
        img = escalar_9_16(img)
        p = f'/tmp/mvbot_user_{idx}_{generar_hash(path_original)}.jpg'
        img.save(p, 'JPEG', quality=92)
        return p
    except Exception as e:
        log(f"Error procesando imagen usuario {path_original}: {e}", 'debug')
        return None

def aplicar_filtro_color(path_img, filtro):
    """Aplica filtro de color según paleta elegida."""
    if filtro == 'ninguno':
        return path_img
    try:
        from PIL import Image, ImageEnhance, ImageFilter
        import numpy as np
        img = Image.open(path_img).convert('RGB')

        if filtro == 'oscuro':
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(0.75)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.2)

        elif filtro == 'neon':
            enhancer = ImageEnhance.Brightness(img)
            img = enhancer.enhance(0.6)
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(1.8)
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(1.4)

        elif filtro == 'calido':
            arr = np.array(img, dtype=np.float32)
            arr[:,:,0] = np.clip(arr[:,:,0] * 1.1, 0, 255)
            arr[:,:,2] = np.clip(arr[:,:,2] * 0.85, 0, 255)
            img = Image.fromarray(arr.astype(np.uint8))

        elif filtro == 'vintage':
            arr = np.array(img, dtype=np.float32)
            arr[:,:,0] = np.clip(arr[:,:,0] * 1.1 + 10, 0, 255)
            arr[:,:,1] = np.clip(arr[:,:,1] * 0.95 + 5, 0, 255)
            arr[:,:,2] = np.clip(arr[:,:,2] * 0.75, 0, 255)
            img = Image.fromarray(arr.astype(np.uint8))
            enhancer = ImageEnhance.Color(img)
            img = enhancer.enhance(0.7)

        elif filtro == 'suave':
            img = img.filter(ImageFilter.GaussianBlur(radius=0.5))
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(0.9)

        p_out = path_img.replace('.jpg', '_filtered.jpg')
        img.save(p_out, 'JPEG', quality=90)
        return p_out
    except Exception as e:
        log(f"Filtro error: {e}", 'debug')
        return path_img

def recopilar_imagenes(config, concepto):
    log("🖼️ Recopilando imágenes...", 'img')
    palette_key = config.get('palette', 'oscuro').lower()
    paleta = PALETAS.get(palette_key, PALETAS['oscuro'])
    filtro = paleta['filtro']

    paths_finales = []

    # ── NIVEL 1: Imágenes del usuario ────────────────────────
    mis_imgs = cargar_mis_imagenes()
    for i, p in enumerate(mis_imgs[:6]):
        proc = procesar_imagen_usuario(p, i)
        if proc:
            filtered = aplicar_filtro_color(proc, filtro)
            paths_finales.append(filtered)
            log(f"   Imagen usuario {i+1}: {Path(p).name}", 'img')

    # ── NIVEL 2: Búsqueda en Pixabay / Pexels ────────────────
    queries = concepto.get('queries_imagenes', [])
    for q in queries:
        if len(paths_finales) >= 8:
            break
        for url in buscar_pixabay(q, 3):
            if len(paths_finales) >= 8:
                break
            p = descargar_imagen(url, len(paths_finales), 'px')
            if p:
                filtered = aplicar_filtro_color(p, filtro)
                paths_finales.append(filtered)

    for q in queries:
        if len(paths_finales) >= 8:
            break
        for url in buscar_pexels(q, 3):
            if len(paths_finales) >= 8:
                break
            p = descargar_imagen(url, len(paths_finales), 'pe')
            if p:
                filtered = aplicar_filtro_color(p, filtro)
                paths_finales.append(filtered)

    log(f"   Imágenes reales: {len(paths_finales)}", 'img')

    # ── NIVEL 3: IA (Pollinations) ────────────────────────────
    prompts_ia = concepto.get('prompts_ia', [])
    for i, prompt in enumerate(prompts_ia):
        if len(paths_finales) >= 10:
            break
        p = generar_imagen_pollinations(prompt, i, config.get('song_name',''))
        if p:
            filtered = aplicar_filtro_color(p, filtro)
            paths_finales.append(filtered)

    log(f"   ✅ Total imágenes: {len(paths_finales)}", 'ok')
    return paths_finales

# ──────────────────────────────────────────────
# PASO 5: GENERACIÓN DE VIDEO
# ──────────────────────────────────────────────
def superponer_texto_musica(frame_pil, config, concepto, idx_img, total_imgs, paleta):
    """Superpone texto del video musical sobre el frame."""
    from PIL import Image, ImageDraw, ImageFont
    import math

    texto_pantalla = concepto.get('texto_pantalla', '')
    text_style     = config.get('text_style', 'Nombre + artista')
    if text_style == 'Sin texto':
        return frame_pil

    lineas_texto = texto_pantalla.split('\n')
    song_name = lineas_texto[0] if lineas_texto else config.get('song_name', '')
    artist    = lineas_texto[1] if len(lineas_texto) > 1 else config.get('artist', '')

    try:
        font_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 64)
        font_artist = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 44)
        font_small  = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 30)
    except:
        font_titulo = font_artist = font_small = ImageFont.load_default()

    w, h = frame_pil.size
    color_texto = paleta.get('texto', '#ffffff')
    color_acento = paleta.get('acento', '#ffffff')

    # Solo en primera y última imagen (o "solo al inicio")
    mostrar = False
    if text_style == 'Nombre + artista':
        mostrar = (idx_img == 0 or idx_img == total_imgs - 1)
    elif text_style == 'Solo al inicio':
        mostrar = idx_img == 0
    elif text_style == 'Letra sincronizada':
        mostrar = True

    if not mostrar:
        return frame_pil

    # Overlay degradado inferior
    overlay = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for y_off in range(300):
        alpha = int(180 * (y_off / 300))
        od.line([(0, h - 300 + y_off), (w, h - 300 + y_off)], fill=(0, 0, 0, alpha))

    frame_pil = frame_pil.convert('RGBA')
    frame_pil = Image.alpha_composite(frame_pil, overlay).convert('RGB')
    draw = ImageDraw.Draw(frame_pil)

    # Nombre de canción
    nombre_wrap = textwrap.fill(song_name, width=16)
    y_text = h - 260
    for linea in nombre_wrap.split('\n'):
        draw.text((50, y_text), linea, font=font_titulo, fill=color_texto)
        y_text += 76

    # Artista
    draw.text((50, y_text + 4), artist, font=font_artist, fill=color_acento)

    # Indicador de slide (pequeño, arriba a la derecha)
    draw.text((w - 100, 40), f"{idx_img+1}/{total_imgs}", font=font_small,
              fill=color_texto + '99' if len(color_texto) == 7 else color_texto)

    return frame_pil

def aplicar_ken_burns(img_pil, progreso, direccion='derecha'):
    from PIL import Image
    import math
    w, h = img_pil.size
    p_smooth = math.sin(progreso * math.pi / 2)
    zoom = 1.0 + 0.05 * p_smooth
    nw = int(w * zoom)
    nh = int(h * zoom)
    frame_zoom = img_pil.resize((nw, nh), Image.BILINEAR)
    dirs = {
        'derecha':   (int((nw-w)*p_smooth), (nh-h)//2),
        'izquierda': (int((nw-w)*(1-p_smooth)), (nh-h)//2),
        'arriba':    ((nw-w)//2, int((nh-h)*p_smooth)),
        'abajo':     ((nw-w)//2, int((nh-h)*(1-p_smooth))),
    }
    x, y = dirs.get(direccion, ((nw-w)//2, (nh-h)//2))
    x = max(0, min(x, nw-w))
    y = max(0, min(y, nh-h))
    return frame_zoom.crop((x, y, x+w, y+h))

def blend_frames(img1, img2, alpha):
    from PIL import Image
    import math
    alpha_s = alpha * alpha * (3 - 2 * alpha)  # smoothstep
    if img1.size != img2.size:
        img2 = img2.resize(img1.size, Image.BILINEAR)
    return Image.blend(img1, img2, alpha_s)

def slide_frame(img1, img2, alpha, direction='left'):
    from PIL import Image
    import math
    alpha_s = alpha * alpha * (3 - 2 * alpha)
    w, h = img1.size
    if img2.size != (w, h):
        img2 = img2.resize((w, h), Image.BILINEAR)
    result = Image.new('RGB', (w, h))
    if direction == 'left':
        offset = int(w * alpha_s)
        result.paste(img1.crop((offset, 0, w, h)), (0, 0))
        result.paste(img2.crop((0, 0, w-offset, h)), (w-offset, 0))
    elif direction == 'right':
        offset = int(w * alpha_s)
        result.paste(img1.crop((0, 0, w-offset, h)), (offset, 0))
        result.paste(img2.crop((offset, 0, w, h)), (0, 0))
    elif direction == 'up':
        offset = int(h * alpha_s)
        result.paste(img1.crop((0, offset, w, h)), (0, 0))
        result.paste(img2.crop((0, 0, w, h-offset)), (0, h-offset))
    else:
        offset = int(h * alpha_s)
        result.paste(img1.crop((0, 0, w, h-offset)), (0, offset))
        result.paste(img2.crop((0, h-offset, w, h)), (0, 0))
    return result

def calcular_duracion_video(config):
    """Calcula duración en segundos según selección del usuario."""
    dur_str = config.get('duration', '60 seg').lower()
    if '30' in dur_str:
        return 30
    elif '90' in dur_str:
        return 90
    elif 'completa' in dur_str or 'full' in dur_str:
        return None  # None = duración del audio
    else:
        return 60  # default

def generar_video_musical(paths_imagenes, config, concepto, audio_path):
    """Ensambla el video musical final."""
    log("🎬 Generando video musical...", 'video')
    try:
        import numpy as np
        from PIL import Image
        try:
            from moviepy.editor import ImageSequenceClip, AudioFileClip
        except ImportError:
            from moviepy import ImageSequenceClip, AudioFileClip

        total_imgs = len(paths_imagenes)
        if total_imgs == 0:
            log("Sin imágenes", 'error')
            return None

        palette_key = config.get('palette', 'oscuro').lower()
        paleta      = PALETAS.get(palette_key, PALETAS['oscuro'])
        transition  = config.get('transition', 'Ken Burns (zoom)').lower()
        rhythm      = int(config.get('rhythm', 3))

        # Duración por imagen según ritmo (1=lento=12s, 5=rápido=5s)
        seg_por_img = {1: 12, 2: 10, 3: 8, 4: 6, 5: 5}[rhythm]

        # Si hay audio, calcular duración total
        dur_target = calcular_duracion_video(config)
        if audio_path and dur_target is None:
            try:
                audio_clip = AudioFileClip(audio_path)
                dur_target = audio_clip.duration
                audio_clip.close()
            except:
                dur_target = 60

        if dur_target:
            seg_por_img = max(4, min(14, dur_target / total_imgs))

        FRAMES_IMG  = int(VIDEO_FPS * seg_por_img)
        FRAMES_TRANS = int(VIDEO_FPS * 1.0)

        log(f"   {total_imgs} imágenes × {seg_por_img:.1f}s | ritmo={rhythm} | paleta={palette_key}", 'video')

        # Cargar imágenes PIL
        imgs_pil = []
        for p in paths_imagenes:
            try:
                img = Image.open(p).convert('RGB')
                if img.size != (VIDEO_ANCHO, VIDEO_ALTO):
                    img = escalar_9_16(img)
                imgs_pil.append(img)
            except Exception as e:
                log(f"   Error cargando {p}: {e}", 'debug')

        if not imgs_pil:
            log("Sin imágenes PIL", 'error')
            return None

        # Efectos y transiciones
        EFECTOS = ['kb_derecha', 'kb_izquierda', 'kb_arriba', 'kb_abajo', 'zoom_in']
        TRANS   = ['fade', 'slide_izq', 'slide_der', 'slide_arr', 'slide_aba']

        # Según selección del usuario
        if 'fade' in transition:
            TRANS = ['fade'] * 5
        elif 'slide horizontal' in transition:
            TRANS = ['slide_izq', 'slide_der'] * 3
        elif 'slide vertical' in transition:
            TRANS = ['slide_arr', 'slide_aba'] * 3
        elif 'ken burns' in transition or 'zoom' in transition:
            TRANS = ['fade'] * 3 + ['slide_izq', 'slide_der']

        efectos_asign = [EFECTOS[i % len(EFECTOS)] for i in range(len(imgs_pil))]
        trans_asign   = [TRANS[i % len(TRANS)] for i in range(len(imgs_pil))]
        random.shuffle(efectos_asign)

        # Generar frames
        todos_frames = []
        for i, img_pil in enumerate(imgs_pil):
            efecto = efectos_asign[i]

            for f in range(FRAMES_IMG):
                p = f / max(FRAMES_IMG - 1, 1)
                if efecto == 'kb_derecha':
                    frame = aplicar_ken_burns(img_pil, p, 'derecha')
                elif efecto == 'kb_izquierda':
                    frame = aplicar_ken_burns(img_pil, p, 'izquierda')
                elif efecto == 'kb_arriba':
                    frame = aplicar_ken_burns(img_pil, p, 'arriba')
                elif efecto == 'kb_abajo':
                    frame = aplicar_ken_burns(img_pil, p, 'abajo')
                elif efecto == 'zoom_in':
                    frame = aplicar_ken_burns(img_pil, p * 0.06, 'derecha')
                else:
                    frame = img_pil.copy()

                frame = superponer_texto_musica(frame, config, concepto, i, len(imgs_pil), paleta)
                todos_frames.append(np.array(frame))

            # Transición hacia siguiente
            if i < len(imgs_pil) - 1:
                img_sig   = imgs_pil[i + 1]
                tipo_trans = trans_asign[i]

                for f in range(FRAMES_TRANS):
                    alpha = f / FRAMES_TRANS
                    if tipo_trans == 'fade':
                        frame_t = blend_frames(img_pil, img_sig, alpha)
                    elif tipo_trans == 'slide_izq':
                        frame_t = slide_frame(img_pil, img_sig, alpha, 'left')
                    elif tipo_trans == 'slide_der':
                        frame_t = slide_frame(img_pil, img_sig, alpha, 'right')
                    elif tipo_trans == 'slide_arr':
                        frame_t = slide_frame(img_pil, img_sig, alpha, 'up')
                    else:
                        frame_t = slide_frame(img_pil, img_sig, alpha, 'down')

                    frame_t = superponer_texto_musica(frame_t, config, concepto, i, len(imgs_pil), paleta)
                    todos_frames.append(np.array(frame_t))

        log(f"   Frames: {len(todos_frames)} ({len(todos_frames)/VIDEO_FPS:.1f}s)", 'video')

        clip = ImageSequenceClip(todos_frames, fps=VIDEO_FPS)

        # Agregar audio
        if audio_path and os.path.exists(audio_path):
            try:
                audio = AudioFileClip(audio_path)
                if audio.duration >= clip.duration:
                    clip = clip.set_audio(audio.subclip(0, clip.duration))
                else:
                    clip = clip.set_audio(audio)
                log("   ✅ Audio agregado", 'ok')
            except Exception as e:
                log(f"   Error audio: {e}", 'warn')

        # Exportar
        Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        nombre_limpio = limpiar_nombre_archivo(config.get('song_name', 'video'))
        video_path = f"{OUTPUT_DIR}/{nombre_limpio}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp4"

        clip.write_videofile(
            video_path,
            codec='libx264',
            audio_codec='aac',
            preset='ultrafast',
            ffmpeg_params=['-crf', '23', '-profile:v', 'baseline', '-level', '3.0'],
            logger=None
        )
        clip.close()

        size_mb = os.path.getsize(video_path) / (1024 * 1024)
        dur_real = len(todos_frames) / VIDEO_FPS
        log(f"✅ Video guardado: {video_path} ({size_mb:.1f} MB, {dur_real:.0f}s)", 'ok')
        return video_path

    except ImportError as e:
        log(f"moviepy no disponible: {e}", 'error')
        return None
    except Exception as e:
        log(f"Error generando video: {e}", 'error')
        import traceback
        traceback.print_exc()
        return None

# ──────────────────────────────────────────────
# PASO 6: MEMORIA DE PROYECTOS
# ──────────────────────────────────────────────
def guardar_proyecto(config, concepto, video_path):
    proyectos = cargar_json(PROYECTOS_PATH, {'proyectos': []})
    proyecto = {
        'id':          generar_hash(config.get('song_name','') + config.get('artist','')),
        'song_name':   config.get('song_name', ''),
        'artist':      config.get('artist', ''),
        'genres':      config.get('genres', ''),
        'palette':     config.get('palette', ''),
        'transition':  config.get('transition', ''),
        'concepto':    concepto.get('concepto', ''),
        'video_path':  video_path or '',
        'fecha':       datetime.now().isoformat(),
        'fecha_str':   datetime.now().strftime('%d/%m/%Y %H:%M'),
    }
    proyectos['proyectos'].insert(0, proyecto)
    if len(proyectos['proyectos']) > 50:
        proyectos['proyectos'] = proyectos['proyectos'][:50]
    proyectos['ultimo'] = proyecto
    guardar_json(PROYECTOS_PATH, proyectos)
    log(f"Proyecto guardado en {PROYECTOS_PATH}", 'ok')

def mostrar_memoria():
    """Muestra el último proyecto al inicio del run."""
    proyectos = cargar_json(PROYECTOS_PATH, {'proyectos': []})
    ultimo = proyectos.get('ultimo')
    if not ultimo:
        return
    print(f"\n{'='*60}")
    print(f"🕐 ÚLTIMO PROYECTO: '{ultimo['song_name']}' — {ultimo['artist']}")
    print(f"   Generado: {ultimo.get('fecha_str','')}")
    print(f"   Paleta: {ultimo.get('palette','')} | Géneros: {ultimo.get('genres','')}")
    print(f"{'='*60}\n")

# ──────────────────────────────────────────────
# LIMPIAR TEMPORALES
# ──────────────────────────────────────────────
def limpiar_temporales(paths_imgs):
    for p in paths_imgs:
        try:
            if p and p.startswith('/tmp/') and os.path.exists(p):
                os.remove(p)
        except:
            pass

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def main():
    print("\n" + "="*60)
    print("🎬 MUSIC VIDEO BOT")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60 + "\n")

    mostrar_memoria()

    # PASO 1 — Leer configuración
    config = leer_config()
    if not config:
        return False

    # Buscar audio
    audio_path = None
    audio_name = config.get('audio_name', '')
    if audio_name:
        for d in [MIS_IMAGENES_DIR, '.', 'audio']:
            candidate = os.path.join(d, audio_name)
            if os.path.exists(candidate):
                audio_path = candidate
                log(f"Audio encontrado: {audio_path}", 'music')
                break
    if not audio_path:
        # Buscar cualquier MP3 en mis_imagenes/
        for ext in ['*.mp3', '*.wav', '*.m4a']:
            from glob import glob
            found = glob(os.path.join(MIS_IMAGENES_DIR, ext))
            if found:
                audio_path = found[0]
                log(f"Audio encontrado: {audio_path}", 'music')
                break

    if not audio_path:
        log("Audio no encontrado — video sin audio", 'warn')

    # PASO 2 — Obtener letra
    letra = obtener_letra(config)

    # PASO 3 — Concepto visual
    concepto = obtener_concepto_visual(config, letra)

    # PASO 4 — Imágenes
    paths_imagenes = recopilar_imagenes(config, concepto)
    if not paths_imagenes:
        log("Sin imágenes disponibles", 'error')
        return False

    # PASO 5 — Generar video
    video_path = generar_video_musical(paths_imagenes, config, concepto, audio_path)
    if not video_path:
        limpiar_temporales(paths_imagenes)
        return False

    # PASO 6 — Guardar en memoria
    guardar_proyecto(config, concepto, video_path)

    # Limpiar
    limpiar_temporales(paths_imagenes)

    print(f"\n{'='*60}")
    print(f"✅ VIDEO LISTO: {video_path}")
    print(f"   Canción: '{config.get('song_name')}' — {config.get('artist')}")
    print(f"   Concepto: {concepto.get('concepto','')[:80]}")
    print(f"   Hashtags: {concepto.get('hashtags','')}")
    print(f"{'='*60}\n")
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
