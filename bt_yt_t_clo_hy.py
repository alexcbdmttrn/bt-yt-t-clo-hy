# -*- coding: utf-8 -*-
"""
BT_YT_T_CLO_HY - Bot Horóscopo Master (Tu Cielo Hoy) - VERSIÓN ÉLITE x10 (CORREGIDA TAGS)
Fix: Cálculo exacto de longitud de tags para la API de YouTube (sin contar comas), 
     Títulos indican "12 Signos", Prompts 'Safe', Texto de miniatura 100% variable.
"""
import asyncio, base64, bisect, json, os, random, re, ssl, socket, sys, time, traceback, unicodedata
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

CANAL_LINK = "https://www.youtube.com/@tucielhoy"
VOZ_CANAL = "es-MX-DaliaNeural"
TITULOS_FILE = "titulos_publicados.json"
W, H, FPS = 1920, 1080, 24

# ================================================================
# 🏷️ MOTOR DE TAGS SEO PREMIUM (NIVEL VIDIQ x10 - CÁLCULO EXACTO)
# ================================================================
TAGS_GENERALES_SIEMPRE = [
    "horoscopo", "horoscopo diario", "astrologia", "zodiaco", "tu cielo hoy",
    "aries", "tauro", "geminis", "cancer", "leo", "virgo", "libra", "escorpio",
    "sagitario", "capricornio", "acuario", "piscis", "mensaje del universo",
    "energia del dia", "fase lunar", "crecimiento espiritual", "bienestar",
    "lectura de tarot", "carta astral", "prediccion astral"
]

TAGS_POR_MODO = {
    "daily": ["horoscopo de hoy", "horoscopo hoy", "prediccion de hoy", "energia de hoy", "mensaje de hoy", "horoscopo completo"],
    "weekly": ["horoscopo semanal", "horoscopo de la semana", "semana astral", "prediccion semanal", "tendencias zodiacales"],
    "monthly": ["horoscopo mensual", "horoscopo del mes", "prediccion mensual", "ciclo lunar", "luna llena", "luna nueva"]
}

HASHTAGS_YOUTUBE = "\n\n#Horoscopo #Astrologia #Zodiaco #TuCieloHoy #MensajeDelUniverso #HoroscopoDeHoy #EnergiaDelDia #SignosDelZodiaco"

def normalizar_ascii(texto):
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()

def construir_tags_finales(tags_dinamicos_ia, modo="daily"):
    tags_finales = []
    total_chars = 0
    
    todas_las_fuentes = list(TAGS_GENERALES_SIEMPRE) + list(TAGS_POR_MODO.get(modo, []))
    if isinstance(tags_dinamicos_ia, list):
        todas_las_fuentes.extend(tags_dinamicos_ia)
    
    for tag in todas_las_fuentes:
        # 1. Normalizar y limpiar a fondo
        tag_limpio = normalizar_ascii(str(tag)).strip()
        # SOLO permitir letras, números y espacios (elimina acentos y símbolos)
        tag_limpio = re.sub(r'[^a-z0-9\s]', '', tag_limpio)
        tag_limpio = re.sub(r'\s+', ' ', tag_limpio).strip()
        
        # 2. Validar longitud de cada tag (YouTube pide entre 2 y 30 caracteres)
        if 2 <= len(tag_limpio) <= 30 and tag_limpio not in tags_finales:
            # ✅ CORRECCIÓN: YouTube cuenta la longitud de las cadenas, NO las comas.
            # Usamos 480 como límite seguro (el máximo absoluto es 500).
            if total_chars + len(tag_limpio) <= 480:
                tags_finales.append(tag_limpio)
                total_chars += len(tag_limpio)
                
    print(f"🏷️ Tags finales: {len(tags_finales)} tags, {total_chars}/480 caracteres")
    print(f"   Tags enviados a YouTube: {', '.join(tags_finales)}")
    return tags_finales

print("=" * 70)
print("🔮 BT_YT_T_CLO_HY MASTER - VERSIÓN ÉLITE x10 (CORREGIDA)")
print(f"📅 {datetime.now(TZ):%Y-%m-%d %H:%M} (CDMX)")
print("=" * 70)

if not all([DEEPSEEK_API_KEY, PEXELS_API_KEY, CF_ACCOUNT_ID, CF_API_TOKEN, YT_TOKEN_STR]):
    print("❌ ERROR: Faltan variables de entorno en los Secrets de GitHub.")
    sys.exit(1)

# ================================================================
# 2. UTILIDADES Y ESTADO
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
    return any(n == t.lower().strip() for t in data["titulos"])

def guardar_titulo(titulo):
    data = cargar_json(TITULOS_FILE, {"titulos": []})
    if titulo not in data["titulos"]:
        data["titulos"].append(titulo)
    guardar_json(TITULOS_FILE, data)

def parsear_json(texto):
    t = re.sub(r"```(?:json)?", " ", texto, flags=re.I)
    i, j = t.find("{"), t.rfind("}")
    if i == -1 or j == -1: raise ValueError("sin JSON")
    return json.loads(t[i:j + 1], strict=False)

# ================================================================
# 3. IA (DEEPSEEK) - PROMPTS SEO PREMIUM VIRAL
# ================================================================
PROMPT_DIARIO = """
Eres la astróloga más prestigiosa de YouTube y EXPERTA EN SEO Viral (Nivel VidIQ x10). Tono: femenino, cálido, místico, URGENTE.
Fecha: {fecha}. Fase Lunar: {fase_lunar}.
Genera horóscopo DIARIO para los 12 signos.

REGLAS CRÍTICAS DE SEO Y RETENCIÓN (ANTI-REPETICIÓN EXTREMA):
1. TÍTULO (Máx 70 chars, Alto CTR y 100% ÚNICO): DEBE dejar claro que es un horóscopo para los 12 SIGNOS. NO pongas un solo signo en el título principal.
   - Estructuras: "🔮 HORÓSCOPO HOY: La [Palabra de Poder] para los 12 Signos | [Tránsito]", "⚠️ ALERTA ZODIACAL: Lo que el cosmos revela a los 12 Signos hoy | [Tránsito]", "✨ HORÓSCOPO COMPLETO: Un [Tema] inesperado espera a los 12 Signos | [Tránsito]", "💫 VERDAD OCULTA: El mensaje urgente que los 12 Signos necesitan HOY | [Tránsito]"
   - Palabras de Poder: Revelación, Alerta, Secreto, Impactante, Verdad, Destino, Prohibido, Urgente, Sorpresa.
   - Temas: Amor, Dinero, Karma, Suerte, Destino, Cambio.
   - Tránsito: ej: "Luna en Cáncer", "Mercurio en Géminis", etc.

2. DESCRIPCIÓN (SEO Enriquecido x10): 3 párrafos. 
   - P1: Gancho emocional mencionando "horóscopo diario para los 12 signos", "mensaje del universo" y la energía de hoy.
   - P2: Lista de lo que encontrarán (amor, dinero, salud, mantra) usando lenguaje natural y persuasivo.
   - P3: Llamado a la acción fuerte para suscribirse y comentar su signo para decretar.

3. GUION: 90-110 palabras por signo. DEBE comenzar con: "[Signo], hoy la energía..." y ser único.

4. IMÁGENES Y MINIATURA (ARTE DIGITAL PREMIUM Y VARIABLE): 
   - visual_prompt: Debe ser una descripción de "Arte Digital Premium" (ej: "masterpiece, radiant cosmic energy, volumetric lighting, vibrant color grading, hyper-detailed, 8k, trending on ArtStation, no text").
   - miniatura_prompt: Similar, enfocado en alta calidad visual y colores vibrantes.
   - miniatura_texto: 2-3 palabras MAYÚSCULAS de ALTO IMPACTO y ÚNICAS para el día. ¡PROHIBIDO repetir siempre "VERDAD OCULTA"! Elige una diferente según el tema: "CAMBIO RADICAL", "DINERO INESPERADO", "ALERTA AMOR", "TU DESTINO", "SEÑAL URGENTE", "NUEVA ETAPA", "KARMA ACTIVO".
   - miniatura_banner: 2-3 palabras que complementen: "PARA LOS 12 SIGNOS", "HORÓSCOPO DE HOY", "MENSAJE DEL UNIVERSO", "PREDICCIÓN ASTROLÓGICA".

Responde SOLO JSON:
{{
  "titulo": "🔮 HORÓSCOPO HOY: La Revelación Impactante para los 12 Signos | Luna en Cáncer",
  "descripcion": "...",
  "tags": ["horoscopo diario", "mensaje del universo", "prediccion astral", "horoscopo completo"],
  "comentario_fijado": "✨ ¿Sientes esta energía? Escribe 'HECHO ESTÁ' y tu signo en los comentarios para decretar.",
  "miniatura_prompt": "masterpiece, radiant cosmic energy, volumetric lighting, hyper-detailed, 8k resolution, trending on ArtStation, no text, no watermark",
  "miniatura_texto": "CAMBIO RADICAL",
  "miniatura_banner": "PARA LOS 12 SIGNOS",
  "signos": [
    {{"nombre": "Aries", "simbolo": "♈", "titulo_cap": "Chispa de Valentía", "guion": "Aries, hoy la energía...", "visual_prompt": "masterpiece, radiant cosmic flames and golden embers, dramatic volumetric lighting, vibrant red and orange color grading, mystical fire energy, highly detailed, 8k resolution, cinematic composition, no text"}},
    {{"nombre": "Tauro", "simbolo": "♉", "titulo_cap": "Siembra de Abundancia", "guion": "Tauro, hoy la tierra...", "visual_prompt": "masterpiece, lush enchanted forest with radiant golden sunlight beams, vibrant emerald and gold color palette, magical glowing crystals, highly detailed, 8k, cinematic, no text"}},
    {{"nombre": "Géminis", "simbolo": "♊", "titulo_cap": "Comunicación Estelar", "guion": "Géminis, tu mente...", "visual_prompt": "masterpiece, swirling ethereal aurora borealis with electric cyan and silver, cosmic wind energy, vibrant sky with beautiful stars, highly detailed, 8k, cinematic, no text"}},
    {{"nombre": "Cáncer", "simbolo": "♋", "titulo_cap": "Marea Emocional", "guion": "Cáncer, tu intuición...", "visual_prompt": "masterpiece, deep mystical ocean with bioluminescent glowing creatures, vibrant turquoise and deep purple color grading, magical underwater light rays, 8k, no text"}},
    {{"nombre": "Leo", "simbolo": "♌", "titulo_cap": "Brillo Real", "guion": "Leo, tu carisma...", "visual_prompt": "masterpiece, radiant cosmic flames and golden embers, dramatic volumetric lighting, vibrant red and orange color grading, mystical fire energy, highly detailed, 8k, no text"}},
    {{"nombre": "Virgo", "simbolo": "♍", "titulo_cap": "Detalle Perfecto", "guion": "Virgo, el orden...", "visual_prompt": "masterpiece, lush enchanted forest with radiant golden sunlight beams, vibrant emerald and gold color palette, magical glowing crystals, highly detailed, 8k, no text"}},
    {{"nombre": "Libra", "simbolo": "♎", "titulo_cap": "Armonía Renovada", "guion": "Libra, el equilibrio...", "visual_prompt": "masterpiece, swirling ethereal aurora borealis with electric cyan and silver, cosmic wind energy, vibrant sky with beautiful stars, highly detailed, 8k, no text"}},
    {{"nombre": "Escorpio", "simbolo": "♏", "titulo_cap": "Poder Transformador", "guion": "Escorpio, tu intensidad...", "visual_prompt": "masterpiece, deep mystical ocean with bioluminescent glowing creatures, vibrant turquoise and deep purple color grading, magical underwater light rays, 8k, no text"}},
    {{"nombre": "Sagitario", "simbolo": "♐", "titulo_cap": "Aventura Cósmica", "guion": "Sagitario, tu libertad...", "visual_prompt": "masterpiece, radiant cosmic flames and golden embers, dramatic volumetric lighting, vibrant red and orange color grading, mystical fire energy, highly detailed, 8k, no text"}},
    {{"nombre": "Capricornio", "simbolo": "♑", "titulo_cap": "Construcción Sólida", "guion": "Capricornio, tu disciplina...", "visual_prompt": "masterpiece, lush enchanted forest with radiant golden sunlight beams, vibrant emerald and gold color palette, magical glowing crystals, highly detailed, 8k, no text"}},
    {{"nombre": "Acuario", "simbolo": "♒", "titulo_cap": "Visión Innovadora", "guion": "Acuario, tu originalidad...", "visual_prompt": "masterpiece, swirling ethereal aurora borealis with electric cyan and silver, cosmic wind energy, vibrant sky with beautiful stars, highly detailed, 8k, no text"}},
    {{"nombre": "Piscis", "simbolo": "♓", "titulo_cap": "Sueño Profético", "guion": "Piscis, tu sensibilidad...", "visual_prompt": "masterpiece, deep mystical ocean with bioluminescent glowing creatures, vibrant turquoise and deep purple color grading, magical underwater light rays, 8k, no text"}}
  ]
}}
"""

PROMPT_SEMANAL = PROMPT_DIARIO.replace("DIARIO", "SEMANAL").replace("90-110 palabras", "150-180 palabras").replace("horóscopo diario", "horóscopo semanal")
PROMPT_MENSUAL = PROMPT_DIARIO.replace("DIARIO", "MENSUAL").replace("90-110 palabras", "250-300 palabras").replace("horóscopo diario", "horóscopo mensual")

def llamar_deepseek(fecha, fase_lunar, modo="daily"):
    if modo == "weekly": prompt = PROMPT_SEMANAL
    elif modo == "monthly": prompt = PROMPT_MENSUAL
    else: prompt = PROMPT_DIARIO
    
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.95, "response_format": {"type": "json_object"}}
    
    for i in range(3):
        try:
            print(f"    Intento {i+1}/3 con DeepSeek (modo {modo})...")
            r = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=180)
            r.raise_for_status()
            datos = parsear_json(r.json()["choices"][0]["message"]["content"].strip())
            if len(datos.get("signos", [])) != 12:
                raise ValueError(f"La IA solo generó {len(datos.get('signos', []))} signos.")
            nombres_generados = [s["nombre"].lower() for s in datos["signos"]]
            nombres_esperados = ["aries", "tauro", "géminis", "cáncer", "leo", "virgo", "libra", "escorpio", "sagitario", "capricornio", "acuario", "piscis"]
            if set(nombres_generados) != set(nombres_esperados):
                raise ValueError("La IA repitió signos o faltan algunos.")
            return datos
        except Exception as e:
            print(f"⚠️ DeepSeek intento {i+1} falló: {e}")
            time.sleep(3)
    raise Exception("Fallo DeepSeek tras 3 intentos")

# ================================================================
# 4. IMÁGENES (2 INTENTOS CLOUDFLARE → PEXELS INMEDIATO)
# ================================================================
def generar_cf(prompt, ruta):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    clean_prompt = re.sub(r'[^a-zA-Z\s]', ' ', prompt)[:150]
    clean_prompt = ' '.join(clean_prompt.split())
    payload = {"prompt": clean_prompt, "steps": 4}
    
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code != 200:
        print(f"   ❌ Cloudflare HTTP {r.status_code}: {r.text[:200]}")
    r.raise_for_status()
    
    result = r.json()
    if "result" not in result or "image" not in result["result"]:
        raise ValueError(f"Respuesta sin imagen: {str(result)[:200]}")
        
    with open(ruta, "wb") as f:
        f.write(base64.b64decode(result["result"]["image"]))
    with Image.open(ruta) as im:
        im = ImageOps.fit(im.convert("RGB"), (W, H), Image.LANCZOS)
        im.save(ruta, "JPEG", quality=95)
    return ruta

def generar_pexels(query, ruta):
    headers = {"Authorization": PEXELS_API_KEY}
    r = requests.get("https://api.pexels.com/v1/search", headers=headers, params={"query": query, "orientation": "landscape", "size": "large", "per_page": 5}, timeout=15)
    r.raise_for_status()
    fotos = r.json().get("photos", [])
    if not fotos: raise Exception("Sin Pexels")
    with requests.get(fotos[0]["src"]["large2x"], stream=True, timeout=15) as r_img:
        with open(ruta, "wb") as f:
            for chunk in r_img.iter_content(8192): f.write(chunk)
    with Image.open(ruta) as im:
        im = ImageOps.fit(im.convert("RGB"), (W, H), Image.LANCZOS)
        im.save(ruta, "JPEG", quality=95)
    return ruta

def obtener_imagen_segura(prompt, ruta, es_miniatura=False):
    for i in range(1, 3):
        try:
            print(f"   ☁️ CF Intento {i}/2 (Arte Premium)...")
            return generar_cf(prompt, ruta)
        except Exception as e:
            print(f"   ⚠️ CF intento {i} falló: {str(e)[:100]}")
            time.sleep(2)
    
    print("   ⚠️ CF agotado, usando Pexels como respaldo...")
    try:
        query = prompt + " bright vibrant mystical" if es_miniatura else prompt + " vivid cinematic"
        return generar_pexels(query, ruta)
    except Exception as e:
        print(f"   ❌ Pexels también falló: {e}")
        return None

# ================================================================
# 5. AUDIO (CON REINTENTOS ANTI-403 + FALLBACK gTTS) Y MINIATURAS
# ================================================================
async def generar_audio(texto, ruta):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            print(f"   🎤 Generando audio con Edge TTS (Intento {attempt + 1}/{max_retries})...")
            communicate = edge_tts.Communicate(texto, VOZ_CANAL, rate="-4%")
            await communicate.save(ruta)
            if os.path.exists(ruta) and os.path.getsize(ruta) > 500:
                print(f"   ✅ Audio Edge TTS generado exitosamente.")
                return True
        except Exception as e:
            error_msg = str(e)
            print(f"   ⚠️ Error en Edge TTS (Intento {attempt + 1}): {error_msg[:150]}")
            if attempt < max_retries - 1:
                print(f"   ⏳ Esperando 5 segundos antes de reintentar (posible bloqueo temporal de Microsoft)...")
                await asyncio.sleep(5)
    
    print("   ⚠️ Edge TTS falló tras 3 intentos. Activando respaldo gTTS (Google)...")
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
        if len(palabras) > 4:
            texto_principal = " ".join(palabras[:4])
        
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
        print(f"✅ Miniatura 8K Brillante generada: {salida}")
        return True
    except Exception as e:
        print(f"⚠️ Error en miniatura 8K: {e}")
        return False

# ================================================================
# 6. RENDER DE VIDEO
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
        if not e["zin"]: p = 1 - p
        cw = bw / (1 + 0.2 * p)
        ch = cw * bh / bw
        mx, my = bw - cw, bh - ch
        x0 = min(max(mx / 2 + e["ax"] * mx / 2 * 0.8, 0), mx)
        y0 = min(max(my / 2 + e["ay"] * my / 2 * 0.8, 0), my)
        fr = np.asarray(base.resize(self.size, Image.BILINEAR, box=(x0, y0, x0 + cw, y0 + ch)))
        f = 1.0
        if e.get("fade") and lt < 0.6: f = lt / 0.6
        if t > self.total - 1.5: f = min(f, max(0.0, (self.total - t) / 1.5))
        if f < 1.0: fr = (fr.astype(np.float32) * f).astype(np.uint8)
        return fr

def renderizar_video(signos_data, salida):
    escenas, t_total = [], 0.0
    for i, signo in enumerate(signos_data):
        img_path, audio_path = f"temp_signo_{i}.jpg", f"temp_audio_{i}.mp3"
        if not os.path.exists(img_path) or not os.path.exists(audio_path): continue
        
        dur = AudioFileClip(audio_path).duration + 0.5
        img = Image.open(img_path).convert("RGB").resize((W, H))
        draw = ImageDraw.Draw(img)
        try:
            font_t = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 110)
            font_s = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
        except:
            font_t = font_s = ImageFont.load_default()
            
        draw.text((W//2, 250), f"{signo['simbolo']} {signo['nombre']}", font=font_t, fill=(255, 255, 255), anchor="mm", stroke_width=10, stroke_fill=(0, 0, 0))
        mantra = signo['guion'].split('.')[-1].strip()[:60]
        draw.text((W//2, 850), mantra, font=font_s, fill=(255, 215, 0), anchor="mm", stroke_width=8, stroke_fill=(0, 0, 0))
        img.save(f"temp_frame_{i}.jpg")
        
        escenas.append({"path": f"temp_frame_{i}.jpg", "inicio": t_total, "dur": dur, "etapa": "mystic", "fade": i==0, "zin": i%2==0, "ax": random.uniform(-1, 1), "ay": random.uniform(-1, 1)})
        t_total += dur

    render = RenderEscenas(escenas, (W, H), t_total)
    video = VideoClip(render.frame, duration=t_total)
    clips_audio = [AudioFileClip(e["path"].replace("temp_frame_", "temp_audio_").replace(".jpg", ".mp3")).set_start(e["inicio"]) for e in escenas]
    
    musicas_disponibles = [f for f in os.listdir(".") if f.lower().endswith(".mp3") and not f.startswith("temp_")]
    if musicas_disponibles:
        musica_elegida = random.choice(musicas_disponibles)
        try:
            bg = AudioFileClip(musica_elegida)
            if bg.duration < t_total:
                bg = concatenate_audioclips([bg] * (int(t_total / bg.duration) + 1))
            clips_audio.append(bg.subclip(0, t_total).volumex(0.08).audio_fadein(3).audio_fadeout(3))
            print(f"🎵 Música de fondo aplicada (8%): {musica_elegida}")
        except Exception as e:
            print(f"⚠️ Error al cargar música de fondo: {e}")

    video = video.set_audio(CompositeAudioClip(clips_audio))
    print("🎬 Renderizando con Ken Burns y Viñetas...")
    video.write_videofile(salida, fps=FPS, codec="libx264", audio_codec="aac", threads=4, preset="ultrafast", logger=None)
    return salida

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
    tiempo_acumulado = 0.0
    caps = []
    for i, s in enumerate(datos["signos"]):
        audio_path = f"temp_audio_{i}.mp3"
        duracion_real = 35.0
        if os.path.exists(audio_path):
            try: duracion_real = AudioFileClip(audio_path).duration
            except: pass
        mins = int(tiempo_acumulado // 60)
        secs = int(tiempo_acumulado % 60)
        caps.append(f"{mins:02d}:{secs:02d} {s['simbolo']} {s['nombre']}: {s['titulo_cap']}")
        tiempo_acumulado += duracion_real + 0.5
        
    desc = f"{datos['descripcion']}\n\n⏰ CAPÍTULOS:\n" + "\n".join(caps) + f"\n\n🔔 Suscríbete para más mensajes del universo: {CANAL_LINK}"
    desc += HASHTAGS_YOUTUBE
    
    tags_finales = construir_tags_finales(datos.get("tags", []), modo)
    
    body = {
        "snippet": {"title": datos["titulo"][:100], "description": desc[:5000], "tags": tags_finales, "categoryId": "22", "defaultLanguage": "es", "defaultAudioLanguage": "es"},
        "status": {"privacyStatus": "private", "publishAt": hora_utc, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
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
                print(f"⚠️ Reintentando subida ({reintentos}/8)...")
                time.sleep(2 ** reintentos)
            else: raise e
            
    video_id = resp["id"]
    print(f"✅ Video subido. ID: {video_id}")
    
    if ruta_miniatura and os.path.exists(ruta_miniatura):
        youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(ruta_miniatura)).execute()
        print("✅ Miniatura aplicada.")
        
    if datos.get("comentario_fijado"):
        try:
            youtube.commentThreads().insert(part="snippet", body={
                "snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": datos["comentario_fijado"]}}}
            }).execute()
            print("✅ Comentario fijado publicado.")
        except HttpError as e:
            print(f"⚠️ Error comentario: Debes regenerar tu token incluyendo 'youtube.force-ssl'")
            
    return video_id

# ================================================================
# 8. MAIN
# ================================================================
def main():
    try:
        tipo = os.getenv("TIPO_HOROSCOPO", "daily")
        ahora = datetime.now(TZ)
        print(f"🤖 Modo detectado: {tipo.upper()}")
        
        if tipo == "monthly":
            hora_final = ahora.replace(hour=12, minute=random.randint(0, 10), second=0, microsecond=0)
            if ahora >= hora_final: hora_final += timedelta(days=1)
        elif tipo == "weekly":
            hoy_inicio = ahora.replace(hour=9, minute=0, second=0, microsecond=0)
            hoy_fin = ahora.replace(hour=12, minute=0, second=0, microsecond=0)
            if ahora >= hoy_fin: hoy_inicio += timedelta(days=1); hoy_fin += timedelta(days=1)
            minutos_a_sumar = random.randint(0, int((hoy_fin - hoy_inicio).total_seconds() / 60))
            hora_final = hoy_inicio + timedelta(minutes=minutos_a_sumar)
        else:
            hoy_inicio = ahora.replace(hour=5, minute=0, second=0, microsecond=0)
            hoy_fin = ahora.replace(hour=8, minute=0, second=0, microsecond=0)
            if ahora >= hoy_fin: hoy_inicio += timedelta(days=1); hoy_fin += timedelta(days=1)
            minutos_a_sumar = random.randint(0, int((hoy_fin - hoy_inicio).total_seconds() / 60))
            hora_final = hoy_inicio + timedelta(minutes=minutos_a_sumar)

        hora_utc = hora_final.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
        print(f"🎯 Programando para: {hora_final:%d-%m-%Y a las %H:%M} (CDMX)")
        
        fecha_hoy = datetime.now(TZ).strftime("%d de %B de %Y")
        fase_lunar = "Creciente"
        
        print(f"🧠 1. Generando contenido SEO Premium con DeepSeek (modo {tipo})...")
        datos = llamar_deepseek(fecha_hoy, fase_lunar, tipo)
        
        if titulo_ya_publicado(datos["titulo"]):
            print("⚠️ Título repetido detectado. Solicitando variación...")
            datos["titulo"] = f"{datos['titulo']} (Edición Especial)"
            
        print("🎨 2. Generando activos (Imágenes y Audio)...")
        for i, signo in enumerate(datos["signos"]):
            print(f"   Procesando {signo['nombre']}...")
            obtener_imagen_segura(signo.get("visual_prompt", "masterpiece, mystical galaxy, volumetric lighting, 8k"), f"temp_signo_{i}.jpg")
            guion_con_nombre = f"{signo['nombre']}. {signo['guion']}"
            asyncio.run(generar_audio(guion_con_nombre, f"temp_audio_{i}.mp3"))
            
        print("🖼️ 3. Creando miniatura 8K Brillante...")
        obtener_imagen_segura(datos.get("miniatura_prompt", "masterpiece, radiant cosmic energy, volumetric lighting, hyper-detailed, 8k"), "temp_bg_thumb.jpg", es_miniatura=True)
        
        texto_miniatura = datos.get("miniatura_texto", "MENSAJE URGENTE")
        banner_miniatura = datos.get("miniatura_banner", "PARA LOS 12 SIGNOS")
        print(f"   📝 Texto de miniatura: '{texto_miniatura}' | Banner: '{banner_miniatura}'")
        
        crear_miniatura_8k_elite("temp_bg_thumb.jpg", texto_miniatura, banner_miniatura, "miniatura.jpg")
        
        print("🎬 4. Renderizando video...")
        renderizar_video(datos["signos"], "video_final.mp4")
        
        print("📤 5. Subiendo a YouTube...")
        video_id = subir_a_youtube("video_final.mp4", "miniatura.jpg", datos, hora_utc, tipo)
            
        print(f"✨ ¡PROCESO COMPLETADO! Video programado para {hora_final:%H:%M} (CDMX)")
        guardar_titulo(datos["titulo"])
        
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
