import io
import os
import re
from html import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

COLOR_PRIMARY_RED = colors.HexColor("#B72727")
COLOR_TEXT_DARK = colors.HexColor("#1A1A1A")
COLOR_HEADER_BG = colors.HexColor("#F2F2F2")
COLOR_BORDER = colors.HexColor("#CFCFCF")
PAGE_WIDTH, PAGE_HEIGHT = A4

LEFT_MARGIN = 25
RIGHT_MARGIN = 25
TOP_MARGIN = 18
FOOTER_AREA = 58
BOTTOM_MARGIN = FOOTER_AREA + 8


def safe_text(value):
    return escape(str(value or ""))


def format_currency(val):
    if val is None:
        return "-"
    return f"{int(round(float(val))):,}"


def format_pct(val):
    if val is None:
        return "-"
    return f"{float(val) * 100:.1f}%"


def _wrap_plain_text(text, font_name, font_size, max_width):
    """Envuelve texto del footer respetando saltos de línea ingresados por el usuario."""
    output = []
    paragraphs = str(text or "").splitlines() or [""]
    for paragraph in paragraphs:
        if not paragraph.strip():
            output.append("")
            continue
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if stringWidth(candidate, font_name, font_size) <= max_width:
                current = candidate
            else:
                if current:
                    output.append(current)
                current = word
        if current:
            output.append(current)
    return output


class FooterCanvas(canvas.Canvas):
    def __init__(self, *args, footer_text="", **kwargs):
        super().__init__(*args, **kwargs)
        self.footer_text = footer_text or ""

    def draw_footer(self):
        if not self.footer_text.strip():
            return

        self.saveState()
        max_width = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN
        font_name = "Helvetica"
        font_size = 7.0
        leading = 8.5

        # Si el usuario ingresa bastante texto, reduce moderadamente el tamaño
        # para conservar todas las líneas dentro de la zona reservada.
        while font_size >= 5.5:
            lines = _wrap_plain_text(self.footer_text, font_name, font_size, max_width)
            leading = font_size + 1.4
            if len(lines) * leading <= FOOTER_AREA - 13:
                break
            font_size -= 0.25

        self.setStrokeColor(COLOR_BORDER)
        self.setLineWidth(0.5)
        self.line(LEFT_MARGIN, FOOTER_AREA, PAGE_WIDTH - RIGHT_MARGIN, FOOTER_AREA)
        self.setFillColor(COLOR_TEXT_DARK)
        self.setFont(font_name, font_size)

        y = FOOTER_AREA - 11
        for line in lines:
            if y < 5:
                break
            self.drawString(LEFT_MARGIN, y, line)
            y -= leading
        self.restoreState()

    def showPage(self):
        self.draw_footer()
        super().showPage()

    def save(self):
        # Garantiza footer también en la última página si ReportLab no llamó showPage aún.
        super().save()


def _density_profile(project_info):
    """Selecciona una densidad de maquetación considerando TODO el contenido variable."""
    resumen_len = len(project_info.get("resumen", "") or "")
    fin_rows = len(project_info.get("financiero", []))
    fisico = project_info.get("fisico", {})
    physical_len = sum(len((fisico.get(k) or {}).get("desc", "") or "") for k in fisico)
    name_len = len(project_info.get("nombre_inversion", "") or "")

    score = resumen_len + physical_len + (fin_rows * 75) + (name_len * 0.5)
    if score > 1500 or fin_rows >= 9:
        return "dense"
    if score > 1050 or fin_rows >= 8:
        return "compact"
    return "normal"


def generate_pdf_bytes(project_info, footer_text, logo_produce_path, logo_itp_path):
    buffer = io.BytesIO()
    density = _density_profile(project_info)

    settings = {
        "normal":  {"spacer": 5, "body": 8.0, "body_lead": 10.2, "table": 7.2, "table_lead": 8.7, "pad": 2.5},
        "compact": {"spacer": 3, "body": 7.5, "body_lead": 9.2,  "table": 6.7, "table_lead": 8.0, "pad": 1.8},
        "dense":   {"spacer": 2, "body": 7.0, "body_lead": 8.3,  "table": 6.2, "table_lead": 7.2, "pad": 1.2},
    }[density]

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        allowSplitting=1,
    )

    styles = getSampleStyleSheet()
    proj_title = ParagraphStyle(
        "ProjTitle", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=9.5 if density == "normal" else 8.8, leading=11,
        textColor=COLOR_PRIMARY_RED, alignment=TA_LEFT,
    )
    header_label = ParagraphStyle(
        "HeaderLabel", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=7.7, leading=9.2, textColor=COLOR_TEXT_DARK,
    )
    header_val = ParagraphStyle(
        "HeaderVal", parent=styles["Normal"], fontName="Helvetica",
        fontSize=7.7, leading=9.2, textColor=COLOR_TEXT_DARK,
    )
    section_heading = ParagraphStyle(
        "SectionHeading", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=8.2, leading=9.7, textColor=COLOR_PRIMARY_RED,
    )
    body_text = ParagraphStyle(
        "BodyTextCustom", parent=styles["Normal"], fontName="Helvetica",
        fontSize=settings["body"], leading=settings["body_lead"],
        textColor=COLOR_TEXT_DARK, alignment=TA_JUSTIFY,
    )
    tbl_cell = ParagraphStyle(
        "TblCell", parent=styles["Normal"], fontName="Helvetica",
        fontSize=settings["table"], leading=settings["table_lead"],
        textColor=COLOR_TEXT_DARK, alignment=TA_LEFT,
    )
    tbl_cell_bold = ParagraphStyle("TblCellBold", parent=tbl_cell, fontName="Helvetica-Bold")
    tbl_header = ParagraphStyle(
        "TblHeader", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=settings["table"], leading=settings["table_lead"],
        textColor=COLOR_TEXT_DARK, alignment=TA_CENTER,
    )
    pct_style = ParagraphStyle(
        "PctStyle", parent=header_label, alignment=TA_RIGHT,
        fontSize=7.5 if density != "dense" else 7.0,
    )

    story = []

    # Encabezado institucional. Si falta un logo, se usa marcador visible en vez de romper el PDF.
    produce = Paragraph("<b>PRODUCE</b>", header_label)
    if os.path.exists(logo_produce_path):
        produce = Image(str(logo_produce_path), width=130, height=28, kind="proportional")
    itp = Paragraph("<b>ITP</b>", header_label)
    if os.path.exists(logo_itp_path):
        itp = Image(str(logo_itp_path), width=100, height=28, kind="proportional")

    title = Paragraph(f"<b>PROYECTO:</b><br/>{safe_text(project_info['proyecto'])}", proj_title)
    header = Table([[produce, title, itp]], colWidths=[140, 265, 140])
    header.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
    ]))
    story += [header, Spacer(1, settings["spacer"])]

    meta = [
        [Paragraph("<b>CUI</b>", header_label), Paragraph(f": {safe_text(project_info['cui'])}", header_val),
         Paragraph("<b>TIPO</b>", header_label), Paragraph(f": {safe_text(project_info['tipo'])}", header_val)],
        [Paragraph("<b>PROYECTO</b>", header_label), Paragraph(f": {safe_text(project_info['nombre_inversion'] or project_info['proyecto'])}", header_val),
         Paragraph("<b>ESTADO</b>", header_label), Paragraph(f": {safe_text(project_info['estado'])}", header_val)],
    ]
    meta_table = Table(meta, colWidths=[70, 260, 55, 160])
    meta_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story += [meta_table, Spacer(1, settings["spacer"] + 1)]

    story += [Paragraph("I. Resumen de la Inversión", section_heading), Spacer(1, 1)]
    story.append(Paragraph(safe_text(project_info.get("resumen") or "-"), body_text))
    story.append(Spacer(1, settings["spacer"] + 1))

    story += [Paragraph("II. Avance Financiero", section_heading), Spacer(1, 1)]
    fin_table_data = [[
        Paragraph("Componente", tbl_header), Paragraph("Monto de<br/>Inversión", tbl_header),
        Paragraph("Ejecución<br/>Acumulada", tbl_header), Paragraph("% Avance", tbl_header),
        Paragraph("PIM 2026", tbl_header), Paragraph("Ejecución 2026", tbl_header),
    ]]

    fin_list = project_info.get("financiero", [])
    for row in fin_list:
        is_total = row["componente"].strip().upper() == "TOTAL"
        cell = tbl_cell_bold if is_total else tbl_cell
        right = ParagraphStyle("NumRight", parent=cell, alignment=TA_RIGHT)
        center = ParagraphStyle("PctCenter", parent=cell, alignment=TA_CENTER)
        fin_table_data.append([
            Paragraph(safe_text(row["componente"]), cell),
            Paragraph(format_currency(row["monto"]), right),
            Paragraph(format_currency(row["ejec_acum"]), right),
            Paragraph(format_pct(row["pct_avance"]), center),
            Paragraph(format_currency(row["pim_2026"]), right),
            Paragraph(format_currency(row["ejec_2026"]), right),
        ])

    if len(fin_table_data) == 1:
        fin_table_data.append([Paragraph("Sin información financiera", tbl_cell)] + ["-"] * 5)

    fin_table = Table(fin_table_data, colWidths=[145, 80, 80, 60, 90, 90], repeatRows=1)
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_HEADER_BG),
        ("GRID", (0, 0), (-1, -1), 0.45, COLOR_BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), settings["pad"]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), settings["pad"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for idx, row in enumerate(fin_list, start=1):
        if row["componente"].strip().upper() == "TOTAL":
            table_style += [
                ("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#FAFAFA")),
                ("LINEABOVE", (0, idx), (-1, idx), 0.7, colors.HexColor("#999999")),
            ]
    fin_table.setStyle(TableStyle(table_style))
    story += [fin_table, Spacer(1, settings["spacer"] + 1)]

    fisico = project_info.get("fisico", {})
    blocks = [
        ("III. Avance Físico del Componente de Infraestructura", fisico.get("infraestructura")),
        ("IV. Avance Físico del Componente de Equipamiento", fisico.get("equipamiento")),
        ("V. Avance Físico del Componente de Capacitación", fisico.get("capacitacion")),
        ("VI. Avance Físico del Componente de Transferencia Tecnológica", fisico.get("transferencia")),
    ]
    for block_title, info in blocks:
        info = info or {"desc": "-", "porcentaje": None}
        desc = safe_text(info.get("desc") or "-")
        pct = format_pct(info.get("porcentaje"))
        block_table = Table([[Paragraph(desc, body_text), Paragraph(f"<b>% Avance :</b> {pct}", pct_style)]], colWidths=[415, 130])
        block_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(KeepTogether([
            Paragraph(block_title, section_heading), Spacer(1, 1), block_table,
            Spacer(1, settings["spacer"]),
        ]))

    def canvas_maker(*args, **kwargs):
        return FooterCanvas(*args, footer_text=footer_text, **kwargs)

    doc.build(story, canvasmaker=canvas_maker)
    buffer.seek(0)
    return buffer.getvalue()
