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
    """
    Extrae de forma robusta únicamente el bloque JSON, omitiendo cualquier texto
    conversacional que la IA haya agregado antes o después.
    """
    texto = texto_respuesta.strip()
    
    # 1. Intentamos buscar por bloques markdown explícitos
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

    # 2. Si no hay bloques formales, recortamos desde la primera llave { hasta la última }
    inicio = texto.find('{')
    fin = texto.rfind('}')
    if inicio != -1 and fin != -1 and fin > inicio:
        return texto[inicio:fin+1].strip()
        
    return texto

def consultar_groq(texto_pdf, nombre_archivo):
    # Solicitamos directamente el formato homologado que usa tu buscador para evitar desajustes
    prompt = f"""
    Analiza el siguiente texto extraído de un documento médico pediátrico y genera un objeto JSON que describa su contenido para un buscador clínico estructurado.
    
    El formato de salida DEBE ser estrictamente un JSON válido, sin bloques de código markdown externos, siguiendo esta estructura exacta:
    {{
        "nombre": "Título representativo y completo del documento pediátrico",
        "archivo": "{nombre_archivo}",
        "palabras_clave": [
            "Lista exhaustiva de términos médicos clave, síntomas, tratamientos, diagnósticos, y sinónimos relevantes en minúsculas presentes o relacionados con el texto"
        ],
        "excluir": [
            "Lista de términos o patologías pediátricas comunes que NO se tratan en este documento para evitar falsos positivos (por ejemplo: si es de asma, excluir meningitis, ataxia, brue, etc.)"
        ]
    }}

    Texto extraído del documento:
    {texto_pdf[:4000]}
    """

    try:
        print("   Enviando fragmento de texto a la API de Groq...")
        chat_completion = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            temperature=0.1,
        )
        respuesta_bruta = chat_completion.choices[0].message.content
        respuesta_limpia = limpiar_respuesta_json(respuesta_bruta)
        
        # Validamos que realmente sea un JSON estructurado
        datos_json = json.loads(respuesta_limpia)
        
        # Forzar que existan los campos clave requeridos por el buscador
        if "nombre" not in datos_json and "titulo" in datos_json:
            datos_json["nombre"] = datos_json.pop("titulo")
            
        datos_json["archivo"] = nombre_archivo
        
        if "palabras_clave" not in datos_json:
            datos_json["palabras_clave"] = []
        if "excluir" not in datos_json:
            datos_json["excluir"] = []
            
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

    # Nos aseguramos de mantener un formato de lista homogénea
    if not isinstance(datos, list):
        if isinstance(datos, dict):
            if "libros" in datos:
                datos = datos["libros"]
            elif "items" in datos:
                datos = datos["items"]
            else:
                datos = list(datos.values())[0] if datos else []
        else:
            datos = []

    # Añadimos el nuevo ítem ya ecualizado
    datos.append(nuevo_item)

    with open(ARCHIVO_INDEX, 'w', encoding='utf-8') as f:
        json.dump(datos, f, indent=4, ensure_ascii=False)
    print("   [ÉXITO] index.json actualizado localmente con los nuevos metadatos ecualizados.")

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
        info_json = consultar_groq(texto, nombre_archivo)
        
        if info_json:
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
