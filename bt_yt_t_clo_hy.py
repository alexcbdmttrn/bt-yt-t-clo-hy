# -*- coding: utf-8 -*-
"""
BT_YT_T_CLO_HY - Bot de Horóscopos Diarios (Tu Cielo Hoy) - VERSIÓN ÉLITE FINAL
Motor completo: DeepSeek + Cloudflare 3 intentos + Pexels fallback + Ken Burns + Miniaturas virales + Shorts
Optimizado para ejecución 100% en GitHub Actions (Ubuntu 22.04)
"""
import asyncio
import base64
import bisect
import json
import os
import random
import re
import ssl
import socket
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import edge_tts
import numpy as np
import requests
import urllib3
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload
from moviepy.editor import (
    AudioFileClip, AudioClip, CompositeAudioClip, CompositeVideoClip,
    ImageClip, VideoClip, concatenate_audioclips, concatenate_videoclips
)
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ================================================================
# 1. CONFIGURACIÓN PRINCIPAL
# ================================================================
TZ = ZoneInfo("America/Mexico_City")

# Variables de entorno (GitHub Secrets)
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
YT_TOKEN_STR = os.getenv("YOUTUBE_USER_TOKEN", "{}")

CANAL_LINK = "https://www.youtube.com/@tucielhoy"
FACEBOOK_LINK = ""

# Archivos de estado
ESTADO_FILE = "estado_horoscopo.json"
TITULOS_FILE = "titulos_publicados.json"

# Configuración de video
W, H, FPS = 1920, 1080, 24
DURACION_MINIMA_SEG = 480   # 8 min
DURACION_MAXIMA_SEG = 720   # 12 min
VOL_FONDO = 0.08

# Ventana de publicación (5:00 AM - 8:00 AM CDMX)
HORA_INICIO_PICO = 5
HORA_FIN_PICO = 8

# Voz femenina cálida y mística
VOZ_CANAL = {"voz": "es-MX-DaliaNeural", "tono": "+0Hz", "rate": "-4%"}
VOCES_RESPALDO = ["es-MX-DaliaNeural", "es-ES-ElviraNeural", "es-AR-ElenaNeural", "es-US-PalomaNeural"]

# Activar disclosure de IA
ACTIVAR_DISCLOSURE_IA = True
DISCLOSURE_TEXT = (
    "\n\n✨ Reflexión astrológica generada con inteligencia artificial. "
    "La astrología es una herramienta de autoconocimiento, no un destino escrito en piedra."
)

# Fuente para miniaturas
FUENTE_URL = "https://raw.githubusercontent.com/google/fonts/main/ofl/anton/Anton-Regular.ttf"

print("=" * 70)
print("🔮 BT_YT_T_CLO_HY ÉLITE - Tu Cielo Hoy")
print(f"📅 {datetime.now(TZ):%Y-%m-%d %H:%M} (CDMX)")
print("=" * 70)

# Verificar variables críticas
if not DEEPSEEK_API_KEY:
    print("❌ Falta DEEPSEEK_API_KEY")
    sys.exit(1)
if not YT_TOKEN_STR or YT_TOKEN_STR == "{}":
    print("❌ Falta YOUTUBE_USER_TOKEN")
    sys.exit(1)

# ================================================================
# 2. UTILIDADES Y ESTADO
# ================================================================
def cargar_json(ruta, default):
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def guardar_json(ruta, data):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, ruta)

def titulo_ya_publicado(titulo):
    data = cargar_json(TITULOS_FILE, {"titulos": []})
    n = titulo.lower().strip()
    for t in data["titulos"]:
        if n == t.lower().strip():
            return True
    return False

def guardar_titulo(titulo):
    data = cargar_json(TITULOS_FILE, {"titulos": []})
    if titulo not in data["titulos"]:
        data["titulos"].append(titulo)
    guardar_json(TITULOS_FILE, data)

def parsear_json(texto):
    if not texto:
        raise ValueError("respuesta vacía")
    t = re.sub(r"```(?:json)?", " ", texto, flags=re.I)
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1:
        raise ValueError("sin JSON")
    t = t[i:j + 1]
    t = re.sub(r",\s*([}\]])", r"\1", t)
    return json.loads(t, strict=False)

def fmt_ts(seg):
    seg = int(seg)
    h, m, s = seg // 3600, seg % 3600 // 60, seg % 60
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

# ================================================================
# 3. MOTOR DE PROGRAMACIÓN (5:00 AM - 8:00 AM CDMX)
# ================================================================
def calcular_hora_publicacion():
    """Calcula hora aleatoria entre 5 y 8 AM CDMX y devuelve formato UTC para YouTube."""
    ahora = datetime.now(TZ)
    hoy_inicio = ahora.replace(hour=HORA_INICIO_PICO, minute=0, second=0, microsecond=0)
    hoy_fin = ahora.replace(hour=HORA_FIN_PICO, minute=0, second=0, microsecond=0)

    if ahora >= hoy_fin:
        hoy_inicio += timedelta(days=1)
        hoy_fin += timedelta(days=1)
        print(" Ya pasó la ventana de hoy. Programando para MAÑANA.")
    else:
        print("⏳ Ventana de hoy activa. Programando para HOY.")

    minutos_totales = int((hoy_fin - hoy_inicio).total_seconds() / 60)
    minutos_a_sumar = random.randint(0, minutos_totales - 1)
    hora_final_cdmx = hoy_inicio + timedelta(minutes=minutos_a_sumar)

    hora_utc = hora_final_cdmx.astimezone(timezone.utc)
    return hora_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"), hora_final_cdmx.strftime("%H:%M")

# ================================================================
# 4. INTELIGENCIA ARTIFICIAL (DEEPSEEK) - PROMPT ÉLITE
# ================================================================
SIGNOS_ZODIACO = [
    {"nombre": "Aries", "simbolo": "♈", "elemento": "fuego", "visual": "red sunrise fire sparks"},
    {"nombre": "Tauro", "simbolo": "♉", "elemento": "tierra", "visual": "green forest sunlight"},
    {"nombre": "Géminis", "simbolo": "♊", "elemento": "aire", "visual": "wind blowing trees mirror"},
    {"nombre": "Cáncer", "simbolo": "♋", "elemento": "agua", "visual": "ocean waves calm moonlight"},
    {"nombre": "Leo", "simbolo": "♌", "elemento": "fuego", "visual": "golden sunset lion silhouette"},
    {"nombre": "Virgo", "simbolo": "♍", "elemento": "tierra", "visual": "morning dew leaves wheat"},
    {"nombre": "Libra", "simbolo": "♎", "elemento": "aire", "visual": "pink sunset clouds symmetry"},
    {"nombre": "Escorpio", "simbolo": "♏", "elemento": "agua", "visual": "deep ocean dark mysterious"},
    {"nombre": "Sagitario", "simbolo": "♐", "elemento": "fuego", "visual": "mountain peak sunrise arrow"},
    {"nombre": "Capricornio", "simbolo": "♑", "elemento": "tierra", "visual": "stone architecture winter"},
    {"nombre": "Acuario", "simbolo": "♒", "elemento": "aire", "visual": "aurora borealis electric sky"},
    {"nombre": "Piscis", "simbolo": "♓", "elemento": "agua", "visual": "underwater coral reef dreamy"},
]

PROMPT_ELITE = """
Eres la astróloga más prestigiosa y empática de YouTube. Tu tono es femenino, cálido, místico y reconfortante.
Fecha de hoy: {fecha}. Fase Lunar: {fase_lunar}.
Genera el contenido completo para un video de horóscopo diario que abarque los 12 signos del zodiaco en orden.

REGLAS SEO ÉLITE:
1. Título: 55-65 caracteres. Debe incluir el tránsito lunar y un gancho de curiosidad.
2. Descripción: 3 párrafos. P1: Gancho emocional. P2: Entity stacking (menciona planetas, energía del día y los 12 signos). P3: Llamada a la acción.
3. Tags: EXACTAMENTE 15 tags cortos en español (máximo 20 caracteres cada uno).
4. Comentario Fijado: Frase mística que invite a comentar el propio signo y decretar algo positivo.
5. Miniatura: Prompt en inglés para IA (fondo místico, sin texto) y 2-3 palabras en MAYÚSCULAS para el texto.
6. Signos: Para cada uno de los 12 signos, genera: nombre, simbolo, titulo_cap (4-6 palabras), guion (~80 palabras: Energía, Amor, Dinero, Mantra final de 5 palabras), visual_prompt (3 palabras en inglés).

Responde SOLO con este formato JSON válido, sin markdown:
{
  "titulo": "...",
  "descripcion": "...",
  "tags": ["tag1", "tag2"],
  "comentario_fijado": "...",
  "miniatura_prompt": "...",
  "miniatura_texto": "...",
  "signos": [
    {"nombre": "Aries", "simbolo": "♈", "titulo_cap": "...", "guion": "...", "visual_prompt": "red sunrise fire sparks"},
    {"nombre": "Tauro", "simbolo": "♉", "titulo_cap": "...", "guion": "...", "visual_prompt": "green forest sunlight"},
    {"nombre": "Géminis", "simbolo": "♊", "titulo_cap": "...", "guion": "...", "visual_prompt": "wind blowing trees"},
    {"nombre": "Cáncer", "simbolo": "♋", "titulo_cap": "...", "guion": "...", "visual_prompt": "ocean waves calm"},
    {"nombre": "Leo", "simbolo": "♌", "titulo_cap": "...", "guion": "...", "visual_prompt": "golden sunset"},
    {"nombre": "Virgo", "simbolo": "♍", "titulo_cap": "...", "guion": "...", "visual_prompt": "morning dew leaves"},
    {"nombre": "Libra", "simbolo": "♎", "titulo_cap": "...", "guion": "...", "visual_prompt": "symmetry nature"},
    {"nombre": "Escorpio", "simbolo": "♏", "titulo_cap": "...", "guion": "...", "visual_prompt": "deep ocean dark"},
    {"nombre": "Sagitario", "simbolo": "♐", "titulo_cap": "...", "guion": "...", "visual_prompt": "mountain peak sunrise"},
    {"nombre": "Capricornio", "simbolo": "♑", "titulo_cap": "...", "guion": "...", "visual_prompt": "stone architecture"},
    {"nombre": "Acuario", "simbolo": "♒", "titulo_cap": "...", "guion": "...", "visual_prompt": "aurora borealis"},
    {"nombre": "Piscis", "simbolo": "♓", "titulo_cap": "...", "guion": "...", "visual_prompt": "underwater coral reef"}
  ]
}
"""

def llamar_deepseek(fecha, fase_lunar):
    prompt = PROMPT_ELITE.format(fecha=fecha, fase_lunar=fase_lunar)
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7,
        "max_tokens": 3500,
        "response_format": {"type": "json_object"}
    }

    for intento in range(3):
        try:
            print(f"   🧠 Intento {intento+1}/3 con DeepSeek...")
            r = requests.post(DEEPSEEK_URL, headers=headers, json=payload, timeout=120)
            r.raise_for_status()
            texto = r.json()["choices"][0]["message"]["content"].strip()
            texto = texto.replace("```json", "").replace("```", "").strip()
            return parsear_json(texto)
        except Exception as e:
            print(f"   ️ DeepSeek intento {intento+1} falló: {e}")
            time.sleep(5)
    raise Exception("No se pudo obtener respuesta de DeepSeek tras 3 intentos")

# ================================================================
# 5. GENERACIÓN DE IMÁGENES (CLOUDFLARE 3 INTENTOS + PEXELS)
# ================================================================
def generar_cf(prompt, ruta_salida):
    """Genera imagen con Cloudflare Workers AI (Flux-1-Schnell)."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}

    # Limpieza extrema del prompt
    clean_prompt = re.sub(r'[^a-zA-Z0-9\s,]', ' ', prompt)[:400]

    payload = {
        "prompt": f"{clean_prompt}, mystical, ethereal, cinematic lighting, 8k, highly detailed, no text, no letters, no watermark",
        "steps": 4
    }

    r = requests.post(url, headers=headers, json=payload, timeout=60)

    if r.status_code == 400:
        print(f"   ❌ Cloudflare 400 Bad Request. Detalle: {r.text[:200]}")

    r.raise_for_status()

    result = r.json()
    if "result" not in result or "image" not in result["result"]:
        raise ValueError(f"Respuesta de Cloudflare sin imagen: {str(result)[:200]}")

    img_data = base64.b64decode(result["result"]["image"])
    with open(ruta_salida, "wb") as f:
        f.write(img_data)

    # Normalizar a 1920x1080
    with Image.open(ruta_salida) as im:
        im = ImageOps.fit(im.convert("RGB"), (W, H), Image.LANCZOS)
        im.save(ruta_salida, "JPEG", quality=92)

    return ruta_salida

def generar_pexels(query, ruta_salida):
    """Busca y descarga imagen de Pexels."""
    headers = {"Authorization": PEXELS_API_KEY}
    r = requests.get(
        "https://api.pexels.com/v1/search",
        headers=headers,
        params={"query": query, "orientation": "landscape", "size": "large", "per_page": 5},
        timeout=15
    )
    r.raise_for_status()
    fotos = r.json().get("photos", [])
    if not fotos:
        raise Exception("Sin resultados en Pexels")

    url_img = fotos[0]["src"]["large2x"]
    with requests.get(url_img, stream=True, timeout=15) as r_img:
        r_img.raise_for_status()
        with open(ruta_salida, "wb") as f:
            for chunk in r_img.iter_content(8192):
                f.write(chunk)

    with Image.open(ruta_salida) as im:
        im = ImageOps.fit(im.convert("RGB"), (W, H), Image.LANCZOS)
        im.save(ruta_salida, "JPEG", quality=92)

    return ruta_salida

def obtener_imagen_segura(prompt, ruta, es_miniatura=False):
    """Lógica Élite: 3 intentos Cloudflare + fallback Pexels infalible."""
    print(f"   🎨 Generando: '{prompt}'...")

    # 3 Intentos con Cloudflare
    for i in range(1, 4):
        try:
            print(f"   ☁️ Intento {i}/3 con Cloudflare...")
            return generar_cf(prompt, ruta)
        except Exception as e:
            print(f"   ⚠️ CF falló ({i}/3): {str(e)[:100]}")
            time.sleep(2)

    # Fallback a Pexels
    print("   ⚠️ Cloudflare agotado. Activando respaldo Pexels...")
    try:
        query_pexels = prompt + " dark mystical cosmic" if es_miniatura else prompt
        return generar_pexels(query_pexels, ruta)
    except Exception as e:
        print(f"   ❌ Fallo total de imagen: {e}")
        return None

# ================================================================
# 6. AUDIO (EDGE TTS)
# ================================================================
def duracion_audio(ruta):
    try:
        a = AudioFileClip(ruta)
        d = a.duration
        a.close()
        return d
    except Exception:
        return 0

async def generar_audio(texto, ruta, voz=None, rate=None):
    voz = voz or VOZ_CANAL["voz"]
    rate = rate or VOZ_CANAL["rate"]
    limpio = re.sub(r'[{}[\]"]', ' ', texto)
    limpio = re.sub(r'\s+', ' ', limpio).strip()

    if len(limpio) < 10:
        return None

    voces = [voz] + [v for v in VOCES_RESPALDO if v != voz]

    for v in voces:
        for intento in range(2):
            try:
                communicate = edge_tts.Communicate(limpio, v, rate=rate, pitch=VOZ_CANAL["tono"])
                await communicate.save(ruta)
                if os.path.exists(ruta) and os.path.getsize(ruta) > 500:
                    return ruta
            except Exception as e:
                print(f"   ⚠️ TTS {v} falló: {e}")
                time.sleep(2)

    return None

def sintetizar(segs):
    ok = []
    for i, s in enumerate(segs):
        ruta = f"temp_audio_{i}.mp3"
        resultado = asyncio.run(generar_audio(s["texto"], ruta))
        if not resultado:
            print(f"   ⚠️ Segmento {i} sin audio, se omite")
            continue
        s["audio"] = ruta
        s["dur_audio"] = duracion_audio(ruta)
        ok.append(s)
        time.sleep(0.3)
    return ok

# ================================================================
# 7. RENDER DE VIDEO (KEN BURNS + VIÑETAS)
# ================================================================
_VIG = {}

def vignette(size, base=1.0, fuerza=0.55):
    k = (size, base)
    if k not in _VIG:
        w, h = size
        y, x = np.ogrid[-1:1:h * 1j, -1:1:w * 1j]
        d = np.clip(np.sqrt(x ** 2 + y ** 2) / 1.414, 0, 1)
        _VIG[k] = ((1 - fuerza * d ** 2.2) * base).astype(np.float32)[..., None]
    return _VIG[k]

def grade(img, etapa="mystic"):
    img = ImageEnhance.Color(img).enhance(0.85)
    img = ImageEnhance.Contrast(img).enhance(1.15)
    img = ImageEnhance.Brightness(img).enhance(0.92)
    return Image.blend(img, Image.new("RGB", img.size, (20, 10, 40)), 0.08)

class RenderEscenas:
    def __init__(self, escenas, size, total):
        self.esc, self.size, self.total = escenas, size, total
        self.starts = [e["inicio"] for e in escenas]
        self._ikey = self._img = None
        self.vig = vignette(size, 1.0)

    def _base(self, e):
        key = (e["path"], e["etapa"])
        if self._ikey != key:
            sz = (int(self.size[0] * 1.2), int(self.size[1] * 1.2))
            im = ImageOps.fit(Image.open(e["path"]).convert("RGB"), sz, Image.LANCZOS)
            arr = np.asarray(grade(im, e["etapa"]), dtype=np.float32) * vignette(sz, 1.0)
            self._img, self._ikey = Image.fromarray(arr.astype(np.uint8)), key
        return self._img

    def frame(self, t):
        i = max(0, bisect.bisect_right(self.starts, t) - 1)
        e = self.esc[i]
        lt = t - e["inicio"]
        base = self._base(e)
        bw, bh = base.size
        p = min(max(lt / e["dur"], 0), 1) if e["dur"] > 0 else 0
        if not e["zin"]:
            p = 1 - p

        cw = bw / (1 + 0.2 * p)
        ch = cw * bh / bw
        mx, my = bw - cw, bh - ch
        x0 = min(max(mx / 2 + e["ax"] * mx / 2 * 0.8, 0), mx)
        y0 = min(max(my / 2 + e["ay"] * my / 2 * 0.8, 0), my)

        fr = np.asarray(base.resize(self.size, Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch)))

        f = 1.0
        if e.get("fade") and lt < 0.6:
            f = lt / 0.6
        if t > self.total - 1.5:
            f = min(f, max(0.0, (self.total - t) / 1.5))
        if f < 1.0:
            fr = (fr.astype(np.float32) * f).astype(np.uint8)
        return fr

def renderizar_video(signos_data, salida):
    escenas = []
    t_total = 0.0

    for i, signo in enumerate(signos_data):
        img_path = f"temp_signo_{i}.jpg"
        audio_path = f"temp_audio_{i}.mp3"

        if not os.path.exists(img_path) or not os.path.exists(audio_path):
            print(f"   ️ Faltan archivos para {signo['nombre']}, saltando...")
            continue

        dur = duracion_audio(audio_path) + 0.5

        # Superponer texto en la imagen
        img = Image.open(img_path).convert("RGB").resize((W, H))
        draw = ImageDraw.Draw(img)

        try:
            font_t = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 110)
            font_s = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
        except Exception:
            font_t = font_s = ImageFont.load_default()

        draw.text((W//2, 250), f"{signo['simbolo']} {signo['nombre']}", font=font_t,
                  fill=(255, 255, 255), anchor="mm", stroke_width=8, stroke_fill=(0, 0, 0))

        # Mantra (última oración)
        oraciones = signo['guion'].split('.')
        mantra = oraciones[-1].strip() if oraciones else ""
        if len(mantra) > 60:
            mantra = mantra[:60] + "..."
        draw.text((W//2, 850), mantra, font=font_s,
                  fill=(255, 215, 0), anchor="mm", stroke_width=6, stroke_fill=(0, 0, 0))

        img.save(f"temp_frame_{i}.jpg")

        escenas.append({
            "path": f"temp_frame_{i}.jpg",
            "inicio": t_total,
            "dur": dur,
            "etapa": "mystic",
            "fade": i == 0,
            "zin": i % 2 == 0,
            "ax": random.uniform(-1, 1),
            "ay": random.uniform(-1, 1)
        })
        t_total += dur

    if not escenas:
        raise Exception("No hay escenas válidas para renderizar")

    render = RenderEscenas(escenas, (W, H), t_total)
    video = VideoClip(render.frame, duration=t_total)

    # Audio
    clips_audio = [AudioFileClip(e["path"].replace("temp_frame_", "temp_audio_").replace(".jpg", ".mp3"))
                   .set_start(e["inicio"]) for e in escenas]
    audio_final = CompositeAudioClip(clips_audio)
    video = video.set_audio(audio_final)

    print("🎬 Renderizando con Ken Burns y Viñetas...")
    video.write_videofile(
        salida, fps=FPS, codec="libx264", audio_codec="aac",
        threads=4, preset="ultrafast", logger=None,
        ffmpeg_params=["-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    )
    return salida

# ================================================================
# 8. MINIATURAS ÉLITE (DEGRADADOS + BANNERS)
# ================================================================
def obtener_fuente(size):
    os.makedirs("fonts", exist_ok=True)
    ruta = "fonts/Anton-Regular.ttf"
    if not os.path.exists(ruta):
        try:
            r = requests.get(FUENTE_URL, timeout=20)
            if r.status_code == 200 and len(r.content) > 20000:
                with open(ruta, "wb") as f:
                    f.write(r.content)
        except Exception:
            pass

    for p in [ruta, "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()

def render_texto_gradiente(texto, font_path, size, top=(255, 242, 90), bottom=(255, 150, 0)):
    font = ImageFont.truetype(font_path, size)
    b = font.getbbox(texto)
    w = (b[2] - b[0]) + 20
    h = (b[3] - b[1]) + 20
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    d.text((10, 10), texto, font=font, fill=(10, 10, 10), stroke_width=8, stroke_fill=(10, 10, 10))

    grad = np.zeros((h, w, 4), dtype=np.uint8)
    t = np.linspace(0, 1, h)[:, None]
    grad_rgb = (np.array(top, float) * (1 - t) + np.array(bottom, float) * t).astype(np.uint8)
    grad[:, :, :3] = np.broadcast_to(grad_rgb[:, None, :], (h, w, 3))
    grad[:, :, 3] = 255
    grad_img = Image.fromarray(grad, "RGBA")

    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).text((10, 10), texto, font=font, fill=255)
    grad_img.putalpha(mask)

    return Image.alpha_composite(out, grad_img)

def render_banner(texto, font_path, size, bg=(198, 30, 30)):
    font = ImageFont.truetype(font_path, size)
    b = font.getbbox(texto)
    w = (b[2] - b[0]) + 40
    h = (b[3] - b[1]) + 20
    img = Image.new("RGBA", (w + 14, h + 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([7, 10, w + 7, h + 10], radius=14, fill=(0, 0, 0, 140))
    d.rounded_rectangle([7, 6, w + 7, h + 6], radius=14, fill=bg + (255,), outline=(255, 235, 59, 255), width=4)
    d.text((7 + 20 - b[0], 6 + 12 - b[1]), texto, font=font, fill=(255, 255, 255, 255))
    return img

def crear_miniatura_elite(img_path, texto, salida):
    try:
        img = Image.open(img_path).convert("RGB").resize((1280, 720))
        img = ImageEnhance.Contrast(img).enhance(1.25)
        img = ImageEnhance.Color(img).enhance(1.2)
        img = img.convert("RGBA")

        fuente = "fonts/Anton-Regular.ttf"
        if not os.path.exists(fuente):
            fuente = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

        # Texto principal con degradado
        bloque1 = render_texto_gradiente(texto, fuente, 90)
        bloque1 = bloque1.rotate(2, expand=True, resample=Image.BICUBIC)
        x = (1280 - bloque1.width) // 2
        y = (720 - bloque1.height) // 2 - 50

        # Banner rojo
        bloque2 = render_banner("MENSAJE DEL UNIVERSO", fuente, 40)
        bloque2 = bloque2.rotate(-2, expand=True, resample=Image.BICUBIC)
        y2 = y + bloque1.height + 30
        x2 = (1280 - bloque2.width) // 2

        img.paste(bloque1, (x, y), bloque1)
        img.paste(bloque2, (x2, y2), bloque2)
        img.convert("RGB").save(salida, "JPEG", quality=92)
        return True
    except Exception as e:
        print(f"⚠️ Error miniatura: {e}")
        traceback.print_exc()
        return False

# ================================================================
# 9. SUBIDA A YOUTUBE (CON REINTENTOS EXPONENCIALES)
# ================================================================
def limpiar_y_validar_tags(tags_lista):
    if not isinstance(tags_lista, list):
        tags_lista = [t.strip() for t in str(tags_lista).split(",")] if tags_lista else []

    tags_limpios = []
    total_length = 0

    for tag in tags_lista:
        t = str(tag).strip().strip('"\'').lower()
        t = re.sub(r'[^\w\sáéíóúñ]', ' ', t)
        t = re.sub(r'\s+', ' ', t).strip()

        if len(t) < 2 or len(t) > 30:
            continue

        if t not in tags_limpios:
            if total_length + len(t) + 1 <= 500:
                tags_limpios.append(t)
                total_length += len(t) + 1
            else:
                break

    if not tags_limpios:
        tags_limpios = ["horoscopo diario", "astrologia", "zodiaco", "tu cielo hoy"]

    return tags_limpios

def obtener_credenciales_youtube():
    yt_token = json.loads(YT_TOKEN_STR)
    creds = Credentials(
        token=yt_token.get("token"),
        refresh_token=yt_token.get("refresh_token"),
        token_uri=yt_token.get("token_uri"),
        client_id=yt_token.get("client_id"),
        client_secret=yt_token.get("client_secret"),
        scopes=yt_token.get("scopes")
    )

    if creds.expired and creds.refresh_token:
        print("🔄 Token expirado, refrescando...")
        try:
            creds.refresh(Request())
            print("✅ Token refrescado")
        except Exception as e:
            print(f"❌ Error refrescando token: {e}")
            sys.exit(1)

    return creds

def subir_a_youtube(ruta_video, ruta_miniatura, datos, hora_utc):
    creds = obtener_credenciales_youtube()
    youtube = build("youtube", "v3", credentials=creds)

    # Capítulos con timestamps estimados
    tiempo_acumulado = 0
    caps = []
    for s in datos["signos"]:
        caps.append(f"{tiempo_acumulado//60:02d}:{tiempo_acumulado%60:02d} {s['simbolo']} {s['nombre']}: {s['titulo_cap']}")
        tiempo_acumulado += 50

    desc_final = f"{datos['descripcion']}\n\n⏰ CAPÍTULOS:\n" + "\n".join(caps) + f"\n\n🔔 Suscríbete: {CANAL_LINK}"

    if ACTIVAR_DISCLOSURE_IA:
        desc_final += DISCLOSURE_TEXT

    tags_seguros = limpiar_y_validar_tags(datos.get("tags", []))
    print(f"🏷️ Tags validados: {len(tags_seguros)} tags")

    body = {
        "snippet": {
            "title": datos["titulo"][:100],
            "description": desc_final[:5000],
            "tags": tags_seguros,
            "categoryId": "24",
            "defaultLanguage": "es",
            "defaultAudioLanguage": "es"
        },
        "status": {
            "privacyStatus": "private",
            "publishAt": hora_utc,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True
        }
    }

    media = MediaFileUpload(ruta_video, chunksize=4*1024*1024, resumable=True, mimetype="video/mp4")
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)

    # Reintentos robustos
    resp, reintentos = None, 0
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st:
                print(f"   ️ {int(st.progress() * 100)}%")
        except (HttpError, ssl.SSLError, ConnectionError, socket.timeout, OSError) as e:
            if reintentos < 8:
                reintentos += 1
                espera = 2 ** reintentos
                print(f"⚠️ Error de red (intento {reintentos}/8). Reintentando en {espera}s...")
                time.sleep(espera)
            else:
                raise e

    video_id = resp["id"]
    print(f"✅ Video subido. ID: {video_id}")

    # Subir miniatura
    if ruta_miniatura and os.path.exists(ruta_miniatura):
        try:
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(ruta_miniatura, mimetype="image/jpeg")
            ).execute()
            print("✅ Miniatura aplicada.")
        except Exception as e:
            print(f"⚠️ Error miniatura: {e}")

    # Comentario fijado
    if datos.get("comentario_fijado"):
        try:
            youtube.commentThreads().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "topLevelComment": {
                            "snippet": {"textOriginal": datos["comentario_fijado"]}
                        }
                    }
                }
            ).execute()
            print("✅ Comentario fijado publicado.")
        except Exception as e:
            print(f"⚠️ Error comentario: {e}")

    return video_id

# ================================================================
# 10. GENERACIÓN DE SHORTS
# ================================================================
def crear_short(signos_data, plan, salida="short_final.mp4"):
    """Crea un Short con los 3 signos más interesantes del día."""
    # Seleccionar 3 signos aleatorios
    seleccion = random.sample(signos_data, min(3, len(signos_data)))

    escenas = []
    t_total = 0.0

    for i, signo in enumerate(seleccion):
        img_path = f"temp_signo_{signos_data.index(signo)}.jpg"
        audio_path = f"temp_audio_{signos_data.index(signo)}.mp3"

        if not os.path.exists(img_path) or not os.path.exists(audio_path):
            continue

        dur = duracion_audio(audio_path)
        if dur > 15:
            dur = 15  # Limitar a 15 seg por signo para el short

        escenas.append({
            "path": img_path,
            "inicio": t_total,
            "dur": dur,
            "etapa": "mystic",
            "fade": i == 0,
            "zin": i % 2 == 0,
            "ax": random.uniform(-1, 1),
            "ay": random.uniform(-1, 1)
        })
        t_total += dur

    if not escenas or t_total < 10:
        print("⚠️ No hay material suficiente para el Short")
        return None

    # Agregar CTA final
    cta_texto = "Historia completa en el canal. Suscríbete."
    cta_path = "temp_audio_cta.mp3"
    asyncio.run(generar_audio(cta_texto, cta_path, rate="-6%"))

    if os.path.exists(cta_path):
        dur_cta = duracion_audio(cta_path)
        escenas.append({
            "path": escenas[-1]["path"],
            "inicio": t_total,
            "dur": dur_cta + 0.5,
            "etapa": "mystic",
            "fade": False,
            "zin": False,
            "ax": 0,
            "ay": 0
        })
        t_total += dur_cta + 0.5

    render = RenderEscenas(escenas, (1080, 1920), t_total)
    video = VideoClip(render.frame, duration=t_total)

    clips_audio = []
    for e in escenas:
        idx = signos_data.index(next((s for s in signos_data if f"temp_signo_{signos_data.index(s)}.jpg" == e["path"]), None))
        audio_path = f"temp_audio_{idx}.mp3"
        if os.path.exists(audio_path):
            clips_audio.append(AudioFileClip(audio_path).set_start(e["inicio"]))

    if clips_audio:
        video = video.set_audio(CompositeAudioClip(clips_audio))

    video.write_videofile(
        salida, fps=FPS, codec="libx264", audio_codec="aac",
        threads=4, preset="ultrafast", logger=None
    )
    return salida

# ================================================================
# 11. LIMPIEZA
# ================================================================
def limpiar_temporales():
    for f in os.listdir("."):
        if f.startswith("temp_") or f in ["video_final.mp4", "miniatura.jpg", "short_final.mp4"]:
            try:
                os.remove(f)
            except OSError:
                pass

# ================================================================
# 12. FLUJO PRINCIPAL
# ================================================================
def main():
    try:
        # 1. Calcular hora de publicación
        hora_utc, hora_cdmx = calcular_hora_publicacion()
        print(f" Programando publicación para hoy a las {hora_cdmx} (CDMX)")

        # 2. Obtener fecha y fase lunar
        fecha_hoy = datetime.now(TZ).strftime("%d de %B de %Y")
        fase_lunar = "Creciente"  # Se puede mejorar con librería 'ephem'

        # 3. Generar contenido con DeepSeek
        print(" 1. Generando contenido con DeepSeek...")
        datos = llamar_deepseek(fecha_hoy, fase_lunar)
        print(f"   Título elegido: {datos['titulo']}")

        # Anti-repetición
        if titulo_ya_publicado(datos["titulo"]):
            print("⚠️ Título repetido, forzando variación...")
            datos["titulo"] = f"{datos['titulo']} (Edición Especial)"

        # 4. Generar imágenes y audio para los 12 signos
        print("🎨 2. Generando activos (Imágenes y Audio) para los 12 signos...")
        for i, signo in enumerate(datos["signos"]):
            print(f"   Procesando {signo['nombre']}...")
            img_path = f"temp_signo_{i}.jpg"
            audio_path = f"temp_audio_{i}.mp3"

            obtener_imagen_segura(
                signo.get("visual_prompt", "mystical galaxy stars"),
                img_path
            )
            asyncio.run(generar_audio(signo["guion"], audio_path))

        # 5. Crear miniatura
        print("🖼️ 3. Creando miniatura Élite...")
        ruta_miniatura = "miniatura.jpg"
        obtener_imagen_segura(
            datos.get("miniatura_prompt", "mystical zodiac wheel glowing"),
            "temp_bg_thumb.jpg",
            es_miniatura=True
        )
        crear_miniatura_elite("temp_bg_thumb.jpg", datos.get("miniatura_texto", "HORÓSCOPO HOY"), ruta_miniatura)

        # 6. Renderizar video
        print(" 4. Renderizando video...")
        ruta_video = "video_final.mp4"
        renderizar_video(datos["signos"], ruta_video)

        # 7. Subir a YouTube
        print("📤 5. Subiendo a YouTube con reintentos...")
        video_id = subir_a_youtube(ruta_video, ruta_miniatura, datos, hora_utc)

        # 8. Generar Short (opcional)
        print("📱 6. Generando Short embudo...")
        try:
            short_path = crear_short(datos["signos"], datos)
            if short_path and os.path.exists(short_path):
                t_short = str(datos.get("titulo", "Horóscopo Hoy"))[:88] + " #Shorts"
                d_short = f"Historia completa 👉 https://youtu.be/{video_id}\n\nSuscríbete: {CANAL_LINK}\n\n#Shorts #Horoscopo"
                subir_a_youtube(short_path, None, {"titulo": t_short, "descripcion": d_short, "tags": ["shorts", "horoscopo"], "comentario_fijado": ""}, hora_utc)
        except Exception as e:
            print(f"️ Short falló (el video largo ya está subido): {e}")

        print("✨ ¡PROCESO COMPLETADO CON ÉXITO!")
        guardar_titulo(datos["titulo"])

        # Limpieza
        limpiar_temporales()

    except Exception as e:
        print(f" ERROR FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
