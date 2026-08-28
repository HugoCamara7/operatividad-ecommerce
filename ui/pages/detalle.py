# -*- coding: utf-8 -*-
"""Detalle navegable y descarga del análisis."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from core import export
from ui import components as c
from ui.helpers import contexto_periodo


TABLAS = {
    "Pedidos (detalle de líneas)": "ordenes",
    "OTIF / tiempos": "otif",
    "Carrier / tracking": "carrier",
    "Quiebres de stock": "quiebres",
}


def render(ctx) -> None:
    c.section_header("Detalle y descarga", ctx.meta(), ctx.chips())

    # -- Selección de tabla -------------------------------------------------
    disponibles = {k: v for k, v in TABLAS.items() if not getattr(ctx, v).empty}
    if not disponibles:
        c.empty_state("Sin registros para el filtro actual")
        return

    col1, col2 = st.columns([2, 1.4], gap="small")
    with col1:
        elegida = st.radio("Tabla", list(disponibles), horizontal=True,
                           label_visibility="collapsed", key="tabla_detalle")
    df = getattr(ctx, disponibles[elegida])

    with col2:
        buscar = st.text_input("Buscar", placeholder="Orden, SKU, cliente, tienda…",
                               label_visibility="collapsed", key="buscar_detalle")

    if buscar:
        df = _buscar(df, buscar)

    # -- Resumen de la selección -------------------------------------------
    c.kpi_row([
        dict(label="Registros", value=len(df), kind="num", icon="📋"),
        dict(label="Pedidos", value=df["orden"].nunique() if "orden" in df else None,
             kind="num", icon="🧾"),
        dict(label="Venta", value=float(df["total"].sum()) if "total" in df else None,
             kind="money", icon="💰"),
        dict(label="Columnas", value=len(df.columns), kind="num", icon="🧮"),
    ])

    # -- Tabla --------------------------------------------------------------
    st.markdown("")
    todas = st.toggle("Mostrar todas las columnas", value=False, key="todas_cols")
    if todas or disponibles[elegida] != "ordenes":
        vista = df
    else:
        columnas = [col for col in export._COLUMNAS_DETALLE if col in df.columns]
        vista = df[columnas]

    limite = 5000
    st.dataframe(
        vista.head(limite).rename(
            columns={col: export._ETIQUETAS.get(col, col.replace("_", " ").title())
                     for col in vista.columns}),
        hide_index=True, width="stretch", height=460,
    )
    if len(vista) > limite:
        st.caption(
            f"Se muestran {limite:,} de {len(vista):,} registros. "
            f"La descarga incluye el conjunto completo.".replace(",", " "))

    # -- Descargas ----------------------------------------------------------
    st.markdown("")
    c.note('El archivo Excel incluye <b>indicadores calculados</b>, los '
           '<b>filtros aplicados</b>, la serie diaria, los cortes por sitio, marca, '
           'tienda, departamento y medio de pago, más el <b>detalle</b> tal como se '
           've en pantalla.')
    st.write("")

    col1, col2, col3 = st.columns([1, 1, 2], gap="small")
    sello = datetime.now().strftime("%Y%m%d_%H%M")

    with col1:
        incluir = st.checkbox("Incluir detalle", value=True, key="incl_detalle")
        if st.button("Generar Excel", width="stretch", type="primary"):
            with st.spinner("Construyendo el libro…"):
                st.session_state["excel_bytes"] = export.construir_excel(ctx, incluir)
                st.session_state["excel_nombre"] = f"Analisis_Operatividad_{sello}.xlsx"
        if st.session_state.get("excel_bytes"):
            st.download_button(
                "⤓ Descargar Excel", st.session_state["excel_bytes"],
                file_name=st.session_state.get("excel_nombre", f"analisis_{sello}.xlsx"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                width="stretch")

    with col2:
        st.write("")
        st.download_button(
            "⤓ Descargar CSV", export.csv_detalle(df),
            file_name=f"detalle_{disponibles[elegida]}_{sello}.csv",
            mime="text/csv", width="stretch")

    with col3:
        st.write("")
        st.caption(
            f"Origen: {ctx.model.report.source or 'sin identificar'} · "
            f"{len(df):,} registros tras los filtros activos.".replace(",", " "))


# ---------------------------------------------------------------------------
def _buscar(df: pd.DataFrame, termino: str) -> pd.DataFrame:
    """Búsqueda libre sobre las columnas de texto."""
    termino = termino.strip()
    if not termino:
        return df
    texto = df.select_dtypes(include=["object", "string"])
    if texto.empty:
        return df
    mask = pd.Series(False, index=df.index)
    for columna in texto.columns:
        mask |= df[columna].astype("string").str.contains(termino, case=False, na=False, regex=False)
    return df[mask]
