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
        # Extraemos un máximo de 10 páginas para dar contexto a la IA sin pasarnos del límite
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
    """Limpia los bloques de código ```json ... ``` que la IA suele añadir"""
    lineas = texto_respuesta.strip().split('\n')
    lineas_limpias = []
    for linea in lineas:
        linea_strip = linea.strip()
        if linea_strip.startswith("```"):
            continue
        lineas_limpias.append(linea)
    return "\n".join(lineas_limpias).strip()

def consultar_groq(texto_pdf):
    prompt = f"""
    Analiza el siguiente texto extraído de un libro o documento y genera un objeto JSON que describa su contenido para un motor de búsqueda médica o científica.
    
    El formato de salida DEBE ser estrictamente un JSON válido, sin bloques de código markdown, siguiendo esta estructura exacta:
    {{
        "titulo": "Título de la obra",
        "autor": "Nombre del autor",
        "año": "Año de publicación",
        "resumen": "Un resumen conciso de 3-4 líneas sobre de qué trata y su utilidad",
        "palabras_clave": ["palabra1", "palabra2"],
        "categorias": ["categoria1"]
    }}

    Texto extraído del documento:
    {texto_pdf[:4000]}
    """

    try:
        print("   Enviando fragmento de texto a la API de Groq...")
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",  # Actualizado al modelo activo de Groq
            temperature=0.1,
        )
        respuesta_bruta = chat_completion.choices[0].message.content
        respuesta_limpia = limpiar_respuesta_json(respuesta_bruta)
        
        # Validamos que realmente sea un JSON estructurado
        datos_json = json.loads(respuesta_limpia)
        return datos_json
    except json.JSONDecodeError as je:
        print(f"   [ERROR] La IA no devolvió un JSON válido. Respuesta recibida:\n{respuesta_bruta}")
        return None
    except Exception as e:
        print(f"   [ERROR] Falló la comunicación con Groq: {e}")
        return None

def actualizar_index(nuevo_item):
    if os.path.exists(ARCHIVO_INDEX):
        with open(ARCHIVO_INDEX, 'r', encoding='utf-8') as f:
            try:
                datos = json.load(f)
            except json.JSONDecodeError:
                print("[ADVERTENCIA] index.json estaba corrupto o vacío. Reiniciando base de datos.")
                datos = []
    else:
        datos = []

    # Se adapta al formato actual de tu index.json
    if isinstance(datos, list):
        datos.append(nuevo_item)
    elif isinstance(datos, dict) and "libros" in datos:
        datos["libros"].append(nuevo_item)
    else:
        if "items" not in datos:
            datos["items"] = []
        datos["items"].append(nuevo_item)

    with open(ARCHIVO_INDEX, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)
    print("   [ÉXITO] index.json actualizado localmente con los nuevos metadatos.")

def main():
    procesados = cargar_procesados()
    archivos_pdf = glob.glob(os.path.join(CARPETA_PDFS, "*.pdf"))
    
    print(f"[INFO] Se encontraron {len(archivos_pdf)} archivos PDF en la raíz del repositorio.")
    hubo_cambios = False

    for ruta_pdf in archivos_pdf:
        nombre_archivo = os.path.basename(ruta_pdf)
        
        if nombre_archivo in procesados:
            print(f"-> Saltando '{nombre_archivo}': ya fue procesado previamente.")
            continue

        print(f"-> NUEVO DOCUMENTO DETECTADO: '{nombre_archivo}'")
        texto = extraer_texto_pdf(ruta_pdf)
        
        if not texto or len(texto.strip()) == 0:
            print("   [ADVERTENCIA] No se pudo extraer texto. Es posible que el PDF esté escaneado como imagen. Saltando...")
            continue
            
        print(f"   Texto extraído correctamente ({len(texto)} caracteres).")
        info_json = consultar_groq(texto)
        
        if info_json:
            # Construir URL directa de descarga
            info_json["url_pdf"] = f"[https://navarrodavidguillermo.github.io/biblioteca/](https://navarrodavidguillermo.github.io/biblioteca/){nombre_archivo}"
            actualizar_index(info_json)
            guardar_procesado(nombre_archivo)
            hubo_cambios = True
            print(f"   [OK] '{nombre_archivo}' registrado con éxito.")
        else:
            print(f"   [FALLO] No se pudieron obtener metadatos para '{nombre_archivo}'.")

    if hubo_cambios:
        print("=== PROCESAMIENTO TERMINADO: Se guardaron nuevos datos ===")
    else:
        print("=== PROCESAMIENTO TERMINADO: No hubo cambios que guardar ===")

if __name__ == "__main__":
    main()
