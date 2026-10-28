# -*- coding: utf-8 -*-
"""
BT_YT_SHORTS_CLO_HY - Bot Shorts Horóscopo (Tu Cielo Hoy) - VERSIÓN PREMIUM ELITE 2026
============================================================================
NOVEDADES vs versión anterior:
- INTRO de 2s con música + micro-zoom (antes de la narración)
- Voz fija por elemento (fuego/tierra/aire/agua)
- Música por elemento + volumen 12% (antes 8% random)
- 5 títulos candidatos con scorer local (longitud, signo, trigger, emoji)
- Descripción en 3 capas (hook 125 + keywords + CTA)
- Hook rotado (5 estructuras con información-gap)
- Tags reducidos a 10-12 hiper-específicos
- Hashtags rotados por tema (dinero/amor/alerta/general)
- Intro teaser de 2-3 palabras en los 2 primeros segundos
- Scheduling inteligente (nunca programa a las 2 AM)
- Fix PLACEHOLDER (no inyecta URL rota si no hay video largo)
- Fix Image.open por frame (carga una sola vez)
- Fix _VIG (viñeta cacheada)
- Cloudflare con backoff exponencial
- Fix bg.duration == 0
"""
import asyncio, base64, json, os, random, re, ssl, socket, sys, time, traceback, unicodedata, subprocess
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
MAX_SHORTS_DIARIOS = 3
INTRO_DUR = 2.0  # segundos de música antes de la narración

# Voz + rate por elemento (consistencia de marca)
VOICE_CONFIG = {
    "fuego": ("es-MX-DaliaNeural", "+2%"),
    "tierra": ("es-AR-ElenaNeural", "-2%"),
    "aire": ("es-CO-SalomeNeural", "+0%"),
    "agua": ("es-ES-ElviraNeural", "-4%"),
}

# Música por elemento (fallback a cualquier mp3 si no existe)
MUSIC_BY_ELEMENT = {
    "fuego": "Astral Zenith.mp3",
    "tierra": "Sylvan Sanctuary.mp3",
    "aire": "Celestial Drift.mp3",
    "agua": "Verdant Stream.mp3",
}

ESTADO_FILE = "estado_shorts.json"
W_SHORT, H_SHORT, FPS = 1080, 1920, 24

SIGNOS_COLA = [
    {"nombre": "Aries", "simbolo": "♈", "elemento": "fuego"},
    {"nombre": "Tauro", "simbolo": "♉", "elemento": "tierra"},
    {"nombre": "Géminis", "simbolo": "♊", "elemento": "aire"},
    {"nombre": "Cáncer", "simbolo": "♋", "elemento": "agua"},
    {"nombre": "Leo", "simbolo": "♌", "elemento": "fuego"},
    {"nombre": "Virgo", "simbolo": "♍", "elemento": "tierra"},
    {"nombre": "Libra", "simbolo": "♎", "elemento": "aire"},
    {"nombre": "Escorpio", "simbolo": "♏", "elemento": "agua"},
    {"nombre": "Sagitario", "simbolo": "♐", "elemento": "fuego"},
    {"nombre": "Capricornio", "simbolo": "♑", "elemento": "tierra"},
    {"nombre": "Acuario", "simbolo": "♒", "elemento": "aire"},
    {"nombre": "Piscis", "simbolo": "♓", "elemento": "agua"}
]

PROMPTS_IMAGEN_ELEMENTO = {
    "fuego": "vertical masterpiece, intense cosmic flames and golden embers, dramatic volumetric lighting, vibrant red and orange color grading, mystical fire energy, hyper-detailed, 8k resolution, cinematic composition, trending on ArtStation, no text, no watermark",
    "tierra": "vertical masterpiece, lush enchanted forest with radiant golden sunlight beams, vibrant emerald and gold color palette, magical glowing crystals and ancient plants, hyper-detailed, 8k resolution, cinematic composition, trending on ArtStation, no text, no watermark",
    "aire": "vertical masterpiece, swirling ethereal aurora borealis with electric cyan and silver, cosmic wind energy, vibrant sky with shooting stars, hyper-detailed, 8k resolution, cinematic composition, trending on ArtStation, no text, no watermark",
    "agua": "vertical masterpiece, deep mystical ocean with bioluminescent glowing creatures, vibrant turquoise and deep purple color grading, magical underwater light rays, hyper-detailed, 8k resolution, cinematic composition, trending on ArtStation, no text, no watermark"
}

ELEMENT_STYLES = {
    "fuego": {"text_color": (255, 120, 0), "stroke_color": (255, 255, 0), "mantra_color": (255, 215, 0)},
    "tierra": {"text_color": (0, 180, 50), "stroke_color": (255, 215, 0), "mantra_color": (255, 255, 255)},
    "aire": {"text_color": (0, 220, 255), "stroke_color": (255, 255, 255), "mantra_color": (192, 192, 192)},
    "agua": {"text_color": (138, 43, 226), "stroke_color": (0, 255, 255), "mantra_color": (0, 255, 255)}
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

def construir_tags_shorts_premium(signo, tema="general"):
    """Tags hiper-específicos (10-12) enfocados en búsqueda exacta."""
    signo_norm = normalizar_ascii(signo["nombre"])
    
    tags = [
        f"horoscopo {signo_norm} hoy",
        f"{signo_norm} hoy",
        f"prediccion {signo_norm}",
        f"horoscopo diario para {signo_norm}",
        f"mensaje del universo {signo_norm}",
        f"astrologia {signo_norm}",
        f"{signo_norm} {tema}" if tema != "general" else f"{signo_norm} diario",
        f"que le espera a {signo_norm} hoy",
        "señales del universo",
        "shorts horoscopo",
        f"{signo_norm} 2026",
    ]
    
    result, total = [], 0
    for tag in tags:
        clean = re.sub(r'[^a-z0-9\sáéíóúñ]', '', tag.lower()).strip()
        if 3 <= len(clean) <= 30 and clean not in result:
            if total + len(clean) + 1 <= 480:
                result.append(clean)
                total += len(clean) + 1
    
    print(f"   🏷️ Tags: {len(result)} tags, {total}/480 chars")
    return result

def construir_hashtags(signo, tema="general"):
    """Hashtags rotados por tema (3-5 máximo)."""
    signo_norm = normalizar_ascii(signo["nombre"])
    especifico = HASHTAGS_BY_THEME.get(tema, HASHTAGS_BY_THEME["general"])
    return f"#{signo_norm} #horoscopo #astrologia #shorts {especifico}"

def detectar_tema(datos):
    """Devuelve el tema: dinero|amor|alerta|general."""
    tema = datos.get("tema")
    if tema in ["dinero", "amor", "alerta", "general"]:
        return tema
    texto = (datos.get("guion", "") + " " + datos.get("titulo", "")).lower()
    if any(w in texto for w in ["dinero", "riqueza", "abundancia", "financiero", "económica", "prosperidad"]):
        return "dinero"
    if any(w in texto for w in ["amor", "corazón", "pareja", "alma gemela", "romance"]):
        return "amor"
    if any(w in texto for w in ["alerta", "cuidado", "advertencia", "peligro", "no ignores"]):
        return "alerta"
    return "general"

def obtener_musica(elemento):
    """Devuelve la ruta de la música por elemento, con fallback al pool."""
    preferida = MUSIC_BY_ELEMENT.get(elemento)
    if preferida and os.path.exists(preferida):
        return preferida
    musicas = [f for f in os.listdir(".") if f.lower().endswith(".mp3") and not f.startswith("temp_")]
    return random.choice(musicas) if musicas else None

print("=" * 70)
print("📱 BT_YT_SHORTS_CLO_HY - ELITE 2026 (2s intro + voz/música por elemento)")
print(f"📅 {datetime.now(TZ):%Y-%m-%d %H:%M} (CDMX)")
print("=" * 70)

if not all([DEEPSEEK_API_KEY, PEXELS_API_KEY, CF_ACCOUNT_ID, CF_API_TOKEN, YT_TOKEN_STR]):
    print("❌ ERROR: Faltan variables de entorno.")
    sys.exit(1)

# ================================================================
# 2. ESTADO DEL BOT
# ================================================================
def cargar_estado():
    try:
        with open(ESTADO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            hoy = datetime.now(TZ).strftime("%Y-%m-%d")
            if data.get("fecha") != hoy:
                print(f"🔄 Nuevo día detectado. Índice: {data.get('indice', 0)}.")
                data["fecha"] = hoy
                data["publicados_hoy"] = []
                return data
            return data
    except:
        return {"fecha": datetime.now(TZ).strftime("%Y-%m-%d"), "indice": 0, "publicados_hoy": []}

def guardar_estado(data):
    with open(ESTADO_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(ESTADO_FILE + ".tmp", ESTADO_FILE)

def hacer_commit_estado():
    if not GITHUB_TOKEN:
        return False
    try:
        subprocess.run(["git", "config", "user.name", "bot-shorts"], check=False, capture_output=True)
        subprocess.run(["git", "config", "user.email", "bot@tucielhoy.com"], check=False, capture_output=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False, capture_output=True)
        subprocess.run(["git", "add", ESTADO_FILE], check=False, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"Update {datetime.now(TZ).strftime('%H:%M')}"], check=False, capture_output=True)
        remote_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{REPO_NAME}.git"
        result = subprocess.run(["git", "push", remote_url, "HEAD:main"], check=False, capture_output=True, text=True)
        return result.returncode == 0
    except Exception as e:
        print(f"⚠️ Error commit: {e}")
        return False

def elegir_siguiente_signo(estado):
    indice = estado.get("indice", 0)
    publicados_hoy = estado.get("publicados_hoy", [])
    
    if len(publicados_hoy) >= 12:
        print("🔄 Ciclo de 12 signos completado. Reiniciando...")
        indice = 0
        publicados_hoy = []
    
    signo = SIGNOS_COLA[indice % 12]
    
    if signo["nombre"] in publicados_hoy:
        print(f"⚠️ {signo['nombre']} ya fue publicado. Buscando siguiente disponible...")
        for i in range(1, 12):
            candidato = SIGNOS_COLA[(indice + i) % 12]
            if candidato["nombre"] not in publicados_hoy:
                signo = candidato
                indice = (indice + i) % 12
                print(f"✅ Signo seleccionado: {signo['nombre']} (índice {indice})")
                break
    
    estado["indice"] = (indice + 1) % 12
    if signo["nombre"] not in publicados_hoy:
        publicados_hoy.append(signo["nombre"])
    estado["publicados_hoy"] = publicados_hoy
    
    return signo

# ================================================================
# 3. YOUTUBE & DEEPSEEK
# ================================================================
def obtener_credenciales_youtube():
    yt_token = json.loads(YT_TOKEN_STR)
    creds = Credentials(token=yt_token.get("token"), refresh_token=yt_token.get("refresh_token"),
                        token_uri=yt_token.get("token_uri"), client_id=yt_token.get("client_id"),
                        client_secret=yt_token.get("client_secret"), scopes=yt_token.get("scopes"))
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
    return creds

def buscar_ultimo_video_largo():
    try:
        youtube = build("youtube", "v3", credentials=obtener_credenciales_youtube())
        response = youtube.search().list(part="snippet", forMine=True, type="video", maxResults=5, order="date").execute()
        for item in response.get("items", []):
            stats = youtube.videos().list(part="contentDetails", id=item["id"]["videoId"]).execute()
            if stats.get("items") and "M" in stats["items"][0]["contentDetails"]["duration"]:
                return item["id"]["videoId"]
        return None
    except:
        return None

PROMPT_SHORT_SEO = """
Eres EXPERTA EN SEO Viral para YouTube Shorts (Nivel VidIQ 80+). Tono: femenino, cálido, místico, PERSUASIVO.
Fecha: {fecha}. Signo: {signo} ({simbolo}). Elemento: {elemento}.

REGLAS OBLIGATORIAS:

1. TÍTULOS — Genera EXACTAMENTE 5 títulos candidatos con estas estructuras DIFERENTES:
   - estructura "alerta_especificidad": "[Signo] ⚠️ ALERTA: esto cambia HOY"
   - estructura "curiosidad_negativa": "Nadie te dijo esto sobre [Signo] HOY"
   - estructura "numero_promesa": "[Signo]: 3 señales que el universo da HOY 🔮"
   - estructura "identificacion": "¿Eres [Signo]? El universo te avisa esto 💰"
   - estructura "temporalidad": "Si eres [Signo], lee esto antes de la 1 PM ⚠️"
   
   Cada título DEBE cumplir:
   - Entre 52 y 62 caracteres
   - Empezar con el nombre del signo en los primeros 15 chars
   - Incluir UN emoji de: 💰 🔮 ✨ 💕 🔥 ⚠️ 🌟
   - NO tener hashtags

2. INTRO TEASER (2-3 palabras para los 2 primeros segundos del video):
   Opciones: "DINERO HOY", "ALERTA HOY", "AMOR HOY", "CAMBIO HOY", "SEÑAL HOY", "VERDAD HOY", "SUERTE HOY", "DESTINO HOY"

3. TEMA (elige UNO): "dinero" | "amor" | "alerta" | "general"

4. DESCRIPCIÓN EN 3 CAPAS:
   - descripcion_hook_125: Los primeros 125 caracteres (preview). Hook emocional fuerte y específico. Menciona al signo.
   - descripcion_keywords: Párrafo de 300-500 chars con keywords naturales (señales del universo, mensaje astral, predicción, horóscopo, energía).

5. GUION (75-95 palabras = 30-35 segundos):
   - HOOK (3-4s / 8-12 palabras): UNA de estas 5 estructuras rotadas:
     * "Nadie te dijo esto, {signo}, pero tu [área] está a punto de cambiar."
     * "{signo}, tienes hasta [día] para aprovechar esta energía."
     * "{signo}, el universo te da 3 señales HOY. La tercera es la clave."
     * "Si eres {signo} y estás viendo esto, no es casualidad."
     * "{signo}, esta semana NO es como las demás. Te explico."
   - CONTEXTO (5s): por qué HOY es especial
   - CUERPO AMOR (7s): revelación específica sobre amor
   - CUERPO DINERO (7s): revelación específica sobre dinero
   - MANTRA (4s): frase ÚNICA de 5-7 palabras para hoy (NO "atraigo abundancia infinita")
   - CTA (4s): "Mira el video completo en mi canal para los 12 signos"

6. COMENTARIO FIJADO:
   - Pregunta persuasiva + "Decreta 'HECHO ESTÁ' y tu signo"

Responde SOLO JSON con este formato exacto (llaves dobles para escape):
{{
  "titulos": [
    {{"texto": "Leo ⚠️ ALERTA: esto cambia HOY", "estructura": "alerta_especificidad"}},
    {{"texto": "Nadie te dijo esto sobre Leo HOY", "estructura": "curiosidad_negativa"}},
    {{"texto": "Leo: 3 señales que el universo da HOY 🔮", "estructura": "numero_promesa"}},
    {{"texto": "¿Eres Leo? El universo te avisa esto 💰", "estructura": "identificacion"}},
    {{"texto": "Si eres Leo, lee esto antes de la 1 PM ⚠️", "estructura": "temporalidad"}}
  ],
  "intro_teaser": "DINERO HOY",
  "tema": "dinero",
  "descripcion_hook_125": "Leo, el universo tiene un mensaje urgente sobre tu dinero HOY. No ignores esta señal.",
  "descripcion_keywords": "En este short descubrirás la oportunidad financiera que llega antes del viernes, la advertencia sobre un gasto impulsivo, y el mantra específico para decretar abundancia. Ideal si buscas señales del universo, mensaje astral, o predicciones para Leo en amor y dinero.",
  "comentario_fijado": "¿Sientes esta energía, Leo? Decreta 'HECHO ESTÁ' y tu signo.",
  "guion": "Leo, esta semana NO es como las demás. Te explico. El cosmos alinea tu energía de fuego con una oportunidad que no ves desde hace meses. En el amor, alguien del pasado reaparece con intenciones claras. En lo financiero, una puerta inesperada se abre antes del jueves. Tu mantra: 'El universo conspira a mi favor'. Mira el video completo en mi canal.",
  "visual_prompt": "vertical mystical fuego energy"
}}
"""

def seleccionar_mejor_titulo(titulos, signo_nombre):
    """Scorer local: elige el título con mayor CTR predicho."""
    emojis = ["💰", "🔮", "✨", "💕", "🔥", "⚠️", "🌟"]
    triggers = ["HOY", "hoy", "Nadie", "Señal", "señal", "Alerta", "alerta", "Cambio", "cambio", "ya"]
    
    best_score, best_titulo = -1, ""
    
    for t in titulos:
        texto = t.get("texto", "") if isinstance(t, dict) else str(t)
        
        score = 0
        L = len(texto)
        # Longitud óptima (52-62)
        if 52 <= L <= 62:
            score += 30
        elif 45 <= L <= 68:
            score += 15
        # Signo en primeros 20 chars
        if signo_nombre.lower() in texto[:20].lower():
            score += 25
        # Trigger de urgencia
        if any(trig in texto for trig in triggers):
            score += 10
        # Emoji presente
        if any(e in texto for e in emojis):
            score += 15
        # Número en el título (estructura clara)
        if any(d in texto for d in "0123456789"):
            score += 5
        
        if score > best_score:
            best_score = score
            best_titulo = texto
    
    if not best_titulo:
        best_titulo = titulos[0].get("texto", "") if isinstance(titulos[0], dict) else str(titulos[0])
    
    # Truncar por si acaso
    if len(best_titulo) > 65:
        best_titulo = best_titulo[:62] + "..."
    
    return best_titulo

def llamar_deepseek_short(signo, fecha, video_largo_id=None):
    prompt = PROMPT_SHORT_SEO.format(
        fecha=fecha, signo=signo["nombre"], simbolo=signo["simbolo"],
        elemento=signo["elemento"]
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}],
               "temperature": 0.9, "response_format": {"type": "json_object"}}
    
    for i in range(3):
        try:
            print(f"    Intento {i+1}/3 con DeepSeek...")
            r = requests.post("https://api.deepseek.com/v1/chat/completions",
                              headers=headers, json=payload, timeout=90)
            r.raise_for_status()
            texto = r.json()["choices"][0]["message"]["content"].strip()
            t = re.sub(r"```(?:json)?", " ", texto, flags=re.I)
            i_json, j_json = t.find("{"), t.rfind("}")
            datos = json.loads(t[i_json:j_json + 1], strict=False)
            
            # Compatibilidad con formato viejo
            if "titulos" not in datos and "titulo" in datos:
                datos["titulos"] = [{"texto": datos["titulo"], "estructura": "legacy"}]
            
            # Validación mínima
            if not datos.get("titulos") or len(datos["titulos"]) < 1:
                raise ValueError("Faltan títulos")
            if not datos.get("guion") or len(datos["guion"].split()) < 50:
                raise ValueError("Guion inválido")
            
            # Elegir mejor título
            mejor_titulo = seleccionar_mejor_titulo(datos["titulos"], signo["nombre"])
            datos["titulo"] = mejor_titulo
            print(f"   🏆 Título elegido: {mejor_titulo} ({len(mejor_titulo)} chars)")
            
            palabras = len(datos["guion"].split())
            print(f"   📄 Guion: {palabras} palabras")
            
            # Componer descripción en 3 capas
            partes = []
            if datos.get("descripcion_hook_125"):
                partes.append(datos["descripcion_hook_125"][:125])
            if datos.get("descripcion_keywords"):
                partes.append(datos["descripcion_keywords"])
            
            # Solo añadir URL si hay video largo REAL
            if video_largo_id:
                partes.append(f"🎥 Video completo: https://www.youtube.com/watch?v={video_largo_id}")
            
            partes.append(f"🔔 Suscríbete: {CANAL_LINK}")
            datos["descripcion"] = "\n\n".join(partes)
            
            # Comentario
            comentario = datos.get("comentario_fijado", "")
            if video_largo_id and video_largo_id not in comentario:
                comentario += f"\nVideo completo: https://www.youtube.com/watch?v={video_largo_id}"
            datos["comentario_fijado"] = comentario
            
            # Tema
            datos["tema"] = detectar_tema(datos)
            
            return datos
        except Exception as e:
            print(f"⚠️ DeepSeek intento {i+1} falló: {e}")
            time.sleep(2)
    raise Exception("Fallo DeepSeek tras 3 intentos")

# ================================================================
# 4. IMÁGENES
# ================================================================
def generar_cf_vertical(prompt, ruta):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    clean_prompt = re.sub(r'[^a-zA-Z\s]', ' ', prompt)[:150]
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
        im = im.convert("RGB")
        w, h = im.size
        target_ratio = 9/16
        if w/h > target_ratio:
            new_w = int(h * target_ratio)
            im = im.crop(((w - new_w) // 2, 0, (w + new_w) // 2, h))
        else:
            new_h = int(w / target_ratio)
            im = im.crop((0, (h - new_h) // 2, w, (h + new_h) // 2))
        im = im.resize((W_SHORT, H_SHORT), Image.LANCZOS)
        im.save(ruta, "JPEG", quality=95)
    return ruta

def generar_pexels_vertical(query, ruta):
    headers = {"Authorization": PEXELS_API_KEY}
    r = requests.get("https://api.pexels.com/v1/search", headers=headers,
                     params={"query": query, "orientation": "portrait", "size": "large", "per_page": 5},
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
        im = ImageOps.fit(im.convert("RGB"), (W_SHORT, H_SHORT), Image.LANCZOS)
        im.save(ruta, "JPEG", quality=95)
    return ruta

def obtener_imagen_short(signo, ruta):
    prompt_epico = PROMPTS_IMAGEN_ELEMENTO.get(signo["elemento"], PROMPTS_IMAGEN_ELEMENTO["fuego"])
    delays = [5, 15]  # backoff exponencial
    for i, delay in enumerate(delays, start=1):
        try:
            print(f"   ☁️ CF Intento {i}/{len(delays)}...")
            return generar_cf_vertical(prompt_epico, ruta)
        except Exception as e:
            print(f"   ⚠️ CF intento {i} falló: {e}")
            if i < len(delays):
                print(f"   ⏳ Esperando {delay}s...")
                time.sleep(delay)
    
    print("   ⚠️ CF agotado, usando Pexels...")
    return generar_pexels_vertical(prompt_epico, ruta)

# ================================================================
# 5. AUDIO (voz por elemento)
# ================================================================
async def generar_audio(texto, ruta, elemento="fuego"):
    max_retries = 3
    voz_elegida, rate = VOICE_CONFIG.get(elemento, VOICE_CONFIG["fuego"])
    print(f"   🎤 Voz: {voz_elegida} (rate {rate})")
    
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(texto, voz_elegida, rate=rate)
            await communicate.save(ruta)
            if os.path.exists(ruta) and os.path.getsize(ruta) > 500:
                print(f"   ✅ Audio Edge TTS OK")
                return True
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(5)
    
    print("   ⚠️ Edge TTS falló, usando gTTS...")
    try:
        tts = gTTS(text=texto, lang='es', slow=False)
        tts.save(ruta)
        if os.path.exists(ruta) and os.path.getsize(ruta) > 500:
            print(f"   ✅ Audio gTTS OK")
            return True
        raise Exception("gTTS vacío")
    except Exception as e:
        raise Exception(f"Fallo TTS: {str(e)}")

# ================================================================
# 6. RENDER (con INTRO_DUR + micro-zoom + música por elemento)
# ================================================================
def renderizar_short(signo, guion, img_path, audio_path, salida, intro_teaser=""):
    audio_narracion = AudioFileClip(audio_path)
    audio_dur = audio_narracion.duration
    dur = INTRO_DUR + audio_dur + 0.5
    
    print(f"   ⏱️ Duración total: {dur:.1f}s ({INTRO_DUR:.0f}s intro + {audio_dur:.1f}s narración + 0.5s cola)")
    print(f"   🎬 Intro teaser: '{intro_teaser}'")
    
    # Imagen base
    img = Image.open(img_path).convert("RGB")
    img = ImageEnhance.Brightness(img).enhance(1.15)
    img = ImageEnhance.Contrast(img).enhance(1.25)
    img = ImageEnhance.Color(img).enhance(1.5)
    
    draw = ImageDraw.Draw(img)
    try:
        font_nombre = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 140)
        font_mantra = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 55)
        font_teaser = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 85)
    except:
        font_nombre = font_mantra = font_teaser = ImageFont.load_default()
    
    estilo = ELEMENT_STYLES.get(signo["elemento"], ELEMENT_STYLES["fuego"])
    
    draw.text((W_SHORT//2, 400), f"{signo['simbolo']} {signo['nombre'].upper()}",
              font=font_nombre, fill=estilo["text_color"], anchor="mm",
              stroke_width=14, stroke_fill=estilo["stroke_color"])
    
    mantra = guion.split('.')[-1].strip()[:80]
    draw.text((W_SHORT//2, 1600), mantra, font=font_mantra,
              fill=estilo["mantra_color"], anchor="mm",
              stroke_width=10, stroke_fill=(0, 0, 0))
    
    # Teaser en el centro para los 2s de intro
    if intro_teaser:
        draw.text((W_SHORT//2, 960), intro_teaser.upper(), font=font_teaser,
                  fill=(255, 255, 255), anchor="mm",
                  stroke_width=12, stroke_fill=estilo["text_color"])
    
    img.save("temp_short_frame.jpg")
    
    # Viñeta cacheada
    def vignette_vert(size, base=1.0, fuerza=0.3):
        w, h = size
        y, x = np.ogrid[-1:1:h * 1j, -1:1:w * 1j]
        d = np.clip(np.sqrt(x ** 2 + y ** 2) / 1.414, 0, 1)
        return ((1 - fuerza * d ** 2.2) * base).astype(np.float32)[..., None]
    
    # Imagen base cargada UNA sola vez
    base_img = Image.open("temp_short_frame.jpg").convert("RGB")
    base_sz = (int(W_SHORT * 1.15), int(H_SHORT * 1.15))
    base_img = ImageOps.fit(base_img, base_sz, Image.LANCZOS)
    vig = vignette_vert(base_sz, 1.0)
    arr = np.asarray(base_img, dtype=np.float32) * vig
    base_img = Image.fromarray(arr.astype(np.uint8))
    
    def frame(t):
        if t < INTRO_DUR:
            # Intro: micro-zoom 100% → 103%, centrado
            p = t / INTRO_DUR
            zoom = 1 + 0.03 * p
            y_drift = 0
        else:
            # Cuerpo: Ken Burns normal
            p = min(max((t - INTRO_DUR) / audio_dur, 0), 1)
            zoom = 1 + 0.15 * p
            y_drift = 0.3 * p
        
        cw = base_sz[0] / zoom
        ch = cw * base_sz[1] / base_sz[0]
        mx, my = base_sz[0] - cw, base_sz[1] - ch
        y0 = my / 2 + my * y_drift
        
        fr = np.asarray(base_img.resize(
            (W_SHORT, H_SHORT), Image.BILINEAR,
            box=(mx/2, y0, mx/2+cw, y0+ch)
        ))
        return fr
    
    video = VideoClip(frame, duration=dur)
    
    # Narración retrasada por INTRO_DUR
    audio_narracion = audio_narracion.set_start(INTRO_DUR)
    
    # Música por elemento
    musica_elegida = obtener_musica(signo["elemento"])
    
    if musica_elegida:
        try:
            bg = AudioFileClip(musica_elegida)
            if bg.duration <= 0:
                print(f"   ⚠️ Música {musica_elegida} inválida, sin música")
                video = video.set_audio(audio_narracion)
            else:
                if bg.duration < dur:
                    bg = concatenate_audioclips([bg] * (int(dur / bg.duration) + 1))
                bg = bg.subclip(0, dur).volumex(0.12).audio_fadein(0.5).audio_fadeout(2)
                video = video.set_audio(CompositeAudioClip([audio_narracion, bg]))
                print(f"   🎵 Música: {musica_elegida} (vol 12%)")
        except Exception as e:
            print(f"   ⚠️ Error música: {e}")
            video = video.set_audio(audio_narracion)
    else:
        video = video.set_audio(audio_narracion)
    
    print("🎬 Renderizando...")
    video.write_videofile(salida, fps=FPS, codec="libx264", audio_codec="aac",
                          threads=4, preset="ultrafast", logger=None)
    return salida

# ================================================================
# 7. SUBIDA (con hashtags rotados por tema)
# ================================================================
def subir_short_youtube(ruta_video, datos, signo, video_largo_id, hora_utc):
    youtube = build("youtube", "v3", credentials=obtener_credenciales_youtube())
    
    tema = datos.get("tema", "general")
    hashtags = construir_hashtags(signo, tema)
    desc = f"{datos['descripcion']}\n\n{hashtags}"
    
    body = {
        "snippet": {
            "title": datos["titulo"][:100],
            "description": desc[:5000],
            "tags": construir_tags_shorts_premium(signo, tema),
            "categoryId": "22",
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
    
    req = youtube.videos().insert(
        part="snippet,status", body=body,
        media_body=MediaFileUpload(ruta_video, chunksize=4*1024*1024, resumable=True)
    )
    resp, reintentos = None, 0
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st:
                print(f"   ⬆️ {int(st.progress() * 100)}%")
        except Exception as e:
            if reintentos < 8:
                reintentos += 1
                time.sleep(2 ** reintentos)
            else:
                raise e
            
    print(f"✅ Short subido. ID: {resp['id']}")
    if datos.get("comentario_fijado"):
        try:
            youtube.commentThreads().insert(
                part="snippet",
                body={"snippet": {"videoId": resp['id'],
                                  "topLevelComment": {"snippet": {"textOriginal": datos["comentario_fijado"]}}}}
            ).execute()
        except:
            pass
    return resp['id']

# ================================================================
# 8. MAIN (con scheduling inteligente)
# ================================================================
def calcular_hora_publicacion(ahora):
    """Devuelve una hora óptima de publicación según la hora actual."""
    h = ahora.hour
    
    if 0 <= h < 4:
        # Madrugada → programar 6:00-7:00 AM mismo día
        base = ahora.replace(hour=6, minute=0, second=0, microsecond=0)
        mins = random.randint(0, 60)
    elif 4 <= h < 6:
        base = ahora.replace(hour=6, minute=0, second=0, microsecond=0)
        mins = random.randint(5, 50)
    elif 6 <= h < 10:
        base = ahora.replace(hour=10, minute=0, second=0, microsecond=0)
        mins = random.randint(5, 45)
    elif 10 <= h < 14:
        # Almuerzo
        base = ahora.replace(hour=14, minute=0, second=0, microsecond=0)
        mins = random.randint(5, 45)
    elif 14 <= h < 18:
        # Tarde → programar 7 PM
        base = ahora.replace(hour=19, minute=0, second=0, microsecond=0)
        mins = random.randint(0, 45)
    elif 18 <= h < 21:
        # Evening scroll (mejor hora)
        base = ahora
        mins = random.randint(5, 40)
    else:
        # 21-24h → mañana 6:00-7:00 AM
        manana = ahora + timedelta(days=1)
        base = manana.replace(hour=6, minute=0, second=0, microsecond=0)
        mins = random.randint(0, 60)
    
    return base + timedelta(minutes=mins)

def main():
    try:
        ahora = datetime.now(TZ)
        print(f"🤖 Bot ejecutándose...")
        
        estado = cargar_estado()
        
        if len(estado.get("publicados_hoy", [])) >= MAX_SHORTS_DIARIOS:
            print(f"⚠️ LÍMITE ALCANZADO: {MAX_SHORTS_DIARIOS} Shorts hoy.")
            print(f"📋 Publicados: {estado['publicados_hoy']}")
            return
        
        signo = elegir_siguiente_signo(estado)
        print(f"🎯 Signo: {signo['simbolo']} {signo['nombre']} ({signo['elemento']})")
        print(f"📊 Progreso: {len(estado['publicados_hoy'])}/{MAX_SHORTS_DIARIOS}")
        
        hora_final = calcular_hora_publicacion(ahora)
        hora_utc = hora_final.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print(f"📅 Programado: {hora_final:%H:%M} (CDMX)")
        
        video_largo_id = buscar_ultimo_video_largo()
        print(f"🎬 Video largo ID: {video_largo_id}")
        
        datos = llamar_deepseek_short(
            signo,
            datetime.now(TZ).strftime("%d de %B de %Y"),
            video_largo_id  # None si no hay → no se inyecta URL rota
        )
        print(f"   📝 Título: {datos['titulo']} ({len(datos['titulo'])} chars)")
        print(f"   🎨 Tema: {datos['tema']}")
        print(f"   💡 Teaser: {datos.get('intro_teaser', '')}")
        
        obtener_imagen_short(signo, "temp_short_img.jpg")
        asyncio.run(generar_audio(datos["guion"], "temp_short_audio.mp3", signo["elemento"]))
        renderizar_short(
            signo, datos["guion"], "temp_short_img.jpg", "temp_short_audio.mp3",
            "short_final.mp4", intro_teaser=datos.get("intro_teaser", "")
        )
        subir_short_youtube("short_final.mp4", datos, signo, video_largo_id, hora_utc)
        
        guardar_estado(estado)
        hacer_commit_estado()
        print(f"✨ ¡COMPLETADO! {signo['nombre']} para {hora_final:%H:%M}")
        
        for f in os.listdir():
            if f.startswith("temp_") or f == "short_final.mp4":
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
