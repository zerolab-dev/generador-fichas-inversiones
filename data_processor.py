import re
import unicodedata
import pandas as pd

# Mapeo explícito de la estructura validada de los tres archivos fuente.
MAESTRO_COLS = {
    "cui": "CUI",
    "proyecto": "PROYECTO",
    "red_cite": "RED CITE",
    "nombre_inversion": "NOMBRE DE LA INVERSIÓN",
    "resumen": "RESUMEN",
    "tipo": "MODALIDAD DE EJECUCIÓN - TIPO INTERVENCION",
    "estado": "ESTADO SITUACIONAL",
    "region": "REGION",
}

FISICO_COLS = {
    "cui": "CUI",
    "proyecto": "PROYECTO",
    "infra_desc": "ESTADO DE LA INFRAESTRUCTURA",
    "equip_desc": "ESTADO DEL EQUIPAMIENTO",
    "capa_desc": "ESTADO DE LA CAPACITACIÓN",
    "trans_desc": "ESTADO DE LA TRANSFERENCIA",
    "infra_pct": "% AVANCE FISICO INFRAESTRUCTURA",
    "equip_pct": "% AVANCE FISICO EQUIPAMIENTO",
    "capa_pct": "% AVANCE FISICO CAPACITACIÓN",
    "trans_pct": "% AVANCE FISICO TRANSFERENCIA",
}

FIN_COLS = {
    "cui": "CUI",
    "proyecto": "PROYECTO",
    "componente": "COMPONENTE_2",
    "monto": "MONTO DE INVERSIÓN ACTUALIZADO",
    "ejec_acum": "EJECUCION FINANCIERA ACUMULADA",
    # El nombre de origen conserva 2025, pero en las fichas corresponde al periodo 2026.
    "pim": "PIM 2025",
    "ejec_periodo": "EJECUCION FINANCIERA  2025",
}


def normalize_text(val):
    if val is None or pd.isna(val):
        return ""
    return str(val).strip()


def normalize_key_text(val):
    """Normaliza solo para emparejar claves; no altera el texto que se muestra."""
    text = normalize_text(val)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"\s+", " ", text)
    return text.upper()


def normalize_cui(val):
    text = normalize_text(val)
    return text[:-2] if text.endswith(".0") else text


def make_key(cui, proyecto):
    return f"{normalize_cui(cui)}__{normalize_key_text(proyecto)}"


def clean_filename(text):
    text = normalize_text(text)
    text = re.sub(r'[\\/*?:"<>|]', "", text)
    text = re.sub(r"\s+", " ", text).strip().rstrip(".")
    return text or "ficha"


def _missing_columns(df, mapping):
    return [col for col in mapping.values() if col not in df.columns]


def _parse_pct(val):
    """Devuelve None si no hay dato; conserva la diferencia entre vacío y 0%."""
    if val is None or pd.isna(val) or normalize_text(val) == "":
        return None
    try:
        number = float(val)
        return number if abs(number) <= 1 else number / 100.0
    except (TypeError, ValueError):
        return None


def _parse_num(val):
    if val is None or pd.isna(val) or normalize_text(val) == "":
        return 0.0
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


def process_excel_files(file_maestro, file_fisico, file_financiero):
    try:
        df_maestro = pd.read_excel(file_maestro)
        df_fisico = pd.read_excel(file_fisico)
        df_financiero = pd.read_excel(file_financiero)
    except Exception as exc:
        return None, f"Error al abrir los archivos Excel: {exc}"

    checks = [
        ("Maestro de proyectos", df_maestro, MAESTRO_COLS),
        ("Avance físico", df_fisico, FISICO_COLS),
        ("Avance financiero", df_financiero, FIN_COLS),
    ]
    for label, df, mapping in checks:
        missing = _missing_columns(df, mapping)
        if missing:
            return None, f"{label}: faltan columnas requeridas: {', '.join(missing)}"

    projects_data = {}

    # 1) Maestro: una ficha por combinación CUI + PROYECTO.
    for _, row in df_maestro.iterrows():
        cui = normalize_cui(row[MAESTRO_COLS["cui"]])
        proyecto = normalize_text(row[MAESTRO_COLS["proyecto"]])
        if not cui or not proyecto:
            continue

        key = make_key(cui, proyecto)
        projects_data[key] = {
            "key": key,
            "cui": cui,
            "proyecto": proyecto,
            "display_label": f"{cui} - {proyecto}",
            "filename_clean": clean_filename(f"{cui} {proyecto}"),
            "red_cite": normalize_text(row[MAESTRO_COLS["red_cite"]]),
            "nombre_inversion": normalize_text(row[MAESTRO_COLS["nombre_inversion"]]),
            "resumen": normalize_text(row[MAESTRO_COLS["resumen"]]),
            "tipo": normalize_text(row[MAESTRO_COLS["tipo"]]),
            "estado": normalize_text(row[MAESTRO_COLS["estado"]]),
            "region": normalize_text(row[MAESTRO_COLS["region"]]),
            "fisico": {
                "infraestructura": {"desc": "-", "porcentaje": None},
                "equipamiento": {"desc": "-", "porcentaje": None},
                "capacitacion": {"desc": "-", "porcentaje": None},
                "transferencia": {"desc": "-", "porcentaje": None},
            },
            "financiero": [],
        }

    # 2) Avance físico.
    for _, row in df_fisico.iterrows():
        key = make_key(row[FISICO_COLS["cui"]], row[FISICO_COLS["proyecto"]])
        if key not in projects_data:
            continue

        target = projects_data[key]["fisico"]
        assignments = [
            ("infraestructura", "infra_desc", "infra_pct"),
            ("equipamiento", "equip_desc", "equip_pct"),
            ("capacitacion", "capa_desc", "capa_pct"),
            ("transferencia", "trans_desc", "trans_pct"),
        ]
        for target_name, desc_key, pct_key in assignments:
            desc = normalize_text(row[FISICO_COLS[desc_key]])
            target[target_name]["desc"] = desc or "-"
            target[target_name]["porcentaje"] = _parse_pct(row[FISICO_COLS[pct_key]])

    # 3) Avance financiero. Se conserva el orden original de las filas del Excel.
    for _, row in df_financiero.iterrows():
        key = make_key(row[FIN_COLS["cui"]], row[FIN_COLS["proyecto"]])
        if key not in projects_data:
            continue

        componente = normalize_text(row[FIN_COLS["componente"]])
        if not componente:
            continue

        monto = _parse_num(row[FIN_COLS["monto"]])
        ejec_acum = _parse_num(row[FIN_COLS["ejec_acum"]])
        pim = _parse_num(row[FIN_COLS["pim"]])
        ejec_periodo = _parse_num(row[FIN_COLS["ejec_periodo"]])

        projects_data[key]["financiero"].append({
            "componente": componente,
            "monto": monto,
            "ejec_acum": ejec_acum,
            "pct_avance": (ejec_acum / monto) if monto else None,
            "pim_2026": pim,
            "ejec_2026": ejec_periodo,
        })

    # Orden de presentación usado en las fichas institucionales.
    preferred_order = [
        "TOTAL", "INFRAESTRUCTURA", "EQUIPAMIENTO", "CAPACITACION",
        "TRANSFERENCIA TECNOLOGICA", "EXPEDIENTE", "SUPERVISION",
        "GESTION DEL PROYECTO", "OTRO",
    ]

    def canonical(text):
        text = unicodedata.normalize("NFKD", normalize_key_text(text))
        return "".join(ch for ch in text if not unicodedata.combining(ch))

    def order_rank(component):
        name = canonical(component)
        for idx, expected in enumerate(preferred_order):
            if name == expected or expected in name:
                return idx
        return len(preferred_order)

    for project in projects_data.values():
        project["financiero"].sort(key=lambda row: order_rank(row["componente"]))

    return projects_data, None
