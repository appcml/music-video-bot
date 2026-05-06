#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
music_video_bot.py v2 — Ensamblador de Videos Musicales
Repositorio: appcml/music-video-bot

MODO RÁPIDO (imágenes en mis_imagenes/): ~3 min
MODO COMPLETO (sin imágenes): ~8 min con búsqueda en internet
"""

import os, re, json, random, hashlib, textwrap, math
import requests
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import numpy as np

# ──────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────
GEMINI_API_KEY     = os.getenv('GEMINI_API_KEY', '')
PIXABAY_API_KEY    = os.getenv('PIXABAY_API_KEY', '')
PEXELS_API_KEY     = os.getenv('PEXELS_API_KEY', '')
CONFIG_PATH        = 'config_cancion.json'
PROYECTOS_PATH     = 'proyectos/proyectos.json'
IMAGENES_DIR       = 'mis_imagenes'
OUTPUT_DIR         = 'output'
VIDEO_ANCHO        = 1080
VIDEO_ALTO         = 1920
VIDEO_FPS          = 24
HEADERS            = {'User-Agent': 'Mozilla/5.0'}

PALETAS = {
    'oscuro':   {'acento':(224,224,224),'texto':(255,255,255),'fondo':(10,10,10)},
    'luminoso': {'acento':(45,45,45),  'texto':(26,26,26),   'fondo':(245,245,240)},
    'neon':     {'acento':(127,119,221),'texto':(255,255,255),'fondo':(5,5,16)},
    'natural':  {'acento':(93,202,165), 'texto':(232,245,224),'fondo':(26,36,16)},
    'vintage':  {'acento':(239,159,39), 'texto':(245,232,208),'fondo':(42,31,20)},
    'pastel':   {'acento':(212,83,126), 'texto':(61,26,42),   'fondo':(250,240,245)},
}

def log(msg, tipo='info'):
    iconos = {'info':'ℹ️','ok':'✅','error':'❌','warn':'⚠️','video':'🎬','img':'🖼️','music':'🎵'}
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {iconos.get(tipo,'ℹ️')} {msg}")

def cargar_json(ruta, default=None):
    default = default or {}
    if os.path.exists(ruta):
        try:
            with open(ruta,'r',encoding='utf-8') as f:
                c = f.read().strip()
                return json.loads(c) if c else default.copy()
        except: pass
    return default.copy()

def guardar_json(ruta, datos):
    Path(ruta).parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta+'.tmp'
    with open(tmp,'w',encoding='utf-8') as f:
        json.dump(datos,f,ensure_ascii=False,indent=2)
    os.replace(tmp,ruta)

def gh(texto):
    return hashlib.md5(str(texto).encode()).hexdigest()[:8]

def limpiar(nombre):
    return re.sub(r'[^\w\s-]','',nombre).strip().replace(' ','_')[:40]

# ──────────────────────────────────────────────
# IMAGEN HELPERS
# ──────────────────────────────────────────────
def escalar_9_16(img):
    target = VIDEO_ALTO / VIDEO_ANCHO
    ratio  = img.height / img.width
    if ratio > target:
        nw,nh = VIDEO_ANCHO, int(VIDEO_ANCHO*ratio)
    else:
        nw,nh = int(VIDEO_ALTO/ratio), VIDEO_ALTO
    img = img.resize((nw,nh), Image.LANCZOS)
    x = (nw-VIDEO_ANCHO)//2
    y = (nh-VIDEO_ALTO)//2
    return img.crop((x,y,x+VIDEO_ANCHO,y+VIDEO_ALTO))

def aplicar_filtro(img, palette_key):
    try:
        pk = palette_key.lower()
        if pk == 'oscuro':
            img = ImageEnhance.Brightness(img).enhance(0.75)
            img = ImageEnhance.Contrast(img).enhance(1.15)
        elif pk == 'neon':
            img = ImageEnhance.Brightness(img).enhance(0.65)
            img = ImageEnhance.Color(img).enhance(1.7)
        elif pk == 'vintage':
            arr = np.array(img, dtype=np.float32)
            arr[:,:,0] = np.clip(arr[:,:,0]*1.1+10,0,255)
            arr[:,:,2] = np.clip(arr[:,:,2]*0.75,0,255)
            img = Image.fromarray(arr.astype(np.uint8))
            img = ImageEnhance.Color(img).enhance(0.7)
        elif pk == 'natural':
            arr = np.array(img, dtype=np.float32)
            arr[:,:,1] = np.clip(arr[:,:,1]*1.05,0,255)
            img = Image.fromarray(arr.astype(np.uint8))
    except: pass
    return img

def kb(img, progreso, dir='derecha'):
    p = math.sin(progreso*math.pi/2)
    zoom = 1.0+0.05*p
    w,h = img.size
    nw,nh = int(w*zoom),int(h*zoom)
    iz = img.resize((nw,nh),Image.BILINEAR)
    dirs = {'derecha':(int((nw-w)*p),(nh-h)//2),'izquierda':(int((nw-w)*(1-p)),(nh-h)//2),
            'arriba':((nw-w)//2,int((nh-h)*p)),'abajo':((nw-w)//2,int((nh-h)*(1-p)))}
    x,y = dirs.get(dir,((nw-w)//2,(nh-h)//2))
    return iz.crop((max(0,x),max(0,y),max(0,x)+w,max(0,y)+h))

def blend(i1,i2,a):
    a2 = a*a*(3-2*a)
    if i1.size!=i2.size: i2=i2.resize(i1.size,Image.BILINEAR)
    return Image.blend(i1,i2,a2)

def slide(i1,i2,a,d='left'):
    a2=a*a*(3-2*a); w,h=i1.size
    if i2.size!=(w,h): i2=i2.resize((w,h),Image.BILINEAR)
    r=Image.new('RGB',(w,h))
    if d=='left':
        o=int(w*a2); r.paste(i1.crop((o,0,w,h)),(0,0)); r.paste(i2.crop((0,0,w-o,h)),(w-o,0))
    elif d=='right':
        o=int(w*a2); r.paste(i1.crop((0,0,w-o,h)),(o,0)); r.paste(i2.crop((o,0,w,h)),(0,0))
    elif d=='up':
        o=int(h*a2); r.paste(i1.crop((0,o,w,h)),(0,0)); r.paste(i2.crop((0,0,w,h-o)),(0,h-o))
    else:
        o=int(h*a2); r.paste(i1.crop((0,0,w,h-o)),(0,o)); r.paste(i2.crop((0,h-o,w,h)),(0,0))
    return r

def texto_overlay(frame, config, idx, total):
    style = config.get('text_style','Nombre + artista').lower()
    if 'sin' in style: return frame
    mostrar = ('nombre' in style and (idx==0 or idx==total-1)) or \
              ('inicio' in style and idx==0) or \
              ('letra' in style)
    if not mostrar: return frame

    pk = config.get('palette','Oscuro').lower()
    pal = PALETAS.get(pk, PALETAS['oscuro'])
    w,h = frame.size

    try:
        ft = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",64)
        fa = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",44)
        fs = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",28)
    except:
        ft=fa=fs=ImageFont.load_default()

    ov = Image.new('RGBA',(w,h),(0,0,0,0))
    od = ImageDraw.Draw(ov)
    for yo in range(350):
        al = int(210*(yo/350))
        od.line([(0,h-350+yo),(w,h-350+yo)],fill=(0,0,0,al))
    frame = frame.convert('RGBA')
    frame = Image.alpha_composite(frame,ov).convert('RGB')
    draw = ImageDraw.Draw(frame)

    song = textwrap.fill(config.get('song_name','')[:50], width=16)
    artist = config.get('artist','')[:40]
    y = h-300
    for l in song.split('\n'):
        draw.text((50,y),l,font=ft,fill=pal['texto']); y+=78
    draw.text((50,y+8),artist,font=fa,fill=pal['acento'])
    draw.text((w-100,40),f"{idx+1}/{total}",font=fs,fill=pal['texto'])
    return frame

def gen_img_texto(titulo, sub, idx, total, palette_key):
    try:
        pk = palette_key.lower()
        pal = PALETAS.get(pk, PALETAS['oscuro'])
        arr = np.zeros((VIDEO_ALTO,VIDEO_ANCHO,3),dtype=np.uint8)
        fondo,acento,texto_c = pal['fondo'],pal['acento'],pal['texto']
        bot = tuple(min(255,c+25) for c in fondo)
        for y in range(VIDEO_ALTO):
            t=y/VIDEO_ALTO
            arr[y,:] = [int(fondo[i]+(bot[i]-fondo[i])*t) for i in range(3)]
        noise = np.random.randint(0,8,(VIDEO_ALTO,VIDEO_ANCHO,3),dtype=np.uint8)
        arr = np.clip(arr.astype(np.int16)+noise-4,0,255).astype(np.uint8)
        img = Image.fromarray(arr)
        draw = ImageDraw.Draw(img)
        try:
            fb=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",80)
            fm=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",50)
            fs=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",32)
        except:
            fb=fm=fs=ImageFont.load_default()
        draw.rectangle([(0,0),(VIDEO_ANCHO,100)],fill=acento)
        draw.text((40,32),"MUSIC VIDEO",font=fs,fill=fondo)
        draw.text((VIDEO_ANCHO-100,35),f"{idx+1}/{total}",font=fs,fill=fondo)
        cy=VIDEO_ALTO//2
        draw.rectangle([(60,cy-2),(VIDEO_ANCHO-60,cy+2)],fill=acento)
        tw=textwrap.fill(titulo[:80],width=14)
        y=int(VIDEO_ALTO*0.28)
        for l in tw.split('\n'):
            draw.text((60,y),l,font=fb,fill=texto_c); y+=96
        if sub:
            sw=textwrap.fill(sub[:100],width=20); y+=20
            for l in sw.split('\n'):
                draw.text((60,y),l,font=fm,fill=acento); y+=62
        p=f'/tmp/mvbot_gen_{idx}_{gh(titulo)}.jpg'
        img.save(p,'JPEG',quality=88)
        return p
    except Exception as e:
        log(f"gen_img_texto error: {e}",'error')
        return None

# ──────────────────────────────────────────────
# BÚSQUEDA INTERNET (modo completo)
# ──────────────────────────────────────────────
def buscar_pixabay(q,n=5):
    if not PIXABAY_API_KEY: return []
    try:
        r=requests.get("https://pixabay.com/api/",
            params={'key':PIXABAY_API_KEY,'q':q[:100],'image_type':'photo',
                    'orientation':'vertical','min_width':600,'per_page':n,'safesearch':'true'},
            timeout=15).json()
        return [h['largeImageURL'] for h in r.get('hits',[])]
    except: return []

def buscar_pexels(q,n=5):
    if not PEXELS_API_KEY: return []
    try:
        r=requests.get("https://api.pexels.com/v1/search",
            headers={"Authorization":PEXELS_API_KEY},
            params={'query':q[:100],'orientation':'portrait','per_page':n},
            timeout=15).json()
        return [p['src']['large'] for p in r.get('photos',[])]
    except: return []

def dl_img(url,idx):
    try:
        from io import BytesIO
        r=requests.get(url,headers=HEADERS,timeout=20)
        if r.status_code!=200 or 'image' not in r.headers.get('content-type',''): return None
        if len(r.content)<5000: return None
        img=Image.open(BytesIO(r.content)).convert('RGB')
        if img.size[0]<300 or img.size[1]<200: return None
        img=escalar_9_16(img)
        p=f'/tmp/mvbot_dl_{idx}_{gh(url)}.jpg'
        img.save(p,'JPEG',quality=88)
        return p
    except: return None

# ──────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────
def main():
    print("\n"+"="*60)
    print("🎬 MUSIC VIDEO BOT v2")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*60+"\n")

    # 1. Config
    if not os.path.exists(CONFIG_PATH):
        log(f"No se encontró {CONFIG_PATH}",'error'); return False
    config = cargar_json(CONFIG_PATH)
    log(f"🎵 '{config.get('song_name')}' — {config.get('artist')}",'music')
    log(f"   Paleta:{config.get('palette')} Transición:{config.get('transition')}",'info')

    # 2. Detectar archivos del usuario
    exts_img   = {'.jpg','.jpeg','.png','.webp','.bmp'}
    exts_audio = {'.mp3','.wav','.m4a','.flac'}
    imagenes_u, audio_u = [], None

    if os.path.exists(IMAGENES_DIR):
        for f in sorted(Path(IMAGENES_DIR).iterdir()):
            if f.name=='.gitkeep': continue
            if f.suffix.lower() in exts_img:
                imagenes_u.append(str(f))
                log(f"   📸 {f.name}",'img')
            elif f.suffix.lower() in exts_audio and not audio_u:
                audio_u = str(f)
                log(f"   🎵 Audio: {f.name}",'music')

    modo = 'rapido' if imagenes_u else 'completo'
    log(f"Modo: {modo.upper()} — {len(imagenes_u)} imgs, audio:{'sí' if audio_u else 'no'}",'ok')

    # 3. Preparar imágenes
    pk = config.get('palette','Oscuro')
    paths = []

    if modo == 'rapido':
        for i,p in enumerate(imagenes_u):
            try:
                img = Image.open(p).convert('RGB')
                img = escalar_9_16(img)
                img = aplicar_filtro(img, pk)
                op = f'/tmp/mvbot_u_{i}_{gh(p)}.jpg'
                img.save(op,'JPEG',quality=90)
                paths.append(op)
                log(f"   ✅ {Path(p).name}",'img')
            except Exception as e:
                log(f"   Error {p}: {e}",'warn')
    else:
        # Buscar en internet
        song = config.get('song_name','')
        genres = config.get('genres','music')
        desc = config.get('song_desc','')
        palabras = [w for w in desc.split() if len(w)>4][:3]
        queries = [
            ' '.join(palabras) if palabras else genres,
            f"{genres.split(',')[0].strip()} music aesthetic",
            'music video landscape cinematic',
            'nature landscape vertical',
        ]
        for q in queries:
            if len(paths)>=8: break
            for url in buscar_pixabay(q,4):
                if len(paths)>=8: break
                p=dl_img(url,len(paths))
                if p: paths.append(p)
        for q in queries:
            if len(paths)>=8: break
            for url in buscar_pexels(q,4):
                if len(paths)>=8: break
                p=dl_img(url,len(paths))
                if p: paths.append(p)
        log(f"Imágenes internet: {len(paths)}",'img')

    # Completar con Pillow si faltan
    song = config.get('song_name','')
    artist = config.get('artist','')
    while len(paths) < 4:
        subs = [artist,song,config.get('genres',''),'♪',song,artist]
        p = gen_img_texto(song, subs[len(paths)%len(subs)], len(paths), max(6,len(paths)+2), pk)
        if p: paths.append(p)
        else: break

    if not paths:
        log("Sin imágenes",'error'); return False

    log(f"Total imágenes: {len(paths)}",'ok')

    # 4. Ensamblar
    try:
        try:
            from moviepy.editor import ImageSequenceClip, AudioFileClip
        except ImportError:
            from moviepy import ImageSequenceClip, AudioFileClip

        rhythm = int(config.get('rhythm','3'))
        seg_map = {1:14,2:11,3:9,4:7,5:5}
        spi = seg_map.get(rhythm,9)

        # Ajustar duración
        dur_str = config.get('duration','60').lower()
        if '30' in dur_str: dur_t=30
        elif '90' in dur_str: dur_t=90
        elif 'completa' in dur_str and audio_u:
            try:
                a=AudioFileClip(audio_u); dur_t=a.duration; a.close()
            except: dur_t=60
        else: dur_t=60

        spi = max(4, min(16, dur_t/len(paths)))
        FI = int(VIDEO_FPS*spi)
        FT = int(VIDEO_FPS*0.8)

        log(f"   {len(paths)} imgs × {spi:.1f}s | dur_obj={dur_t}s",'video')

        # Cargar PIL
        imgs_pil=[]
        for p in paths:
            try:
                img=Image.open(p).convert('RGB')
                if img.size!=(VIDEO_ANCHO,VIDEO_ALTO): img=escalar_9_16(img)
                imgs_pil.append(img)
            except: pass

        if not imgs_pil:
            log("Sin PIL",'error'); return False

        # Efectos
        EF=['kb_d','kb_i','kb_a','kb_b','zoom']
        tr_cfg = config.get('transition','Ken Burns').lower()
        if 'fade' in tr_cfg: TR=['fade']*5
        elif 'horizontal' in tr_cfg: TR=['sl','sr']*3
        elif 'vertical' in tr_cfg: TR=['su','sd']*3
        else: TR=['fade','sl','sr','su','fade']

        efs=[EF[i%len(EF)] for i in range(len(imgs_pil))]
        trs=[TR[i%len(TR)] for i in range(len(imgs_pil))]
        random.shuffle(efs)
        KBD=['derecha','izquierda','arriba','abajo']

        frames=[]
        for i,img in enumerate(imgs_pil):
            ef=efs[i]; kbd=KBD[i%4]
            for f in range(FI):
                p=f/max(FI-1,1)
                if ef.startswith('kb'): fr=kb(img,p,kbd)
                elif ef=='zoom': fr=kb(img,p*0.06,'derecha')
                else: fr=img.copy()
                fr=texto_overlay(fr,config,i,len(imgs_pil))
                frames.append(np.array(fr))
            if i<len(imgs_pil)-1:
                sig=imgs_pil[i+1]; tr=trs[i]
                for f in range(FT):
                    a=f/FT
                    if tr=='fade': ft=blend(img,sig,a)
                    elif tr=='sl': ft=slide(img,sig,a,'left')
                    elif tr=='sr': ft=slide(img,sig,a,'right')
                    elif tr=='su': ft=slide(img,sig,a,'up')
                    else: ft=slide(img,sig,a,'down')
                    ft=texto_overlay(ft,config,i,len(imgs_pil))
                    frames.append(np.array(ft))

        dur_real=len(frames)/VIDEO_FPS
        log(f"   Frames:{len(frames)} → {dur_real:.1f}s",'video')

        clip=ImageSequenceClip(frames,fps=VIDEO_FPS)

        if audio_u and os.path.exists(audio_u):
            try:
                audio=AudioFileClip(audio_u)
                clip=clip.set_audio(audio.subclip(0,clip.duration) if audio.duration>=clip.duration else audio)
                log("   Audio OK",'ok')
            except Exception as e:
                log(f"   Audio error:{e}",'warn')

        Path(OUTPUT_DIR).mkdir(parents=True,exist_ok=True)
        nombre=limpiar(config.get('song_name','video'))
        out=f"{OUTPUT_DIR}/{nombre}_{datetime.now().strftime('%Y%m%d_%H%M')}.mp4"

        clip.write_videofile(out,codec='libx264',audio_codec='aac',
            preset='ultrafast',
            ffmpeg_params=['-crf','28','-profile:v','baseline','-level','3.0'],
            logger=None)
        clip.close()

        mb=os.path.getsize(out)/(1024*1024)
        log(f"✅ VIDEO LISTO: {out} ({mb:.1f}MB, {dur_real:.0f}s)",'ok')

        # Guardar memoria
        try:
            pj=cargar_json(PROYECTOS_PATH,{'proyectos':[]})
            entry={'song_name':config.get('song_name',''),'artist':config.get('artist',''),
                   'genres':config.get('genres',''),'palette':config.get('palette',''),
                   'video':out,'modo':modo,'fecha':datetime.now().isoformat(),
                   'fecha_str':datetime.now().strftime('%d/%m/%Y %H:%M')}
            pj['proyectos'].insert(0,entry); pj['ultimo']=entry
            if len(pj['proyectos'])>50: pj['proyectos']=pj['proyectos'][:50]
            guardar_json(PROYECTOS_PATH,pj)
        except: pass

        # Limpiar /tmp
        for p in paths:
            try:
                if p.startswith('/tmp/') and os.path.exists(p): os.remove(p)
            except: pass

        print(f"\n{'='*60}\n✅ {out}\n   '{config.get('song_name')}' — {config.get('artist')}\n{'='*60}\n")
        return True

    except Exception as e:
        log(f"Error ensamblando:{e}",'error')
        import traceback; traceback.print_exc()
        return False

if __name__=="__main__":
    try:
        ok=main(); exit(0 if ok else 1)
    except Exception as e:
        log(f"Error crítico:{e}",'error')
        import traceback; traceback.print_exc()
        exit(1)
