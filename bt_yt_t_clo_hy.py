# -*- coding: utf-8 -*-
"""
BT_YT_T_CLO_HY - Bot Horóscopo Master (Tu Cielo Hoy) - VERSIÓN ROBUSTA
Fix: Validación relajada + Expansión automática de guiones cortos
"""
import asyncio, base64, bisect, json, os, random, re, ssl, socket, sys, time, traceback, unicodedata
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
TITULOS_FILE = "titulos_publicados.json"
W, H, FPS = 1920, 1080, 24

# ================================================================
# 🏷️ MOTOR DE TAGS INTELIGENTE (ASCII PURO)
# ================================================================
TAGS_GENERALES_SIEMPRE = [
    "horoscopo", "horoscopo diario", "astrologia", "zodiaco", "tu cielo hoy",
    "aries", "tauro", "geminis", "cancer", "leo", "virgo", "libra", "escorpio",
    "sagitario", "capricornio", "acuario", "piscis", "mensaje del universo",
    "energia del dia", "fase lunar", "crecimiento espiritual", "bienestar"
]

TAGS_POR_MODO = {
    "daily": ["horoscopo de hoy", "horoscopo hoy", "prediccion de hoy", "energia de hoy", "mensaje de hoy"],
    "weekly": ["horoscopo semanal", "horoscopo de la semana", "semana astral", "prediccion semanal"],
    "monthly": ["horoscopo mensual", "horoscopo del mes", "prediccion mensual", "ciclo lunar"]
}

def normalizar_ascii(texto):
    texto = unicodedata.normalize('NFKD', texto)
    texto = ''.join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()

def construir_tags_finales(tags_dinamicos_ia, modo="daily"):
    tags_finales = []
    total_chars = 0
    
    for tag in TAGS_GENERALES_SIEMPRE:
        tag_limpio = normalizar_ascii(tag).strip()
        tag_limpio = re.sub(r'[^a-z0-9\s]', '', tag_limpio)
        tag_limpio = re.sub(r'\s+', ' ', tag_limpio).strip()
        if 2 <= len(tag_limpio) <= 30 and tag_limpio not in tags_finales:
            if total_chars + len(tag_limpio) + 1 <= 480:
                tags_finales.append(tag_limpio)
                total_chars += len(tag_limpio) + 1
    
    for tag in TAGS_POR_MODO.get(modo, []):
        tag_limpio = normalizar_ascii(tag).strip()
        tag_limpio = re.sub(r'[^a-z0-9\s]', '', tag_limpio)
        tag_limpio = re.sub(r'\s+', ' ', tag_limpio).strip()
        if 2 <= len(tag_limpio) <= 30 and tag_limpio not in tags_finales:
            if total_chars + len(tag_limpio) + 1 <= 480:
                tags_finales.append(tag_limpio)
                total_chars += len(tag_limpio) + 1
    
    if isinstance(tags_dinamicos_ia, list):
        for tag in tags_dinamicos_ia:
            t = normalizar_ascii(str(tag)).strip()
            t = re.sub(r'[^a-z0-9\s]', '', t)
            t = re.sub(r'\s+', ' ', t).strip()
            if 2 <= len(t) <= 30 and t not in tags_finales:
                if total_chars + len(t) + 1 <= 480:
                    tags_finales.append(t)
                    total_chars += len(t) + 1
    
    if not tags_finales:
        tags_finales = TAGS_GENERALES_SIEMPRE[:15]
    
    print(f"🏷️ Tags finales: {len(tags_finales)} tags, {total_chars} caracteres")
    return tags_finales

print("=" * 70)
print("🔮 BT_YT_T_CLO_HY MASTER - Tu Cielo Hoy (Versión Robusta)")
print(f"📅 {datetime.now(TZ):%Y-%m-%d %H:%M} (CDMX)")
print("=" * 70)

if not all([DEEPSEEK_API_KEY, PEXELS_API_KEY, CF_ACCOUNT_ID, CF_API_TOKEN, YT_TOKEN_STR]):
    print(" ERROR: Faltan variables de entorno en los Secrets de GitHub.")
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
# 3. IA (DEEPSEEK) - 3 PROMPTS + EXPANSIÓN AUTOMÁTICA
# ================================================================
PROMPT_DIARIO = """
Eres la astróloga más prestigiosa de YouTube. Tono: femenino, cálido, místico.
Fecha: {fecha}. Fase Lunar: {fase_lunar}.
Genera horóscopo DIARIO para los 12 signos.

REGLAS:
1. TÍTULO: Estructura "Horóscopo HOY: [Gancho] | [Tránsito lunar]". Máx 65 chars.
2. Cada signo debe tener texto TOTALMENTE ÚNICO.
3. Descripción: 3 párrafos (Gancho, Entity stacking, CTA).
4. Tags: 10 tags cortos específicos del día (máx 20 chars cada uno, SIN acentos).
5. Comentario Fijado: Frase mística para decretar.
6. Miniatura: Prompt en inglés (fondo místico oscuro) y 2-3 palabras MAYÚSCULAS.
7. ⚠️ DURACIÓN CRÍTICA: Cada signo debe tener EXACTAMENTE 110-125 palabras. Esto es OBLIGATORIO.
   Estructura: Energía general (30 palabras) + Amor (30 palabras) + Dinero (30 palabras) + Mantra final (5 palabras).
   NO seas breve. Desarrolla cada sección con detalles específicos.

Responde SOLO JSON:
{{
  "titulo": "...", "descripcion": "...", "tags": ["tag1"], "comentario_fijado": "...",
  "miniatura_prompt": "...", "miniatura_texto": "...", "miniatura_banner": "MENSAJE DEL UNIVERSO",
  "signos": [
    {{"nombre": "Aries", "simbolo": "♈", "titulo_cap": "Chispa de Valentía", "guion": "...", "visual_prompt": "red sunrise fire sparks"}},
    {{"nombre": "Tauro", "simbolo": "♉", "titulo_cap": "Siembra de Abundancia", "guion": "...", "visual_prompt": "green forest sunlight"}},
    {{"nombre": "Géminis", "simbolo": "♊", "titulo_cap": "Comunicación Estelar", "guion": "...", "visual_prompt": "wind blowing trees"}},
    {{"nombre": "Cáncer", "simbolo": "♋", "titulo_cap": "Marea Emocional", "guion": "...", "visual_prompt": "ocean waves calm"}},
    {{"nombre": "Leo", "simbolo": "♌", "titulo_cap": "Brillo Real", "guion": "...", "visual_prompt": "golden sunset"}},
    {{"nombre": "Virgo", "simbolo": "♍", "titulo_cap": "Detalle Perfecto", "guion": "...", "visual_prompt": "morning dew leaves"}},
    {{"nombre": "Libra", "simbolo": "♎", "titulo_cap": "Armonía Renovada", "guion": "...", "visual_prompt": "pink sunset clouds"}},
    {{"nombre": "Escorpio", "simbolo": "♏", "titulo_cap": "Poder Transformador", "guion": "...", "visual_prompt": "deep ocean dark"}},
    {{"nombre": "Sagitario", "simbolo": "♐", "titulo_cap": "Aventura Cósmica", "guion": "...", "visual_prompt": "mountain peak sunrise"}},
    {{"nombre": "Capricornio", "simbolo": "♑", "titulo_cap": "Construcción Sólida", "guion": "...", "visual_prompt": "stone architecture"}},
    {{"nombre": "Acuario", "simbolo": "♒", "titulo_cap": "Visión Innovadora", "guion": "...", "visual_prompt": "aurora borealis"}},
    {{"nombre": "Piscis", "simbolo": "♓", "titulo_cap": "Sueño Profético", "guion": "...", "visual_prompt": "underwater coral reef"}}
  ]
}}
"""

PROMPT_SEMANAL = """
Eres la astróloga más prestigiosa de YouTube. Tono: femenino, cálido, místico.
Semana del {fecha}. Fase Lunar: {fase_lunar}.
Genera horóscopo SEMANAL detallado para los 12 signos.

REGLAS:
1. TÍTULO: Estructura "Horóscopo SEMANAL: [Gancho fuerte] | [Semana clave]". Máx 70 chars.
2. Cada signo debe tener texto TOTALMENTE ÚNICO y profundo.
3. Descripción: 3 párrafos enfocados en tendencias de la semana.
4. Tags: 10 tags específicos de la semana (máx 20 chars, SIN acentos).
5. Comentario Fijado: Pregunta sobre la semana.
6. Miniatura: Prompt en inglés y 2-3 palabras MAYÚSCULAS.
7. ️ DURACIÓN CRÍTICA: Cada signo debe tener EXACTAMENTE 200-220 palabras.
   Estructura: Tendencia general (50 palabras) + Amor semana (50 palabras) + Dinero semana (50 palabras) + Día clave (30 palabras) + Mantra (10 palabras).

Responde SOLO JSON:
{{
  "titulo": "...", "descripcion": "...", "tags": ["tag1"], "comentario_fijado": "...",
  "miniatura_prompt": "...", "miniatura_texto": "...", "miniatura_banner": "SEMANA CLAVE",
  "signos": [
    {{"nombre": "Aries", "simbolo": "♈", "titulo_cap": "Semana de Acción", "guion": "...", "visual_prompt": "red sunrise fire sparks"}},
    {{"nombre": "Tauro", "simbolo": "♉", "titulo_cap": "Semana de Cosecha", "guion": "...", "visual_prompt": "green forest sunlight"}},
    {{"nombre": "Géminis", "simbolo": "♊", "titulo_cap": "Semana de Cambios", "guion": "...", "visual_prompt": "wind blowing trees"}},
    {{"nombre": "Cáncer", "simbolo": "♋", "titulo_cap": "Semana Emocional", "guion": "...", "visual_prompt": "ocean waves calm"}},
    {{"nombre": "Leo", "simbolo": "♌", "titulo_cap": "Semana de Brillo", "guion": "...", "visual_prompt": "golden sunset"}},
    {{"nombre": "Virgo", "simbolo": "♍", "titulo_cap": "Semana de Orden", "guion": "...", "visual_prompt": "morning dew leaves"}},
    {{"nombre": "Libra", "simbolo": "♎", "titulo_cap": "Semana de Equilibrio", "guion": "...", "visual_prompt": "pink sunset clouds"}},
    {{"nombre": "Escorpio", "simbolo": "♏", "titulo_cap": "Semana de Poder", "guion": "...", "visual_prompt": "deep ocean dark"}},
    {{"nombre": "Sagitario", "simbolo": "♐", "titulo_cap": "Semana de Aventura", "guion": "...", "visual_prompt": "mountain peak sunrise"}},
    {{"nombre": "Capricornio", "simbolo": "♑", "titulo_cap": "Semana de Metas", "guion": "...", "visual_prompt": "stone architecture"}},
    {{"nombre": "Acuario", "simbolo": "♒", "titulo_cap": "Semana de Innovación", "guion": "...", "visual_prompt": "aurora borealis"}},
    {{"nombre": "Piscis", "simbolo": "", "titulo_cap": "Semana de Intuición", "guion": "...", "visual_prompt": "underwater coral reef"}}
  ]
}}
"""

PROMPT_MENSUAL = """
Eres la astróloga más prestigiosa de YouTube. Tono: femenino, cálido, místico.
Mes de {fecha}. Fase Lunar dominante: {fase_lunar}.
Genera horóscopo MENSUAL PROFUNDO para los 12 signos.

REGLAS:
1. TÍTULO: Estructura "PREDICCIÓN MENSUAL [Mes]: [Gancho épico] | [Evento astral]". Máx 75 chars.
2. Cada signo debe tener texto TOTALMENTE ÚNICO, profundo y detallado.
3. Descripción: 3 párrafos sobre el ciclo mensual completo.
4. Tags: 10 tags específicos del mes (máx 20 chars, SIN acentos).
5. Comentario Fijado: Decreto mensual.
6. Miniatura: Prompt en inglés y 2-3 palabras MAYÚSCULAS.
7. ️ DURACIÓN CRÍTICA: Cada signo debe tener EXACTAMENTE 350-400 palabras.
   Estructura: Ciclo completo (80 palabras) + Fechas clave de suerte (60 palabras) + Amor mes (70 palabras) + Dinero mes (70 palabras) + Reto del mes (50 palabras) + Mantra mensual (20 palabras).

Responde SOLO JSON:
{{
  "titulo": "...", "descripcion": "...", "tags": ["tag1"], "comentario_fijado": "...",
  "miniatura_prompt": "...", "miniatura_texto": "...", "miniatura_banner": "PREDICCIÓN MENSUAL",
  "signos": [
    {{"nombre": "Aries", "simbolo": "♈", "titulo_cap": "Mes de Conquista", "guion": "...", "visual_prompt": "red sunrise fire sparks"}},
    {{"nombre": "Tauro", "simbolo": "♉", "titulo_cap": "Mes de Abundancia", "guion": "...", "visual_prompt": "green forest sunlight"}},
    {{"nombre": "Géminis", "simbolo": "♊", "titulo_cap": "Mes de Transformación", "guion": "...", "visual_prompt": "wind blowing trees"}},
    {{"nombre": "Cáncer", "simbolo": "♋", "titulo_cap": "Mes de Sanación", "guion": "...", "visual_prompt": "ocean waves calm"}},
    {{"nombre": "Leo", "simbolo": "♌", "titulo_cap": "Mes de Coronación", "guion": "...", "visual_prompt": "golden sunset"}},
    {{"nombre": "Virgo", "simbolo": "♍", "titulo_cap": "Mes de Perfección", "guion": "...", "visual_prompt": "morning dew leaves"}},
    {{"nombre": "Libra", "simbolo": "♎", "titulo_cap": "Mes de Armonía", "guion": "...", "visual_prompt": "pink sunset clouds"}},
    {{"nombre": "Escorpio", "simbolo": "♏", "titulo_cap": "Mes de Renacimiento", "guion": "...", "visual_prompt": "deep ocean dark"}},
    {{"nombre": "Sagitario", "simbolo": "♐", "titulo_cap": "Mes de Expansión", "guion": "...", "visual_prompt": "mountain peak sunrise"}},
    {{"nombre": "Capricornio", "simbolo": "♑", "titulo_cap": "Mes de Logros", "guion": "...", "visual_prompt": "stone architecture"}},
    {{"nombre": "Acuario", "simbolo": "♒", "titulo_cap": "Mes de Revolución", "guion": "...", "visual_prompt": "aurora borealis"}},
    {{"nombre": "Piscis", "simbolo": "♓", "titulo_cap": "Mes de Despertar", "guion": "...", "visual_prompt": "underwater coral reef"}}
  ]
}}
"""

def expandir_guion_corto(signo_nombre, guion_actual, modo):
    """Usa DeepSeek para expandir un guion que es demasiado corto."""
    palabras_actuales = len(guion_actual.split())
    
    if modo == "daily":
        target = 115
        prompt_extra = f"El guion actual tiene {palabras_actuales} palabras. Necesita llegar a 115 palabras. Añade más detalles sobre energía, amor y dinero."
    elif modo == "weekly":
        target = 210
        prompt_extra = f"El guion actual tiene {palabras_actuales} palabras. Necesita llegar a 210 palabras. Expande cada sección con más detalles."
    else:
        target = 375
        prompt_extra = f"El guion actual tiene {palabras_actuales} palabras. Necesita llegar a 375 palabras. Desarrolla profundamente cada aspecto."
    
    prompt = f"""
Eres la astróloga más prestigiosa de YouTube. Necesitas EXPANDIR este guion de {signo_nombre}:

GUION ACTUAL:
"{guion_actual}"

{prompt_extra}

Mantén el mismo tono místico y cálido. NO repitas lo que ya está escrito. Añade contenido nuevo y relevante.
Devuelve SOLO el guion expandido, sin comillas, sin explicaciones adicionales.
"""
    
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 500}
    
    try:
        r = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        texto_expandido = r.json()["choices"][0]["message"]["content"].strip()
        
        # Combinar guion original con expansión
        guion_final = f"{guion_actual} {texto_expandido}"
        palabras_finales = len(guion_final.split())
        print(f"   ✅ {signo_nombre} expandido: {palabras_actuales} → {palabras_finales} palabras")
        return guion_final
    except Exception as e:
        print(f"   ⚠️ No se pudo expandir {signo_nombre}: {e}")
        return guion_actual

def llamar_deepseek(fecha, fase_lunar, modo="daily"):
    if modo == "weekly":
        prompt = PROMPT_SEMANAL.format(fecha=fecha, fase_lunar=fase_lunar)
        min_palabras = 150  # Mínimo relajado (target 200-220)
    elif modo == "monthly":
        prompt = PROMPT_MENSUAL.format(fecha=fecha, fase_lunar=fase_lunar)
        min_palabras = 250  # Mínimo relajado (target 350-400)
    else:
        prompt = PROMPT_DIARIO.format(fecha=fecha, fase_lunar=fase_lunar)
        min_palabras = 70  # ✅ MÍNIMO RELAJADO (target 110-125)
    
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "response_format": {"type": "json_object"}}
    
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
            
            # ✅ VALIDACIÓN RELAJADA: Solo rechazamos si es MUY corto (menos de 50 palabras)
            signos_muy_cortos = [s for s in datos["signos"] if len(s["guion"].split()) < 50]
            if signos_muy_cortos:
                raise ValueError(f"{len(signos_muy_cortos)} signos tienen menos de 50 palabras.")
                
            return datos
        except Exception as e:
            print(f"️ DeepSeek intento {i+1} falló: {e}")
            time.sleep(3)
    raise Exception("Fallo DeepSeek tras 3 intentos")

def expandir_signos_cortos(datos, modo):
    """Expande automáticamente los signos que tienen menos palabras de las ideales."""
    if modo == "daily":
        umbral_expansion = 90  # Expandir si tiene menos de 90 palabras
    elif modo == "weekly":
        umbral_expansion = 150
    else:
        umbral_expansion = 280
    
    print(f"\n📝 Verificando longitud de guiones (umbral: {umbral_expansion} palabras)...")
    
    for signo in datos["signos"]:
        palabras = len(signo["guion"].split())
        if palabras < umbral_expansion:
            print(f"   ⚠️ {signo['nombre']} tiene {palabras} palabras (mínimo {umbral_expansion}). Expandiendo...")
            signo["guion"] = expandir_guion_corto(signo["nombre"], signo["guion"], modo)
            time.sleep(1)  # Pausa para no saturar la API
    
    return datos

# ================================================================
# 4. IMÁGENES (CLOUDFLARE SIMPLIFICADO + PEXELS)
# ================================================================
def generar_cf(prompt, ruta):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    clean_prompt = re.sub(r'[^a-zA-Z0-9\s,]', ' ', prompt)[:200]
    enhanced_prompt = f"{clean_prompt}, 8k, vivid colors, cinematic lighting, no text"
    payload = {"prompt": enhanced_prompt, "steps": 4}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code == 400:
        print(f"   ❌ Cloudflare 400: {r.text[:150]}")
    r.raise_for_status()
    result = r.json()
    if "result" not in result or "image" not in result["result"]:
        raise ValueError(f"Sin imagen: {str(result)[:100]}")
    with open(ruta, "wb") as f:
        f.write(base64.b64decode(result["result"]["image"]))
    with Image.open(ruta) as im:
        im = ImageOps.fit(im.convert("RGB"), (W, H), Image.LANCZOS)
        im.save(ruta, "JPEG", quality=92)
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
        im.save(ruta, "JPEG", quality=92)
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
    try:
        query = prompt + " mystical cosmic" if es_miniatura else prompt
        return generar_pexels(query, ruta)
    except:
        return None

# ================================================================
# 5. AUDIO Y MINIATURAS NEÓN 8K
# ================================================================
async def generar_audio(texto, ruta):
    await edge_tts.Communicate(texto, VOZ_CANAL, rate="-4%").save(ruta)
    return os.path.getsize(ruta) > 500

def render_texto_gradiente_8k(texto, font_path, size):
    font = ImageFont.truetype(font_path, size)
    b = font.getbbox(texto)
    w, h = (b[2] - b[0]) + 40, (b[3] - b[1]) + 40
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    cx, cy = 20 - b[0], 20 - b[1]
    d.text((cx, cy), texto, font=font, fill=(0, 0, 0), stroke_width=14, stroke_fill=(0, 0, 0))
    d.text((cx, cy), texto, font=font, fill=(128, 0, 128), stroke_width=8, stroke_fill=(128, 0, 128))
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
    d.rounded_rectangle([10, 10, w + 10, h + 10], radius=16, outline=(255, 215, 0, 255), width=4)
    d.text((10 + 30 - b[0], 10 + 15 - b[1]), texto, font=font, fill=(255, 255, 255, 255))
    return img

def crear_miniatura_8k_elite(img_path, texto_principal, texto_banner, salida):
    try:
        img = Image.open(img_path).convert("RGB").resize((1280, 720))
        img = ImageEnhance.Brightness(img).enhance(0.5)
        img = ImageEnhance.Contrast(img).enhance(1.4)
        img = ImageEnhance.Color(img).enhance(1.3)
        img = img.convert("RGBA")
        vignette = Image.new("RGBA", (1280, 720), (0, 0, 0, 0))
        draw_vig = ImageDraw.Draw(vignette)
        for x in range(400):
            draw_vig.line([(x, 0), (x, 720)], fill=(0, 0, 0, int(200 * (1 - x/400))))
            draw_vig.line([(1280-x, 0), (1280-x, 720)], fill=(0, 0, 0, int(200 * (1 - x/400))))
        img = Image.alpha_composite(img, vignette)
        fuente = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        bloque1 = render_texto_gradiente_8k(texto_principal, fuente, 130)
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
        print(f"✅ Miniatura 8K Élite generada: {salida}")
        return True
    except Exception as e:
        print(f"⚠️ Error en miniatura 8K: {e}")
        return False

# ================================================================
# 6. RENDER DE VIDEO (KEN BURNS + MÚSICA ALEATORIA)
# ================================================================
_VIG = {}
def vignette(size, base=1.0, fuerza=0.6):
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
    print(" Renderizando con Ken Burns y Viñetas...")
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
    desc = f"{datos['descripcion']}\n\n⏰ CAPÍTULOS:\n" + "\n".join(caps) + f"\n\n🔔 Suscríbete: {CANAL_LINK}"
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
            youtube.commentThreads().insert(part="snippet", body={"snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": datos["comentario_fijado"]}}}}).execute()
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
        print(f"🧠 1. Generando contenido con DeepSeek (modo {tipo})...")
        datos = llamar_deepseek(fecha_hoy, fase_lunar, tipo)
        
        # ✅ EXPANSIÓN AUTOMÁTICA DE GUIONES CORTOS
        print("\n📝 1.5 Expandiendo guiones cortos si es necesario...")
        datos = expandir_signos_cortos(datos, tipo)
        
        if titulo_ya_publicado(datos["titulo"]):
            datos["titulo"] = f"{datos['titulo']} (Edición Especial)"
        print("🎨 2. Generando activos (Imágenes y Audio)...")
        for i, signo in enumerate(datos["signos"]):
            print(f"   Procesando {signo['nombre']}...")
            obtener_imagen_segura(signo.get("visual_prompt", "mystical galaxy"), f"temp_signo_{i}.jpg")
            asyncio.run(generar_audio(signo["guion"], f"temp_audio_{i}.mp3"))
        print("🖼️ 3. Creando miniatura 8K Élite...")
        obtener_imagen_segura(datos.get("miniatura_prompt", "mystical zodiac wheel glowing 8k"), "temp_bg_thumb.jpg", es_miniatura=True)
        crear_miniatura_8k_elite("temp_bg_thumb.jpg", datos.get("miniatura_texto", "HORÓSCOPO HOY"), datos.get("miniatura_banner", "MENSAJE DEL UNIVERSO"), "miniatura.jpg")
        print("🎬 4. Renderizando video...")
        renderizar_video(datos["signos"], "video_final.mp4")
        print(" 5. Subiendo a YouTube...")
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
