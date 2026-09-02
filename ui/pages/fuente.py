# -*- coding: utf-8 -*-
"""Fuente de datos: conexión automática, estado y reemplazo manual."""
from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from core import auth, repository
from core.master import MODOS, normalizar_url
from core.normalize import load_schema
from ui import components as c


def render(ctx, fuente, estado, on_upload, on_refresh, directo=None) -> None:
    c.section_header("Fuente de datos",
                     "Conexión al Excel maestro, validación de estructura y calidad")

    # -- estado de la conexión ---------------------------------------------
    col1, col2, col3 = st.columns([1.15, 1, 1], gap="small")
    with col1:
        st.markdown(
            f'<div class="srccard"><div class="title">🔌 Conexión</div>'
            f'{_fila("Modo", _MODO_TEXTO.get(estado.modo, estado.modo))}'
            f'{_fila("Estado", _ESTADO_TEXTO.get(estado.estado, estado.estado))}'
            f'{_fila("Archivo", estado.etiqueta)}'
            f'{_fila("Ubicación", estado.detalle or "—")}'
            f'</div>', unsafe_allow_html=True)
    with col2:
        st.markdown(
            f'<div class="srccard"><div class="title">🕒 Actualización</div>'
            f'{_fila("Última", estado.actualizado_texto)}'
            f'{_fila("Tamaño", estado.tamano_texto)}'
            f'{_fila("Procesado", repository.saved_at(st.session_state.get("huella", "")) or "—")}'
            f'</div>', unsafe_allow_html=True)
    with col3:
        st.markdown('<div class="srccard"><div class="title">⚡ Acciones</div></div>', unsafe_allow_html=True)
        if st.button("Actualizar ahora", type="primary", width="stretch",
                     help="Vuelve a leer el maestro y reprocesa si cambió."):
            on_refresh(forzar=True)
        st.caption("Se relee la fuente y el reporte se refresca automáticamente.")
        sesion = auth.sesion_actual()
        if not sesion.abierta:
            if st.button("Cerrar sesión", width="stretch"):
                auth.cerrar_sesion()
                st.rerun()

    if estado.error:
        st.warning(f"No se pudo leer la fuente automática: {estado.error}", icon="⚠️")

    # -- origen directo -----------------------------------------------------
    if directo is not None:
        error = st.session_state.get("error_bigquery")
        if error:
            st.warning(f"Origen directo ({directo.label}) no disponible: {error} "
                       f"Se está usando el Excel maestro.", icon="⚠️")
        else:
            st.success(f"Origen directo activo: {directo.label}. "
                       f"El Excel queda como respaldo.", icon="🔗")

    # -- reemplazo manual ---------------------------------------------------
    c.section_label("Reemplazo manual")
    col1, col2 = st.columns([1.5, 1], gap="small")
    with col1:
        subido = st.file_uploader(
            "Excel de operación", type=["xlsx", "xlsm"], key="uploader",
            label_visibility="collapsed",
            help="Reemplaza temporalmente la fuente automática en esta sesión.")
        if subido is not None:
            on_upload(subido)
    with col2:
        c.note("La carga manual es un <b>respaldo</b>: la fuente configurada sigue "
               "activa y vuelve a usarse al pulsar <b>Actualizar ahora</b>.")

    # -- configuración ------------------------------------------------------
    with st.expander("Cómo se configura la fuente automática"):
        st.markdown(
            "Agregue esta sección a `.streamlit/secrets.toml` "
            "(o defina `OPS_MASTER_PATH` / `OPS_MASTER_URL` como variables de entorno):")
        st.code(
            '[datasource]\n'
            '# Opción A — carpeta sincronizada de OneDrive/SharePoint (recomendado en local)\n'
            'modo = "local"\n'
            'ruta = "C:/Users/usuario/OneDrive - Peru Forus S.A/Operacion/BD Operacion Ecommerce.xlsx"\n\n'
            '# Opción B — enlace de descarga directa (recomendado en la nube)\n'
            '# modo = "url"\n'
            '# url  = "https://forus-my.sharepoint.com/:x:/g/personal/.../archivo.xlsx"\n\n'
            'refrescar_cada_min = 60\n',
            language="toml")
        st.caption("El enlace compartido de OneDrive, SharePoint o Google Drive se convierte "
                   "solo a descarga directa; no hace falta prepararlo a mano.")
        if fuente.modo == "url" and fuente.url:
            st.caption(f"URL efectiva: `{normalizar_url(fuente.url)}`")

    if ctx is None:
        c.empty_state("Aún no hay datos cargados", "Conecte una fuente o suba el archivo.")
        _mostrar_esquema()
        return

    # -- estructura reconocida ---------------------------------------------
    reporte = ctx.model.report
    c.section_label("Estructura reconocida")
    for mensaje in reporte.blocking_errors:
        st.error(mensaje, icon="⛔")
    for mensaje in reporte.messages:
        st.warning(mensaje, icon="⚠️")

    col1, col2 = st.columns([1.5, 1], gap="small")
    with col1:
        c.panel_open("Conjuntos detectados",
                     "Se identifican por sus columnas firma, no por el nombre de la hoja")
        c.dataset_status(reporte)
        c.panel_close()
    with col2:
        c.panel_open("Resumen")
        total = sum(d.rows for d in reporte.datasets.values())
        desde, hasta = ctx.model.periodo
        c.kpi_card("Registros procesados", total, "num", icon="🗂️", sub=reporte.source)
        if desde is not None:
            st.write("")
            c.kpi_card("Días cubiertos", (hasta - desde).days + 1, "num", icon="📆",
                       sub=f"{desde:%d/%m/%Y} – {hasta:%d/%m/%Y}")
        else:
            st.write("")
            st.error("Ninguna fecha de compra se pudo interpretar: el reporte no "
                     "puede acotar períodos. Revise el formato de «Fecha Compra» "
                     "en el Excel.", icon="📆")
        c.panel_close()

    # -- mapeo --------------------------------------------------------------
    c.section_label("Mapeo de columnas")
    st.caption("Qué encabezado del Excel alimenta cada campo del reporte.")
    pestanas = st.tabs([d.label for d in reporte.datasets.values()])
    for pestana, item in zip(pestanas, reporte.datasets.values()):
        with pestana:
            if not item.found:
                c.empty_state(f"No se encontró «{item.label}»",
                              "Revise las columnas firma en config/schema.yml.")
                continue
            filas = [{"Campo del reporte": k, "Encabezado en el Excel": v}
                     for k, v in item.mapped.items()]
            filas += [{"Campo del reporte": f"⛔ {n}", "Encabezado en el Excel": "FALTA (crítica)"}
                      for n in item.missing_required]
            filas += [{"Campo del reporte": f"○ {n}", "Encabezado en el Excel": "no presente (opcional)"}
                      for n in item.missing_optional]
            st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch", height=290)
            if item.unmapped_columns:
                with st.expander(f"{len(item.unmapped_columns)} columnas sin usar"):
                    st.write(", ".join(item.unmapped_columns))

    # -- calidad ------------------------------------------------------------
    c.section_label("Calidad de los datos")
    _calidad(ctx.model.ordenes)


# ---------------------------------------------------------------------------
_MODO_TEXTO = {"local": "Carpeta sincronizada", "url": "Enlace remoto",
               "upload": "Carga manual"}
_ESTADO_TEXTO = {"ok": "Conectado", "error": "Con error", "pendiente": "Sin conexión"}


def _fila(etiqueta: str, valor: str) -> str:
    return (f'<div class="row"><span>{html.escape(etiqueta)}</span>'
            f'<b>{html.escape(str(valor))}</b></div>')


def _calidad(df: pd.DataFrame) -> None:
    if df.empty:
        return
    col1, col2 = st.columns([1.2, 1], gap="small")
    with col1:
        c.panel_open("Completitud por campo", "Porcentaje de registros con dato")
        total = len(df)
        filas = [{"Campo": columna,
                  "Completitud": int(df[columna].notna().sum()) / total * 100,
                  "Vacíos": total - int(df[columna].notna().sum())}
                 for columna in df.columns if not columna.startswith("_")]
        completitud = pd.DataFrame(filas).sort_values("Completitud")
        st.dataframe(
            completitud.head(22), hide_index=True, width="stretch", height=320,
            column_config={
                "Completitud": st.column_config.ProgressColumn(
                    "Completitud", format="%.1f%%", min_value=0.0, max_value=100.0),
                "Vacíos": st.column_config.NumberColumn("Vacíos", format="%d")})
        c.panel_close()
    with col2:
        c.panel_open("Avisos", "Puntos a vigilar en esta carga")
        avisos = _avisos(df)
        if avisos:
            for aviso in avisos:
                st.markdown(f'<div class="status-row">• {aviso}</div>', unsafe_allow_html=True)
        else:
            st.success("Sin anomalías relevantes.", icon="✅")
        c.panel_close()


def _avisos(df: pd.DataFrame) -> list[str]:
    avisos: list[str] = []
    total = len(df)
    if "orden" in df:
        avisos.append(f"Las filas son <b>líneas de pedido</b>: "
                      f"{total / max(df['orden'].nunique(), 1):.1f} por pedido en promedio.")
    if "total" in df and int((df["total"] < 0).sum()):
        avisos.append(f"<b>{int((df['total'] < 0).sum())}</b> líneas con total negativo "
                      f"(devoluciones o notas de crédito).")
    if "total_sin_igv" in df and int((df["total_sin_igv"] == 0).sum()):
        avisos.append(f"<b>{int((df['total_sin_igv'] == 0).sum()):,}</b> líneas con "
                      f"total sin IGV en cero.".replace(",", " "))
    if "fecha_compra" in df and df["fecha_compra"].notna().any():
        ultimo = df["fecha_compra"].max()
        if ultimo.day < 28:
            avisos.append(f"El último mes está <b>incompleto</b> (hasta el "
                          f"{ultimo:%d/%m/%Y}): las comparaciones mensuales no son directas.")
    if int(df.duplicated().sum()):
        avisos.append(f"<b>{int(df.duplicated().sum())}</b> filas idénticas repetidas.")
    if "operador_logistico" in df:
        vacios = int(df["operador_logistico"].isna().sum())
        if vacios:
            avisos.append(f"<b>{vacios:,}</b> registros sin operador logístico "
                          f"({vacios/total*100:.0f}%).".replace(",", " "))
    return avisos


def _mostrar_esquema() -> None:
    c.section_label("Estructura esperada")
    schema = load_schema()
    pestanas = st.tabs([spec.get("label", k) for k, spec in schema["datasets"].items()])
    for pestana, (clave, spec) in zip(pestanas, schema["datasets"].items()):
        with pestana:
            st.caption(spec.get("description", ""))
            filas = [{"Campo": nombre,
                      "Crítico": "Sí" if cfg.get("required") else "No",
                      "Encabezados aceptados": ", ".join(cfg.get("aliases", []))}
                     for nombre, cfg in spec["fields"].items()]
            st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch", height=360)
