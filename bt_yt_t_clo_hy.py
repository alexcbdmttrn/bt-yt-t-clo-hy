# -*- coding: utf-8 -*-
"""
BT_YT_T_CLO_HY - Bot de Horóscopos Diarios (Tu Cielo Hoy) - VERSIÓN ÉLITE
Fusión de motores: Ken Burns, Miniaturas con Degradados, Reintentos de Subida y Fallback de Imágenes.
"""
import os, sys, json, time, random, base64, traceback, asyncio, re, bisect
import requests, numpy as np
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
import edge_tts
from moviepy.editor import AudioFileClip, CompositeAudioClip, VideoClip, concatenate_audioclips
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import ssl, socket

# ================================================================
# 1. CONFIGURACIÓN
# ================================================================
TZ = ZoneInfo("America/Mexico_City")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
YT_TOKEN_STR = os.getenv("YOUTUBE_USER_TOKEN")

CANAL_LINK = "https://www.youtube.com/@tucielhoy"
VOZ_CANAL = "es-MX-DaliaNeural"
ESTADO_FILE = "estado_horoscopo.json"
TITULOS_FILE = "titulos_publicados.json"

print("=" * 70)
print("🔮 BT_YT_T_CLO_HY ÉLITE - Iniciando...")
print(f"📅 Fecha: {datetime.now(TZ):%Y-%m-%d %H:%M} (CDMX)")
print("=" * 70)

if not all([DEEPSEEK_API_KEY, PEXELS_API_KEY, CF_ACCOUNT_ID, CF_API_TOKEN, YT_TOKEN_STR]):
    print("❌ ERROR: Faltan variables de entorno.")
    sys.exit(1)

# ================================================================
# 2. ESTADO Y ANTI-REPETICIÓN
# ================================================================
def cargar_json(ruta, default):
    try:
        with open(ruta, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def guardar_json(ruta, data):
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f: json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, ruta)

def titulo_ya_publicado(titulo):
    data = cargar_json(TITULOS_FILE, {"titulos": []})
    n = titulo.lower().strip()
    for t in data["titulos"]:
        if n == t.lower().strip(): return True
    return False

def guardar_titulo(titulo):
    data = cargar_json(TITULOS_FILE, {"titulos": []})
    if titulo not in data["titulos"]:
        data["titulos"].append(titulo)
    guardar_json(TITULOS_FILE, data)

# ================================================================
# 3. IA (DEEPSEEK)
# ================================================================
PROMPT_ELITE = """
Eres la astróloga más prestigiosa de YouTube. Tono: femenino, cálido, místico.
Fecha: {fecha}. Fase Lunar: {fase_lunar}.
Genera horóscopo diario para los 12 signos.

REGLAS:
1. Título: 55-65 chars. Incluye tránsito lunar y gancho (ej: "Horóscopo HOY: La Luna en {fase_lunar} exige soltar esto").
2. Descripción: 3 párrafos (Gancho, Entity stacking, CTA).
3. Tags: 15 tags cortos (máx 20 chars cada uno).
4. Comentario Fijado: Frase mística para decretar.
5. Miniatura: Prompt en inglés (fondo místico sin texto) y 2-3 palabras MAYÚSCULAS para texto (ej: "ALERTA ZODIACAL").
6. Signos: 12 signos. Cada uno: nombre, símbolo, titulo_cap (4-6 palabras), guion (~80 palabras: Energía, Amor, Dinero, Mantra 5 palabras), visual_prompt (3 palabras en inglés).

Responde SOLO JSON válido:
{
  "titulo": "...", "descripcion": "...", "tags": ["tag1"], "comentario_fijado": "...",
  "miniatura_prompt": "...", "miniatura_texto": "...",
  "signos": [
    {"nombre": "Aries", "simbolo": "", "titulo_cap": "...", "guion": "...", "visual_prompt": "red sunrise fire"},
    ... (repetir para los 12 signos en orden)
  ]
}
"""

def llamar_deepseek(fecha, fase_lunar):
    prompt = PROMPT_ELITE.format(fecha=fecha, fase_lunar=fase_lunar)
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "response_format": {"type": "json_object"}}
    
    for i in range(3):
        try:
            r = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=90)
            r.raise_for_status()
            texto = r.json()["choices"][0]["message"]["content"].strip().replace("```json", "").replace("```", "")
            return json.loads(texto)
        except Exception as e:
            print(f"⚠️ DeepSeek intento {i+1} falló: {e}")
            time.sleep(3)
    raise Exception("Fallo DeepSeek")

# ================================================================
# 4. IMÁGENES (CLOUDFLARE 3 INTENTOS + PEXELS)
# ================================================================
def generar_cf(prompt, ruta):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    clean_prompt = re.sub(r'[^a-zA-Z0-9\s,]', ' ', prompt)[:400]
    payload = {"prompt": f"{clean_prompt}, mystical, ethereal, cinematic lighting, 8k, no text", "steps": 4}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    with open(ruta, "wb") as f: f.write(base64.b64decode(r.json()["result"]["image"]))
    return ruta

def generar_pexels(query, ruta):
    headers = {"Authorization": PEXELS_API_KEY}
    r = requests.get("https://api.pexels.com/v1/search", headers=headers, params={"query": query, "orientation": "landscape", "size": "large", "per_page": 3}, timeout=15)
    r.raise_for_status()
    fotos = r.json().get("photos", [])
    if not fotos: raise Exception("Sin Pexels")
    with requests.get(fotos[0]["src"]["large2x"], stream=True, timeout=15) as r_img:
        with open(ruta, "wb") as f:
            for chunk in r_img.iter_content(8192): f.write(chunk)
    return ruta

def obtener_imagen_segura(prompt, ruta, es_miniatura=False):
    for i in range(1, 4):
        try:
            print(f"   ☁️ CF Intento {i}/3...")
            return generar_cf(prompt, ruta)
        except Exception as e:
            print(f"   ⚠️ CF falló ({i}/3)")
            time.sleep(2)
    print("   ⚠️ Activando Pexels...")
    try: return generar_pexels(prompt + " dark mystical" if es_miniatura else prompt, ruta)
    except: return None

# ================================================================
# 5. AUDIO Y MINIATURAS ÉLITE (Degradados y Banners)
# ================================================================
async def generar_audio(texto, ruta):
    await edge_tts.Communicate(texto, VOZ_CANAL, rate="-4%").save(ruta)
    return os.path.getsize(ruta) > 500

def obtener_fuente(size):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]:
        try: return ImageFont.truetype(p, size)
        except: pass
    return ImageFont.load_default()

def render_texto_gradiente(texto, font, size, top=(255, 242, 90), bottom=(255, 150, 0)):
    font = ImageFont.truetype(font, size)
    b = font.getbbox(texto)
    w, h = (b[2] - b[0]) + 20, (b[3] - b[1]) + 20
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    # Contorno negro
    d.text((10, 10), texto, font=font, fill=(10, 10, 10), stroke_width=8, stroke_fill=(10, 10, 10))
    # Degradado
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

def render_banner(texto, font, size, bg=(198, 30, 30)):
    font = ImageFont.truetype(font, size)
    b = font.getbbox(texto)
    w, h = (b[2] - b[0]) + 40, (b[3] - b[1]) + 20
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w, h], radius=10, fill=bg)
    d.text((20, 10), texto, font=font, fill=(255, 255, 255))
    return img

def crear_miniatura_elite(img_path, texto, salida):
    try:
        img = Image.open(img_path).convert("RGB").resize((1280, 720))
        img = ImageEnhance.Contrast(img).enhance(1.2).convert("RGBA")
        fuente = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        
        # Texto principal con degradado
        bloque1 = render_texto_gradiente(texto, fuente, 90)
        bloque1 = bloque1.rotate(2, expand=True)
        x = (1280 - bloque1.width) // 2
        y = (720 - bloque1.height) // 2 - 50
        
        # Banner rojo
        bloque2 = render_banner("MENSAJE DEL UNIVERSO", fuente, 40)
        bloque2 = bloque2.rotate(-2, expand=True)
        y2 = y + bloque1.height + 30
        x2 = (1280 - bloque2.width) // 2
        
        img.paste(bloque1, (x, y), bloque1)
        img.paste(bloque2, (x2, y2), bloque2)
        img.convert("RGB").save(salida, "JPEG", quality=90)
        return True
    except Exception as e:
        print(f"️ Error miniatura: {e}")
        return False

# ================================================================
# 6. RENDER DE VIDEO (KEN BURNS + VIÑETAS)
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
            # Filtro místico: bajar saturación, subir contraste
            im = ImageEnhance.Color(im).enhance(0.85)
            im = ImageEnhance.Contrast(im).enhance(1.15)
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
        if not e["zin"]: p = 1 - p # Zoom in/out alternado
        
        cw = bw / (1 + 0.2 * p)
        ch = cw * bh / bw
        mx, my = bw - cw, bh - ch
        x0 = min(max(mx / 2 + e["ax"] * mx / 2 * 0.8, 0), mx)
        y0 = min(max(my / 2 + e["ay"] * my / 2 * 0.8, 0), my)
        
        fr = np.asarray(base.resize(self.size, Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch)))
        
        # Fade in/out suave al inicio y final del video
        f = 1.0
        if e.get("fade") and lt < 0.6: f = lt / 0.6
        if t > self.total - 1.5: f = min(f, max(0.0, (self.total - t) / 1.5))
        if f < 1.0: fr = (fr.astype(np.float32) * f).astype(np.uint8)
        return fr

def renderizar_video(signos_data, salida):
    escenas = []
    t_total = 0.0
    for i, signo in enumerate(signos_data):
        img_path = f"temp_signo_{i}.jpg"
        audio_path = f"temp_audio_{i}.mp3"
        dur = AudioFileClip(audio_path).duration + 0.5 # Pausa mística
        
        # Superponer texto en la imagen
        img = Image.open(img_path).convert("RGB").resize((1920, 1080))
        draw = ImageDraw.Draw(img)
        font_t = obtener_fuente(110)
        font_s = obtener_fuente(50)
        draw.text((960, 250), f"{signo['simbolo']} {signo['nombre']}", font=font_t, fill=(255, 255, 255), anchor="mm", stroke_width=8, stroke_fill=(0,0,0))
        draw.text((960, 850), signo['guion'].split('.')[-1].strip(), font=font_s, fill=(255, 215, 0), anchor="mm", stroke_width=6, stroke_fill=(0,0,0))
        img.save(f"temp_frame_{i}.jpg")
        
        escenas.append({"path": f"temp_frame_{i}.jpg", "inicio": t_total, "dur": dur, "etapa": "mystic", 
                        "fade": i==0, "zin": i%2==0, "ax": random.uniform(-1, 1), "ay": random.uniform(-1, 1)})
        t_total += dur

    render = RenderEscenas(escenas, (1920, 1080), t_total)
    video = VideoClip(render.frame, duration=t_total)
    
    # Audio
    clips_audio = [AudioFileClip(f"temp_audio_{i}.mp3").set_start(escenas[i]["inicio"]) for i in range(len(signos_data))]
    audio_final = CompositeAudioClip(clips_audio)
    video = video.set_audio(audio_final)
    
    print(" Renderizando con Ken Burns y Viñetas...")
    video.write_videofile(salida, fps=24, codec="libx264", audio_codec="aac", threads=4, preset="ultrafast", logger=None)
    return salida

# ================================================================
# 7. SUBIDA A YOUTUBE (CON REINTENTOS EXPONENCIALES)
# ================================================================
def limpiar_tags(tags_lista):
    tags_limpios, total = [], 0
    for tag in (tags_lista or []):
        t = re.sub(r'[^\w\sáéíóúñ]', ' ', str(tag)).strip().lower()
        if 2 <= len(t) <= 30 and t not in tags_limpios:
            if total + len(t) + 1 <= 500:
                tags_limpios.append(t)
                total += len(t) + 1
    return tags_limpios or ["horoscopo diario", "astrologia", "zodiaco"]

def subir_a_youtube(ruta_video, ruta_miniatura, datos, hora_utc):
    yt_token = json.loads(YT_TOKEN_STR)
    creds = Credentials(token=yt_token.get("token"), refresh_token=yt_token.get("refresh_token"),
                        token_uri=yt_token.get("token_uri"), client_id=yt_token.get("client_id"),
                        client_secret=yt_token.get("client_secret"), scopes=yt_token.get("scopes"))
    youtube = build("youtube", "v3", credentials=creds)
    
    # Capítulos
    tiempo, caps = 0, []
    for s in datos["signos"]:
        caps.append(f"{tiempo//60:02d}:{tiempo%60:02d} {s['simbolo']} {s['nombre']}: {s['titulo_cap']}")
        tiempo += 50
    desc = f"{datos['descripcion']}\n\n⏰ CAPÍTULOS:\n" + "\n".join(caps) + f"\n\n🔔 Suscríbete: {CANAL_LINK}"
    
    body = {
        "snippet": {"title": datos["titulo"][:100], "description": desc[:5000], "tags": limpiar_tags(datos.get("tags")), "categoryId": "24", "defaultLanguage": "es"},
        "status": {"privacyStatus": "private", "publishAt": hora_utc, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    }
    
    media = MediaFileUpload(ruta_video, chunksize=4*1024*1024, resumable=True)
    req = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    
    # Reintentos robustos (Copiado del bot de Terror)
    resp, reintentos = None, 0
    while resp is None:
        try:
            st, resp = req.next_chunk()
            if st: print(f"   ⬆️ {int(st.progress() * 100)}%")
        except (HttpError, ssl.SSLError, ConnectionError, socket.timeout, OSError) as e:
            if reintentos < 8:
                reintentos += 1
                espera = 2 ** reintentos
                print(f"️ Error de red (intento {reintentos}/8). Reintentando en {espera}s...")
                time.sleep(espera)
            else:
                raise e

    video_id = resp["id"]
    print(f"✅ Video subido. ID: {video_id}")
    
    if os.path.exists(ruta_miniatura):
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(ruta_miniatura)).execute()
        print("✅ Miniatura aplicada.")
        
    youtube.commentThreads().insert(part="snippet", body={
        "snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": datos["comentario_fijado"]}}}
    }).execute()
    print("✅ Comentario fijado publicado.")
    return video_id

# ================================================================
# 8. MAIN
# ================================================================
def main():
    try:
        # Horario 5-8 AM
        ahora = datetime.now(TZ)
        hoy_inicio = ahora.replace(hour=5, minute=0, second=0, microsecond=0)
        hoy_fin = ahora.replace(hour=8, minute=0, second=0, microsecond=0)
        if ahora >= hoy_fin:
            hoy_inicio += timedelta(days=1); hoy_fin += timedelta(days=1)
        minutos_a_sumar = random.randint(0, int((hoy_fin - hoy_inicio).total_seconds() / 60))
        hora_final = hoy_inicio + timedelta(minutes=minutos_a_sumar)
        hora_utc = hora_final.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print(f"🎯 Programando para hoy a las {hora_final:%H:%M} (CDMX)")
        
        fecha_hoy = datetime.now(TZ).strftime("%d de %B de %Y")
        fase_lunar = "Creciente" # Se puede mejorar con ephem
        
        print("🧠 1. Generando contenido con DeepSeek...")
        datos = llamar_deepseek(fecha_hoy, fase_lunar)
        
        # Anti-repetición de título
        if titulo_ya_publicado(datos["titulo"]):
            print("⚠️ Título repetido, forzando variación...")
            datos["titulo"] = f"{datos['titulo']} (Edición Especial)"
        
        print(" 2. Generando activos (Imágenes y Audio)...")
        for i, signo in enumerate(datos["signos"]):
            print(f"   Procesando {signo['nombre']}...")
            obtener_imagen_segura(signo.get("visual_prompt", "mystical galaxy"), f"temp_signo_{i}.jpg")
            asyncio.run(generar_audio(signo["guion"], f"temp_audio_{i}.mp3"))
            
        print("️ 3. Creando miniatura Élite...")
        obtener_imagen_segura(datos["miniatura_prompt"], "temp_bg_thumb.jpg", es_miniatura=True)
        crear_miniatura_elite("temp_bg_thumb.jpg", datos["miniatura_texto"], "miniatura.jpg")
        
        print("🎬 4. Renderizando video...")
        renderizar_video(datos["signos"], "video_final.mp4")
        
        print("📤 5. Subiendo a YouTube con reintentos...")
        subir_a_youtube("video_final.mp4", "miniatura.jpg", datos, hora_utc)
        
        print("✨ ¡PROCESO COMPLETADO!")
        guardar_titulo(datos["titulo"])
        
        # Limpieza
        for f in os.listdir():
            if f.startswith("temp_") or f in ["video_final.mp4", "miniatura.jpg"]:
                try: os.remove(f)
                except: pass
                
    except Exception as e:
        print(f"❌ ERROR FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
