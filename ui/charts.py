# -*- coding: utf-8 -*-
"""Constructores de gráficos.

Todos devuelven una figura de Plotly ya con la plantilla del dashboard, para que
las páginas no repitan configuración y el conjunto se lea como un solo sistema.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from . import theme

CONFIG = {"displayModeBar": False, "scrollZoom": False, "locale": "es", "locales": {}}

#: Plotly rotularía los meses en inglés. En lugar de depender de que el
#: componente registre un idioma, los ejes de fecha usan formato numérico, que es
#: inequívoco en cualquier idioma y se adapta al nivel de zoom.
TICKS_FECHA = [
    dict(dtickrange=[None, 3600000], value="%H:%M"),
    dict(dtickrange=[3600000, 86400000], value="%d/%m %H:%M"),
    dict(dtickrange=[86400000, 2592000000], value="%d/%m"),
    dict(dtickrange=[2592000000, 31536000000], value="%m/%Y"),
    dict(dtickrange=[31536000000, None], value="%Y"),
]


_MESES_ES = ("ene", "feb", "mar", "abr", "may", "jun",
             "jul", "ago", "sep", "oct", "nov", "dic")


def etiqueta_periodo(valores) -> list[str]:
    """Convierte '2026-07' en 'jul 2026'; deja el resto intacto.

    Además evita que Plotly interprete la etiqueta como fecha, cosa que rompía
    los ejes de las series mensuales.
    """
    out = []
    for valor in valores:
        texto = str(valor)
        if len(texto) == 7 and texto[4] == "-" and texto[:4].isdigit() and texto[5:].isdigit():
            mes = int(texto[5:])
            if 1 <= mes <= 12:
                out.append(f"{_MESES_ES[mes - 1]} {texto[:4]}")
                continue
        out.append(texto)
    return out


def _fig(height: int = 300, legend: bool = True, margin_top: int = 12) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(**theme.plotly_layout(height, legend, margin_top))
    fig.update_layout(separators=", ")          # 1 234,56 al estilo local
    return fig


def vacio(height: int = 300, mensaje: str = "Sin datos") -> go.Figure:
    fig = _fig(height, legend=False)
    fig.add_annotation(
        text=mensaje, showarrow=False,
        font=dict(size=12, color=theme.MUTED), x=0.5, y=0.5, xref="paper", yref="paper",
    )
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# ---------------------------------------------------------------------------
#  Tendencias
# ---------------------------------------------------------------------------
def tendencia(df: pd.DataFrame, x: str, y: str, nombre: str = "", kind: str = "money",
              height: int = 280, color: str = theme.ACCENT, media_movil: int = 0) -> go.Figure:
    """Área + línea. Opcionalmente superpone una media móvil para leer la señal."""
    if df.empty or x not in df or y not in df:
        return vacio(height)
    fig = _fig(height, legend=bool(media_movil))
    hover = _hover(kind)
    fig.add_trace(go.Scatter(
        x=df[x], y=df[y], mode="lines", name=nombre or y,
        line=dict(color=color, width=2.4, shape="spline", smoothing=0.5),
        fill="tozeroy", fillcolor=_alpha(color, 0.16),
        hovertemplate=f"%{{x|%d/%m/%Y}}<br><b>%{{y:{hover}}}</b><extra></extra>",
    ))
    if media_movil and len(df) > media_movil:
        fig.add_trace(go.Scatter(
            x=df[x], y=df[y].rolling(media_movil, min_periods=2).mean(),
            mode="lines", name=f"Media {media_movil}d",
            line=dict(color=theme.NAVY, width=1.6, dash="dot"),
            hovertemplate=f"Media: <b>%{{y:{hover}}}</b><extra></extra>",
        ))
    fig.update_xaxes(tickformatstops=TICKS_FECHA)
    return fig


def lineas_multiples(df: pd.DataFrame, x: str, series: dict[str, str], kind: str = "pct",
                     height: int = 300) -> go.Figure:
    """Varias series comparables en el mismo eje."""
    if df.empty:
        return vacio(height)
    fig = _fig(height)
    hover = _hover(kind)
    eje = etiqueta_periodo(df[x])
    for i, (columna, etiqueta) in enumerate(series.items()):
        if columna not in df:
            continue
        fig.add_trace(go.Scatter(
            x=eje, y=df[columna], mode="lines+markers", name=etiqueta,
            line=dict(color=theme.SERIES[i % len(theme.SERIES)], width=2.2, shape="spline", smoothing=0.4),
            marker=dict(size=5),
            hovertemplate=f"{etiqueta}: <b>%{{y:{hover}}}</b><extra></extra>",
        ))
    fig.update_xaxes(type="category")
    if kind == "pct":
        fig.update_yaxes(tickformat=".0%")
    return fig


def barras_comparadas(df: pd.DataFrame, x: str, series: dict[str, str],
                      kind: str = "money", height: int = 300) -> go.Figure:
    """Barras agrupadas: comparación período a período."""
    if df.empty:
        return vacio(height)
    fig = _fig(height)
    hover = _hover(kind)
    for i, (columna, etiqueta) in enumerate(series.items()):
        if columna not in df:
            continue
        fig.add_trace(go.Bar(
            x=df[x], y=df[columna], name=etiqueta,
            marker_color=theme.SERIES[i % len(theme.SERIES)],
            marker_line_width=0,
            hovertemplate=f"{etiqueta}: <b>%{{y:{hover}}}</b><extra></extra>",
        ))
    fig.update_layout(barmode="group", bargap=0.28, bargroupgap=0.08)
    fig.update_xaxes(type="category")
    return fig


# ---------------------------------------------------------------------------
#  Rankings
# ---------------------------------------------------------------------------
def barras_horizontales(df: pd.DataFrame, dimension: str, valor: str, kind: str = "money",
                        height: int = 320, color: str = theme.ACCENT,
                        destacar_extremos: bool = False) -> go.Figure:
    """Ranking horizontal, ordenado de mayor a menor."""
    if df.empty or dimension not in df or valor not in df:
        return vacio(height)
    base = df.sort_values(valor, ascending=True)
    if destacar_extremos and len(base) > 2:
        colores = [theme.BAD] + [color] * (len(base) - 2) + [theme.GOOD]
    else:
        colores = [color] * len(base)
    fig = _fig(height, legend=False)
    hover = _hover(kind)
    fig.add_trace(go.Bar(
        x=base[valor], y=base[dimension].astype(str), orientation="h",
        marker=dict(color=colores, line_width=0),
        text=[_texto(v, kind) for v in base[valor]],
        textposition="outside", textfont=dict(size=10.5, color=theme.MUTED), cliponaxis=False,
        hovertemplate=f"%{{y}}<br><b>%{{x:{hover}}}</b><extra></extra>",
    ))
    fig.update_xaxes(showgrid=True, gridcolor=theme.LINE, showticklabels=False)
    fig.update_yaxes(showgrid=False)
    if kind == "pct":
        fig.update_xaxes(range=[0, min(1.0, float(base[valor].max()) * 1.28)])
    else:
        fig.update_xaxes(range=[0, float(base[valor].max()) * 1.22])
    return fig


def barras_desvio(df: pd.DataFrame, dimension: str, valor: str, referencia: float,
                  kind: str = "pct", height: int = 320) -> go.Figure:
    """Barras coloreadas según estén sobre o bajo la meta."""
    if df.empty:
        return vacio(height)
    base = df.sort_values(valor, ascending=True)
    colores = [theme.GOOD if v >= referencia else (theme.WARN if v >= referencia * 0.9 else theme.BAD)
               for v in base[valor]]
    fig = _fig(height, legend=False)
    hover = _hover(kind)
    fig.add_trace(go.Bar(
        x=base[valor], y=base[dimension].astype(str), orientation="h",
        marker=dict(color=colores, line_width=0),
        text=[_texto(v, kind) for v in base[valor]],
        textposition="outside", textfont=dict(size=10.5, color=theme.MUTED), cliponaxis=False,
        hovertemplate=f"%{{y}}<br><b>%{{x:{hover}}}</b><extra></extra>",
    ))
    fig.add_vline(x=referencia, line=dict(color=theme.NAVY, width=1.4, dash="dash"),
                  annotation_text="meta", annotation_position="top",
                  annotation_font=dict(size=9.5, color=theme.NAVY))
    fig.update_xaxes(showgrid=True, gridcolor=theme.LINE, showticklabels=False,
                     range=[0, max(float(base[valor].max()) * 1.25, referencia * 1.15)])
    return fig


# ---------------------------------------------------------------------------
#  Distribuciones
# ---------------------------------------------------------------------------
def dona(df: pd.DataFrame, dimension: str, valor: str, height: int = 280,
         centro_titulo: str = "", centro_valor: str = "") -> go.Figure:
    """Distribución con el total en el centro."""
    if df.empty or dimension not in df:
        return vacio(height)
    fig = _fig(height, legend=True, margin_top=26)
    fig.add_trace(go.Pie(
        labels=df[dimension].astype(str), values=df[valor], hole=0.68,
        marker=dict(colors=theme.SERIES[:len(df)], line=dict(color="#fff", width=2)),
        textinfo="percent", textposition="outside",
        textfont=dict(size=10.5, color=theme.MUTED),
        hovertemplate="%{label}<br><b>%{value:,.0f}</b> (%{percent})<extra></extra>",
        sort=True, direction="clockwise",
    ))
    if centro_valor:
        fig.add_annotation(text=f"<b>{centro_valor}</b>", showarrow=False, x=0.5, y=0.53,
                           font=dict(size=19, color=theme.INK))
        fig.add_annotation(text=centro_titulo, showarrow=False, x=0.5, y=0.42,
                           font=dict(size=9.5, color=theme.MUTED))
    fig.update_layout(legend=dict(orientation="v", x=1.0, y=0.5, xanchor="left", yanchor="middle",
                                  font=dict(size=10.5, color=theme.MUTED)))
    return fig


def barras_apiladas_100(df: pd.DataFrame, x: str, dimension: str, valor: str,
                        height: int = 300) -> go.Figure:
    """Evolución del mix: cada período suma 100%."""
    if df.empty:
        return vacio(height)
    pivot = df.pivot_table(index=x, columns=dimension, values=valor, aggfunc="sum").fillna(0)
    total = pivot.sum(axis=1).replace(0, np.nan)
    pivot = pivot.div(total, axis=0)
    fig = _fig(height)
    for i, columna in enumerate(pivot.columns):
        fig.add_trace(go.Bar(
            x=etiqueta_periodo(pivot.index), y=pivot[columna], name=str(columna),
            marker_color=theme.SERIES[i % len(theme.SERIES)], marker_line_width=0,
            hovertemplate=f"{columna}: <b>%{{y:.1%}}</b><extra></extra>",
        ))
    fig.update_layout(barmode="stack", bargap=0.3)
    fig.update_xaxes(type="category")
    fig.update_yaxes(tickformat=".0%", range=[0, 1])
    return fig


def heatmap(matriz: pd.DataFrame, kind: str = "num", height: int = 320,
            escala: str | None = None) -> go.Figure:
    """Mapa de calor para cruces de dos dimensiones."""
    if matriz.empty:
        return vacio(height)
    colorscale = escala or [[0, "#F2F8FD"], [0.5, theme.ACCENT], [1, theme.NAVY]]
    fig = _fig(height, legend=False)
    fig.add_trace(go.Heatmap(
        z=matriz.values, x=[str(c) for c in matriz.columns], y=[str(i) for i in matriz.index],
        colorscale=colorscale, showscale=False,
        hovertemplate="%{y} · %{x}<br><b>%{z:,.0f}</b><extra></extra>",
        xgap=2, ygap=2,
    ))
    return fig


# ---------------------------------------------------------------------------
#  Medidor
# ---------------------------------------------------------------------------
def gauge(valor: float, titulo: str, meta: float, alerta: float,
          height: int = 190, invertido: bool = False, maximo: float | None = None,
          kind: str = "pct") -> go.Figure:
    """Medidor con zonas de meta; usado sólo donde hay un objetivo real."""
    if valor is None or not np.isfinite(valor):
        return vacio(height, "Sin dato")
    tope = maximo if maximo is not None else (1.0 if kind == "pct" else max(valor, meta) * 1.5)
    if invertido:
        pasos = [
            {"range": [0, meta], "color": "#E3F6EE"},
            {"range": [meta, alerta], "color": "#FCF1DC"},
            {"range": [alerta, tope], "color": "#FDE7E7"},
        ]
        color = theme.GOOD if valor <= meta else (theme.WARN if valor <= alerta else theme.BAD)
    else:
        pasos = [
            {"range": [0, alerta], "color": "#FDE7E7"},
            {"range": [alerta, meta], "color": "#FCF1DC"},
            {"range": [meta, tope], "color": "#E3F6EE"},
        ]
        color = theme.GOOD if valor >= meta else (theme.WARN if valor >= alerta else theme.BAD)

    sufijo = "%" if kind == "pct" else (" h" if kind == "hours" else "")
    mostrado = valor * 100 if kind == "pct" else valor
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=mostrado,
        number=dict(suffix=sufijo, font=dict(size=27, color=theme.INK, family="Inter"),
                    valueformat=".1f"),
        gauge=dict(
            axis=dict(range=[0, tope * 100 if kind == "pct" else tope],
                      tickwidth=0, tickfont=dict(size=9, color=theme.MUTED)),
            bar=dict(color=color, thickness=0.62),
            bgcolor="rgba(0,0,0,0)", borderwidth=0,
            steps=[{"range": [s["range"][0] * (100 if kind == "pct" else 1),
                              s["range"][1] * (100 if kind == "pct" else 1)],
                    "color": s["color"]} for s in pasos],
            threshold=dict(line=dict(color=theme.NAVY, width=2.5), thickness=0.8,
                           value=meta * (100 if kind == "pct" else 1)),
        ),
    ))
    fig.update_layout(
        height=height, margin=dict(l=14, r=14, t=26, b=4),
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color=theme.INK),
        title=dict(text=titulo, font=dict(size=11.5, color=theme.MUTED), x=0.5, xanchor="center", y=0.97),
    )
    return fig


# ---------------------------------------------------------------------------
#  Dispersión
# ---------------------------------------------------------------------------
def dispersion(df: pd.DataFrame, x: str, y: str, tamano: str, etiqueta: str,
               height: int = 330, x_kind: str = "num", y_kind: str = "pct",
               ref_y: float | None = None) -> go.Figure:
    """Volumen contra desempeño: separa lo grande de lo problemático."""
    if df.empty:
        return vacio(height)
    sizes = pd.to_numeric(df[tamano], errors="coerce").fillna(0)
    escala = sizes / sizes.max() * 38 + 8 if sizes.max() else pd.Series(12, index=df.index)
    colores = [theme.GOOD if (ref_y is None or v >= ref_y) else theme.BAD for v in df[y]]
    fig = _fig(height, legend=False)
    fig.add_trace(go.Scatter(
        x=df[x], y=df[y], mode="markers", text=df[etiqueta].astype(str),
        marker=dict(size=escala, color=colores, opacity=0.72,
                    line=dict(width=1.2, color="#fff")),
        hovertemplate=(f"<b>%{{text}}</b><br>{x}: %{{x:{_hover(x_kind)}}}"
                       f"<br>{y}: %{{y:{_hover(y_kind)}}}<extra></extra>"),
    ))
    if ref_y is not None:
        fig.add_hline(y=ref_y, line=dict(color=theme.NAVY, width=1.3, dash="dash"),
                      annotation_text="meta", annotation_position="right",
                      annotation_font=dict(size=9.5, color=theme.NAVY))
    if y_kind == "pct":
        fig.update_yaxes(tickformat=".0%")
    return fig


def embudo(etapas: list[str], valores: list[float], height: int = 290) -> go.Figure:
    """Embudo del flujo operativo, con la retención entre etapas."""
    if not valores:
        return vacio(height)
    fig = _fig(height, legend=False)
    fig.add_trace(go.Funnel(
        y=etapas, x=valores,
        marker=dict(color=[theme.NAVY, theme.ACCENT_DEEP, theme.ACCENT, theme.CYAN,
                           "#8CA3C4"][:len(etapas)], line=dict(width=0)),
        # Plotly abrevia los valores en notación SI ("66,408k"); se fija el
        # formato para que muestre el número real.
        texttemplate="%{value:,.0f}  ·  %{percentInitial:.0%}",
        textposition="inside", insidetextanchor="middle",
        textfont=dict(size=10.5, color="#fff", family="IBM Plex Mono"),
        connector=dict(line=dict(color=theme.LINE, width=1)),
        hovertemplate="%{y}<br><b>%{x:,.0f}</b><extra></extra>",
    ))
    return fig


# ---------------------------------------------------------------------------
#  Auxiliares
# ---------------------------------------------------------------------------
def _hover(kind: str) -> str:
    return {"money": ",.0f", "pct": ".1%", "hours": ".1f", "num": ",.0f", "days": ".1f"}.get(kind, ",.0f")


def _texto(valor, kind: str) -> str:
    if valor is None or not np.isfinite(valor):
        return ""
    if kind == "money":
        if abs(valor) >= 1_000_000:
            return f"S/ {valor/1_000_000:.2f}M"
        if abs(valor) >= 1_000:
            return f"S/ {valor/1_000:.0f}k"
        return f"S/ {valor:,.0f}"
    if kind == "pct":
        return f"{valor*100:.1f}%"
    if kind in ("hours", "days"):
        return f"{valor:.1f}"
    return f"{valor:,.0f}".replace(",", " ")


def _alpha(hex_color: str, alpha: float) -> str:
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r},{g},{b},{alpha})"
