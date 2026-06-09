import os
import json
import glob
from pypdf import PdfReader
from groq import Groq

# Configuración de rutas
GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
CARPETA_PDFS = "./"  # Raíz del repositorio
ARCHIVO_INDEX = "./index.json"
PROCESADOS_LOG = "./procesados.txt"

print("=== INICIANDO DETECTOR E INDEXADOR DE BIBLIOTECA ===")

if not GROQ_API_KEY:
    print("[ERROR CRÍTICO] No se encontró la GROQ_API_KEY en los secretos de GitHub.")
    exit(1)

client = Groq(api_key=GROQ_API_KEY)

def cargar_procesados():
    if os.path.exists(PROCESADOS_LOG):
        with open(PROCESADOS_LOG, 'r', encoding='utf-8') as f:
            lineas = f.read().splitlines()
            print(f"[INFO] Encontrados {len(lineas)} archivos ya procesados anteriormente.")
            return set(lineas)
    print("[INFO] No se encontró historial de procesados previos. Se iniciará desde cero.")
    return set()

def guardar_procesado(archivo):
    with open(PROCESADOS_LOG, 'a', encoding='utf-8') as f:
        f.write(archivo + "\n")

def extraer_texto_pdf(ruta_pdf):
    try:
        reader = PdfReader(ruta_pdf)
        texto = ""
        paginas_a_leer = min(len(reader.pages), 10)
        print(f"   Leyendo {paginas_a_leer} páginas de {os.path.basename(ruta_pdf)}...")
        
        for i in range(paginas_a_leer):
            content = reader.pages[i].extract_text()
            if content:
                texto += content
        return texto
    except Exception as e:
        print(f"   [ERROR] No se pudo leer el archivo PDF: {e}")
        return None

def limpiar_respuesta_json(texto_respuesta):
    texto = texto_respuesta.strip()
    if "```json" in texto:
        partes = texto.split("```json")
        if len(partes) > 1:
            return partes[1].split("```")[0].strip()
    elif "```" in texto:
        partes = texto.split("```")
        if len(partes) > 1:
            sub_texto = partes[1].strip()
            if sub_texto.lower().startswith("json"):
                sub_texto = sub_texto[4:].strip()
            return sub_texto
    inicio = texto.find('{')
    fin = texto.rfind('}')
    if inicio != -1 and fin != -1 and fin > inicio:
        return texto[inicio:fin+1].strip()
    return texto

def consultar_groq(texto_pdf, nombre_archivo):
    prompt = f"""
    Analiza el siguiente texto de un documento médico y genera un JSON.
    El campo "nombre" DEBE ser exactamente: "{nombre_archivo}"
    
    Estructura requerida:
    {{
        "nombre": "{nombre_archivo}",
        "archivo": "{nombre_archivo}",
        "palabras_clave": ["lista de términos médicos"],
        "excluir": ["lista de términos a excluir"]
    }}

    Texto extraído:
    {texto_pdf[:4000]}
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.1,
        )
        respuesta_bruta = chat_completion.choices[0].message.content
        respuesta_limpia = limpiar_respuesta_json(respuesta_bruta)
        
        datos_json = json.loads(respuesta_limpia)
        
        # --- LÓGICA DE FUERZA BRUTA PARA MANTENER EL NOMBRE ---
        datos_json["nombre"] = nombre_archivo
        datos_json["archivo"] = nombre_archivo
        
        if "palabras_clave" not in datos_json:
            datos_json["palabras_clave"] = []
        if "excluir" not in datos_json:
            datos_json["excluir"] = []
            
        return datos_json
    except Exception as e:
        print(f"   [ERROR] Falló el procesamiento con Groq: {e}")
        return None

def actualizar_index(nuevo_item):
    if os.path.exists(ARCHIVO_INDEX):
        with open(ARCHIVO_INDEX, 'r', encoding='utf-8') as f:
            try:
                datos = json.load(f)
            except:
                datos = []
    else:
        datos = []

    if not isinstance(datos, list):
        datos = []

    datos.append(nuevo_item)

    with open(ARCHIVO_INDEX, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)
    print("   [ÉXITO] index.json actualizado.")

def main():
    procesados = cargar_procesados()
    archivos_pdf = glob.glob(os.path.join(CARPETA_PDFS, "*.pdf"))
    
    hubo_cambios = False
    for ruta_pdf in archivos_pdf:
        nombre_archivo = os.path.basename(ruta_pdf)
        
        if nombre_archivo in procesados:
            continue

        print(f"-> PROCESANDO: '{nombre_archivo}'")
        texto = extraer_texto_pdf(ruta_pdf)
        
        if texto:
            info_json = consultar_groq(texto, nombre_archivo)
            if info_json:
                actualizar_index(info_json)
                guardar_procesado(nombre_archivo)
                hubo_cambios = True

    if hubo_cambios:
        print("=== PROCESAMIENTO TERMINADO: Cambios guardados ===")

if __name__ == "__main__":
    main()
