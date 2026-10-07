# Generador de Fichas de Inversión

Aplicación Streamlit para generar fichas PDF de proyectos de inversión a partir de tres archivos Excel validados: maestro, avance físico y avance financiero.

## Estructura

```text
generador-fichas-inversion/
├── app.py
├── data_processor.py
├── pdf_generator.py
├── requirements.txt
├── README.md
├── assets/
│   ├── logo_produce.png
│   └── logo_itp.png
└── .streamlit/
    └── config.toml
```

## Funcionamiento

1. Cargar los tres Excel desde la interfaz.
2. La aplicación relaciona la información mediante `CUI + PROYECTO`.
3. Ingresar o modificar libremente el texto de fuente/pie de página.
4. Seleccionar uno, varios o todos los proyectos.
5. Generar las fichas.
6. Descargar un PDF individual o un ZIP con todas las fichas seleccionadas.

Los archivos generados se construyen en memoria y no se guardan permanentemente en el servidor.

## Logos

Colocar en `assets/`:

- `logo_produce.png`
- `logo_itp.png`

## Instalación local

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Despliegue

Subir el repositorio a GitHub y crear una aplicación en Streamlit Community Cloud indicando `app.py` como archivo principal.

## Nota sobre el periodo financiero

Los Excel fuente conservan por compatibilidad los encabezados `PIM 2025` y `EJECUCION FINANCIERA  2025`. En las fichas se muestran como `PIM 2026` y `Ejecución 2026`, conforme al uso actual de estos archivos.
