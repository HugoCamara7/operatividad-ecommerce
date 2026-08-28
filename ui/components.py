# -*- coding: utf-8 -*-
"""Componentes de interfaz del Control Center."""
from __future__ import annotations

import html
import math
from contextlib import contextmanager

import numpy as np
import pandas as pd
import streamlit as st

from . import theme


# ---------------------------------------------------------------------------
#  Formato
# ---------------------------------------------------------------------------
def fmt(value, kind: str = "num", decimals: int | None = None) -> str:
    """Formatea un número según su naturaleza."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    try:
        if pd.isna(value):
            return "—"
    except (TypeError, ValueError):
        pass
    value = float(value)

    if kind == "money":
        if abs(value) >= 1_000_000:
            return f"S/ {value/1_000_000:,.2f}M"
        if abs(value) >= 10_000:
            return f"S/ {value/1_000:,.1f}k"
        return f"S/ {value:,.0f}"
    if kind == "money_full":
        return f"S/ {value:,.2f}"
    if kind == "pct":
        return f"{value*100:,.{1 if decimals is None else decimals}f}%"
    if kind == "pct_pt":
        return f"{value:,.1f} pp"
    if kind == "hours":
        return f"{value/24:,.1f} d" if abs(value) >= 48 else f"{value:,.1f} h"
    if kind == "days":
        return f"{value:,.1f} d"
    if kind == "num2":
        return f"{value:,.2f}"
    if abs(value) >= 1_000_000:
        return f"{value/1_000_000:,.2f}M"
    return f"{value:,.{decimals or 0}f}"


def fmt_dif(value, kind: str) -> str:
    """Diferencia absoluta con signo. En porcentajes se expresa en puntos."""
    if value is None or (isinstance(value, float) and not math.isfinite(value)):
        return "—"
    signo = "+" if value > 0 else ""
    if kind == "pct":
        return f"{signo}{value*100:,.1f} pp"
    return f"{signo}{fmt(value, kind)}"


def _delta_html(var: float | None, invertido: bool = False) -> str:
    if var is None or not math.isfinite(var):
        return ""
    if abs(var) < 0.0005:
        return '<span class="delta flat">0.0%</span>'
    positivo = var > 0
    bueno = (not positivo) if invertido else positivo
    return (f'<span class="delta {"up" if bueno else "down"}">'
            f'{"▲" if positivo else "▼"} {abs(var)*100:,.1f}%</span>')


def _spark_svg(valores, color: str, ancho: int = 62, alto: int = 20) -> str:
    """Mini serie dentro de la tarjeta: contexto sin gastar un gráfico entero."""
    puntos = [float(v) for v in (valores or []) if v is not None and np.isfinite(v)]
    if len(puntos) < 3:
        return ""
    bajo, alto_v = min(puntos), max(puntos)
    rango = (alto_v - bajo) or 1.0
    paso = ancho / (len(puntos) - 1)
    coords = " ".join(
        f"{i*paso:.1f},{alto - 2 - ((v - bajo) / rango) * (alto - 4):.1f}"
        for i, v in enumerate(puntos))
    cx, cy = coords.split(" ")[-1].split(",")
    return (f'<svg class="spark" width="{ancho}" height="{alto}" viewBox="0 0 {ancho} {alto}" '
            f'fill="none" aria-hidden="true">'
            f'<polyline points="{coords}" stroke="{color}" stroke-width="1.6" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
            f'<circle cx="{cx}" cy="{cy}" r="2" fill="{color}"/></svg>')


# ---------------------------------------------------------------------------
#  Tarjeta KPI
# ---------------------------------------------------------------------------
def kpi_card(label: str, value, kind: str = "num", icon: str = "📊",
             referencia: float | None = None, etiqueta_ref: str = "",
             invertido: bool = False, sem: str = "", sub: str = "",
             decimals: int | None = None, spark=None,
             var: float | None = None, dif: float | None = None) -> None:
    """Tarjeta con valor actual y su comparación contra el período de referencia.

    Muestra referencia, diferencia y variación %; si no hay referencia, sólo el
    valor y una nota opcional.
    """
    clase = {"bueno": "good", "alerta": "warn", "critico": "bad"}.get(sem, "")

    if referencia is not None and var is None:
        from core.compare import variacion
        var = variacion(value, referencia)
    if referencia is not None and dif is None:
        from core.compare import diferencia
        dif = diferencia(value, referencia)

    comparacion = ""
    if referencia is not None:
        partes = [f'<span class="ref">{html.escape(etiqueta_ref or "ref")}: '
                  f'<b>{fmt(referencia, kind, decimals)}</b></span>']
        if dif is not None:
            partes.append(f'<span class="ref">{fmt_dif(dif, kind)}</span>')
        salto = _delta_html(var, invertido)
        if salto:
            partes.append(salto)
        comparacion = f'<div class="kpi-cmp">{"".join(partes)}</div>'

    pie = ""
    if sub:
        pie = f'<div class="foot">{html.escape(str(sub))}</div>'
    if sem and not comparacion:
        pie = (f'<div class="foot"><span class="sem {sem}">'
               f'{theme.SEMAFORO_TEXTO.get(sem, "")}</span></div>')
    elif sem and comparacion:
        pie = (f'<div class="foot"><span class="sem {sem}">'
               f'{theme.SEMAFORO_TEXTO.get(sem, "")}</span>'
               f'{" " + html.escape(str(sub)) if sub else ""}</div>')

    grafico = _spark_svg(spark, theme.SEMAFORO_COLOR.get(sem) or theme.ACCENT) if spark else ""
    st.markdown(
        f'<div class="kpi {clase}">{grafico}'
        f'<div class="kpi-top"><div class="ico">{icon}</div>'
        f'<span class="label">{html.escape(label)}</span></div>'
        f'<div class="value">{fmt(value, kind, decimals)}</div>'
        f'{comparacion}{pie}</div>',
        unsafe_allow_html=True)


def kpi_row(cards: list[dict]) -> None:
    if not cards:
        return
    for col, card in zip(st.columns(len(cards), gap="small"), cards):
        with col:
            kpi_card(**card)


def kpi_medidas(medidas, etiqueta_ref: str = "", spark: dict | None = None) -> None:
    """Fila de tarjetas a partir de objetos `Medida` de core.compare."""
    spark = spark or {}
    kpi_row([
        dict(label=m.etiqueta, value=m.actual, kind=m.kind, icon=m.icono,
             referencia=m.referencia, etiqueta_ref=etiqueta_ref,
             invertido=m.invertido, sub=m.nota, spark=spark.get(m.clave))
        for m in medidas
    ])


# ---------------------------------------------------------------------------
#  Estructura
# ---------------------------------------------------------------------------
def section_header(titulo: str, meta: str = "", chips: list[str] | None = None) -> None:
    marcas = "".join(f'<span class="sec-chip">{html.escape(c)}</span>' for c in (chips or []))
    if not marcas:
        marcas = '<span class="sec-chip ghost">sin filtros</span>'
    st.markdown(
        f'<div class="sec"><div><div class="sec-title"><span class="bar"></span>'
        f'<div class="title">{html.escape(titulo)}</div></div>'
        f'{f"<div class=sec-meta style=margin-top:.25rem>{html.escape(meta)}</div>" if meta else ""}'
        f'</div><div class="sec-chips">{marcas}</div></div>',
        unsafe_allow_html=True)


def section_label(texto: str) -> None:
    st.markdown(f'<div class="section-label">{html.escape(texto)}</div>', unsafe_allow_html=True)


_PANELES: list = []


def panel_open(titulo: str, hint: str = "") -> None:
    """Panel de gráfico: contenedor real de Streamlit para que envuelva widgets."""
    contenedor = st.container(border=True)
    contenedor.__enter__()
    _PANELES.append(contenedor)
    extra = f'<div class="hint">{html.escape(hint)}</div>' if hint else ""
    st.markdown(f'<div class="panel-head"><div class="title">{html.escape(titulo)}</div>{extra}</div>',
                unsafe_allow_html=True)


def panel_close() -> None:
    if _PANELES:
        _PANELES.pop().__exit__(None, None, None)


@contextmanager
def panel(titulo: str, hint: str = ""):
    panel_open(titulo, hint)
    try:
        yield
    finally:
        panel_close()


def note(texto_html: str) -> None:
    """Lectura accionable. Recibe HTML ya seguro (usar <b> a mano)."""
    st.markdown(f'<div class="note">{texto_html}</div>', unsafe_allow_html=True)


def empty_state(titulo: str, detalle: str = "") -> None:
    st.markdown(f'<div class="empty"><b>{html.escape(titulo)}</b>{html.escape(detalle)}</div>',
                unsafe_allow_html=True)


def semaforo_badge(sem: str) -> str:
    return f'<span class="sem {sem}">{theme.SEMAFORO_TEXTO.get(sem, "")}</span>' if sem else ""


# ---------------------------------------------------------------------------
#  Tabla del reporte
# ---------------------------------------------------------------------------
def tabla(df: pd.DataFrame, columnas: list[tuple[str, str, str]],
          total: dict | None = None, max_filas: int = 40, barra: str = "") -> None:
    """Tabla HTML con cabecera navy.

    `columnas` es una lista de (columna, encabezado, formato). El formato acepta
    los nombres de `fmt` más 'key' (columna resaltada), 'text', 'signed' y
    'signed_pct'. `barra` dibuja una barra de magnitud detrás de esa columna.
    """
    if df is None or df.empty:
        empty_state("Sin datos para el filtro actual")
        return

    presentes = [(c, t, f) for c, t, f in columnas if c in df.columns]
    if not presentes:
        empty_state("Sin columnas disponibles")
        return

    tope = 0.0
    if barra and barra in df.columns:
        serie = pd.to_numeric(df[barra], errors="coerce")
        tope = float(serie.max()) if serie.notna().any() else 0.0

    cabeza = "".join(f"<th>{html.escape(t)}</th>" for _, t, _ in presentes)
    filas = []
    for _, fila in df.head(max_filas).iterrows():
        celdas = []
        for columna, _, formato in presentes:
            valor = fila[columna]
            if formato == "key":
                celdas.append(f'<td class="key">{html.escape(_texto(valor))}</td>')
            elif formato == "text":
                celdas.append(f"<td>{html.escape(_texto(valor))}</td>")
            elif formato in ("signed", "signed_pct"):
                numero = pd.to_numeric(valor, errors="coerce")
                clase = "pos" if (pd.notna(numero) and numero >= 0) else "neg"
                signo = "+" if (pd.notna(numero) and numero > 0) else ""
                texto = fmt(numero, "pct" if formato == "signed_pct" else "money")
                celdas.append(f'<td class="num {clase}">{signo}{texto}</td>')
            else:
                numero = pd.to_numeric(valor, errors="coerce")
                texto = fmt(numero, formato)
                if columna == barra and tope > 0 and pd.notna(numero):
                    ancho = max(0.0, min(100.0, float(numero) / tope * 100))
                    texto = (f'<span class="cellbar"><i style="width:{ancho:.1f}%"></i>'
                             f'<span>{texto}</span></span>')
                celdas.append(f'<td class="num">{texto}</td>')
        filas.append(f"<tr>{''.join(celdas)}</tr>")

    pie = ""
    if total:
        celdas = []
        for i, (columna, _, formato) in enumerate(presentes):
            if columna in total:
                valor = total[columna]
                if formato in ("key", "text"):
                    celdas.append(f"<td>{html.escape(str(valor))}</td>")
                else:
                    base = "money" if formato in ("signed", "signed_pct") else formato
                    celdas.append(f'<td class="num">{fmt(valor, base)}</td>')
            else:
                celdas.append("<td>Total</td>" if i == 0 else "<td></td>")
        pie = f"<tfoot><tr>{''.join(celdas)}</tr></tfoot>"

    st.markdown(
        f'<div class="tbl-wrap"><div class="tbl-scroll"><table class="rep">'
        f"<thead><tr>{cabeza}</tr></thead><tbody>{''.join(filas)}</tbody>{pie}"
        f"</table></div></div>",
        unsafe_allow_html=True)


def _texto(valor) -> str:
    if valor is None:
        return "—"
    try:
        if pd.isna(valor):
            return "—"
    except (TypeError, ValueError):
        pass
    return str(valor)


# ---------------------------------------------------------------------------
#  Estado de la carga
# ---------------------------------------------------------------------------
def dataset_status(report) -> None:
    for item in report.datasets.values():
        detalle = f"{item.rows:,} filas · {item.origin}" if item.found else "no encontrado"
        aviso = ""
        if item.missing_required:
            aviso = " · falta: " + ", ".join(item.missing_required[:3])
        elif item.missing_optional:
            aviso = f" · {len(item.missing_optional)} opcionales ausentes"
        st.markdown(
            f'<div class="status-row"><span class="status-pill {item.status}">{item.status}</span>'
            f'<span><b>{html.escape(item.label)}</b> '
            f'<span class="mono" style="color:{theme.MUTED}">{html.escape(detalle + aviso)}</span>'
            f'</span></div>',
            unsafe_allow_html=True)
