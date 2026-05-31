import os
import json
import glob
import re
from pypdf import PdfReader
from groq import Groq

# Obtener la API Key desde los secretos configurados en tu GitHub
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CARPETA_PDFS = "./"  # Busca los PDFs en la raíz del repositorio
ARCHIVO_INDEX = "./index.json"
PROCESADOS_LOG = "./procesados.txt"

if not GROQ_API_KEY:
    print("Error: No se encontró la GROQ_API_KEY en las variables de entorno.")
    exit(1)

client = Groq(api_key=GROQ_API_KEY)

def cargar_procesados():
    if os.path.exists(PROCESADOS_LOG):
        with open(PROCESADOS_LOG, 'r', encoding='utf-8') as f:
            return set(f.read().splitlines())
    return set()

def guardar_procesado(archivo):
    with open(PROCESADOS_LOG, 'a', encoding='utf-8') as f:
        f.write(archivo + "\n")

def extraer_texto_pdf(ruta_pdf):
    try:
        reader = PdfReader(ruta_pdf)
        texto = ""
        # Extraemos un máximo de 10 páginas
        for i, page in enumerate(reader.pages):
            content = page.extract_text()
            if content:
                texto += content
            if i > 10: 
                break
        return texto
    except Exception as e:
        print(f"Error leyendo PDF {ruta_pdf}: {e}")
        return None

def limpiar_respuesta_json(texto_respuesta):
    """Limpia cualquier bloque de código markdown o texto basura antes de procesar el JSON"""
    texto_limpio = texto_respuesta.strip()
    # Remover bloques del tipo ```json ... ``` si la IA los incluye por error
    if texto_limpio.startswith("```"):
        texto_limpio = re.sub(r'^
http://googleusercontent.com/immersive_entry_chip/0

### ¿Qué pasará ahora?
Al guardar este cambio, como la automatización solo se despierta cuando subes archivos `.pdf`, esta modificación en específico no va a activar el indexador de inmediato.

Para probar que todo funciona perfecto:
1. Guarda este nuevo código en `procesar.py`.
2. Sube **un nuevo archivo PDF cualquiera** a tu repositorio.
3. Dirígete a la pestaña **Actions** en la parte superior de tu GitHub y verás el proceso ejecutándose. Esta vez terminará con un cheque verde (`✓`) y tu `index.json` se actualizará solo.
