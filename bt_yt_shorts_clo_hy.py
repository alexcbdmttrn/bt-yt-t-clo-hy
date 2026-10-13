# -*- coding: utf-8 -*-
"""
BT_YT_SHORTS_CLO_HY - Bot Shorts Horóscopo (Tu Cielo Hoy) - VERSIÓN FINAL 100% COMPLETA
Fix: Límite estricto de 3 Shorts diarios, rotación de 5 voces femeninas + Fallback a gTTS.
     2 intentos Cloudflare, SEO VidIQ Premium, Imágenes épicas, Cola secuencial sin repeticiones.
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

# ✅ LÍMITE MÁXIMO DE SHORTS POR DÍA
MAX_SHORTS_DIARIOS = 3

# ✅ LISTA DE 5 VOCES FEMENINAS PARA ROTAR Y EVITAR MONOTONÍA
VOICES_LIST = [
    "es-MX-DaliaNeural",
    "es-ES-ElviraNeural",
    "es-AR-ElenaNeural",
    "es-CO-SalomeNeural",
    "es-US-PalomaNeural"
]

ESTADO_FILE = "estado_shorts.json"
W_SHORT, H_SHORT, FPS = 1080, 1920, 24

SIGNOS_COLA = [
    {"nombre": "Aries", "simbolo": "♈", "elemento": "fuego"},
    {"nombre": "Tauro", "simbolo": "", "elemento": "tierra"},
    {"nombre": "Géminis", "simbolo": "♊", "elemento": "aire"},
    {"nombre": "Cáncer", "simbolo": "♋", "elemento": "agua"},
    {"nombre": "Leo", "simbolo": "♌", "elemento": "fuego"},
    {"nombre": "Virgo", "simbolo": "♍", "elemento": "tierra"},
    {"nombre": "Libra", "simbolo": "♎", "elemento": "aire"},
    {"nombre": "Escorpio", "simbolo": "♏", "elemento": "agua"},
    {"nombre": "Sagitario", "simbolo": "♐", "elemento": "fuego"},
    {"nombre": "Capricornio", "simbolo": "♑", "elemento": "tierra"},
    {"nombre": "Acuario", "simbolo": "♒", "elemento": "aire"},
    {"nombre": "Piscis", "simbolo": "", "elemento": "agua"}
]

PROMPTS_IMAGEN_ELEMENTO = {
    "fuego": "vertical intense flames and golden sparks, dramatic red and orange cosmic explosion, mystical fire energy, vibrant glowing embers, 8k cinematic, highly detailed, no text",
    "tierra": "vertical lush green forest with golden sunlight beams, mystical nature energy, vibrant emerald and gold, magical crystals and plants, 8k cinematic, highly detailed, no text",
    "aire": "vertical swirling aurora borealis with electric blue and purple, cosmic wind energy, vibrant sky with shooting stars, 8k cinematic, highly detailed, no text",
    "agua": "vertical deep ocean with bioluminescent creatures, mystical water energy, vibrant turquoise and silver, magical underwater light rays, 8k cinematic, highly detailed, no text"
}

HASHTAGS_SHORTS = "\n\n#shorts #horoscopo #zodiaco #astrologia #tucielhoy #mensajeDelUniverso #energiaDelDia"

def normalizar_ascii(texto):
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()

# ================================================================
# 🚀 MOTOR DE TAGS SEO PREMIUM (NIVEL VIDIQ)
# ================================================================
def construir_tags_shorts_premium(signo):
    signo_norm = normalizar_ascii(signo["nombre"])
    generales = [
        "shorts", "horoscopo", "astrologia", "zodiaco", "mensaje del universo", 
        "energia del dia", "horoscopo diario", "ley de atraccion", "espiritualidad", 
        "crecimiento personal", "universo"
    ]
    especificas = [
        f"horoscopo {signo_norm}", f"{signo_norm} hoy", f"signo {signo_norm}", 
        f"{signo_norm} amor", f"{signo_norm} dinero", f"prediccion {signo_norm}",
        f"caracteristicas de {signo_norm}", f"{signo_norm} 2026"
    ]
    long_tail = [
        f"horoscopo diario para {signo_norm}", 
        f"mensaje urgente del universo para {signo_norm}", 
        f"prediccion astrologica hoy {signo_norm}", 
        f"que le espera a {signo_norm} hoy",
        f"consejos astrologicos para {signo_norm}"
    ]
    
    all_tags = generales + especificas + long_tail
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
print("📱 BT_YT_SHORTS_CLO_HY - VARIACIÓN VIRAL + ANTI-BLOQUEO TTS")
print(f"📅 {datetime.now(TZ):%Y-%m-%d %H:%M} (CDMX)")
print("=" * 70)

if not all([DEEPSEEK_API_KEY, PEXELS_API_KEY, CF_ACCOUNT_ID, CF_API_TOKEN, YT_TOKEN_STR]):
    print("❌ ERROR: Faltan variables de entorno en los Secrets de GitHub.")
    sys.exit(1)

# ================================================================
# 2. ESTADO DEL BOT (SECUENCIA CONTINUA + LÍMITE DE 3 SHORTS)
# ================================================================
def cargar_estado():
    try:
        with open(ESTADO_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            hoy = datetime.now(TZ).strftime("%Y-%m-%d")
            if data.get("fecha") != hoy:
                indice_actual = data.get("indice", 0)
                print(f"🔄 Nuevo día detectado. Continuando secuencia desde el índice {indice_actual}.")
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
    print(f"💾 Estado guardado: índice={data['indice']}, publicados_hoy={data['publicados_hoy']}")

def hacer_commit_estado():
    if not GITHUB_TOKEN:
        print("⚠️ No hay GITHUB_TOKEN.")
        return False
    try:
        subprocess.run(["git", "config", "user.name", "bot-shorts"], check=False, capture_output=True)
        subprocess.run(["git", "config", "user.email", "bot@tucielhoy.com"], check=False, capture_output=True)
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=False, capture_output=True)
        subprocess.run(["git", "add", ESTADO_FILE], check=False, capture_output=True)
        subprocess.run(["git", "commit", "-m", f"🤖 Actualizar estado {datetime.now(TZ).strftime('%H:%M')}"], check=False, capture_output=True)
        remote_url = f"https://x-access-token:{GITHUB_TOKEN}@github.com/{REPO_NAME}.git"
        result = subprocess.run(["git", "push", remote_url, "HEAD:main"], check=False, capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Estado commiteado.")
            return True
        else:
            print(f"️ No se pudo hacer push: {result.stderr[:100]}")
            return False
    except Exception as e:
        print(f"️ Error commit: {e}")
        return False

def elegir_siguiente_signo(estado):
    indice = estado.get("indice", 0)
    publicados_hoy = estado.get("publicados_hoy", [])
    
    if len(publicados_hoy) >= 12:
        print("🔄 Ciclo completado. Reiniciando...")
        indice = 0
        publicados_hoy = []
    
    signo = SIGNOS_COLA[indice % 12]
    
    if signo["nombre"] in publicados_hoy:
        for i in range(1, 12):
            candidato = SIGNOS_COLA[(indice + i) % 12]
            if candidato["nombre"] not in publicados_hoy:
                signo = candidato
                indice = (indice + i) % 12
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
    except Exception as e:
        print(f"⚠️ Error buscando video: {e}")
        return None

PROMPT_SHORT_SEO = """
Eres la astróloga más prestigiosa de YouTube y EXPERTA EN SEO (Nivel VidIQ Premium). Tono: femenino, cálido, místico, URGENTE.
Fecha: {fecha}. Signo: {signo} ({simbolo}). Elemento: {elemento}.

Genera un guion para un YouTube SHORT de 25-35 segundos con SEO MÁXIMO y VARIEDAD TOTAL.

REGLAS CRÍTICAS DE SEO Y VARIEDAD (NO LAS ROMPAS):
1. TÍTULO (Máx 75 caracteres): DEBES elegir UNA de estas estructuras de forma ALEATORIA para que NUNCA se repitan entre signos:
   - Opción A (Urgencia): "⚠️ [SIGNO]: No ignores esta señal del Universo hoy #[signo_lower] #horoscopo #astrologia"
   - Opción B (Beneficio): "💰 [SIGNO]: Revelación inesperada de dinero y amor #[signo_lower] #zodiaco #astrologia"
   - Opción C (Místico): "🔮 El cosmos tiene un mensaje urgente para [SIGNO] #[signo_lower] #horoscopo #energia"
   - Opción D (Elemento): " [SIGNO]: Tu energía está imparable, descubre por qué #[signo_lower] #astrologia #zodiaco"
   - Opción E (Destino): "✨ [SIGNO]: El universo conspira a tu favor en esto #[signo_lower] #horoscopo #astrologia"

2. DESCRIPCIÓN (ÚNICA): Escribe 2 líneas específicas para este signo, mencionando su elemento ({elemento}) y su energía actual. NO uses plantillas genéricas. Incluye el enlace al video largo.

3. GUION (65-85 palabras): 
   - Gancho (3 seg): "{signo}, este mensaje del universo es solo para ti..."
   - Cuerpo (15 seg): Energía, amor y dinero en frases cortas, poderosas y únicas para este signo.
   - Mantra (4 seg): Frase de 5-7 palabras para decretar.
   - CTA FINAL (5-7 seg, PERSUASIVO Y VARIADO): Elige una forma diferente de invitar a ver los videos largos (diarios, semanales, mensuales) en el canal.

4. COMENTARIO FIJADO: Pregunta corta y mística + "Mira el video completo en mi canal".

Responde SOLO JSON:
{{
  "titulo": "🔥 [SIGNO]: Tu energía está imparable, descubre por qué #[signo_lower] #astrologia #zodiaco",
  "descripcion": "...",
  "comentario_fijado": "...",
  "guion": "...",
  "visual_prompt": "vertical mystical {elemento} energy"
}}
"""

def llamar_deepseek_short(signo, fecha):
    signo_lower = normalizar_ascii(signo["nombre"])
    prompt = PROMPT_SHORT_SEO.format(
        fecha=fecha, signo=signo["nombre"], simbolo=signo["simbolo"], 
        elemento=signo["elemento"], signo_lower=signo_lower
    )
    
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], 
               "temperature": 0.85, "response_format": {"type": "json_object"}}
    
    for i in range(3):
        try:
            print(f"    Intento {i+1}/3 con DeepSeek...")
            r = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            texto = r.json()["choices"][0]["message"]["content"].strip()
            t = re.sub(r"```(?:json)?", " ", texto, flags=re.I)
            i_json, j_json = t.find("{"), t.rfind("}")
            datos = json.loads(t[i_json:j_json + 1], strict=False)
            
            palabras = len(datos.get("guion", "").split())
            if palabras < 55 or palabras > 95:
                raise ValueError(f"Guion con {palabras} palabras")
            
            if "#" not in datos.get("titulo", ""):
                datos["titulo"] = f"🔮 {signo['nombre']}: Mensaje del Universo #{signo_lower} #horoscopo #astrologia"
            return datos
        except Exception as e:
            print(f"⚠️ DeepSeek intento {i+1} falló: {e}")
            time.sleep(2)
    raise Exception("Fallo DeepSeek")

# ================================================================
# 4. IMÁGENES (2 INTENTOS CLOUDFLARE → PEXELS)
# ================================================================
def generar_cf_vertical(prompt, ruta):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    clean_prompt = re.sub(r'[^a-zA-Z\s]', ' ', prompt)[:100]
    safe_prompt = f"{clean_prompt}, vertical composition, 8k, highly detailed, no text, no watermark"
    payload = {"prompt": safe_prompt, "steps": 4}
    
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        print(f"   ❌ Cloudflare HTTP {r.status_code}: {r.text[:200]}")
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
        im.save(ruta, "JPEG", quality=92)
    return ruta

def generar_pexels_vertical(query, ruta):
    headers = {"Authorization": PEXELS_API_KEY}
    r = requests.get("https://api.pexels.com/v1/search", headers=headers, 
                    params={"query": query, "orientation": "portrait", "size": "large", "per_page": 5}, timeout=15)
    r.raise_for_status()
    fotos = r.json().get("photos", [])
    if not fotos: raise Exception("Sin Pexels")
    with requests.get(fotos[0]["src"]["large2x"], stream=True, timeout=15) as r_img:
        with open(ruta, "wb") as f:
            for chunk in r_img.iter_content(8192): f.write(chunk)
    with Image.open(ruta) as im:
        im = im.convert("RGB")
        im = ImageOps.fit(im, (W_SHORT, H_SHORT), Image.LANCZOS)
        im.save(ruta, "JPEG", quality=92)
    return ruta

def obtener_imagen_short(signo, ruta):
    prompt_epico = PROMPTS_IMAGEN_ELEMENTO.get(signo["elemento"], PROMPTS_IMAGEN_ELEMENTO["fuego"])
    
    # ✅ 2 INTENTOS EN CLOUDFLARE
    for i in range(1, 3):
        try:
            print(f"   ☁️ CF Intento {i}/2...")
            return generar_cf_vertical(prompt_epico, ruta)
        except Exception as e:
            print(f"   ⚠️ CF intento {i} falló: {str(e)[:100]}")
            time.sleep(2)
    
    print("   ⚠️ CF agotado, usando Pexels como respaldo...")
    try:
        return generar_pexels_vertical(prompt_epico, ruta)
    except Exception as e:
        print(f"   ❌ Pexels también falló: {e}")
        return None

# ================================================================
# 5. AUDIO (ROTACIÓN DE VOCES + FALLBACK gTTS ANTI-403)
# ================================================================
async def generar_audio(texto, ruta):
    max_retries = 3
    voz_elegida = random.choice(VOICES_LIST)
    print(f"   🎤 Voz seleccionada: {voz_elegida}")
    
    # Intento 1: Edge TTS (Mejor calidad)
    for attempt in range(max_retries):
        try:
            print(f"   🎤 Generando audio con Edge TTS (Intento {attempt + 1}/{max_retries})...")
            communicate = edge_tts.Communicate(texto, voz_elegida, rate="-2%")
            await communicate.save(ruta)
            if os.path.exists(ruta) and os.path.getsize(ruta) > 500:
                print(f"   ✅ Audio Edge TTS generado exitosamente.")
                return True
        except Exception as e:
            error_msg = str(e)
            print(f"   ⚠️ Error en Edge TTS (Intento {attempt + 1}): {error_msg[:120]}")
            if attempt < max_retries - 1:
                print(f"   ⏳ Esperando 5 segundos antes de reintentar...")
                await asyncio.sleep(5)
    
    # ✅ FALLBACK ROBUSTO: gTTS (No suele ser bloqueado en GitHub Actions)
    print("   ⚠️ Edge TTS falló tras 3 intentos (posible bloqueo de IP de Microsoft). Activando respaldo gTTS...")
    try:
        tts = gTTS(text=texto, lang='es', slow=False)
        tts.save(ruta)
        if os.path.exists(ruta) and os.path.getsize(ruta) > 500:
            print(f"   ✅ Audio gTTS generado exitosamente como respaldo.")
            return True
        else:
            raise Exception("El archivo gTTS generado está vacío.")
    except Exception as e:
        raise Exception(f"Fallo definitivo en TTS (Edge y gTTS). Último error: {str(e)}")

def renderizar_short(signo, guion, img_path, audio_path, salida):
    dur = AudioFileClip(audio_path).duration + 0.5
    print(f"   ⏱️ Duración: {dur:.1f} seg")
    
    img = Image.open(img_path).convert("RGB")
    img = ImageEnhance.Brightness(img).enhance(1.1)
    img = ImageEnhance.Contrast(img).enhance(1.2)
    img = ImageEnhance.Color(img).enhance(1.4)
    
    draw = ImageDraw.Draw(img)
    try:
        font_nombre = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 140)
        font_mantra = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 55)
    except:
        font_nombre = font_mantra = ImageFont.load_default()
    
    draw.text((W_SHORT//2, 400), f"{signo['simbolo']} {signo['nombre'].upper()}", font=font_nombre, fill=(255, 255, 255), anchor="mm", stroke_width=12, stroke_fill=(0, 0, 0))
    draw.text((W_SHORT//2, 1600), guion.split('.')[-1].strip()[:80], font=font_mantra, fill=(255, 215, 0), anchor="mm", stroke_width=8, stroke_fill=(0, 0, 0))
    img.save("temp_short_frame.jpg")
    
    _VIG = {}
    def vignette_vert(size, base=1.0, fuerza=0.3):
        k = (size, base)
        if k not in _VIG:
            w, h = size
            y, x = np.ogrid[-1:1:h * 1j, -1:1:w * 1j]
            d = np.clip(np.sqrt(x ** 2 + y ** 2) / 1.414, 0, 1)
            _VIG[k] = ((1 - fuerza * d ** 2.2) * base).astype(np.float32)[..., None]
        return _VIG[k]
    
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
        f = 1.0
        if t < 0.5: f = t / 0.5
        if t > dur - 0.5: f = min(f, max(0.0, (dur - t) / 0.5))
        return (fr.astype(np.float32) * f).astype(np.uint8) if f < 1.0 else fr
    
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
# 6. SUBIDA
# ================================================================
def subir_short_youtube(ruta_video, datos, signo, video_largo_id, hora_utc):
    youtube = build("youtube", "v3", credentials=obtener_credenciales_youtube())
    signo_norm = normalizar_ascii(signo["nombre"])
    desc = f"{datos['descripcion']}\n\n"
    if video_largo_id:
        desc += f"🎥 VIDEOS DIARIOS, SEMANALES Y MENSUALES:\nhttps://www.youtube.com/watch?v={video_largo_id}\n\n"
    desc += f"🔔 Suscríbete: {CANAL_LINK}\n\n"
    desc += f"Este horóscopo para {signo['nombre']} revela las energías de hoy. #horoscopo #{signo_norm} #astrologia #zodiaco #shorts"
    
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
            comentario = datos["comentario_fijado"] + (f"\n\n🎥 Video completo: https://www.youtube.com/watch?v={video_largo_id}" if video_largo_id else "")
            youtube.commentThreads().insert(part="snippet", body={"snippet": {"videoId": resp['id'], "topLevelComment": {"snippet": {"textOriginal": comentario}}}}).execute()
        except: pass
    return resp['id']

# ================================================================
# 7. MAIN (CON LÍMITE DE 3 SHORTS DIARIOS)
# ================================================================
def main():
    try:
        ahora = datetime.now(TZ)
        print(f"🤖 Bot ejecutándose...")
        
        estado = cargar_estado()
        
        # ✅ VERIFICAR LÍMITE DE 3 SHORTS DIARIOS
        if len(estado.get("publicados_hoy", [])) >= MAX_SHORTS_DIARIOS:
            print(f"️ LÍMITE DIARIO ALCANZADO: Ya se publicaron {MAX_SHORTS_DIARIOS} Shorts hoy.")
            print(f"📋 Signos publicados hoy: {estado['publicados_hoy']}")
            print(f"✨ El bot se detiene aquí para no exceder el límite.")
            return
        
        signo = elegir_siguiente_signo(estado)
        print(f" Signo: {signo['simbolo']} {signo['nombre']} (Elemento: {signo['elemento']})")
        print(f" Progreso: {len(estado['publicados_hoy'])}/{MAX_SHORTS_DIARIOS} Shorts hoy")
        
        hora_actual = ahora.hour
        if 4 <= hora_actual < 6: hora_base, min_rand = ahora.replace(hour=5, minute=0, second=0, microsecond=0), random.randint(5, 50)
        elif 6 <= hora_actual < 8: hora_base, min_rand = ahora.replace(hour=7, minute=0, second=0, microsecond=0), random.randint(10, 45)
        elif 8 <= hora_actual < 10: hora_base, min_rand = ahora.replace(hour=9, minute=0, second=0, microsecond=0), random.randint(5, 40)
        else: hora_base, min_rand = ahora, random.randint(15, 45)
        
        hora_final = hora_base + timedelta(minutes=min_rand)
        hora_utc = hora_final.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print(f"📅 Programado: {hora_final:%H:%M}")
        
        video_largo_id = buscar_ultimo_video_largo()
        datos = llamar_deepseek_short(signo, datetime.now(TZ).strftime("%d de %B de %Y"))
        print(f"   📝 Título SEO: {datos.get('titulo')}")
        
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
