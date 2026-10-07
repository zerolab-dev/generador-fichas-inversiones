import io
import zipfile
from pathlib import Path

import streamlit as st

from data_processor import process_excel_files
from pdf_generator import generate_pdf_bytes

st.set_page_config(
    page_title="Generador de Fichas de Inversión",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

DEFAULT_FOOTER = (
    "Fuente: Dirección de Gestión Operativa de Red CITE (DGO) - ITP / Actualización al 31.08.2026\n"
    "Elaboración: Dirección de Estadística, Seguimiento y Evaluación (DESE)"
)


def main():
    st.title("📄 Generador de Fichas de Inversión")
    st.markdown("Cargue los tres archivos Excel validados para generar automáticamente las fichas técnicas en PDF.")

    st.subheader("1. Carga de archivos Excel")
    col1, col2, col3 = st.columns(3)
    with col1:
        file_maestro = st.file_uploader("Maestro de proyectos (.xlsx)", type=["xlsx"], key="maestro")
    with col2:
        file_fisico = st.file_uploader("Avance físico (.xlsx)", type=["xlsx"], key="fisico")
    with col3:
        file_financiero = st.file_uploader("Avance financiero (.xlsx)", type=["xlsx"], key="financiero")

    if not (file_maestro and file_fisico and file_financiero):
        st.info("Cargue los tres archivos Excel requeridos para continuar.")
        return

    with st.spinner("Procesando y consolidando información..."):
        projects_data, error_msg = process_excel_files(file_maestro, file_fisico, file_financiero)

    if error_msg:
        st.error(error_msg)
        return
    if not projects_data:
        st.warning("No se encontraron proyectos válidos en los archivos proporcionados.")
        return

    st.success(f"Se identificaron **{len(projects_data)}** proyectos/fichas únicas.")

    st.divider()
    st.subheader("2. Pie de página personalizado")
    footer_text = st.text_area(
        "Fuente / pie de página",
        value=DEFAULT_FOOTER,
        height=100,
        help="El texto se aplicará a todas las fichas del lote y quedará anclado al final de la página.",
    )

    st.divider()
    st.subheader("3. Selección de proyectos")
    project_keys = list(projects_data.keys())
    labels = [projects_data[k]["display_label"] for k in project_keys]
    label_to_key = {projects_data[k]["display_label"]: k for k in project_keys}

    mode = st.radio(
        "Modo de selección:",
        ["Todos los proyectos", "Seleccionar proyectos específicos"],
        horizontal=True,
    )
    if mode == "Todos los proyectos":
        selected_keys = project_keys
        st.caption(f"Se generarán {len(selected_keys)} fichas.")
    else:
        selected_labels = st.multiselect(
            "Seleccione uno o más proyectos (CUI - PROYECTO):",
            options=labels,
            default=labels[:1],
        )
        selected_keys = [label_to_key[label] for label in selected_labels]

    if not selected_keys:
        st.warning("Seleccione al menos un proyecto.")
        return

    st.divider()
    st.subheader("4. Generación y descarga")

    assets_dir = Path(__file__).parent / "assets"
    logo_produce = assets_dir / "logo_produce.png"
    logo_itp = assets_dir / "logo_itp.png"

    missing_logos = [p.name for p in (logo_produce, logo_itp) if not p.exists()]
    if missing_logos:
        st.warning(
            "Faltan los siguientes logos en la carpeta assets: " + ", ".join(missing_logos) +
            ". La aplicación puede generar una prueba con marcadores de texto, pero para el despliegue final agregue los PNG."
        )

    if st.button("🚀 Generar fichas PDF", type="primary", use_container_width=False):
        generated = []
        errors = []
        progress = st.progress(0)
        status = st.empty()

        for idx, key in enumerate(selected_keys, start=1):
            info = projects_data[key]
            status.text(f"Generando {idx}/{len(selected_keys)}: {info['display_label']}")
            try:
                pdf_bytes = generate_pdf_bytes(
                    project_info=info,
                    footer_text=footer_text,
                    logo_produce_path=logo_produce,
                    logo_itp_path=logo_itp,
                )
                generated.append((f"{info['filename_clean']}.pdf", pdf_bytes))
            except Exception as exc:
                errors.append(f"{info['display_label']}: {exc}")
            progress.progress(idx / len(selected_keys))

        status.empty()
        progress.empty()
        st.session_state["generated_files"] = generated
        st.session_state["generation_errors"] = errors

    generated = st.session_state.get("generated_files", [])
    errors = st.session_state.get("generation_errors", [])

    if errors:
        st.error(f"No se pudieron generar {len(errors)} ficha(s).")
        with st.expander("Ver detalle de errores"):
            for error in errors:
                st.write(f"- {error}")

    if generated:
        st.success(f"{len(generated)} ficha(s) generada(s) correctamente.")
        if len(generated) == 1:
            name, pdf = generated[0]
            st.download_button("📥 Descargar PDF", data=pdf, file_name=name, mime="application/pdf")
        else:
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, pdf in generated:
                    zf.writestr(name, pdf)
            zip_buffer.seek(0)
            st.download_button(
                "📥 Descargar todas las fichas (.ZIP)",
                data=zip_buffer.getvalue(),
                file_name="FICHAS_PROYECTOS.zip",
                mime="application/zip",
            )


if __name__ == "__main__":
    main()
