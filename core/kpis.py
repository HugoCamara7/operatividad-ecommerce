# -*- coding: utf-8 -*-
"""Cálculo de KPIs.

Cada función recibe DataFrames ya filtrados y devuelve valores puros: aquí no
hay nada de Streamlit ni de gráficos, de modo que los indicadores se pueden
probar, reutilizar o exportar por separado.

Convenciones de conteo, derivadas de la estructura real de la base:
  * Las filas son LÍNEAS de pedido, no pedidos.
  * `orden` identifica el pedido -> los conteos de pedidos usan nunique().
  * Los montos se suman a nivel línea.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
#  Utilidades
# ---------------------------------------------------------------------------
def _safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b else 0.0


def _rate(series: pd.Series) -> float:
    """Proporción de verdaderos ignorando nulos."""
    if series is None or len(series) == 0:
        return float("nan")
    clean = series.dropna()
    return float(clean.mean()) if len(clean) else float("nan")


@dataclass
class Kpi:
    """Un indicador con su comparación contra el período anterior."""

    key: str
    label: str
    value: float
    fmt: str = "num"                 # num | money | pct | hours | days
    delta: float | None = None       # variación relativa vs. período previo
    previous: float | None = None
    help: str = ""
    semaforo: str = ""               # bueno | alerta | critico | ''

    @property
    def has_delta(self) -> bool:
        return self.delta is not None and np.isfinite(self.delta)


def semaforo(value: float, rules: dict | None) -> str:
    """Clasifica un valor contra los umbrales configurados en schema.yml."""
    if not rules or value is None or not np.isfinite(value):
        return ""
    bueno, alerta = rules.get("bueno"), rules.get("alerta")
    if bueno is None or alerta is None:
        return ""
    if rules.get("invertido"):       # menos es mejor (p. ej. cancelación, horas)
        if value <= bueno:
            return "bueno"
        return "alerta" if value <= alerta else "critico"
    if value >= bueno:
        return "bueno"
    return "alerta" if value >= alerta else "critico"


# ---------------------------------------------------------------------------
#  Bloque comercial
# ---------------------------------------------------------------------------
def ventas(df: pd.DataFrame) -> dict[str, float]:
    """Indicadores de venta y demanda sobre la base de órdenes."""
    if df.empty:
        return {}
    validas = df[~df.get("es_cancelada", False)] if "es_cancelada" in df else df
    n_ordenes = df["orden"].nunique()
    n_validas = validas["orden"].nunique()
    venta = float(validas["total"].sum()) if "total" in validas else 0.0
    neto = float(validas["total_sin_igv"].sum()) if "total_sin_igv" in validas else 0.0
    unidades = float(validas["unidades"].sum()) if "unidades" in validas else 0.0
    out = {
        "ordenes": n_ordenes,
        "ordenes_validas": n_validas,
        "lineas": len(df),
        "venta": venta,
        "venta_neta": neto,
        "unidades": unidades,
        "ticket": _safe_div(venta, n_validas),
        "unidades_por_orden": _safe_div(unidades, n_validas),
        "precio_medio": _safe_div(venta, unidades),
        "lineas_por_orden": _safe_div(len(validas), n_validas),
    }
    if "descuento" in validas and "subtotal" in validas:
        out["descuento_total"] = float(validas["descuento"].sum())
        out["tasa_descuento"] = _safe_div(out["descuento_total"], float(validas["subtotal"].sum()))
    if "uso_cupon" in validas:
        out["pct_cupon"] = _safe_div(validas[validas["uso_cupon"]]["orden"].nunique(), n_validas)
    if "shipping" in validas:
        out["shipping_total"] = float(validas["shipping"].sum())
    return out


def calidad_operativa(df: pd.DataFrame) -> dict[str, float]:
    """Cancelación, documentación y backlog: la salud del flujo de pedidos."""
    if df.empty or "orden" not in df:
        return {}
    por_orden = df.groupby("orden").agg(
        cancelada=("es_cancelada", "max") if "es_cancelada" in df else ("orden", "size"),
    )
    total = len(por_orden)
    out = {"ordenes": total}
    if "es_cancelada" in df:
        canceladas = int(por_orden["cancelada"].sum())
        out["canceladas"] = canceladas
        out["tasa_cancelacion"] = _safe_div(canceladas, total)
        out["venta_perdida"] = float(df.loc[df["es_cancelada"], "total"].sum()) if "total" in df else 0.0
    if "es_finalizada" in df:
        out["tasa_finalizacion"] = _safe_div(
            df[df["es_finalizada"]]["orden"].nunique(), total
        )
    if "es_backlog" in df:
        out["backlog"] = int(df[df["es_backlog"]]["orden"].nunique())
    if "es_documentado" in df:
        out["tasa_documentado"] = _rate(df["es_documentado"])
    if "es_mw" in df:
        out["pct_mw"] = _safe_div(df[df["es_mw"]]["orden"].nunique(), total)
    return out


# ---------------------------------------------------------------------------
#  Bloque logístico
# ---------------------------------------------------------------------------
def otif(df: pd.DataFrame) -> dict[str, float]:
    """OTIF y descomposición de tiempos."""
    if df.empty:
        return {}
    out: dict[str, float] = {"pedidos": df["orden"].nunique() if "orden" in df else len(df)}
    for column, key in (("otif_ok", "otif"), ("on_time_ok", "on_time"), ("in_full_ok", "in_full")):
        if column in df:
            out[key] = _rate(df[column])
    for column, key in (
        ("t_doc_calendario", "t_documentacion"),
        ("t_despacho", "t_despacho"),
        ("t_total", "t_total"),
        ("t_tienda", "t_tienda"),
        ("t_logistico", "t_logistico"),
    ):
        if column in df and df[column].notna().any():
            out[key] = float(df[column].median())
            out[f"{key}_p90"] = float(df[column].quantile(0.90))
    if "responsable_demora" in df:
        resp = df["responsable_demora"].dropna()
        resp = resp[resp.astype(str).str.strip() != ""]
        if len(resp):
            counts = resp.value_counts(normalize=True)
            out["demora_tienda"] = float(counts.get("Tienda", 0.0))
            out["demora_logistica"] = float(counts.get("Logístico", counts.get("Logistico", 0.0)))
            out["con_demora"] = len(resp)
    return out


def carrier(df: pd.DataFrame) -> dict[str, float]:
    """Desempeño del operador logístico según su propio tracking."""
    if df.empty:
        return {}
    out: dict[str, float] = {"envios": len(df)}
    for column, key in (("on_time_ok", "on_time"), ("otif_ok", "otif"), ("in_full_ok", "in_full")):
        if column in df:
            out[key] = _rate(df[column])
    if "entregado" in df:
        out["entregados"] = int(df["entregado"].sum())
        out["tasa_entrega"] = _rate(df["entregado"])
        out["en_transito"] = int((~df["entregado"]).sum())
    if "desvio_dias" in df and df["desvio_dias"].notna().any():
        out["desvio_medio"] = float(df["desvio_dias"].median())
        out["fuera_sla"] = int((df["desvio_dias"] > 0).sum())
    if "sla" in df and df["sla"].notna().any():
        out["sla_medio"] = float(df["sla"].mean())
    if "time_real" in df and df["time_real"].notna().any():
        out["tiempo_real_medio"] = float(df["time_real"].mean())
    if "reintento" in df:
        out["reintentos"] = int(df["reintento"].sum())
        out["tasa_reintento"] = _rate(df["reintento"])
    if "on_time_revisar" in df:
        out["por_revisar"] = int(df["on_time_revisar"].sum())
    return out


def quiebres(df: pd.DataFrame, ordenes: pd.DataFrame | None = None) -> dict[str, float]:
    """Quiebres de stock y venta perdida asociada."""
    if df.empty:
        return {}
    out: dict[str, float] = {
        "quiebres": len(df),
        "ordenes_afectadas": df["orden"].nunique() if "orden" in df else len(df),
        "skus_afectados": df["sku"].nunique() if "sku" in df else 0,
    }
    if "monto_sin_igv" in df:
        out["monto_perdido"] = float(df["monto_sin_igv"].sum())
    if "monto_con_igv" in df:
        out["monto_perdido_igv"] = float(df["monto_con_igv"].sum())
    for column, key in (("dias_tienda", "dias_tienda"), ("dias_gestion", "dias_gestion"),
                        ("tiempo_total", "tiempo_total")):
        if column in df and df[column].notna().any():
            out[key] = float(df[column].median())
    if ordenes is not None and not ordenes.empty and "orden" in ordenes:
        out["tasa_quiebre"] = _safe_div(out["ordenes_afectadas"], ordenes["orden"].nunique())
    return out


# ---------------------------------------------------------------------------
#  Comparación entre períodos
# ---------------------------------------------------------------------------
def periodo_anterior(df: pd.DataFrame, desde: pd.Timestamp, hasta: pd.Timestamp,
                     columna: str = "fecha_compra") -> pd.DataFrame:
    """Mismo número de días inmediatamente anterior al rango indicado."""
    if df.empty or columna not in df:
        return df.iloc[0:0]
    span = (hasta - desde)
    prev_hasta = desde - pd.Timedelta(days=1)
    prev_desde = prev_hasta - span
    fecha = df[columna]
    return df[(fecha >= prev_desde) & (fecha <= prev_hasta)]


def delta(actual: float | None, previo: float | None) -> float | None:
    """Variación relativa; None cuando no es comparable."""
    if actual is None or previo in (None, 0) or not np.isfinite(previo or np.nan):
        return None
    if not np.isfinite(actual):
        return None
    return (actual - previo) / abs(previo)


# ---------------------------------------------------------------------------
#  Agrupaciones para rankings y series
# ---------------------------------------------------------------------------
def serie_temporal(df: pd.DataFrame, freq: str = "D", columna: str = "fecha_compra") -> pd.DataFrame:
    """Venta, pedidos y unidades por día / semana / mes."""
    if df.empty or columna not in df:
        return pd.DataFrame()
    base = df.dropna(subset=[columna]).copy()
    if base.empty:
        return pd.DataFrame()
    base["_periodo"] = base[columna].dt.to_period(freq).dt.to_timestamp()
    agg = {"orden": "nunique"}
    if "total" in base:
        agg["total"] = "sum"
    if "unidades" in base:
        agg["unidades"] = "sum"
    out = base.groupby("_periodo").agg(agg).reset_index()
    out = out.rename(columns={"_periodo": "periodo", "orden": "ordenes", "total": "venta"})
    if "venta" in out and "ordenes" in out:
        out["ticket"] = out["venta"] / out["ordenes"].replace(0, np.nan)
    if "es_cancelada" in base:
        canc = base[base["es_cancelada"]].groupby("_periodo")["orden"].nunique()
        out["canceladas"] = out["periodo"].map(canc).fillna(0)
        out["tasa_cancelacion"] = out["canceladas"] / out["ordenes"].replace(0, np.nan)
    return out


def ranking(df: pd.DataFrame, dimension: str, metrica: str = "venta",
            top: int = 15, ascendente: bool = False) -> pd.DataFrame:
    """Top/Bottom de una dimensión por venta, pedidos o unidades."""
    if df.empty or dimension not in df:
        return pd.DataFrame()
    base = df.dropna(subset=[dimension])
    if base.empty:
        return pd.DataFrame()
    agg = {"orden": "nunique"}
    if "total" in base:
        agg["total"] = "sum"
    if "unidades" in base:
        agg["unidades"] = "sum"
    out = base.groupby(dimension).agg(agg).reset_index()
    out = out.rename(columns={"orden": "ordenes", "total": "venta"})
    if "venta" in out:
        out["ticket"] = out["venta"] / out["ordenes"].replace(0, np.nan)
    if "es_cancelada" in base:
        canc = base.groupby(dimension)["es_cancelada"].mean()
        out["tasa_cancelacion"] = out[dimension].map(canc)
    columna = metrica if metrica in out else ("venta" if "venta" in out else "ordenes")
    return out.sort_values(columna, ascending=ascendente).head(top)


def tasa_por_dimension(df: pd.DataFrame, dimension: str, flag: str,
                       minimo: int = 20) -> pd.DataFrame:
    """Tasa de cumplimiento por dimensión, descartando grupos sin masa crítica."""
    if df.empty or dimension not in df or flag not in df:
        return pd.DataFrame()
    base = df.dropna(subset=[dimension])
    grouped = base.groupby(dimension)[flag]
    out = pd.DataFrame({"tasa": grouped.mean(), "casos": grouped.count()}).reset_index()
    out = out[out["casos"] >= minimo]
    return out.sort_values("tasa", ascending=False)
