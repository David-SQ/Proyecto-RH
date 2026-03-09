import os
from fpdf import FPDF

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