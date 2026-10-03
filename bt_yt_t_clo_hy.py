# -*- coding: utf-8 -*-
"""
BT_YT_T_CLO_HY - Bot de Horóscopos Diarios (Tu Cielo Hoy)
Motor de automatización Élite: Generación, SEO, Miniatura IA y Publicación Programada.
Optimizado para ejecución 100% en GitHub Actions.
"""
import os
import sys
import json
import time
import random
import base64
import traceback
import asyncio
import re
import requests
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import edge_tts
from moviepy.editor import ImageClip, concatenate_videoclips, CompositeAudioClip, AudioFileClip
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# ================================================================
# 1. CONFIGURACIÓN Y VARIABLES DE ENTORNO (GitHub Secrets)
# ================================================================
TZ = ZoneInfo("America/Mexico_City")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
CF_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CF_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
YT_TOKEN_STR = os.getenv("YOUTUBE_USER_TOKEN")

CANAL_LINK = "https://www.youtube.com/@tucielhoy"
VOZ_CANAL = "es-MX-DaliaNeural"  # Voz femenina, cálida y mística

print("=" * 70)
print("🔮 BT_YT_T_CLO_HY - Iniciando motor astrológico Élite...")
print(f"📅 Fecha: {datetime.now(TZ):%Y-%m-%d %H:%M} (CDMX)")
print("=" * 70)

if not all([DEEPSEEK_API_KEY, PEXELS_API_KEY, CF_ACCOUNT_ID, CF_API_TOKEN, YT_TOKEN_STR]):
    print("❌ ERROR: Faltan variables de entorno en los Secrets de GitHub.")
    sys.exit(1)

# ================================================================
# 2. MOTOR DE PROGRAMACIÓN (5:00 AM - 8:00 AM CDMX)
# ================================================================
def calcular_hora_publicacion():
    ahora = datetime.now(TZ)
    hoy_inicio = ahora.replace(hour=5, minute=0, second=0, microsecond=0)
    hoy_fin = ahora.replace(hour=8, minute=0, second=0, microsecond=0)
    
    if ahora >= hoy_fin:
        hoy_inicio += timedelta(days=1)
        hoy_fin += timedelta(days=1)
        print("⏳ Ya pasó la ventana de hoy. Programando para MAÑANA.")
    else:
        print("⏳ Ventana de hoy activa. Programando para HOY.")
        
    minutos_totales = int((hoy_fin - hoy_inicio).total_seconds() / 60)
    minutos_a_sumar = random.randint(0, minutos_totales - 1)
    hora_final_cdmx = hoy_inicio + timedelta(minutes=minutos_a_sumar)
    
    hora_utc = hora_final_cdmx.astimezone(timezone.utc)
    return hora_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z"), hora_final_cdmx.strftime("%H:%M")

# ================================================================
# 3. INTELIGENCIA ARTIFICIAL (DEEPSEEK)
# ================================================================
PROMPT_ELITE = """
Eres la astróloga más prestigiosa y empática de YouTube. Tu tono es femenino, cálido, místico y reconfortante.
Fecha de hoy: {fecha}. Fase Lunar: {fase_lunar}.
Genera el contenido completo para un video de horóscopo diario que abarque los 12 signos del zodiaco en orden.

REGLAS SEO ÉLITE:
1. Título: 55-65 caracteres. Debe incluir el tránsito lunar y un gancho de curiosidad.
2. Descripción: 3 párrafos. P1: Gancho emocional. P2: Entity stacking. P3: Llamada a la acción.
3. Tags: EXACTAMENTE 15 tags cortos en español (máximo 20 caracteres cada uno, ej: "horoscopo tauro", "astrologia hoy").
4. Comentario Fijado: Frase mística que invite a comentar el propio signo.
5. Miniatura: Prompt en inglés para IA (fondo místico, sin texto) y 2-3 palabras en MAYÚSCULAS para el texto.
6. Signos: Para cada uno de los 12 signos, genera: nombre, símbolo, titulo_cap (4-6 palabras), guion (~80 palabras), y visual_prompt (3 palabras en inglés).

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
    payload = {"model": "deepseek-chat", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "response_format": {"type": "json_object"}}
    
    for intento in range(3):
        try:
            print(f"   🧠 Intento {intento+1}/3 con DeepSeek...")
            r = requests.post("https://api.deepseek.com/v1/chat/completions", headers=headers, json=payload, timeout=90)
            r.raise_for_status()
            texto = r.json()["choices"][0]["message"]["content"].strip()
            texto = texto.replace("```json", "").replace("```", "").strip()
            return json.loads(texto)
        except Exception as e:
            print(f"   ⚠️ DeepSeek intento {intento+1} falló: {e}")
            time.sleep(3)
    raise Exception("No se pudo obtener respuesta de DeepSeek tras 3 intentos")

# ================================================================
# 4. GENERACIÓN DE IMÁGENES (CLOUDFLARE 3 INTENTOS + PEXELS)
# ================================================================
def generar_cf(prompt, ruta_salida):
    url = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT_ID}/ai/run/@cf/black-forest-labs/flux-1-schnell"
    headers = {"Authorization": f"Bearer {CF_API_TOKEN}"}
    payload = {"prompt": f"{prompt}, mystical, ethereal, cinematic lighting, 8k, highly detailed, no text, no letters", "steps": 4}
    r = requests.post(url, headers=headers, json=payload, timeout=45)
    r.raise_for_status()
    img_data = base64.b64decode(r.json()["result"]["image"])
    with open(ruta_salida, "wb") as f:
        f.write(img_data)
    return ruta_salida

def generar_pexels(query, ruta_salida):
    headers = {"Authorization": PEXELS_API_KEY}
    r = requests.get("https://api.pexels.com/v1/search", headers=headers, params={"query": query, "orientation": "landscape", "size": "large", "per_page": 5}, timeout=15)
    r.raise_for_status()
    fotos = r.json().get("photos", [])
    if not fotos:
        raise Exception("Sin resultados en Pexels")
    url_img = fotos[0]["src"]["large2x"]
    with requests.get(url_img, stream=True, timeout=15) as r_img:
        with open(ruta_salida, "wb") as f:
            for chunk in r_img.iter_content(8192):
                f.write(chunk)
    return ruta_salida

def obtener_imagen_segura(prompt, ruta, es_miniatura=False):
    print(f"   🎨 Generando: '{prompt}'...")
    for i in range(1, 4):
        try:
            print(f"   ☁️ Intento {i}/3 con Cloudflare...")
            return generar_cf(prompt, ruta)
        except Exception as e:
            print(f"   ⚠️ CF falló ({i}/3): {e}")
            time.sleep(2)
    
    print("   ⚠️ Activando respaldo Pexels...")
    try:
        query_pexels = prompt + " dark mystical cosmic" if es_miniatura else prompt
        return generar_pexels(query_pexels, ruta)
    except Exception as e:
        print(f"   ❌ Fallo total de imagen: {e}")
        return None

# ================================================================
# 5. AUDIO (EDGE TTS)
# ================================================================
async def generar_audio(texto, ruta):
    communicate = edge_tts.Communicate(texto, VOZ_CANAL, rate="-4%", pitch="+0Hz")
    await communicate.save(ruta)
    return os.path.getsize(ruta) > 500

# ================================================================
# 6. RENDER DE VIDEO Y MINIATURA
# ================================================================
def obtener_fuente(size):
    rutas = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]
    for p in rutas:
        try:
            return ImageFont.truetype(p, size)
        except:
            pass
    return ImageFont.load_default()

def crear_miniatura_con_texto(img_path, texto, salida):
    try:
        img = Image.open(img_path).convert("RGB").resize((1280, 720))
        img = ImageEnhance.Contrast(img).enhance(1.2).convert("RGBA")
        draw = ImageDraw.Draw(img)
        font = obtener_fuente(90)
        draw.text((640, 360), texto, font=font, fill=(255, 215, 0), anchor="mm", stroke_width=10, stroke_fill=(0, 0, 0))
        img.convert("RGB").save(salida, "JPEG", quality=90)
        return True
    except Exception as e:
        print(f"⚠️ Error en miniatura: {e}")
        return False

def renderizar_video(signos_data, salida_video):
    clips = []
    for i, signo in enumerate(signos_data):
        img_path = f"temp_signo_{i}.jpg"
        audio_path = f"temp_audio_{i}.mp3"
        
        img = Image.open(img_path).convert("RGB").resize((1920, 1080))
        draw = ImageDraw.Draw(img)
        font_titulo = obtener_fuente(110)
        font_sub = obtener_fuente(50)
        
        draw.text((960, 250), f"{signo['simbolo']} {signo['nombre']}", font=font_titulo, fill=(255, 255, 255), anchor="mm", stroke_width=8, stroke_fill=(0, 0, 0))
        mantra = signo['guion'].split('.')[-1].strip()
        draw.text((960, 850), mantra, font=font_sub, fill=(255, 215, 0), anchor="mm", stroke_width=6, stroke_fill=(0, 0, 0))
        
        frame_path = f"temp_frame_{i}.jpg"
        img.save(frame_path)
        
        duracion_audio = AudioFileClip(audio_path).duration
        clip = ImageClip(frame_path).set_duration(duracion_audio).set_audio(AudioFileClip(audio_path))
        clips.append(clip)
        
    video_final = concatenate_videoclips(clips, method="compose")
    print("🎬 Renderizando video final (esto puede tomar 1-2 minutos)...")
    video_final.write_videofile(salida_video, fps=24, codec="libx264", audio_codec="aac", threads=4, logger=None)
    return salida_video

# ================================================================
# 7. SUBIDA A YOUTUBE (CON FILTRO DE TAGS SEGURO)
# ================================================================
def limpiar_y_validar_tags(tags_lista):
    """Limpia y valida los tags para cumplir estrictamente con los límites de YouTube."""
    if not isinstance(tags_lista, list):
        tags_lista = [t.strip() for t in str(tags_lista).split(",")] if tags_lista else []
        
    tags_limpios = []
    total_length = 0
    
    for tag in tags_lista:
        t = str(tag).strip().strip('"\'').lower()
        t = re.sub(r'[^\w\sáéíóúñ]', ' ', t) # Solo letras, números y espacios
        t = re.sub(r'\s+', ' ', t).strip()
        
        if len(t) < 2 or len(t) > 30: # YouTube exige entre 2 y 30 caracteres por tag
            continue
            
        if t not in tags_limpios:
            if total_length + len(t) + 1 <= 500: # Límite total de 500 caracteres
                tags_limpios.append(t)
                total_length += len(t) + 1
            else:
                break
                
    if not tags_limpios:
        tags_limpios = ["horoscopo diario", "astrologia", "zodiaco", "tu cielo hoy"]
        
    return tags_limpios

def subir_a_youtube(ruta_video, ruta_miniatura, datos, hora_programada_utc):
    yt_token = json.loads(YT_TOKEN_STR)
    creds = Credentials(
        token=yt_token.get("token"), refresh_token=yt_token.get("refresh_token"),
        token_uri=yt_token.get("token_uri"), client_id=yt_token.get("client_id"),
        client_secret=yt_token.get("client_secret"), scopes=yt_token.get("scopes")
    )
    youtube = build("youtube", "v3", credentials=creds)
    
    tiempo_acumulado = 0
    caps = []
    for s in datos["signos"]:
        caps.append(f"{tiempo_acumulado//60:02d}:{tiempo_acumulado%60:02d} {s['simbolo']} {s['nombre']}: {s['titulo_cap']}")
        tiempo_acumulado += 50 
        
    desc_final = f"{datos['descripcion']}\n\n⏰ CAPÍTULOS:\n" + "\n".join(caps) + f"\n\n🔔 Suscríbete: {CANAL_LINK}"
    
    # AQUÍ ESTÁ LA CORRECCIÓN: Filtramos los tags antes de enviarlos
    tags_seguros = limpiar_y_validar_tags(datos.get("tags", []))
    print(f"🏷️ Tags validados para YouTube ({len(tags_seguros)} tags, {sum(len(t)+1 for t in tags_seguros)} chars): {tags_seguros}")
    
    body = {
        "snippet": {"title": datos["titulo"][:100], "description": desc_final[:5000], "tags": tags_seguros, "categoryId": "24", "defaultLanguage": "es"},
        "status": {"privacyStatus": "private", "publishAt": hora_programada_utc, "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True}
    }
    
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=MediaFileUpload(ruta_video, chunksize=4*1024*1024, resumable=True))
    response = request.execute()
    video_id = response["id"]
    print(f"✅ Video subido. ID: {video_id}")
    
    youtube.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(ruta_miniatura)).execute()
    print("✅ Miniatura aplicada.")
    
    youtube.commentThreads().insert(part="snippet", body={
        "snippet": {"videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": datos["comentario_fijado"]}}}
    }).execute()
    print("✅ Comentario fijado publicado.")
    
    return video_id

# ================================================================
# 8. FLUJO PRINCIPAL
# ================================================================
def main():
    try:
        hora_utc, hora_cdmx = calcular_hora_publicacion()
        print(f"🎯 Programando publicación para hoy a las {hora_cdmx} (CDMX)")
        
        fecha_hoy = datetime.now(TZ).strftime("%d de %B de %Y")
        fase_lunar = "Creciente"
        
        print("🧠 1. Generando contenido con DeepSeek...")
        datos = llamar_deepseek(fecha_hoy, fase_lunar)
        print(f"   Título elegido: {datos['titulo']}")
        
        print("🎨 2. Generando activos (Imágenes y Audio) para los 12 signos...")
        for i, signo in enumerate(datos["signos"]):
            print(f"   Procesando {signo['nombre']}...")
            img_path = f"temp_signo_{i}.jpg"
            audio_path = f"temp_audio_{i}.mp3"
            
            obtener_imagen_segura(signo.get("visual_prompt", "mystical galaxy stars"), img_path)
            asyncio.run(generar_audio(signo["guion"], audio_path))
            
        print("🖼️ 3. Creando miniatura...")
        ruta_miniatura = "miniatura.jpg"
        obtener_imagen_segura(datos["miniatura_prompt"], "temp_bg_thumb.jpg", es_miniatura=True)
        crear_miniatura_con_texto("temp_bg_thumb.jpg", datos["miniatura_texto"], ruta_miniatura)
        
        print("🎬 4. Renderizando video...")
        ruta_video = "video_final.mp4"
        renderizar_video(datos["signos"], ruta_video)
        
        print("📤 5. Subiendo a YouTube...")
        subir_a_youtube(ruta_video, ruta_miniatura, datos, hora_utc)
        
        print("✨ ¡PROCESO COMPLETADO CON ÉXITO! El video se publicará automáticamente.")
        
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
