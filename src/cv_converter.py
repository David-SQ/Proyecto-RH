"""
cv_converter.py — Extracción de texto de CVs y generación de PDF formato Entelgy.
Usa pdfplumber para lectura, google-genai para procesamiento IA y fpdf2 para PDF.
"""

import os
import json
import re
from fpdf import FPDF

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


# ══════════════════════════════════════════════════════════
#  Extracción de texto
# ══════════════════════════════════════════════════════════

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


# ══════════════════════════════════════════════════════════
#  Procesamiento con Gemini
# ══════════════════════════════════════════════════════════

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


def actualizar_json_con_gemini(json_actual, datos_extra, api_key,
                               modelo="gemini-2.5-flash"):
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


# ══════════════════════════════════════════════════════════
#  Generación de PDF  (fpdf2)
# ══════════════════════════════════════════════════════════

def _safe(text):
    """Hace el texto seguro para fuentes built-in de fpdf2 (windows-1252)."""
    if not isinstance(text, str):
        text = str(text)
    reemplazos = {
        "\u2022": "-", "\u2023": "-", "\u25cf": "-",
        "\u2013": "-", "\u2014": "-",
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2026": "...", "\u00a0": " ",
    }
    for k, v in reemplazos.items():
        text = text.replace(k, v)
    try:
        text.encode("windows-1252")
        return text
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text.encode("windows-1252", errors="replace").decode("windows-1252")


class _PDFEntelgy(FPDF):
    C_AZUL = (0, 30, 60)
    C_GRIS = (50, 50, 50)
    C_GRIS2 = (80, 80, 80)

    def __init__(self):
        super().__init__()
        self.set_auto_page_break(auto=True, margin=20)

    def header(self):
        if self.page_no() > 1:
            self.set_font("Helvetica", "I", 8)
            self.set_text_color(*self.C_GRIS2)
            self.cell(0, 8, "CV - Formato Entelgy", align="R")
            self.ln(12)

    def seccion(self, titulo):
        self.ln(3)
        self.set_font("Helvetica", "B", 13)
        self.set_text_color(*self.C_AZUL)
        self.cell(0, 10, _safe(titulo), new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*self.C_AZUL)
        self.set_line_width(0.5)
        self.line(self.l_margin, self.get_y(),
                  self.w - self.r_margin, self.get_y())
        self.ln(4)

    def parrafo(self, texto):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*self.C_GRIS)
        self.multi_cell(0, 5.5, _safe(texto))
        self.ln(2)

    def viñeta(self, texto, indent=5):
        old_lm = self.l_margin
        self.set_left_margin(old_lm + indent + 6)
        self.set_x(old_lm + indent)
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*self.C_GRIS)
        self.cell(6, 5.5, "-")
        self.multi_cell(0, 5.5, _safe(texto))
        self.set_left_margin(old_lm)
        self.ln(1)

    def etiqueta(self, label, valor):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*self.C_AZUL)
        w = self.get_string_width(_safe(label)) + 2
        self.cell(w, 5.5, _safe(label))
        self.set_font("Helvetica", "", 10)
        self.set_text_color(*self.C_GRIS)
        self.multi_cell(0, 5.5, _safe(valor))


def generar_pdf_entelgy(datos_cv, ruta_salida, logo_path=None):
    """Genera un PDF con formato Entelgy a partir del JSON estructurado."""
    pdf = _PDFEntelgy()
    pdf.add_page()

    # ── Logo / cabecera ──
    logo_ok = (logo_path and os.path.exists(logo_path)
               and os.path.getsize(logo_path) > 0)
    if logo_ok:
        try:
            pdf.image(logo_path, x=(pdf.w - 50) / 2, y=10, w=50)
            pdf.ln(25)
        except Exception:
            logo_ok = False
    if not logo_ok:
        pdf.ln(5)
        pdf.set_font("Helvetica", "B", 22)
        pdf.set_text_color(0, 30, 60)
        pdf.cell(0, 12, "ENTELGY", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(5)

    # ── Iniciales ──
    iniciales = datos_cv.get("iniciales", "")
    if iniciales:
        pdf.set_font("Helvetica", "B", 28)
        pdf.set_text_color(0, 30, 60)
        pdf.cell(0, 15, _safe(iniciales), align="C",
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)

    # ── Presentación ──
    pres = datos_cv.get("presentacion", "")
    if pres:
        pdf.seccion("PRESENTACION")
        pdf.parrafo(pres)

    # ── Experiencia profesional ──
    exp_list = datos_cv.get("experiencia", [])
    if exp_list:
        pdf.seccion("EXPERIENCIA PROFESIONAL")
        if isinstance(exp_list, str):
            pdf.parrafo(exp_list)
        elif isinstance(exp_list, list):
            for exp in exp_list:
                pdf.set_font("Helvetica", "B", 11)
                pdf.set_text_color(*_PDFEntelgy.C_AZUL)
                pdf.cell(0, 7, _safe(exp.get("empresa", "")),
                         new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("Helvetica", "I", 10)
                pdf.set_text_color(*_PDFEntelgy.C_GRIS2)
                pdf.cell(0, 5.5,
                         _safe(f"Periodo: {exp.get('fechas', '')}"),
                         new_x="LMARGIN", new_y="NEXT")
                pdf.etiqueta("Cargo: ", exp.get("cargo", ""))
                pdf.etiqueta("Sector: ", exp.get("sector", ""))
                pdf.etiqueta("Proyecto: ", exp.get("proyecto", ""))
                pdf.etiqueta("Tecnologia: ", exp.get("tecnologia", ""))
                for func in exp.get("funciones", []):
                    pdf.viñeta(func)
                pdf.ln(3)

    # ── Estudios superiores ──
    for sec_key, sec_titulo in [
        ("estudios_superiores", "ESTUDIOS SUPERIORES"),
        ("certificaciones", "CERTIFICACIONES COMPROBADAS"),
        ("estudios_complementarios", "ESTUDIOS COMPLEMENTARIOS"),
    ]:
        items = datos_cv.get(sec_key, [])
        if items:
            pdf.seccion(sec_titulo)
            for it in items:
                pdf.viñeta(it)

    # ── Idiomas ──
    idiomas = datos_cv.get("idiomas", [])
    if idiomas:
        pdf.seccion("IDIOMAS")
        for idi in idiomas:
            if isinstance(idi, dict):
                nombre = idi.get("idioma", idi.get("nombre", "Desconocido"))
                nivel = idi.get("nivel", "")
                inst = idi.get("institucion", "")
                txt = f"{nombre}: {nivel}"
                if inst:
                    txt += f". Institucion: {inst}"
                pdf.viñeta(txt)
            else:
                pdf.viñeta(str(idi))

    # ── Consideraciones ──
    consid = datos_cv.get("consideraciones", "")
    if consid and consid.strip():
        pdf.seccion("CONSIDERACIONES")
        pdf.parrafo(consid)

    # Guardar
    dir_salida = os.path.dirname(ruta_salida)
    if dir_salida:
        os.makedirs(dir_salida, exist_ok=True)
    pdf.output(ruta_salida)
    return ruta_salida
