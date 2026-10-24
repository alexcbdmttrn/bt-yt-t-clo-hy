# -*- coding: utf-8 -*-
"""
BT_YT_SHORTS_CLO_HY - Bot Shorts Horóscopo (Tu Cielo Hoy) - VERSIÓN PREMIUM 30 SEGUNDOS
Fix: Duración 30-35s (75-95 palabras), Títulos estilo VidIQ 80+, Bug de repetición SOLUCIONADO, KeyError arreglado.
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

VOICES_LIST = [
    "es-MX-DaliaNeural", "es-ES-ElviraNeural", "es-AR-ElenaNeural", 
    "es-CO-SalomeNeural", "es-US-PalomaNeural"
]

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

HASHTAGS_SHORTS = "\n\n#shorts #horoscopo #zodiaco #astrologia #tucielhoy #mensajeDelUniverso #energiaDelDia"

def normalizar_ascii(texto):
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()

def construir_tags_shorts_premium(signo):
    signo_norm = normalizar_ascii(signo["nombre"])
    
    generales = [
        "astrologia", "horoscopo", "zodiaco", "mensaje del universo", 
        "energia del dia", "horoscopo diario", "ley de atraccion", 
        "espiritualidad", "crecimiento personal", "universo", "shorts"
    ]
    
    especificas = [
        f"horoscopo {signo_norm}", 
        f"{signo_norm} hoy", 
        f"horoscopo {signo_norm} hoy",
        f"horoscopo diario para {signo_norm}",
        f"caracteristicas de {signo_norm}",
        f"{signo_norm} amor", 
        f"{signo_norm} dinero",
        f"prediccion {signo_norm}",
        f"que le espera a {signo_norm} hoy",
        f"{signo_norm} 2026"
    ]
    
    all_tags = generales + especificas
    unique_tags, total_chars = [], 0
    
    for tag in all_tags:
        clean_tag = re.sub(r'[^a-z0-9\sáéíóúñ]', '', tag).strip()
        if 3 <= len(clean_tag) <= 30 and clean_tag not in unique_tags:
            if total_chars + len(clean_tag) + 1 <= 480:
                unique_tags.append(clean_tag)
                total_chars += len(clean_tag) + 1
                
    print(f"   🏷️ Tags generados: {len(unique_tags)} tags, {total_chars}/480 caracteres")
    return unique_tags

print("=" * 70)
print("📱 BT_YT_SHORTS_CLO_HY - PREMIUM 30S (TÍTULOS VIDIQ 80+)")
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
    if not GITHUB_TOKEN: return False
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

# ✅ CORREGIDO: Lógica para NO repetir signos hasta completar los 12
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
    if creds.expired and creds.refresh_token: creds.refresh(Request())
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

# ✅ CORREGIDO: Llaves escapadas {{}} para evitar KeyError en .format()
PROMPT_SHORT_SEO = """
Eres EXPERTA EN SEO Viral para YouTube Shorts (Nivel VidIQ 80+). Tono: femenino, cálido, místico, PERSUASIVO.
Fecha: {fecha}. Signo: {signo} ({simbolo}). Elemento: {elemento}.

REGLAS OBLIGATORIAS PARA TÍTULOS PREMIUM:

1. TÍTULO (55-65 caracteres - SIN hashtags - ESTILO VIDIQ):
   Basándote en estos ejemplos de VidIQ que obtienen 80+ puntos, crea títulos específicos y persuasivos:
   
   EJEMPLOS PREMIUM (ANÁLISIS VIDIQ):
   - "Capricornio: La señal que esperabas para el dinero 💰" (84 pts)
   - "¡Atención Capricornio! Abundancia financiera activada 🔥" (82 pts)
   - "¿Qué le espera a Capricornio hoy? 🔮" (82 pts)
   - "Capricornio: Dinero inesperado hoy 💰" (80 pts)
   - "¿Eres Capricornio? Mira tu dinero HOY 💰" (80 pts)
   
   ESTRUCTURAS QUE FUNCIONAN:
   - "{{signo}}: La señal que esperabas para {{tema}} {{emoji}}"
   - "¡Atención {{signo}}! {{Beneficio}} activado {{emoji}}"
   - "¿Qué le espera a {{signo}} hoy? {{emoji}}"
   - "{{signo}}: {{Beneficio}} {{tema}} hoy {{emoji}}"
   - "¿Eres {{signo}}? {{Pregunta}} HOY {{emoji}}"
   
   Temas: Dinero, Amor, Suerte, Destino, Abundancia, Cambios
   Emojis permitidos: 💰, 🔮, ✨, 💕, 🔥, ⚠️, 🌟
   PROHIBIDO hashtags en el título
   PROHIBIDO superar 65 caracteres

2. DESCRIPCIÓN (2-3 líneas):
   - Línea 1: Energía del elemento {elemento} + palabra clave específica
   - Línea 2: "🎥 Video completo: https://www.youtube.com/watch?v={video_largo_id}"
   - Línea 3: "🔔 Suscríbete: https://www.youtube.com/@tucielhoy"

3. GUION (75-95 palabras - PARA 30-35 SEGUNDOS):
   - Gancho (3-4 seg): "{signo}, este mensaje del universo es solo para ti..."
   - Cuerpo (20 seg): Desarrolla amor, dinero y energía con MÁS detalle. Agrega frases como:
     * "La energía de {elemento} que te rodea hoy está activando..."
     * "En el amor, las estrellas revelan que..."
     * "En lo financiero, una oportunidad inesperada..."
     * "Tu intuición está más fuerte que nunca..."
   - Mantra (4 seg): Frase de 5-7 palabras para decretar
   - CTA (4 seg): "Mira el video completo en mi canal para los 12 signos"

4. COMENTARIO FIJADO:
   - Pregunta persuasiva + "Video completo: https://www.youtube.com/watch?v={video_largo_id}"

Responde SOLO JSON:
{{
  "titulo": "♑ Capricornio: La señal que esperabas para el dinero 💰",
  "descripcion": "Tu energía de {elemento} fluye con abundancia financiera. 🎥 Video completo: https://www.youtube.com/watch?v={video_largo_id}\\n🔔 Suscríbete: https://www.youtube.com/@tucielhoy",
  "comentario_fijado": "¿Sientes esta energía? Decreta 'HECHO ESTÁ'. Video: https://www.youtube.com/watch?v={video_largo_id}",
  "guion": "{signo}, este mensaje del universo es solo para ti. Hoy tu elemento {elemento} se activa con una energía imparable que transforma tu realidad. En el amor, las estrellas revelan una verdad que necesitabas escuchar: es momento de abrir tu corazón. En el dinero, una oportunidad inesperada toca tu puerta. Confía en tu intuición, está más fuerte que nunca. Tu mantra: 'Atraigo abundancia infinita'. Mira el video completo en mi canal.",
  "visual_prompt": "vertical mystical {elemento} energy"
}}
"""

def llamar_deepseek_short(signo, fecha, video_largo_id="PLACEHOLDER"):
    signo_lower = normalizar_ascii(signo["nombre"])
    prompt = PROMPT_SHORT_SEO.format(
        fecha=fecha, signo=signo["nombre"], simbolo=signo["simbolo"], 
        elemento=signo["elemento"], signo_lower=signo_lower, video_largo_id=video_largo_id
    )
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.9, "response_format": {"type": "json_object"}}
    
    for i in range(3):
        try:
            print(f"    Intento {i+1}/3 con DeepSeek...")
            r = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            texto = r.json()["choices"][0]["message"]["content"].strip()
            t = re.sub(r"```(?:json)?", " ", texto, flags=re.I)
            i_json, j_json = t.find("{"), t.rfind("}")
            datos = json.loads(t[i_json:j_json + 1], strict=False)
            
            # ✅ LIMPIAR TÍTULO: Quitar hashtags y asegurar longitud óptima
            titulo = datos.get("titulo", "")
            titulo = re.sub(r'\s*#.*', '', titulo)  # Quitar hashtags
            if len(titulo) > 65:
                titulo = titulo[:62] + "..."
            datos["titulo"] = titulo
            
            # ✅ VALIDAR LONGITUD DEL GUION (75-95 palabras)
            palabras_guion = len(datos.get("guion", "").split())
            if palabras_guion < 75:
                print(f"⚠️ Guion corto ({palabras_guion} palabras). Ajustando...")
            elif palabras_guion > 95:
                print(f"⚠️ Guion largo ({palabras_guion} palabras). Ajustando...")
            
            # ✅ ASEGURAR URL REAL
            if video_largo_id and video_largo_id != "PLACEHOLDER":
                url_real = f"https://www.youtube.com/watch?v={video_largo_id}"
                if url_real not in datos.get("descripcion", ""):
                    datos["descripcion"] += f"\n🎥 Video completo: {url_real}"
                if url_real not in datos.get("comentario_fijado", ""):
                    datos["comentario_fijado"] += f"\nVideo: {url_real}"
                
            return datos
        except Exception as e:
            print(f"⚠️ DeepSeek intento {i+1} falló: {e}")
            time.sleep(2)
    raise Exception("Fallo DeepSeek")

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
    r = requests.get("https://api.pexels.com/v1/search", headers=headers, params={"query": query, "orientation": "portrait", "size": "large", "per_page": 5}, timeout=15)
    r.raise_for_status()
    fotos = r.json().get("photos", [])
    if not fotos: raise Exception("Sin Pexels")
    with requests.get(fotos[0]["src"]["large2x"], stream=True, timeout=15) as r_img:
        with open(ruta, "wb") as f:
            for chunk in r_img.iter_content(8192): f.write(chunk)
    with Image.open(ruta) as im:
        im = ImageOps.fit(im.convert("RGB"), (W_SHORT, H_SHORT), Image.LANCZOS)
        im.save(ruta, "JPEG", quality=95)
    return ruta

def obtener_imagen_short(signo, ruta):
    prompt_epico = PROMPTS_IMAGEN_ELEMENTO.get(signo["elemento"], PROMPTS_IMAGEN_ELEMENTO["fuego"])
    for i in range(1, 3):
        try:
            print(f"   ☁️ CF Intento {i}/2...")
            return generar_cf_vertical(prompt_epico, ruta)
        except Exception as e:
            print(f"   ⚠️ CF intento {i} falló")
            time.sleep(2)
    
    print("   ⚠️ CF agotado, usando Pexels...")
    return generar_pexels_vertical(prompt_epico, ruta)

# ================================================================
# 5. AUDIO
# ================================================================
async def generar_audio(texto, ruta):
    max_retries = 3
    voz_elegida = random.choice(VOICES_LIST)
    print(f"   🎤 Voz: {voz_elegida}")
    
    for attempt in range(max_retries):
        try:
            communicate = edge_tts.Communicate(texto, voz_elegida, rate="-2%")
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
# 6. RENDER
# ================================================================
def renderizar_short(signo, guion, img_path, audio_path, salida):
    dur = AudioFileClip(audio_path).duration + 0.5
    print(f"   ⏱️ Duración: {dur:.1f} seg ({len(guion.split())} palabras)")
    
    img = Image.open(img_path).convert("RGB")
    img = ImageEnhance.Brightness(img).enhance(1.15)
    img = ImageEnhance.Contrast(img).enhance(1.25)
    img = ImageEnhance.Color(img).enhance(1.5)
    
    draw = ImageDraw.Draw(img)
    try:
        font_nombre = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 140)
        font_mantra = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 55)
    except:
        font_nombre = font_mantra = ImageFont.load_default()
    
    estilo = ELEMENT_STYLES.get(signo["elemento"], ELEMENT_STYLES["fuego"])
    
    draw.text((W_SHORT//2, 400), f"{signo['simbolo']} {signo['nombre'].upper()}", font=font_nombre, 
              fill=estilo["text_color"], anchor="mm", stroke_width=14, stroke_fill=estilo["stroke_color"])
    
    mantra = guion.split('.')[-1].strip()[:80]
    draw.text((W_SHORT//2, 1600), mantra, font=font_mantra, 
              fill=estilo["mantra_color"], anchor="mm", stroke_width=10, stroke_fill=(0, 0, 0))
    
    img.save("temp_short_frame.jpg")
    
    _VIG = {}
    def vignette_vert(size, base=1.0, fuerza=0.3):
        w, h = size
        y, x = np.ogrid[-1:1:h * 1j, -1:1:w * 1j]
        d = np.clip(np.sqrt(x ** 2 + y ** 2) / 1.414, 0, 1)
        return ((1 - fuerza * d ** 2.2) * base).astype(np.float32)[..., None]
    
    def frame(t):
        base = Image.open("temp_short_frame.jpg").convert("RGB")
        sz = (int(W_SHORT * 1.15), int(H_SHORT * 1.15))
        base = ImageOps.fit(base, sz, Image.LANCZOS)
        arr = np.asarray(base, dtype=np.float32) * vignette_vert(sz, 1.0)
        base = Image.fromarray(arr.astype(np.uint8))
        p = min(max(t / dur, 0), 1)
        cw = sz[0] / (1 + 0.15 * p)
        ch = cw * sz[1] / sz[0]
        mx, my = sz[0] - cw, sz[1] - ch
        fr = np.asarray(base.resize((W_SHORT, H_SHORT), Image.BILINEAR, box=(mx/2, my/2 + my*0.3*p, mx/2+cw, my/2+my*0.3*p+ch)))
        return fr
    
    video = VideoClip(frame, duration=dur)
    audio = AudioFileClip(audio_path)
    musicas = [f for f in os.listdir(".") if f.lower().endswith(".mp3") and not f.startswith("temp_")]
    
    if musicas:
        bg = AudioFileClip(random.choice(musicas))
        if bg.duration < dur: bg = concatenate_audioclips([bg] * (int(dur / bg.duration) + 1))
        video = video.set_audio(CompositeAudioClip([audio, bg.subclip(0, dur).volumex(0.08).audio_fadein(2).audio_fadeout(2)]))
    else:
        video = video.set_audio(audio)
    
    print("🎬 Renderizando...")
    video.write_videofile(salida, fps=FPS, codec="libx264", audio_codec="aac", threads=4, preset="ultrafast", logger=None)
    return salida

# ================================================================
# 7. SUBIDA
# ================================================================
def subir_short_youtube(ruta_video, datos, signo, video_largo_id, hora_utc):
    youtube = build("youtube", "v3", credentials=obtener_credenciales_youtube())
    signo_norm = normalizar_ascii(signo["nombre"])
    
    desc = f"{datos['descripcion']}\n\n"
    desc += f"#horoscopo #{signo_norm} #astrologia #zodiaco #shorts"
    
    body = {
        "snippet": {"title": datos["titulo"][:100], "description": desc[:5000], "tags": construir_tags_shorts_premium(signo), 
                    "categoryId": "22", "defaultLanguage": "es", "defaultAudioLanguage": "es"},
        "status": {"privacyStatus": "private", "publishAt": hora_utc, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    }
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(ruta_video, chunksize=4*1024*1024, resumable=True))
    resp, reintentos = None, 0
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st: print(f"   ⬆️ {int(st.progress() * 100)}%")
        except Exception as e:
            if reintentos < 8:
                reintentos += 1
                time.sleep(2 ** reintentos)
            else: raise e
            
    print(f"✅ Short subido. ID: {resp['id']}")
    if datos.get("comentario_fijado"):
        try:
            youtube.commentThreads().insert(part="snippet", body={"snippet": {"videoId": resp['id'], "topLevelComment": {"snippet": {"textOriginal": datos["comentario_fijado"]}}}}).execute()
        except: pass
    return resp['id']

# ================================================================
# 8. MAIN
# ================================================================
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
        
        hora_actual = ahora.hour
        if 4 <= hora_actual < 6: hora_base, min_rand = ahora.replace(hour=5, minute=0, second=0, microsecond=0), random.randint(5, 50)
        elif 6 <= hora_actual < 8: hora_base, min_rand = ahora.replace(hour=7, minute=0, second=0, microsecond=0), random.randint(10, 45)
        elif 8 <= hora_actual < 10: hora_base, min_rand = ahora.replace(hour=9, minute=0, second=0, microsecond=0), random.randint(5, 40)
        else: hora_base, min_rand = ahora, random.randint(15, 45)
        
        hora_final = hora_base + timedelta(minutes=min_rand)
        hora_utc = hora_final.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print(f"📅 Programado: {hora_final:%H:%M}")
        
        video_largo_id = buscar_ultimo_video_largo()
        id_para_prompt = video_largo_id if video_largo_id else "PLACEHOLDER"
        print(f"🎬 Video largo ID: {video_largo_id}")
        
        datos = llamar_deepseek_short(signo, datetime.now(TZ).strftime("%d de %B de %Y"), id_para_prompt)
        print(f"   📝 Título: {datos.get('titulo')} ({len(datos.get('titulo', ''))} chars)")
        print(f"   📄 Guion: {len(datos.get('guion', '').split())} palabras")
        
        obtener_imagen_short(signo, "temp_short_img.jpg")
        asyncio.run(generar_audio(datos["guion"], "temp_short_audio.mp3"))
        renderizar_short(signo, datos["guion"], "temp_short_img.jpg", "temp_short_audio.mp3", "short_final.mp4")
        subir_short_youtube("short_final.mp4", datos, signo, video_largo_id, hora_utc)
        
        guardar_estado(estado)
        hacer_commit_estado()
        print(f"✨ ¡COMPLETADO! {signo['nombre']} para {hora_final:%H:%M}")
        
        for f in os.listdir():
            if f.startswith("temp_") or f == "short_final.mp4":
                try: os.remove(f)
                except: pass
    except Exception as e:
        print(f"❌ ERROR FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
