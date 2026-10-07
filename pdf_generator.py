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
    """Genera una ficha A4 inspirada en la maqueta institucional original de Tableau."""
    buffer = io.BytesIO()
    density = _density_profile(project_info)

    settings = {
        "normal":  {"body": 8.0, "body_lead": 10.3, "table": 7.0, "table_lead": 8.2, "pad": 2.1, "gap": 8.0},
        "compact": {"body": 7.5, "body_lead": 9.4,  "table": 6.6, "table_lead": 7.7, "pad": 1.6, "gap": 6.0},
        "dense":   {"body": 7.0, "body_lead": 8.5,  "table": 6.2, "table_lead": 7.2, "pad": 1.1, "gap": 4.5},
    }[density]

    # El original aprovecha un área central más estrecha que la primera versión.
    content_left = 55
    content_right = 55
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=content_left,
        rightMargin=content_right,
        topMargin=18,
        bottomMargin=BOTTOM_MARGIN,
        allowSplitting=1,
    )
    usable = PAGE_WIDTH - content_left - content_right

    styles = getSampleStyleSheet()
    project_box_label = ParagraphStyle(
        "ProjectBoxLabel", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=9.0, leading=10.5, alignment=TA_CENTER, textColor=COLOR_TEXT_DARK,
    )
    project_box_name = ParagraphStyle(
        "ProjectBoxName", parent=project_box_label,
        fontSize=10.0 if density == "normal" else 9.2, leading=11.5,
    )
    red_label = ParagraphStyle(
        "RedLabel", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=7.2, leading=8.4, textColor=colors.white,
    )
    meta_value = ParagraphStyle(
        "MetaValue", parent=styles["Normal"], fontName="Helvetica",
        fontSize=7.4, leading=9.0, textColor=COLOR_TEXT_DARK,
    )
    section_heading = ParagraphStyle(
        "SectionHeading", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=8.3, leading=9.8, textColor=COLOR_TEXT_DARK,
    )
    body_text = ParagraphStyle(
        "BodyTextCustom", parent=styles["Normal"], fontName="Helvetica",
        fontSize=settings["body"], leading=settings["body_lead"],
        textColor=COLOR_TEXT_DARK, alignment=TA_JUSTIFY,
    )
    physical_text = ParagraphStyle(
        "PhysicalText", parent=body_text, alignment=TA_LEFT,
        fontSize=max(settings["body"] - 0.2, 6.8),
        leading=max(settings["body_lead"] - 0.5, 8.0),
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
        textColor=colors.white, alignment=TA_CENTER,
    )
    pct_label_style = ParagraphStyle(
        "PctLabel", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=7.0, leading=8.0, textColor=colors.white, alignment=TA_CENTER,
    )
    pct_value_style = ParagraphStyle(
        "PctValue", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=7.2, leading=8.0, textColor=COLOR_TEXT_DARK, alignment=TA_CENTER,
    )

    story = []

    # 1) Logos en una línea propia, como en la ficha Tableau.
    produce = Paragraph("<b>PRODUCE</b>", meta_value)
    if os.path.exists(logo_produce_path):
        produce = Image(str(logo_produce_path), width=130, height=32, kind="proportional")
    itp = Paragraph("<b>ITP</b>", meta_value)
    if os.path.exists(logo_itp_path):
        itp = Image(str(logo_itp_path), width=95, height=32, kind="proportional")

    logos = Table([[produce, "", itp]], colWidths=[145, usable - 240, 95])
    logos.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (0, 0), "LEFT"),
        ("ALIGN", (2, 0), (2, 0), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    story.append(logos)

    # 2) Caja central del nombre del proyecto con borde rojo y pequeño acento superior.
    project_box = Table([
        [Paragraph("PROYECTO:", project_box_label)],
        [Paragraph(safe_text(project_info["proyecto"]), project_box_name)],
    ], colWidths=[usable])
    project_box.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.8, COLOR_PRIMARY_RED),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 6),
    ]))
    story += [project_box, Spacer(1, 6)]

    # 3) Datos generales: etiquetas rojas a la izquierda y valores en celdas claras.
    label_w = 62
    value_w = usable - label_w
    meta_rows = [
        ("CUI", project_info.get("cui", "")),
        ("PROYECTO", project_info.get("nombre_inversion") or project_info.get("proyecto", "")),
        ("TIPO", project_info.get("tipo", "")),
        ("ESTADO", project_info.get("estado", "")),
    ]
    meta_data = []
    for label, value in meta_rows:
        meta_data.append([
            Paragraph(safe_text(label), red_label),
            Paragraph(safe_text(value), meta_value),
        ])
    meta_table = Table(meta_data, colWidths=[label_w, value_w])
    meta_style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (0, -1), COLOR_PRIMARY_RED),
        ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#E2E2E2")),
        ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E8E8E8")),
        ("LEFTPADDING", (0, 0), (0, -1), 4),
        ("RIGHTPADDING", (0, 0), (0, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2.2),
        ("LEFTPADDING", (1, 0), (1, -1), 5),
    ]
    meta_table.setStyle(TableStyle(meta_style))
    story += [meta_table, Spacer(1, 8 if density == "normal" else 5)]

    # 4) Resumen.
    story += [Paragraph("I. Resumen de la Inversión", section_heading), Spacer(1, 2)]
    story.append(Paragraph(safe_text(project_info.get("resumen") or "-"), body_text))
    story.append(Spacer(1, 9 if density == "normal" else 6))

    # 5) Tabla financiera: cabecera roja con texto blanco, fila Total destacada.
    story += [Paragraph("II. Avance Financiero", section_heading), Spacer(1, 3)]
    fin_table_data = [[
        Paragraph("Componente", tbl_header), Paragraph("Monto de<br/>Inversión", tbl_header),
        Paragraph("Ejecución<br/>Acumulada", tbl_header), Paragraph("% Avance", tbl_header),
        Paragraph("PIM 2026", tbl_header), Paragraph("Ejecución 2026", tbl_header),
    ]]

    fin_list = project_info.get("financiero", [])
    for row in fin_list:
        is_total = row["componente"].strip().upper() == "TOTAL"
        cell = tbl_cell_bold if is_total else tbl_cell
        right = ParagraphStyle(f"NumRight_{len(fin_table_data)}", parent=cell, alignment=TA_RIGHT)
        center = ParagraphStyle(f"PctCenter_{len(fin_table_data)}", parent=cell, alignment=TA_CENTER)
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

    widths = [usable * x for x in (0.23, 0.15, 0.16, 0.14, 0.16, 0.16)]
    fin_table = Table(fin_table_data, colWidths=widths, repeatRows=1)
    table_style = [
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PRIMARY_RED),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D5D5D5")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), settings["pad"]),
        ("BOTTOMPADDING", (0, 0), (-1, -1), settings["pad"]),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
    ]
    for idx, row in enumerate(fin_list, start=1):
        if row["componente"].strip().upper() == "TOTAL":
            table_style += [
                ("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#E9E9E9")),
                ("LINEABOVE", (0, idx), (-1, idx), 0.55, colors.HexColor("#B0B0B0")),
            ]
    fin_table.setStyle(TableStyle(table_style))
    story += [fin_table, Spacer(1, 10 if density == "normal" else 6)]

    # 6) Bloques físicos con el porcentaje en una caja roja/blanca a la derecha.
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
        pct_box = Table([
            [Paragraph("% Avance :", pct_label_style), Paragraph(pct, pct_value_style)]
        ], colWidths=[56, 48])
        pct_box.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (0, 0), COLOR_PRIMARY_RED),
            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#F6F6F6")),
            ("BOX", (0, 0), (-1, -1), 0.35, colors.HexColor("#D0D0D0")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ]))

        title_and_pct = Table([
            [Paragraph(block_title, section_heading), pct_box]
        ], colWidths=[usable - 110, 110])
        title_and_pct.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ]))

        story.append(KeepTogether([
            title_and_pct,
            Spacer(1, 2),
            Paragraph(desc, physical_text),
            Spacer(1, settings["gap"]),
        ]))

    def canvas_maker(*args, **kwargs):
        return FooterCanvas(*args, footer_text=footer_text, **kwargs)

    doc.build(story, canvasmaker=canvas_maker)
    buffer.seek(0)
    return buffer.getvalue()
