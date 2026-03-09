import json

try:
    import pdfplumber
    PDFPLUMBER_OK = True
except ImportError:
    PDFPLUMBER_OK = False

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
    GEMINI_OK = True
except ImportError:
    GEMINI_OK = False


PROMPT_SISTEMA = """
Eres un asistente experto en Recursos Humanos y extracción de datos.
Tu tarea es leer el texto de un currículum vitae (CV) desestructurado y extraer la información en un formato JSON estricto, adaptado a la plantilla de la empresa Entelgy.

REGLAS DE EXTRACCIÓN:
1. "iniciales": Extrae la primera letra de cada nombre y apellido. Ejemplo: "David Josue Solano Quinte" -> "D. J. S. Q."
2. "presentacion": Crea un resumen profesional de máximo 4 líneas mencionando universidad, ciclo, tecnologías clave y competencias.
3. "experiencia": ¡MUY IMPORTANTE! Extrae ÚNICAMENTE experiencia laboral o pre-profesional real en empresas. EXCLUYE ESTRICTAMENTE proyectos universitarios, trabajos de curso, hackathons o "Logros Académicos". Ordena de la más reciente a la más antigua. Si el CV no tiene experiencia laboral real, reemplaza la lista con: "Sin experiencia laboral previa.".
4. "proyectos_academicos": Si el candidato menciona sistemas, proyectos o logros académicos (como el "Sistema Eficiente de Gestión de Biblioteca"), intégralos dentro de la lista de "estudios_complementarios" usando este formato: "Proyecto Académico: [Nombre del proyecto] - Tecnologías: [Tecnologías]".
5. Reemplaza cualquier viñeta especial (como • o asteriscos) por guiones (-) en los textos.
6. "consideraciones": Revisa si en la experiencia laboral extraída faltó mencionar datos clave de Entelgy como el "sector", el "proyecto" o la "tecnología". Si se omitieron, redacta un breve párrafo indicando qué datos faltaron en el CV original. Si todo estaba completo o si no hay experiencia laboral, indica: "No se omitieron campos clave o el CV no presenta experiencia laboral."
7. DEBES responder ÚNICAMENTE con un objeto JSON válido. No incluyas texto antes ni después, ni bloques de código markdown.
8. "idiomas": Siempre se considerará el idioma "Español: Nativo" por defecto y debe ser el primer elemento de la lista a menos que el CV indique explícitamente otra lengua materna. Los elementos de esta lista DEBEN ser cadenas de texto simples (strings), NUNCA objetos ni diccionarios.

ESTRUCTURA JSON REQUERIDA:
{
    "iniciales": "...",
    "presentacion": "...",
    "experiencia": [
        {
            "empresa": "...",
            "fechas": "Mes Año - Mes Año o Actualidad",
            "cargo": "...",
            "sector": "...",
            "proyecto": "...",
            "tecnologia": "...",
            "funciones": ["función 1", "función 2"]
        }
    ],
    "estudios_superiores": ["Universidad, Facultad, Grado, año de egreso"],
    "certificaciones": ["Institución: Nombre Certificación - Año"],
    "estudios_complementarios": ["Nombre del curso, taller o Proyecto Académico"],
    "idiomas": ["Español: Nativo", "Inglés: Avanzado. Institución: ICPNA"],
    "consideraciones": "..."
}
"""

def extraer_texto_pdf(ruta_pdf):
    """Extrae y limpia el texto de un archivo PDF."""
    if not PDFPLUMBER_OK:
        return None
    texto = ""
    try:
        with pdfplumber.open(ruta_pdf) as pdf:
            for pagina in pdf.pages:
                t = pagina.extract_text(layout=True)
                if t:
                    texto += t + "\n"
        lineas = [l.rstrip() for l in texto.split("\n") if l.strip()]
        return "\n".join(lineas)
    except Exception:
        return None

def procesar_con_gemini(texto_cv, api_key, modelo="gemini-2.5-flash", datos_extra=""):
    """Procesa el texto de un CV con Gemini y devuelve JSON estructurado."""
    if not GEMINI_OK:
        return None, "El paquete google-genai no está instalado."

    cliente = genai.Client(api_key=api_key)
    prompt = f"{PROMPT_SISTEMA}\n\nTEXTO DEL CV:\n{texto_cv}"
    if datos_extra and datos_extra.strip():
        prompt += (
            f"\n\nDATOS EXTRA DEL USUARIO:\n{datos_extra}\n"
            "(Asegúrate de integrar o modificar el CV original con estos datos)."
        )

    try:
        response = cliente.models.generate_content(
            model=modelo,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
        return json.loads(response.text), None
    except APIError as e:
        return None, f"Error API Gemini: {e}"
    except json.JSONDecodeError as e:
        return None, f"JSON inválido de la IA: {e}"
    except Exception as e:
        return None, f"Error inesperado: {e}"

def actualizar_json_con_gemini(json_actual, datos_extra, api_key, modelo="gemini-2.5-flash"):
    """Actualiza un JSON de CV existente con instrucciones del usuario vía Gemini."""
    if not GEMINI_OK:
        return None, "El paquete google-genai no está instalado."

    cliente = genai.Client(api_key=api_key)
    prompt = (
        "Eres un asistente experto en Recursos Humanos.\n"
        "JSON actual del CV estructurado según plantilla Entelgy:\n"
        f"{json.dumps(json_actual, ensure_ascii=False)}\n\n"
        f"INSTRUCCIONES DE MODIFICACIÓN:\n{datos_extra}\n\n"
        "Aplica las modificaciones y devuelve ÚNICAMENTE el JSON actualizado.\n"
        'La lista de "idiomas" debe contener SOLO cadenas de texto (strings).\n'
        "No incluyas texto extra ni bloques markdown."
    )

    try:
        response = cliente.models.generate_content(
            model=modelo,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            ),
        )
        return json.loads(response.text), None
    except Exception as e:
        return None, f"Error al actualizar: {e}"