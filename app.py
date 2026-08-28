# -*- coding: utf-8 -*-
"""Operatividad Control Center.

Punto de entrada: acceso, cabecera, navegación, filtros y ruteo de secciones.
Toda la lógica de datos vive en `core/`.
"""
from __future__ import annotations

import html
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import auth, compare, filters, repository          # noqa: E402
from core.bigquery import BigQuerySource, BigQueryNoDisponible, leer_config  # noqa: E402
from core.compare import Periodo                              # noqa: E402
from core.filters import FilterState                          # noqa: E402
from core.master import FuenteMaestra                         # noqa: E402
from core.sources import ExcelSource                          # noqa: E402
from core.transform import build_model                        # noqa: E402
from ui import components as c, login, report, theme          # noqa: E402
from ui.helpers import Context                                # noqa: E402
from ui.pages import detalle, fuente as pagina_fuente         # noqa: E402

SECCIONES = list(report.SECCIONES) + ["Detalle", "Fuente"]
ICONOS = {"Resumen": "◧", "Operatividad": "⚙", "Tiendas": "🏬", "Productos": "🔖",
          "Comparativos": "⇄", "Detalle": "▤", "Fuente": "🔌"}
MESES = ("ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic")


# ---------------------------------------------------------------------------
#  Carga de datos
# ---------------------------------------------------------------------------
@st.cache_resource(show_spinner=False, max_entries=4)
def _procesar(payload: bytes, nombre: str, huella: str):
    """Procesa el Excel una sola vez por huella de contenido."""
    modelo = repository.load(huella)
    if modelo is not None:
        return modelo
    modelo = build_model(ExcelSource(payload, nombre))
    try:
        repository.save(modelo, huella)
        repository.prune(keep=5)
    except Exception:
        pass                       # el caché es una optimización, no un requisito
    return modelo


def _cargar(payload: bytes, nombre: str):
    origen = ExcelSource(payload, nombre)
    huella = origen.fingerprint
    st.session_state["huella"] = huella
    mensaje = ("Recuperando la carga guardada…" if repository.exists(huella)
               else "Leyendo el maestro y validando la estructura…")
    with st.spinner(mensaje):
        return _procesar(payload, nombre, huella)


@st.cache_resource(show_spinner=False)
def _fuente_configurada():
    try:
        config = dict(st.secrets.get("datasource", {}))
    except Exception:
        config = {}
    return FuenteMaestra.desde_config(config)


@st.cache_resource(show_spinner=False)
def _origen_directo():
    """Origen BigQuery si está habilitado en los secrets; si no, None."""
    try:
        config, cuenta = leer_config(st.secrets)
    except Exception:
        return None
    try:
        return BigQuerySource.desde_config(config, cuenta)
    except Exception:
        return None


@st.cache_resource(show_spinner=False, max_entries=2)
def _procesar_directo(huella: str, _origen):
    """Construye el modelo desde el origen directo (BigQuery)."""
    modelo = repository.load(huella)
    if modelo is not None:
        return modelo
    modelo = build_model(_origen)
    try:
        repository.save(modelo, huella)
    except Exception:
        pass
    return modelo


def _sincronizar_directo(origen) -> bool:
    """Intenta cargar desde BigQuery. Devuelve False para caer al Excel."""
    if origen is None:
        return False
    try:
        with st.spinner("Consultando BigQuery…"):
            modelo = _procesar_directo(origen.fingerprint, origen)
    except BigQueryNoDisponible as exc:
        st.session_state["error_bigquery"] = str(exc)
        return False
    except Exception as exc:
        st.session_state["error_bigquery"] = str(exc)[:200]
        return False
    if not modelo.report.usable:
        st.session_state["error_bigquery"] = (
            "BigQuery respondió, pero faltan columnas críticas. Se usa el Excel.")
        return False
    st.session_state["error_bigquery"] = ""
    st.session_state["modelo"] = modelo
    st.session_state["huella"] = origen.fingerprint
    st.session_state["origen_datos"] = origen.label
    return True


def _sincronizar(fuente: FuenteMaestra, estado, forzar: bool = False) -> None:
    """Trae el maestro si cambió (o si se fuerza) y actualiza la sesión."""
    if fuente.modo == "upload" or not estado.conectado:
        return
    firma = estado.huella or estado.actualizado_texto
    if not forzar and st.session_state.get("firma_fuente") == firma and st.session_state.get("modelo"):
        return
    try:
        contenido, nombre = fuente.leer()
    except Exception as exc:
        st.session_state["error_fuente"] = str(exc)[:200]
        return
    st.session_state["error_fuente"] = ""
    st.session_state["modelo"] = _cargar(contenido, nombre)
    st.session_state["firma_fuente"] = firma
    st.session_state["origen_datos"] = nombre


def _on_upload(archivo) -> None:
    modelo = _cargar(archivo.getvalue(), archivo.name)
    st.session_state["modelo"] = modelo
    st.session_state["origen_datos"] = archivo.name
    st.session_state["firma_fuente"] = f"manual::{archivo.name}"
    st.session_state["drill"] = {}
    if modelo.report.usable:
        st.toast(f"«{archivo.name}» procesado correctamente", icon="✅")
    st.rerun()


# ---------------------------------------------------------------------------
#  Cabecera y navegación
# ---------------------------------------------------------------------------
def _cabecera(estado, sesion) -> None:
    ahora = datetime.now()
    sello = f"{ahora.day:02d} {MESES[ahora.month - 1]} {ahora.year} · {ahora:%H:%M}"
    usuario = "" if sesion.abierta else f'<span class="hdr-user">{html.escape(sesion.usuario)}</span>'
    st.markdown(
        f'<div class="hdr"><div class="hdr-row">'
        f'<div class="hdr-brand"><div class="hdr-mark">OC</div>'
        f'<div><div class="title">Operatividad Control Center</div>'
        f'<span>Ecommerce · Perú</span></div></div>'
        f'<div class="hdr-side">'
        f'<div class="src"><span class="led {estado.estado}"></span>'
        f'<div><b>{html.escape(estado.etiqueta)}</b>'
        f'<small>Actualizado {html.escape(estado.actualizado_texto)}</small></div></div>'
        f'{usuario}<span class="hdr-user">{sello}</span>'
        f'</div></div></div>',
        unsafe_allow_html=True)


def _navegacion() -> str:
    with st.container(key="nav"):
        return st.radio(
            "Sección", SECCIONES, horizontal=True, label_visibility="collapsed", key="nav_sec",
            format_func=lambda s: f"{ICONOS.get(s, '')}  {s}")


# ---------------------------------------------------------------------------
#  Filtros
# ---------------------------------------------------------------------------
ATAJOS = ["Todo el histórico", "Últimos 7 días", "Últimos 30 días", "Últimos 90 días",
          "Mes actual", "Mes anterior", "Año actual", "Personalizado"]


def _barra_filtros(modelo) -> tuple[FilterState, str, Periodo | None]:
    state = FilterState()
    ordenes = modelo.ordenes
    minimo, maximo = ordenes["fecha_compra"].min(), ordenes["fecha_compra"].max()

    with st.container(key="filtros"):
        fila = st.columns([1.05, 1.5, 1.15, 1.5, 0.9], gap="small")

        with fila[0]:
            atajo = st.selectbox("Período", ATAJOS, index=2, key="atajo")
        desde, hasta = _rango(atajo, minimo, maximo)
        with fila[1]:
            elegido = st.date_input(
                "Desde – Hasta", value=(desde.date(), hasta.date()),
                min_value=minimo.date(), max_value=maximo.date(), key="rango",
                disabled=atajo != "Personalizado",
                help="Elija «Personalizado» para mover las fechas a mano.")
            if atajo == "Personalizado" and isinstance(elegido, (tuple, list)) and len(elegido) == 2:
                desde, hasta = pd.Timestamp(elegido[0]), pd.Timestamp(elegido[1])
        state.desde, state.hasta = desde, hasta
        actual = Periodo(desde, hasta)

        with fila[2]:
            modo = st.selectbox("Comparar contra", list(compare.MODOS),
                                index=0, key="cmp_modo",
                                format_func=lambda m: compare.MODOS[m])
        personalizado = None
        with fila[3]:
            if modo == "personalizado":
                referencia_previa = compare.periodo_anterior(actual)
                elegido_ref = st.date_input(
                    "Rango de comparación",
                    value=(referencia_previa.desde.date(), referencia_previa.hasta.date()),
                    min_value=minimo.date(), max_value=maximo.date(), key="rango_ref")
                if isinstance(elegido_ref, (tuple, list)) and len(elegido_ref) == 2:
                    personalizado = Periodo(pd.Timestamp(elegido_ref[0]),
                                            pd.Timestamp(elegido_ref[1]))
            else:
                referencia = compare.resolver(actual, modo)
                st.markdown('<span class="filtro-tag">Referencia</span>', unsafe_allow_html=True)
                st.markdown(
                    f'<div class="vs-pill"><i>vs</i> {html.escape(referencia.texto())}</div>'
                    if referencia.valido else
                    '<div class="vs-pill" style="opacity:.6">sin comparación</div>',
                    unsafe_allow_html=True)
        with fila[4]:
            st.markdown('<span class="filtro-tag">&nbsp;</span>', unsafe_allow_html=True)
            if st.button("Limpiar", width="stretch", help="Quita filtros y drill-down"):
                for clave in list(st.session_state):
                    if clave.startswith(("f_", "r_", "drill", "atajo", "rango", "cmp_",
                                         "sin_canc", "unicas")):
                        del st.session_state[clave]
                st.rerun()

        # -- dimensiones ----------------------------------------------------
        fila = st.columns(5, gap="small")
        for col, clave in zip(fila, ["sitio", "marca", "modalidad", "departamento", "estado"]):
            with col:
                _multiselect(ordenes, state, clave)

    with st.expander("Más filtros y ajustes de cálculo"):
        restantes = [k for k in filters.DIMENSIONES
                     if k not in ("sitio", "marca", "modalidad", "departamento", "estado")]
        cols = st.columns(4, gap="small")
        for i, clave in enumerate(restantes):
            with cols[i % 4]:
                _multiselect(ordenes, state, clave)
        cols = st.columns(4, gap="small")
        with cols[0]:
            _slider_rango(ordenes, state, "total", "Ticket de línea (S/)")
        with cols[1]:
            _slider_rango(ordenes, state, "unidades", "Unidades por línea")
        with cols[2]:
            state.excluir_canceladas = st.toggle("Excluir canceladas", value=False, key="sin_canc")
        with cols[3]:
            state.solo_lineas_unicas = st.toggle("Sólo líneas únicas", value=False, key="unicas")

    state.drill = dict(st.session_state.get("drill", {}))
    return state, modo, personalizado


def _multiselect(ordenes: pd.DataFrame, state: FilterState, clave: str) -> None:
    etiqueta, columna = filters.DIMENSIONES[clave]
    if columna not in ordenes:
        return
    opciones = filters.opciones(ordenes, clave)
    if len(opciones) < 2:
        return
    seleccion = st.multiselect(etiqueta, opciones, default=[], key=f"f_{clave}",
                               placeholder="Todos")
    if seleccion:
        state.seleccion[clave] = seleccion


def _slider_rango(ordenes: pd.DataFrame, state: FilterState, columna: str, etiqueta: str) -> None:
    """Filtro por rango numérico; se omite si la columna no existe o es constante."""
    if columna not in ordenes:
        return
    serie = pd.to_numeric(ordenes[columna], errors="coerce").dropna()
    if serie.empty:
        return
    bajo, alto = float(serie.min()), float(serie.quantile(0.999))
    if not (alto > bajo):
        return
    elegido = st.slider(etiqueta, bajo, alto, (bajo, alto),
                        step=max(round((alto - bajo) / 100, 2), 0.01), key=f"r_{columna}")
    if elegido != (bajo, alto):
        state.rangos[columna] = elegido


def _rango(atajo: str, minimo: pd.Timestamp, maximo: pd.Timestamp) -> tuple[pd.Timestamp, pd.Timestamp]:
    if atajo == "Últimos 7 días":
        return max(minimo, maximo - pd.Timedelta(days=6)), maximo
    if atajo == "Últimos 30 días":
        return max(minimo, maximo - pd.Timedelta(days=29)), maximo
    if atajo == "Últimos 90 días":
        return max(minimo, maximo - pd.Timedelta(days=89)), maximo
    if atajo == "Mes actual":
        return max(minimo, maximo.replace(day=1)), maximo
    if atajo == "Mes anterior":
        fin = maximo.replace(day=1) - pd.Timedelta(days=1)
        return max(minimo, fin.replace(day=1)), fin
    if atajo == "Año actual":
        return max(minimo, maximo.replace(month=1, day=1)), maximo
    return minimo, maximo


# ---------------------------------------------------------------------------
#  Aplicación
# ---------------------------------------------------------------------------
def main() -> None:
    theme.page_config()
    if not login.render():
        return
    theme.inject()

    sesion = auth.sesion_actual()
    fuente = _fuente_configurada()
    estado = fuente.estado()
    directo = _origen_directo()

    def refrescar(forzar: bool = False) -> None:
        if forzar:
            st.session_state.pop("modelo", None)
            if not _sincronizar_directo(directo):
                _sincronizar(fuente, estado, forzar=True)
            st.rerun()
        else:
            _sincronizar(fuente, estado)

    if st.session_state.get("modelo") is None:
        # BigQuery manda cuando está habilitado; el Excel es el respaldo.
        if not _sincronizar_directo(directo):
            _sincronizar(fuente, estado)
    modelo = st.session_state.get("modelo")

    _cabecera(estado, sesion)
    seccion = _navegacion()

    if modelo is None or not modelo.report.usable:
        pagina_fuente.render(None if modelo is None else Context.build(modelo, FilterState()),
                             fuente, estado, _on_upload, refrescar, directo)
        return

    state, modo, personalizado = _barra_filtros(modelo)
    ctx = Context.build(modelo, state, modo, personalizado)

    if seccion == "Fuente":
        pagina_fuente.render(ctx, fuente, estado, _on_upload, refrescar, directo)
    elif seccion == "Detalle":
        detalle.render(ctx)
    else:
        report.SECCIONES[seccion](ctx)


if __name__ == "__main__":
    main()
