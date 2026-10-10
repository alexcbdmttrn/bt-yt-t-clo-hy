# -*- coding: utf-8 -*-
"""
BT_YT_SHORTS_CLO_HY - Bot Shorts Horóscopo (Tu Cielo Hoy) - VERSIÓN FINAL SIN ERRORES
Estrategia: 1 Short = 1 Signo, 3 Shorts al día (5AM, 7AM, 9AM CDMX).
Horarios naturales aleatorios. Títulos estilo VidIQ SEO experto.
Duración 25+ segundos. Imágenes: Cloudflare (1 intento) → Pexels.
"""
import asyncio, base64, json, os, random, re, sys, time, traceback, unicodedata
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests, numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
import edge_tts
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

CANAL_LINK = "https://www.youtube.com/@tucielhoy"
VOZ_CANAL = "es-MX-DaliaNeural"
ESTADO_FILE = "estado_shorts.json"
W_SHORT, H_SHORT, FPS = 1080, 1920, 24

SIGNOS_INFO = [
    {"nombre": "Aries", "simbolo": "♈", "elemento": "fuego"},
    {"nombre": "Tauro", "simbolo": "♉", "elemento": "tierra"},
    {"nombre": "Géminis", "simbolo": "♊", "elemento": "aire"},
    {"nombre": "Cáncer", "simbolo": "♋", "elemento": "agua"},
    {"nombre": "Leo", "simbolo": "♌", "elemento": "fuego"},
    {"nombre": "Virgo", "simbolo": "♍", "elemento": "tierra"},
    {"nombre": "Libra", "simbolo": "", "elemento": "aire"},
    {"nombre": "Escorpio", "simbolo": "♏", "elemento": "agua"},
    {"nombre": "Sagitario", "simbolo": "♐", "elemento": "fuego"},
    {"nombre": "Capricornio", "simbolo": "♑", "elemento": "tierra"},
    {"nombre": "Acuario", "simbolo": "♒", "elemento": "aire"},
    {"nombre": "Piscis", "simbolo": "♓", "elemento": "agua"}
]

HASHTAGS_SHORTS = "\n\n#shorts #horoscopo #zodiaco #astrologia #tucielhoy #mensajeDelUniverso #energiaDelDia"

def normalizar_ascii(texto):
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()

def construir_tags_shorts_experto(signo):
    signo_norm = normalizar_ascii(signo["nombre"])
    tags_expertos = [
        "shorts", "horoscopo", "horoscopo de hoy", "zodiaco", "astrologia",
        "tu cielo hoy", "mensaje del universo", "energia del dia",
        signo_norm, f"horoscopo {signo_norm}", f"{signo_norm} hoy",
        "prediccion zodiacal", "signos del zodiaco", "crecimiento espiritual",
        "mantra del dia", "fase lunar", "amor y dinero", "señales del universo",
        "secretos del cosmos", "energia zodiacal", "alerta zodiacal",
        f"horoscopo {signo_norm} amor", f"horoscopo {signo_norm} dinero",
        "mensaje urgente zodiaco", "revelacion cosmica"
    ]
    tags_validos = [t for t in tags_expertos if 2 <= len(t) <= 30]
    return tags_validos[:15]

print("=" * 70)
print("📱 BT_YT_SHORTS_CLO_HY - Bot Shorts Horóscopo (Horarios Naturales)")
print(f"📅 {datetime.now(TZ):%Y-%m-%d %H:%M} (CDMX)")
print("=" * 70)

if not all([DEEPSEEK_API_KEY, PEXELS_API_KEY, CF_ACCOUNT_ID, CF_API_TOKEN, YT_TOKEN_STR]):
    print("❌ ERROR: Faltan variables de entorno en los Secrets de GitHub.")
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
                return {"fecha": hoy, "publicados": [], "contador": 0}
            return data
    except:
        return {"fecha": datetime.now(TZ).strftime("%Y-%m-%d"), "publicados": [], "contador": 0}

def guardar_estado(data):
    with open(ESTADO_FILE + ".tmp", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(ESTADO_FILE + ".tmp", ESTADO_FILE)

def elegir_siguiente_signo(estado):
    publicados = set(estado.get("publicados", []))
    pendientes = [s for s in SIGNOS_INFO if s["nombre"] not in publicados]
    if not pendientes:
        print("🔄 Los 12 signos ya fueron publicados hoy. Reiniciando ciclo...")
        return random.choice(SIGNOS_INFO), True
    signo = random.choice(pendientes)
    return signo, False

# ================================================================
# 3. BUSCAR ÚLTIMO VIDEO LARGO DEL CANAL
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
        request = youtube.search().list(
            part="snippet", forMine=True, type="video", maxResults=5, order="date"
        )
        response = request.execute()
        for item in response.get("items", []):
            video_id = item["id"]["videoId"]
            stats = youtube.videos().list(part="contentDetails,snippet", id=video_id).execute()
            if stats.get("items"):
                duration = stats["items"][0]["contentDetails"]["duration"]
                if "M" in duration:
                    title = stats["items"][0]["snippet"]["title"]
                    print(f"🎬 Último video largo detectado: {title[:50]}...")
                    return video_id
        return None
    except Exception as e:
        print(f"⚠️ No se pudo buscar el último video largo: {e}")
        return None

# ================================================================
# 4. IA (DEEPSEEK) - PROMPT SEO EXPERTO ✅ CORREGIDO
# ================================================================
# ⚠️ IMPORTANTE: Todos los placeholders van en MINÚSCULAS: {signo}, {simbolo}, {elemento}, {signo_lower}
PROMPT_SHORT_SEO = """
Eres la astróloga más prestigiosa de YouTube y EXPERTA EN SEO. Tono: femenino, cálido, místico, URGENTE.
Fecha: {fecha}. Signo: {signo} ({simbolo}). Elemento: {elemento}.

Genera un guion para un YouTube SHORT de 25-30 segundos sobre {signo}.

REGLAS CRÍTICAS DE SEO EXPERTO (ESTILO VIDIO):

1. TÍTULO (60-80 caracteres): Debe seguir UNA de estas fórmulas de alto CTR:
   - Fórmula A: "Señales claras para {signo}: [Beneficio] #{signo_lower} #[tema] #astrologia"
   - Fórmula B: "Secretos del cosmos para {signo} hoy #{signo_lower} #astrologia #zodiaco"
   - Fórmula C: "Atención {signo}: No ignores este mensaje #{signo_lower} #astrologia #mensaje"
   - Fórmula D: "La energía de {signo} está imparable hoy #{signo_lower} #energia #horoscopo"
   - Fórmula E: "{signo}: El universo te envía una señal urgente #{signo_lower} #horoscopo #astrologia"
   Usa palabras de alto impacto: señales, secretos, mensaje urgente, no ignores, el universo, energía, dinero, amor, pasión, cosmos.
   INCLUYE 3 hashtags al final del título.

2. GUION (65-80 palabras para durar 25-30 segundos). Estructura:
   - Gancho (3-4 seg): "{signo}, este mensaje del universo es solo para ti..."
   - Mensaje flash (15 seg): Energía del día, amor/relaciones, dinero/trabajo en frases cortas y poderosas
   - Mantra (4 seg): Frase de 5-7 palabras para decretar
   - CTA (5 seg): "Para ver los otros 11 signos, ve al video completo en mi canal"

3. DESCRIPCIÓN (2-3 líneas): Frase mística + CTA al video largo + 3 hashtags.

4. COMENTARIO FIJADO: Pregunta corta para que los seguidores comenten su signo y decreten.

5. IMAGEN: Prompt en inglés (vertical, vibrante, místico, sin texto).

Responde SOLO JSON:
{{
  "titulo": "Señales claras para {signo}: Dinero y pasión #{signo_lower} #dinero #astrologia",
  "descripcion": "...",
  "comentario_fijado": "...",
  "guion": "...",
  "visual_prompt": "vertical mystical {elemento} energy, vibrant glowing, 8k, cinematic"
}}
"""

def llamar_deepseek_short(signo, fecha):
    # ✅ CORRECCIÓN CLAVE: signo_lower se calcula ANTES del format
    signo_lower = normalizar_ascii(signo["nombre"])
    
    prompt = PROMPT_SHORT_SEO.format(
        fecha=fecha,
        signo=signo["nombre"],
        simbolo=signo["simbolo"],
        elemento=signo["elemento"],
        signo_lower=signo_lower
    )
    
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "response_format": {"type": "json_object"}
    }
    
    for i in range(3):
        try:
            print(f"    Intento {i+1}/3 con DeepSeek para {signo['nombre']}...")
            r = requests.post("https://api.deepseek.com/v1/chat/completions", 
                            headers=headers, json=payload, timeout=60)
            r.raise_for_status()
            texto = r.json()["choices"][0]["message"]["content"].strip()
            t = re.sub(r"```(?:json)?", " ", texto, flags=re.I)
            i_json, j_json = t.find("{"), t.rfind("}")
            if i_json == -1 or j_json == -1: raise ValueError("sin JSON")
            datos = json.loads(t[i_json:j_json + 1], strict=False)
            
            palabras = len(datos.get("guion", "").split())
            if palabras < 55 or palabras > 90:
                raise ValueError(f"Guion con {palabras} palabras (debe ser 65-80 para 25+ seg)")
            
            titulo = datos.get("titulo", "")
            if "#" not in titulo:
                print(f"⚠️ Título sin hashtags, añadiendo automáticamente...")
                datos["titulo"] = f"{titulo} #{signo_lower} #astrologia #horoscopo"
            
            return datos
        except Exception as e:
            print(f"⚠️ DeepSeek intento {i+1} falló: {e}")
            time.sleep(2)
    raise Exception("Fallo DeepSeek tras 3 intentos")

# ================================================================
# 5. IMÁGENES (CLOUDFLARE 1 INTENTO → PEXELS)
# ================================================================
def generar_cf_vertical(prompt, ruta):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    
    clean_prompt = re.sub(r'[^a-zA-Z\s]', ' ', prompt)[:100]
    clean_prompt = ' '.join(clean_prompt.split())
    safe_prompt = f"{clean_prompt}, vertical composition, mystical, vibrant colors, 8k, highly detailed, no text, no watermark"
    
    payload = {"prompt": safe_prompt, "steps": 4}
    
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        if r.status_code != 200:
            print(f"   ❌ Cloudflare HTTP {r.status_code}: {r.text[:200]}")
        r.raise_for_status()
        
        result = r.json()
        if "result" not in result or "image" not in result["result"]:
            raise ValueError(f"Sin imagen: {str(result)[:200]}")
            
        with open(ruta, "wb") as f:
            f.write(base64.b64decode(result["result"]["image"]))
        
        with Image.open(ruta) as im:
            im = im.convert("RGB")
            w, h = im.size
            target_ratio = 9/16
            current_ratio = w/h
            if current_ratio > target_ratio:
                new_w = int(h * target_ratio)
                left = (w - new_w) // 2
                im = im.crop((left, 0, left + new_w, h))
            else:
                new_h = int(w / target_ratio)
                top = (h - new_h) // 2
                im = im.crop((0, top, w, top + new_h))
            im = im.resize((W_SHORT, H_SHORT), Image.LANCZOS)
            im.save(ruta, "JPEG", quality=92)
        return ruta
        
    except Exception as e:
        print(f"   ❌ Cloudflare falló: {e}")
        raise

def generar_pexels_vertical(query, ruta):
    headers = {"Authorization": PEXELS_API_KEY}
    r = requests.get("https://api.pexels.com/v1/search", headers=headers, 
                    params={"query": query, "orientation": "portrait", "size": "large", "per_page": 5}, 
                    timeout=15)
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

def obtener_imagen_short(prompt, ruta):
    try:
        print(f"   ☁️ CF Intento 1/1...")
        return generar_cf_vertical(prompt, ruta)
    except Exception as e:
        print(f"   ⚠️ CF falló, usando Pexels...")
    
    try:
        query = prompt + " mystical cosmic vibrant"
        return generar_pexels_vertical(query, ruta)
    except Exception as e:
        print(f"   ❌ Pexels también falló: {e}")
        return None

# ================================================================
# 6. AUDIO Y RENDERIZADO VERTICAL
# ================================================================
async def generar_audio(texto, ruta):
    await edge_tts.Communicate(texto, VOZ_CANAL, rate="-2%").save(ruta)
    return os.path.getsize(ruta) > 500

def renderizar_short(signo, guion, img_path, audio_path, salida):
    dur = AudioFileClip(audio_path).duration + 0.5
    print(f"   ⏱️ Duración del audio: {dur:.1f} segundos")
    
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
    
    texto_nombre = f"{signo['simbolo']} {signo['nombre'].upper()}"
    draw.text((W_SHORT//2, 400), texto_nombre, font=font_nombre, 
              fill=(255, 255, 255), anchor="mm", stroke_width=12, stroke_fill=(0, 0, 0))
    
    mantra = guion.split('.')[-1].strip()[:80]
    draw.text((W_SHORT//2, 1600), mantra, font=font_mantra, 
              fill=(255, 215, 0), anchor="mm", stroke_width=8, stroke_fill=(0, 0, 0))
    
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
        x0 = mx / 2
        y0 = my / 2 + (my * 0.3 * p)
        fr = np.asarray(base.resize((W_SHORT, H_SHORT), Image.BILINEAR, 
                                    box=(x0, y0, x0 + cw, y0 + ch)))
        
        f = 1.0
        if t < 0.5: f = t / 0.5
        if t > dur - 0.5: f = min(f, max(0.0, (dur - t) / 0.5))
        if f < 1.0: fr = (fr.astype(np.float32) * f).astype(np.uint8)
        return fr
    
    video = VideoClip(frame, duration=dur)
    audio = AudioFileClip(audio_path)
    
    musicas = [f for f in os.listdir(".") if f.lower().endswith(".mp3") and not f.startswith("temp_")]
    if musicas:
        musica = random.choice(musicas)
        try:
            bg = AudioFileClip(musica)
            if bg.duration < dur:
                bg = concatenate_audioclips([bg] * (int(dur / bg.duration) + 1))
            audio_final = CompositeAudioClip([audio, bg.subclip(0, dur).volumex(0.08).audio_fadein(2).audio_fadeout(2)])
            print(f"🎵 Música de fondo: {musica}")
        except:
            audio_final = audio
    else:
        audio_final = audio
    
    video = video.set_audio(audio_final)
    print("🎬 Renderizando Short vertical...")
    video.write_videofile(salida, fps=FPS, codec="libx264", audio_codec="aac", 
                         threads=4, preset="ultrafast", logger=None)
    return salida

# ================================================================
# 7. SUBIDA A YOUTUBE COMO SHORT
# ================================================================
def subir_short_youtube(ruta_video, datos, signo, video_largo_id, hora_utc):
    youtube = build("youtube", "v3", credentials=obtener_credenciales_youtube())
    
    desc = f"{datos['descripcion']}\n\n"
    if video_largo_id:
        desc += f"🎥 VIDEO COMPLETO DE HOY:\nhttps://www.youtube.com/watch?v={video_largo_id}\n\n"
    desc += f"🔔 Suscríbete: {CANAL_LINK}{HASHTAGS_SHORTS}\n\n#{normalizar_ascii(signo['nombre'])}"
    
    tags = construir_tags_shorts_experto(signo)
    
    body = {
        "snippet": {
            "title": datos["titulo"][:100],
            "description": desc[:5000],
            "tags": tags,
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
    
    media = MediaFileUpload(ruta_video, chunksize=4*1024*1024, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    resp, reintentos = None, 0
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st: print(f"   ⬆️ {int(st.progress() * 100)}%")
        except (HttpError, ssl.SSLError, ConnectionError, socket.timeout, OSError) as e:
            if reintentos < 8:
                reintentos += 1
                print(f"⚠️ Reintentando ({reintentos}/8)...")
                time.sleep(2 ** reintentos)
            else: raise e
    
    video_id = resp["id"]
    print(f"✅ Short subido. ID: {video_id}")
    
    if datos.get("comentario_fijado"):
        try:
            comentario = datos["comentario_fijado"]
            if video_largo_id:
                comentario += f"\n\n🎥 Video completo: https://www.youtube.com/watch?v={video_largo_id}"
            youtube.commentThreads().insert(part="snippet", body={
                "snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": comentario}}}
            }).execute()
            print("✅ Comentario fijado publicado.")
        except HttpError as e:
            print(f"⚠️ Error comentario: {e}")
    
    return video_id

# ================================================================
# 8. MAIN - CON HORARIOS NATURALES ALEATORIOS
# ================================================================
def main():
    try:
        ahora = datetime.now(TZ)
        print(f"🤖 Bot Shorts ejecutándose...")
        
        # Cargar estado y elegir signo
        estado = cargar_estado()
        signo, reinicio = elegir_siguiente_signo(estado)
        print(f"🎯 Signo elegido: {signo['simbolo']} {signo['nombre']}")
        
        # ✅ HORARIOS NATURALES ALEATORIOS
        hora_actual = ahora.hour
        
        if 4 <= hora_actual < 6:
            # Ventana de 5 AM: publicar entre 5:05 y 5:50 AM
            hora_base = ahora.replace(hour=5, minute=0, second=0, microsecond=0)
            minutos_aleatorios = random.randint(5, 50)
        elif 6 <= hora_actual < 8:
            # Ventana de 7 AM: publicar entre 7:10 y 7:45 AM
            hora_base = ahora.replace(hour=7, minute=0, second=0, microsecond=0)
            minutos_aleatorios = random.randint(10, 45)
        elif 8 <= hora_actual < 10:
            # Ventana de 9 AM: publicar entre 9:05 y 9:40 AM
            hora_base = ahora.replace(hour=9, minute=0, second=0, microsecond=0)
            minutos_aleatorios = random.randint(5, 40)
        else:
            # Fallback: 15-45 minutos desde ahora
            hora_base = ahora
            minutos_aleatorios = random.randint(15, 45)
        
        hora_final = hora_base + timedelta(minutes=minutos_aleatorios)
        hora_utc = hora_final.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print(f" Programado para: {hora_final:%H:%M} (CDMX) - Horario natural aleatorio")
        
        # Buscar último video largo para enlazar
        print("🔍 Buscando último video largo del canal...")
        video_largo_id = buscar_ultimo_video_largo()
        
        # Generar contenido con DeepSeek
        fecha_hoy = datetime.now(TZ).strftime("%d de %B de %Y")
        print(f"🧠 1. Generando guion SEO experto para {signo['nombre']}...")
        datos = llamar_deepseek_short(signo, fecha_hoy)
        print(f"   📝 Título SEO: {datos.get('titulo', 'N/A')}")
        print(f"   📊 Palabras del guion: {len(datos.get('guion', '').split())}")
        
        # Generar imagen y audio
        print(" 2. Generando activos...")
        obtener_imagen_short(datos.get("visual_prompt", f"vertical mystical {signo['elemento']} energy"), "temp_short_img.jpg")
        asyncio.run(generar_audio(datos["guion"], "temp_short_audio.mp3"))
        
        # Renderizar Short
        print("🎬 3. Renderizando Short...")
        renderizar_short(signo, datos["guion"], "temp_short_img.jpg", "temp_short_audio.mp3", "short_final.mp4")
        
        # Subir a YouTube
        print("📤 4. Subiendo a YouTube...")
        subir_short_youtube("short_final.mp4", datos, signo, video_largo_id, hora_utc)
        
        # Actualizar estado
        estado["publicados"].append(signo["nombre"])
        estado["contador"] += 1
        guardar_estado(estado)
        
        print(f"✨ ¡SHORT COMPLETADO! {signo['nombre']} programado para {hora_final:%H:%M}")
        
        # Limpieza
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
