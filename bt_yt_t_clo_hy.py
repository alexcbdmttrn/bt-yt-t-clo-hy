# -*- coding: utf-8 -*-
"""
BT_YT_T_CLO_HY - Bot Horóscopo Master (Tu Cielo Hoy) - VERSIÓN ELITE 2026
============================================================================
NOVEDADES vs versión anterior:
- INTRO de 2s con música al inicio del video (antes de la narración del primer signo)
- 5 títulos candidatos + scorer local (longitud, trigger, emoji, signo)
- Descripción en 3 capas (hook 125 + keywords + capítulos + CTA)
- Hook rotado para la intro (5 estructuras)
- Voz por modo (daily/weekly/monthly con rate distinto)
- Música por modo (no aleatoria)
- Tags hiper-específicos por modo
- Hashtags rotados por tema
- Scheduling con ventana amplia (no salta al día siguiente)
- Persistencia de titulos_publicados.json con commit a GitHub (FIX CRÍTICO)
- try/finally para cerrar AudioFileClip y VideoClip (fix leaks)
- Cloudflare con backoff exponencial
- Fix bg.duration == 0
- Validación de título antes de subir
"""
import asyncio, base64, bisect, json, os, random, re, ssl, socket, sys, time, traceback, unicodedata, subprocess
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
import edge_tts
from gtts import gTTS
from moviepy.editor import AudioFileClip, CompositeAudioClip, VideoClip, concatenate_audioclips
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# ================================================================
# 1. CONFIGURACIÓN
# ================================================================
TZ = ZoneInfo("America/Mexico_City")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID", "")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN", "")
YT_TOKEN_STR = os.getenv("YOUTUBE_USER_TOKEN", "{}")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO_NAME = os.getenv("GITHUB_REPOSITORY", "")

CANAL_LINK = "https://www.youtube.com/@tucielhoy"
TITULOS_FILE = "titulos_publicados.json"
W, H, FPS = 1920, 1080, 24
INTRO_DUR = 2.0  # segundos de música antes de la narración del primer signo

VOZ_CANAL = "es-MX-DaliaNeural"

# Rate de voz según modo (más calmado en mensual)
VOZ_RATE_POR_MODO = {
    "daily": "-4%",
    "weekly": "-3%",
    "monthly": "-2%",
}

# Música fija por modo
MUSICA_POR_MODO = {
    "daily": "Celestial Drift.mp3",
    "weekly": "Astral Zenith.mp3",
    "monthly": "Sylvan Sanctuary.mp3",
}

# ================================================================
# 🏷️ MOTOR DE TAGS SEO
# ================================================================
TAGS_GENERALES = [
    "horoscopo", "astrologia", "zodiaco", "tu cielo hoy", "mensaje del universo",
    "aries", "tauro", "geminis", "cancer", "leo", "virgo", "libra", "escorpio",
    "sagitario", "capricornio", "acuario", "piscis", "energia del dia",
    "crecimiento espiritual", "bienestar", "lectura de tarot", "carta astral"
]

TAGS_POR_MODO = {
    "daily": ["horoscopo diario", "horoscopo de hoy", "prediccion de hoy", "energia de hoy", "mensaje de hoy", "horoscopo completo", "horoscopo hoy"],
    "weekly": ["horoscopo semanal", "horoscopo de la semana", "semana astral", "prediccion semanal", "tendencias zodiacales", "horoscopo semanal completo"],
    "monthly": ["horoscopo mensual", "horoscopo del mes", "prediccion mensual", "ciclo lunar", "luna llena", "luna nueva", "horoscopo mensual completo"]
}

HASHTAGS_BY_THEME = {
    "dinero": "#dinero #abundancia #prosperidad",
    "amor": "#amor #pareja #almaGemela",
    "alerta": "#alerta #universo #señales",
    "general": "#energia #universo #destino",
}

def normalizar_ascii(texto):
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()

def construir_tags_finales(tags_dinamicos_ia, modo="daily"):
    tags_finales, total_chars = [], 0
    todas = list(TAGS_GENERALES) + list(TAGS_POR_MODO.get(modo, []))
    if isinstance(tags_dinamicos_ia, list):
        todas.extend(tags_dinamicos_ia)
    
    for tag in todas:
        tag_limpio = normalizar_ascii(str(tag)).strip()
        tag_limpio = re.sub(r'[^a-z0-9\s]', '', tag_limpio)
        tag_limpio = re.sub(r'\s+', ' ', tag_limpio).strip()
        if 2 <= len(tag_limpio) <= 30 and tag_limpio not in tags_finales:
            if total_chars + len(tag_limpio) <= 450:
                tags_finales.append(tag_limpio)
                total_chars += len(tag_limpio)
    
    print(f"🏷️ Tags finales: {len(tags_finales)} tags, {total_chars}/450 chars")
    return tags_finales

def construir_hashtags(tema="general"):
    especifico = HASHTAGS_BY_THEME.get(tema, HASHTAGS_BY_THEME["general"])
    return f"#Horoscopo #Astrologia #Zodiaco #TuCieloHoy #MensajeDelUniverso #HoroscopoDeHoy {especifico}"

print("=" * 70)
print("🔮 BT_YT_T_CLO_HY MASTER - ELITE 2026 (2s intro + 5 títulos + persistencia)")
print(f"📅 {datetime.now(TZ):%Y-%m-%d %H:%M} (CDMX)")
print("=" * 70)

if not all([DEEPSEEK_API_KEY, PEXELS_API_KEY, CF_ACCOUNT_ID, CF_API_TOKEN, YT_TOKEN_STR]):
    print("❌ ERROR: Faltan variables de entorno.")
    sys.exit(1)

# ================================================================
# 2. UTILIDADES Y ESTADO (persistencia GitHub)
# ================================================================
def cargar_json(ruta, default):
    try:
        with open(ruta, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def guardar_json(ruta, data):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, ruta)

def titulo_ya_publicado(titulo):
    data = cargar_json(TITULOS_FILE, {"titulos": []})
    n = titulo.lower().strip()
    return any(n == t.lower().strip() for t in data["titulos"])

def guardar_titulo(titulo):
    data = cargar_json(TITULOS_FILE, {"titulos": []})
    if titulo not in data["titulos"]:
        data["titulos"].append(titulo)
    guardar_json(TITULOS_FILE, data)

def hacer_commit_titulos():
    """Persiste titulos_publicados.json en GitHub (FIX CRÍTICO)."""
    if not GITHUB_TOKEN or not REPO_NAME:
        print("   ⚠️ Sin GITHUB_TOKEN/REPO_NAME. El estado no se persistirá.")
        return False
    try:
        subprocess.run(["git", "config", "user.name", "bot-largo"], check=False, capture_output=True)
        subprocess.run(["git", "config", "user.email", "bot@tucielhoy.com"], check=False, capture_output=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False, capture_output=True)
        subprocess.run(["git", "add", TITULOS_FILE], check=False, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Update titulos {datetime.now(TZ).strftime('%Y-%m-%d %H:%M')}"], check=False, capture_output=True)
        remote_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{REPO_NAME}.git"
        result = subprocess.run(["git", "push", remote_url, "HEAD:main"], check=False, capture_output=True, text=True)
        if result.returncode == 0:
            print("   ✅ titulos_publicados.json commiteado")
        else:
            print(f"   ⚠️ Commit falló: {result.stderr[:200]}")
        return result.returncode == 0
    except Exception as e:
        print(f"   ⚠️ Error commit: {e}")
        return False

def parsear_json(texto):
    t = re.sub(r"```(?:json)?", " ", texto, flags=re.I)
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1:
        raise ValueError("sin JSON")
    return json.loads(t[i:j + 1], strict=False)

def seleccionar_mejor_titulo(titulos):
    """Scorer local: elige el título con mayor CTR predicho."""
    emojis = ["💰", "🔮", "✨", "💕", "🔥", "⚠️", "🌟", "🌙", "💫"]
    triggers = ["HOY", "hoy", "Nadie", "Señal", "señal", "Alerta", "alerta",
                "Cambio", "cambio", "Secreto", "secreto", "Verdad", "verdad",
                "Revelación", "revelación"]
    
    best_score, best_titulo = -1, ""
    for t in titulos:
        texto = t.get("texto", "") if isinstance(t, dict) else str(t)
        score = 0
        L = len(texto)
        if 55 <= L <= 75:
            score += 30
        elif 45 <= L <= 85:
            score += 15
        if "12 Signos" in texto or "12 signos" in texto:
            score += 15
        if any(trig in texto for trig in triggers):
            score += 15
        if any(e in texto for e in emojis):
            score += 10
        if "|" in texto:  # estructura con pipe (más limpia)
            score += 5
        
        if score > best_score:
            best_score = score
            best_titulo = texto
    
    if not best_titulo:
        best_titulo = titulos[0].get("texto", "") if isinstance(titulos[0], dict) else str(titulos[0])
    
    if len(best_titulo) > 100:
        best_titulo = best_titulo[:97] + "..."
    return best_titulo

# ================================================================
# 3. IA (DEEPSEEK) - PROMPT ELITE 2026
# ================================================================
PROMPT_BASE = """
Eres la astróloga más prestigiosa de YouTube y EXPERTA EN SEO Viral. Tono: femenino, cálido, místico, URGENTE.
Fecha: {fecha}. Fase Lunar: {fase_lunar}. Modo: {modo}.

REGLAS CRÍTICAS DE SEO:

1. TÍTULOS — Genera EXACTAMENTE 5 títulos candidatos con estructuras DIFERENTES:
   - "revelacion": "🔮 HORÓSCOPO {MODO}: La [Palabra] para los 12 Signos | [Tránsito]"
   - "alerta": "⚠️ ALERTA ZODIACAL: Lo que el cosmos revela hoy | [Tránsito]"
   - "completo": "✨ HORÓSCOPO COMPLETO: Un [Tema] inesperado | [Tránsito]"
   - "verdad": "💫 VERDAD OCULTA: Lo que los 12 Signos necesitan HOY | [Tránsito]"
   - "elemento": "🌙 [Tránsito]: Tu energía [elemento] brilla en [tema] | Horóscopo"
   
   Cada título DEBE cumplir:
   - Máximo 95 caracteres
   - Incluir "12 Signos" o "12 signos"
   - UN emoji de: 🔮 ⚠️ ✨ 💫 🌙
   - NO tener hashtags

2. HOOK (para el inicio del video, 1-2 segundos antes de la narración):
   UNA de estas estructuras rotadas:
   - "Nadie te dijo esto sobre tu signo esta semana."
   - "El cosmos acaba de alinear algo que cambiará tu realidad."
   - "Si estás viendo esto, NO es casualidad."
   - "Los 12 signos reciben un mensaje urgente del universo."
   - "Esta semana NO es como las demás. Te explico."

3. TEMA (elige UNO): "dinero" | "amor" | "alerta" | "general"

4. DESCRIPCIÓN EN 3 CAPAS:
   - descripcion_hook_125: Primeros 125 caracteres (preview). Hook emocional específico para HOY.
   - descripcion_keywords: Párrafo de 400-600 chars con keywords naturales (mensaje del universo, horóscopo, predicción, energía, amor, dinero).

5. MINIATURA:
   - miniatura_texto: 1-3 palabras (NO "REVELACIÓN" siempre). Opciones: "ABUNDANCIA YA", "AMOR LLEGA", "ALERTA ZODIACAL", "CAMBIO RADICAL", "VERDAD OCULTA", "DESTINO", "SECRETO REVELADO"
   - miniatura_banner: "PARA LOS 12 SIGNOS", "HORÓSCOPO DE HOY", "MENSAJE DEL UNIVERSO"

6. GUION POR SIGNO: 90-110 palabras (daily), 150-180 (weekly), 250-300 (monthly).
   - Debe comenzar con: "[Signo], hoy la energía..."
   - Incluir amor, dinero, mantra único del día
   - Título de capítulo único y creativo

Responde SOLO JSON con este formato exacto:
{{
  "titulos": [
    {{"texto": "🔮 HORÓSCOPO DIARIO: Un Cambio Radical para los 12 Signos | Luna en Cáncer", "estructura": "revelacion"}},
    {{"texto": "⚠️ ALERTA ZODIACAL: Lo que el cosmos revela hoy | Mercurio directo", "estructura": "alerta"}},
    {{"texto": "✨ HORÓSCOPO COMPLETO: Un Amor inesperado | Luna en Cáncer", "estructura": "completo"}},
    {{"texto": "💫 VERDAD OCULTA: Lo que los 12 Signos necesitan HOY | Mercurio", "estructura": "verdad"}},
    {{"texto": "🌙 Luna en Cáncer: Tu energía agua brilla en amor | Horóscopo", "estructura": "elemento"}}
  ],
  "hook": "Si estás viendo esto, NO es casualidad.",
  "tema": "amor",
  "descripcion_hook_125": "Descubre el mensaje del universo para HOY: amor, dinero y destino revelados en los 12 signos.",
  "descripcion_keywords": "En este horóscopo completo encontrarás la energía del día para cada signo del zodiaco, con predicciones específicas sobre amor, dinero y crecimiento espiritual. Incluye mantra único por signo, capítulos por signo, y revelaciones astrológicas para aprovechar los tránsitos planetarios de hoy.",
  "comentario_fijado": "✨ ¿Sientes esta energía? Decreta 'HECHO ESTÁ' y tu signo.",
  "miniatura_prompt": "masterpiece, radiant cosmic energy, volumetric lighting, hyper-detailed, 8k, trending on ArtStation, no text",
  "miniatura_texto": "CAMBIO RADICAL",
  "miniatura_banner": "PARA LOS 12 SIGNOS",
  "signos": [
    {{"nombre": "Aries", "simbolo": "♈", "titulo_cap": "Fuego Interior", "guion": "Aries, hoy la energía...", "visual_prompt": "masterpiece, radiant cosmic flames, volumetric lighting, 8k"}},
    {{"nombre": "Tauro", "simbolo": "♉", "titulo_cap": "Abundancia Terrenal", "guion": "Tauro, hoy la tierra...", "visual_prompt": "masterpiece, enchanted forest, golden sunlight, 8k"}},
    {{"nombre": "Géminis", "simbolo": "♊", "titulo_cap": "Mente Estelar", "guion": "Géminis, tu mente...", "visual_prompt": "masterpiece, aurora borealis, electric cyan, 8k"}},
    {{"nombre": "Cáncer", "simbolo": "♋", "titulo_cap": "Marea Emocional", "guion": "Cáncer, tu intuición...", "visual_prompt": "masterpiece, mystical ocean, bioluminescent, 8k"}},
    {{"nombre": "Leo", "simbolo": "♌", "titulo_cap": "Brillo Real", "guion": "Leo, tu carisma...", "visual_prompt": "masterpiece, golden sunset, vibrant, 8k"}},
    {{"nombre": "Virgo", "simbolo": "♍", "titulo_cap": "Perfección Práctica", "guion": "Virgo, el orden...", "visual_prompt": "masterpiece, morning dew, emerald, 8k"}},
    {{"nombre": "Libra", "simbolo": "♎", "titulo_cap": "Equilibrio Divino", "guion": "Libra, el equilibrio...", "visual_prompt": "masterpiece, pink sunset clouds, 8k"}},
    {{"nombre": "Escorpio", "simbolo": "♏", "titulo_cap": "Transformación Profunda", "guion": "Escorpio, tu intensidad...", "visual_prompt": "masterpiece, deep ocean, mystical, 8k"}},
    {{"nombre": "Sagitario", "simbolo": "♐", "titulo_cap": "Libertad Cósmica", "guion": "Sagitario, tu libertad...", "visual_prompt": "masterpiece, mountain peak, sunrise, 8k"}},
    {{"nombre": "Capricornio", "simbolo": "♑", "titulo_cap": "Cimientos Sólidos", "guion": "Capricornio, tu disciplina...", "visual_prompt": "masterpiece, stone architecture, golden, 8k"}},
    {{"nombre": "Acuario", "simbolo": "♒", "titulo_cap": "Visión Futurista", "guion": "Acuario, tu originalidad...", "visual_prompt": "masterpiece, aurora borealis, electric, 8k"}},
    {{"nombre": "Piscis", "simbolo": "♓", "titulo_cap": "Sueños Proféticos", "guion": "Piscis, tu sensibilidad...", "visual_prompt": "masterpiece, underwater coral, vibrant, 8k"}}
  ]
}}
"""

def construir_prompt(modo, fecha, fase_lunar):
    modo_label = {"daily": "DIARIO", "weekly": "SEMANAL", "monthly": "MENSUAL"}[modo]
    palabras = {"daily": "90-110", "weekly": "150-180", "monthly": "250-300"}[modo]
    prompt = PROMPT_BASE.format(fecha=fecha, fase_lunar=fase_lunar, modo=modo_label)
    prompt = prompt.replace("90-110 palabras (daily), 150-180 (weekly), 250-300 (monthly)", f"{palabras} palabras")
    return prompt

def llamar_deepseek(fecha, fase_lunar, modo="daily"):
    prompt = construir_prompt(modo, fecha, fase_lunar)
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}],
               "temperature": 0.95, "response_format": {"type": "json_object"}}
    
    for i in range(3):
        try:
            print(f"    Intento {i+1}/3 con DeepSeek (modo {modo})...")
            r = requests.post("https://api.deepseek.com/v1/chat/completions",
                              headers=headers, json=payload, timeout=180)
            r.raise_for_status()
            datos = parsear_json(r.json()["choices"][0]["message"]["content"].strip())
            
            if len(datos.get("signos", [])) != 12:
                raise ValueError(f"La IA generó {len(datos.get('signos', []))} signos (esperados 12)")
            
            # Compatibilidad con formato viejo
            if "titulos" not in datos and "titulo" in datos:
                datos["titulos"] = [{"texto": datos["titulo"], "estructura": "legacy"}]
            
            if not datos.get("titulos"):
                raise ValueError("Faltan títulos")
            
            # Elegir mejor título
            datos["titulo"] = seleccionar_mejor_titulo(datos["titulos"])
            print(f"   🏆 Título elegido: {datos['titulo']} ({len(datos['titulo'])} chars)")
            
            # Componer descripción 3 capas
            partes = []
            if datos.get("descripcion_hook_125"):
                partes.append(datos["descripcion_hook_125"][:125])
            if datos.get("descripcion_keywords"):
                partes.append(datos["descripcion_keywords"])
            datos["descripcion_base"] = "\n\n".join(partes)
            
            # Detectar tema
            if datos.get("tema") not in ["dinero", "amor", "alerta", "general"]:
                texto = (datos["descripcion_base"] + " " + " ".join(s.get("guion","") for s in datos["signos"])).lower()
                if any(w in texto for w in ["dinero", "abundancia", "prosperidad"]):
                    datos["tema"] = "dinero"
                elif any(w in texto for w in ["amor", "pareja", "alma gemela"]):
                    datos["tema"] = "amor"
                elif any(w in texto for w in ["alerta", "cuidado", "no ignores"]):
                    datos["tema"] = "alerta"
                else:
                    datos["tema"] = "general"
            
            return datos
        except Exception as e:
            print(f"⚠️ DeepSeek intento {i+1} falló: {e}")
            time.sleep(3)
    raise Exception("Fallo DeepSeek tras 3 intentos")

# ================================================================
# 4. IMÁGENES (backoff exponencial)
# ================================================================
def generar_cf(prompt, ruta):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    clean_prompt = re.sub(r'[^a-zA-Z\s]', ' ', prompt)[:150]
    clean_prompt = ' '.join(clean_prompt.split())
    payload = {"prompt": clean_prompt, "steps": 4}
    
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        print(f"   ❌ Cloudflare HTTP {r.status_code}")
    r.raise_for_status()
    
    result = r.json()
    if "result" not in result or "image" not in result["result"]:
        raise ValueError("Sin imagen")
    
    with open(ruta, "wb") as f:
        f.write(base64.b64decode(result["result"]["image"]))
    with Image.open(ruta) as im:
        im = ImageOps.fit(im.convert("RGB"), (W, H), Image.LANCZOS)
        im.save(ruta, "JPEG", quality=95)
    return ruta

def generar_pexels(query, ruta):
    headers = {"Authorization": PEXELS_API_KEY}
    r = requests.get("https://api.pexels.com/v1/search", headers=headers,
                     params={"query": query, "orientation": "landscape", "size": "large", "per_page": 5},
                     timeout=15)
    r.raise_for_status()
    fotos = r.json().get("photos", [])
    if not fotos:
        raise Exception("Sin Pexels")
    with requests.get(fotos[0]["src"]["large2x"], stream=True, timeout=15) as r_img:
        with open(ruta, "wb") as f:
            for chunk in r_img.iter_content(8192):
                f.write(chunk)
    with Image.open(ruta) as im:
        im = ImageOps.fit(im.convert("RGB"), (W, H), Image.LANCZOS)
        im.save(ruta, "JPEG", quality=95)
    return ruta

def obtener_imagen_segura(prompt, ruta, es_miniatura=False):
    delays = [5, 15]
    for i, delay in enumerate(delays, start=1):
        try:
            print(f"   ☁️ CF Intento {i}/{len(delays)}...")
            return generar_cf(prompt, ruta)
        except Exception as e:
            print(f"   ⚠️ CF intento {i} falló: {e}")
            if i < len(delays):
                print(f"   ⏳ Esperando {delay}s...")
                time.sleep(delay)
    
    print("   ⚠️ CF agotado, usando Pexels...")
    try:
        query = prompt + " bright vibrant mystical" if es_miniatura else prompt + " vivid cinematic"
        return generar_pexels(query, ruta)
    except Exception as e:
        print(f"   ❌ Pexels falló: {e}")
        return None

# ================================================================
# 5. AUDIO (voz por modo)
# ================================================================
async def generar_audio(texto, ruta, modo="daily"):
    max_retries = 3
    rate = VOZ_RATE_POR_MODO.get(modo, "-4%")
    
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(texto, VOZ_CANAL, rate=rate)
            await communicate.save(ruta)
            if os.path.exists(ruta) and os.path.getsize(ruta) > 500:
                return True
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
    
    print("   ⚠️ Edge TTS falló, usando gTTS...")
    try:
        tts = gTTS(text=texto, lang='es', slow=False)
        tts.save(ruta)
        if os.path.exists(ruta) and os.path.getsize(ruta) > 500:
            return True
        raise Exception("gTTS vacío")
    except Exception as e:
        raise Exception(f"Fallo TTS: {str(e)}")

def render_texto_gradiente_8k(texto, font_path, size):
    font = ImageFont.truetype(font_path, size)
    b = font.getbbox(texto)
    w, h = (b[2] - b[0]) + 40, (b[3] - b[1]) + 40
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    cx, cy = 20 - b[0], 20 - b[1]
    d.text((cx, cy), texto, font=font, fill=(0, 0, 0), stroke_width=16, stroke_fill=(255, 255, 255))
    d.text((cx, cy), texto, font=font, fill=(128, 0, 128), stroke_width=10, stroke_fill=(128, 0, 128))
    d.text((cx, cy), texto, font=font, fill=(255, 255, 0))
    glow = out.filter(ImageFilter.GaussianBlur(radius=6))
    return Image.alpha_composite(glow, out)

def render_banner_grafico(texto, font_path, size):
    font = ImageFont.truetype(font_path, size)
    b = font.getbbox(texto)
    w, h = (b[2] - b[0]) + 60, (b[3] - b[1]) + 30
    img = Image.new("RGBA", (w + 20, h + 20), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([10, 14, w + 10, h + 14], radius=16, fill=(0, 0, 0, 180))
    d.rounded_rectangle([10, 10, w + 10, h + 10], radius=16, fill=(220, 20, 60, 255))
    d.rounded_rectangle([10, 10, w + 10, h + 10], radius=16, outline=(255, 255, 255, 255), width=4)
    d.text((10 + 30 - b[0], 10 + 15 - b[1]), texto, font=font, fill=(255, 255, 255, 255))
    return img

def crear_miniatura_8k_elite(img_path, texto_principal, texto_banner, salida):
    try:
        img = Image.open(img_path).convert("RGB").resize((1280, 720))
        img = ImageEnhance.Brightness(img).enhance(1.15)
        img = ImageEnhance.Contrast(img).enhance(1.2)
        img = ImageEnhance.Color(img).enhance(1.6)
        img = img.convert("RGBA")
        fuente = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        
        palabras = texto_principal.upper().split()
        if len(palabras) > 3:
            texto_principal = " ".join(palabras[:3])
        
        size = 130
        while size > 60:
            bloque1 = render_texto_gradiente_8k(texto_principal, fuente, size)
            if bloque1.width < 1100:
                break
            size -= 10
        
        bloque1 = bloque1.rotate(3, expand=True, resample=Image.BICUBIC)
        x1 = (1280 - bloque1.width) // 2
        y1 = (720 - bloque1.height) // 2 - 60
        
        bloque2 = render_banner_grafico(texto_banner, fuente, 50)
        bloque2 = bloque2.rotate(-2, expand=True, resample=Image.BICUBIC)
        x2 = (1280 - bloque2.width) // 2
        y2 = y1 + bloque1.height + 30
        
        img.paste(bloque1, (x1, y1), bloque1)
        img.paste(bloque2, (x2, y2), bloque2)
        img.convert("RGB").save(salida, "JPEG", quality=95)
        print(f"✅ Miniatura generada: '{texto_principal}'")
        return True
    except Exception as e:
        print(f"⚠️ Error miniatura: {e}")
        return False

# ================================================================
# 6. RENDER DE VIDEO (con INTRO_DUR al inicio)
# ================================================================
_VIG = {}
def vignette(size, base=1.0, fuerza=0.4):
    k = (size, base)
    if k not in _VIG:
        w, h = size
        y, x = np.ogrid[-1:1:h * 1j, -1:1:w * 1j]
        d = np.clip(np.sqrt(x ** 2 + y ** 2) / 1.414, 0, 1)
        _VIG[k] = ((1 - fuerza * d ** 2.2) * base).astype(np.float32)[..., None]
    return _VIG[k]

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
            im = ImageEnhance.Color(im).enhance(1.25)
            im = ImageEnhance.Contrast(im).enhance(1.2)
            arr = np.asarray(im, dtype=np.float32) * vignette(sz, 1.0)
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

def renderizar_video(signos_data, salida, modo="daily"):
    escenas, t_total = [], INTRO_DUR  # ✅ empieza en INTRO_DUR (2s)
    clips_abiertos = []
    
    try:
        for i, signo in enumerate(signos_data):
            img_path = f"temp_signo_{i}.jpg"
            audio_path = f"temp_audio_{i}.mp3"
            if not os.path.exists(img_path) or not os.path.exists(audio_path):
                continue
            
            audio_clip = AudioFileClip(audio_path)
            clips_abiertos.append(audio_clip)
            dur = audio_clip.duration + 0.5
            
            img = Image.open(img_path).convert("RGB").resize((W, H))
            draw = ImageDraw.Draw(img)
            try:
                font_t = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 110)
                font_s = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
            except:
                font_t = font_s = ImageFont.load_default()
            
            draw.text((W//2, 250), f"{signo['simbolo']} {signo['nombre']}", font=font_t,
                      fill=(255, 255, 255), anchor="mm", stroke_width=10, stroke_fill=(0, 0, 0))
            mantra = signo['guion'].split('.')[-1].strip()[:60]
            draw.text((W//2, 850), mantra, font=font_s, fill=(255, 215, 0), anchor="mm",
                      stroke_width=8, stroke_fill=(0, 0, 0))
            img.save(f"temp_frame_{i}.jpg")
            
            escenas.append({
                "path": f"temp_frame_{i}.jpg", "inicio": t_total, "dur": dur,
                "etapa": "mystic", "fade": i == 0, "zin": i % 2 == 0,
                "ax": random.uniform(-1, 1), "ay": random.uniform(-1, 1)
            })
            t_total += dur
        
        if not escenas:
            raise Exception("No hay escenas para renderizar")
        
        render = RenderEscenas(escenas, (W, H), t_total)
        video = VideoClip(render.frame, duration=t_total)
        
        # Audio: narración retrasada por INTRO_DUR, música desde t=0
        clips_audio = [c.set_start(INTRO_DUR + e["inicio"]) for c, e in zip(clips_abiertos, escenas)]
        
        musica_elegida = MUSICA_POR_MODO.get(modo)
        if not musica_elegida or not os.path.exists(musica_elegida):
            musicas = [f for f in os.listdir(".") if f.lower().endswith(".mp3") and not f.startswith("temp_")]
            musica_elegida = random.choice(musicas) if musicas else None
        
        if musica_elegida:
            try:
                bg = AudioFileClip(musica_elegida)
                clips_abiertos.append(bg)
                if bg.duration <= 0:
                    print(f"⚠️ Música {musica_elegida} inválida")
                else:
                    if bg.duration < t_total:
                        bg = concatenate_audioclips([bg] * (int(t_total / bg.duration) + 1))
                    clips_audio.append(bg.subclip(0, t_total).volumex(0.10).audio_fadein(2).audio_fadeout(3))
                    print(f"🎵 Música: {musica_elegida} (vol 10%)")
            except Exception as e:
                print(f"⚠️ Error música: {e}")
        
        video = video.set_audio(CompositeAudioClip(clips_audio))
        print(f"🎬 Renderizando... (intro {INTRO_DUR}s + {len(escenas)} signos)")
        video.write_videofile(salida, fps=FPS, codec="libx264", audio_codec="aac",
                              threads=4, preset="ultrafast", logger=None)
        return salida
    finally:
        for clip in clips_abiertos:
            try:
                clip.close()
            except:
                pass

# ================================================================
# 7. SUBIDA A YOUTUBE
# ================================================================
def obtener_credenciales_youtube():
    yt_token = json.loads(YT_TOKEN_STR)
    creds = Credentials(token=yt_token.get("token"), refresh_token=yt_token.get("refresh_token"),
                        token_uri=yt_token.get("token_uri"), client_id=yt_token.get("client_id"),
                        client_secret=yt_token.get("client_secret"), scopes=yt_token.get("scopes"))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds

def subir_a_youtube(ruta_video, ruta_miniatura, datos, hora_utc, modo="daily"):
    youtube = build("youtube", "v3", credentials=obtener_credenciales_youtube())
    
    # Capítulos (usando duraciones reales sin abrir clips)
    tiempo_acumulado = INTRO_DUR
    caps = []
    for i, s in enumerate(datos["signos"]):
        audio_path = f"temp_audio_{i}.mp3"
        duracion_real = 35.0
        if os.path.exists(audio_path):
            try:
                clip = AudioFileClip(audio_path)
                duracion_real = clip.duration
                clip.close()
            except:
                pass
        mins = int(tiempo_acumulado // 60)
        secs = int(tiempo_acumulado % 60)
        caps.append(f"{mins:02d}:{secs:02d} {s['simbolo']} {s['nombre']}: {s['titulo_cap']}")
        tiempo_acumulado += duracion_real + 0.5
    
    tema = datos.get("tema", "general")
    hashtags = construir_hashtags(tema)
    
    desc = datos.get("descripcion_base", datos.get("descripcion", ""))
    desc += f"\n\n⏰ CAPÍTULOS:\n" + "\n".join(caps)
    desc += f"\n\n🔔 Suscríbete: {CANAL_LINK}"
    desc += f"\n\n{hashtags}"
    
    tags_finales = construir_tags_finales(datos.get("tags", []), modo)
    
    # Validar título
    titulo = datos["titulo"][:100] if len(datos["titulo"]) > 100 else datos["titulo"]
    
    body = {
        "snippet": {
            "title": titulo, "description": desc[:5000], "tags": tags_finales,
            "categoryId": "22", "defaultLanguage": "es", "defaultAudioLanguage": "es"
        },
        "status": {
            "privacyStatus": "private", "publishAt": hora_utc,
            "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True
        }
    }
    
    media = MediaFileUpload(ruta_video, chunksize=4*1024*1024, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    resp, reintentos = None, 0
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st:
                print(f"   ⬆️ {int(st.progress() * 100)}%")
        except Exception as e:
            if reintentos < 8:
                reintentos += 1
                print(f"⚠️ Reintentando ({reintentos}/8)...")
                time.sleep(2 ** reintentos)
            else:
                raise e
    
    video_id = resp["id"]
    print(f"✅ Video subido. ID: {video_id}")
    
    if ruta_miniatura and os.path.exists(ruta_miniatura):
        try:
            youtube.thumbnails().set(videoId=video_id,
                                     media_body=MediaFileUpload(ruta_miniatura)).execute()
            print("✅ Miniatura aplicada.")
        except HttpError as e:
            print(f"⚠️ Error miniatura: {e}")
    
    if datos.get("comentario_fijado"):
        try:
            youtube.commentThreads().insert(part="snippet", body={
                "snippet": {"videoId": video_id,
                            "topLevelComment": {"snippet": {"textOriginal": datos["comentario_fijado"]}}}
            }).execute()
            print("✅ Comentario publicado")
        except HttpError:
            print("⚠️ Error comentario")
    
    return video_id

# ================================================================
# 8. SCHEDULING INTELIGENTE
# ================================================================
def calcular_hora_publicacion(ahora, tipo):
    """Ventana amplia: si ya pasó la hora óptima, publica +2h del mismo día, no mañana."""
    if tipo == "monthly":
        base = ahora.replace(hour=12, minute=0, second=0, microsecond=0)
        if ahora >= base:
            base = ahora + timedelta(hours=2)
        return base.replace(minute=random.randint(0, 10))
    
    if tipo == "weekly":
        # Ventana 9 AM - 3 PM
        inicio = ahora.replace(hour=9, minute=0, second=0, microsecond=0)
        fin = ahora.replace(hour=15, minute=0, second=0, microsecond=0)
        if ahora >= fin:
            # Si ya pasó, programar 9 AM del día siguiente
            inicio += timedelta(days=1)
            return inicio.replace(minute=random.randint(0, 50))
        if ahora < inicio:
            return inicio.replace(minute=random.randint(0, 50))
        return ahora + timedelta(minutes=random.randint(5, 40))
    
    # daily: ventana 5 AM - 12 PM
    inicio = ahora.replace(hour=5, minute=0, second=0, microsecond=0)
    fin = ahora.replace(hour=12, minute=0, second=0, microsecond=0)
    if ahora >= fin:
        # Si ya pasó, programar +2h mismo día si es antes de las 6pm, sino mañana 5am
        candidato = ahora + timedelta(hours=2)
        if candidato.hour < 18:
            return candidato
        return (ahora + timedelta(days=1)).replace(hour=5, minute=random.randint(0, 55), second=0, microsecond=0)
    if ahora < inicio:
        return inicio.replace(minute=random.randint(0, 55))
    return ahora + timedelta(minutes=random.randint(5, 40))

# ================================================================
# 9. MAIN
# ================================================================
def main():
    try:
        ahora = datetime.now(TZ)
        dia_semana = ahora.weekday()
        dia_mes = ahora.day
        
        # Calendario automático
        if dia_mes == 1:
            tipo = "monthly"
            print(f"📅 Día 1 del mes → MENSUAL")
        elif dia_semana == 0:
            tipo = "weekly"
            print(f"📅 Lunes → SEMANAL")
        else:
            tipo = "daily"
            print(f"📅 Día normal → DIARIO")
        
        print(f"🤖 Modo: {tipo.upper()}")
        
        hora_final = calcular_hora_publicacion(ahora, tipo)
        hora_utc = hora_final.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print(f"🎯 Programado: {hora_final:%d-%m-%Y %H:%M} (CDMX)")
        
        fecha_hoy = datetime.now(TZ).strftime("%d de %B de %Y")
        fase_lunar = "Creciente"
        
        print(f"🧠 1. Generando contenido SEO con DeepSeek...")
        datos = llamar_deepseek(fecha_hoy, fase_lunar, tipo)
        
        # Deduplicación (ahora sí funciona porque el archivo se persiste)
        if titulo_ya_publicado(datos["titulo"]):
            print("⚠️ Título repetido. Regenerando...")
            datos = llamar_deepseek(fecha_hoy, fase_lunar, tipo)
        
        print("🎨 2. Generando activos...")
        for i, signo in enumerate(datos["signos"]):
            print(f"   Procesando {signo['nombre']}...")
            obtener_imagen_segura(signo.get("visual_prompt", "masterpiece, mystical galaxy, 8k"),
                                  f"temp_signo_{i}.jpg")
            guion_con_nombre = f"{signo['nombre']}. {signo['guion']}"
            asyncio.run(generar_audio(guion_con_nombre, f"temp_audio_{i}.mp3", tipo))
        
        print("🖼️ 3. Creando miniatura...")
        obtener_imagen_segura(datos.get("miniatura_prompt", "masterpiece, radiant cosmic energy, 8k"),
                              "temp_bg_thumb.jpg", es_miniatura=True)
        
        texto_miniatura = datos.get("miniatura_texto", "CAMBIO RADICAL")
        banner_miniatura = datos.get("miniatura_banner", "PARA LOS 12 SIGNOS")
        print(f"   📝 Miniatura: '{texto_miniatura}' | '{banner_miniatura}'")
        
        crear_miniatura_8k_elite("temp_bg_thumb.jpg", texto_miniatura, banner_miniatura, "miniatura.jpg")
        
        print("🎬 4. Renderizando video...")
        renderizar_video(datos["signos"], "video_final.mp4", tipo)
        
        print("📤 5. Subiendo a YouTube...")
        video_id = subir_a_youtube("video_final.mp4", "miniatura.jpg", datos, hora_utc, tipo)
        
        print(f"✨ ¡COMPLETADO! Programado para {hora_final:%H:%M}")
        
        # Persistencia (FIX CRÍTICO)
        guardar_titulo(datos["titulo"])
        hacer_commit_titulos()
        
        # Cleanup
        for f in os.listdir():
            if f.startswith("temp_") or f in ["video_final.mp4", "miniatura.jpg"]:
                try:
                    os.remove(f)
                except:
                    pass
    
    except Exception as e:
        print(f"❌ ERROR FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
