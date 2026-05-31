import os
import json
import glob
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
        # Extraemos un máximo de 10 páginas para la lectura
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
    """
    Limpia de forma segura los bloques de markdown como ```json ... ``` 
    sin utilizar expresiones regulares que puedan fallar al copiarse.
    """
    lineas = texto_respuesta.strip().split('\n')
    lineas_limpias = []
    for linea in lineas:
        linea_strip = linea.strip()
        # Ignoramos las líneas que abren o cierran bloques de código de markdown
        if linea_strip.startswith("```"):
            continue
        lineas_limpias.append(linea)
    
    return "\n".join(lineas_limpias).strip()

def consultar_groq(texto_pdf):
    prompt = f"""
    Analiza el siguiente texto extraído de un libro/documento y genera un objeto JSON que describa su contenido para un buscador.
    
    El formato de salida DEBE ser estrictamente un JSON válido, sin bloques de código de markdown (sin ```json), siguiendo exactamente esta estructura:
    {{
        "titulo": "Título de la obra",
        "autor": "Nombre del autor",
        "año": "Año de publicación",
        "resumen": "Un resumen conciso de 3-4 líneas sobre de qué trata",
        "palabras_clave": ["palabra1", "palabra2"],
        "categorias": ["categoria1"]
    }}

    Texto del libro:
    {texto_pdf[:4000]}
    """

    try:
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-8b-8192",
            temperature=0.1,
        )
        respuesta_bruta = chat_completion.choices[0].message.content
        respuesta_limpia = limpiar_respuesta_json(respuesta_bruta)
        return json.loads(respuesta_limpia)
    except Exception as e:
        print(f"Error procesando datos con Groq o JSON inválido: {e}")
        return None

def actualizar_index(nuevo_item):
    if os.path.exists(ARCHIVO_INDEX):
        with open(ARCHIVO_INDEX, 'r', encoding='utf-8') as f:
            try:
                datos = json.load(f)
            except json.JSONDecodeError:
                datos = []
    else:
        datos = []

    # Ajuste dinámico según la estructura de tu index.json
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

def main():
    procesados = cargar_procesados()
    archivos_pdf = glob.glob(os.path.join(CARPETA_PDFS, "*.pdf"))
    hubo_cambios = False

    for ruta_pdf in archivos_pdf:
        nombre_archivo = os.path.basename(ruta_pdf)
        if nombre_archivo in procesados:
            continue

        print(f"Procesando nuevo PDF detectado: {nombre_archivo}")
        texto = extraer_texto_pdf(ruta_pdf)
        if not texto:
            continue

        info_json = consultar_groq(texto)
        if info_json:
            # Línea de asignación de la URL
            info_json["url_pdf"] = f"https://navarrodavidguillermo.github.io/biblioteca/{nombre_archivo}"
            actualizar_index(info_json)
            guardar_procesado(nombre_archivo)
            hubo_cambios = True

    if hubo_cambios:
        print("¡Proceso completado con éxito e index.json actualizado!")
    else:
        print("No se encontraron nuevos PDFs listos para procesar.")

if __name__ == "__main__":
    main()
