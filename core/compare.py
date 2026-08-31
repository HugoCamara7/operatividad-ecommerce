# -*- coding: utf-8 -*-
"""Períodos y comparación.

El reporte siempre trabaja con dos ventanas de tiempo: la actual y aquella
contra la que se compara.  Aquí se resuelven ambas y se calculan las
variaciones, para que las páginas sólo tengan que mostrarlas.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: Modos de comparación ofrecidos en la barra de filtros.
MODOS = {
    "anterior": "Período anterior",
    "ly": "Mismo período año anterior",
    "personalizado": "Rango personalizado",
    "ninguno": "Sin comparación",
}

MESES = ("ene", "feb", "mar", "abr", "may", "jun",
         "jul", "ago", "sep", "oct", "nov", "dic")


@dataclass(frozen=True)
class Periodo:
    desde: pd.Timestamp | None = None
    hasta: pd.Timestamp | None = None

    @property
    def valido(self) -> bool:
        return self.desde is not None and self.hasta is not None

    @property
    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1 if self.valido else 0

    def texto(self) -> str:
        if not self.valido:
            return "—"
        return f"{self.desde:%d/%m/%Y} – {self.hasta:%d/%m/%Y}"

    def texto_corto(self) -> str:
        if not self.valido:
            return "—"
        d, h = self.desde, self.hasta
        if (d.year, d.month) == (h.year, h.month):
            return f"{d.day:02d}–{h.day:02d} {MESES[h.month - 1]} {h.year}"
        return f"{d.day:02d} {MESES[d.month - 1]} – {h.day:02d} {MESES[h.month - 1]} {h.year}"


def periodo_anterior(actual: Periodo) -> Periodo:
    """Misma cantidad de días, inmediatamente antes."""
    if not actual.valido:
        return Periodo()
    hasta = actual.desde - pd.Timedelta(days=1)
    return Periodo(hasta - pd.Timedelta(days=actual.dias - 1), hasta)


def mismo_periodo_ly(actual: Periodo) -> Periodo:
    """Mismas fechas del año anterior.

    Se resta un año calendario; si el día no existe (29 de febrero) se ajusta al
    día válido más cercano.
    """
    if not actual.valido:
        return Periodo()
    return Periodo(_un_anio_antes(actual.desde), _un_anio_antes(actual.hasta))


def _un_anio_antes(fecha: pd.Timestamp) -> pd.Timestamp:
    try:
        return fecha.replace(year=fecha.year - 1)
    except ValueError:                       # 29 de febrero en año no bisiesto
        return fecha.replace(year=fecha.year - 1, day=28)


def resolver(actual: Periodo, modo: str, personalizado: Periodo | None = None) -> Periodo:
    """Ventana de comparación según el modo elegido."""
    if modo == "anterior":
        return periodo_anterior(actual)
    if modo == "ly":
        return mismo_periodo_ly(actual)
    if modo == "personalizado" and personalizado and personalizado.valido:
        return personalizado
    return Periodo()


def recortar(df: pd.DataFrame, periodo: Periodo, columna: str = "fecha_compra") -> pd.DataFrame:
    """Subconjunto del DataFrame dentro del período."""
    if df is None or df.empty or not periodo.valido or columna not in df:
        return df.iloc[0:0] if df is not None else pd.DataFrame()
    fecha = df[columna]
    fin = periodo.hasta + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
    return df[(fecha >= periodo.desde) & (fecha <= fin) & fecha.notna()]


# ---------------------------------------------------------------------------
#  Variaciones
# ---------------------------------------------------------------------------
def variacion(actual: float | None, referencia: float | None) -> float | None:
    """Variación relativa; None cuando no es comparable."""
    if actual is None or referencia in (None, 0):
        return None
    try:
        if not (np.isfinite(actual) and np.isfinite(referencia)):
            return None
    except TypeError:
        return None
    return (actual - referencia) / abs(referencia)


def diferencia(actual: float | None, referencia: float | None) -> float | None:
    if actual is None or referencia is None:
        return None
    try:
        if not (np.isfinite(actual) and np.isfinite(referencia)):
            return None
    except TypeError:
        return None
    return actual - referencia


@dataclass
class Medida:
    """Un indicador con su comparación lista para mostrar."""

    clave: str
    etiqueta: str
    actual: float | None
    referencia: float | None = None
    kind: str = "num"
    invertido: bool = False          # True cuando bajar es bueno
    icono: str = "📊"
    nota: str = ""

    @property
    def dif(self) -> float | None:
        return diferencia(self.actual, self.referencia)

    @property
    def var(self) -> float | None:
        return variacion(self.actual, self.referencia)

    @property
    def mejora(self) -> bool | None:
        """Si el movimiento es favorable para el negocio."""
        cambio = self.var
        if cambio is None or abs(cambio) < 0.0005:
            return None
        return (cambio < 0) if self.invertido else (cambio > 0)


def tabla_comparativa(medidas: list[Medida], etiqueta_ref: str = "Referencia") -> pd.DataFrame:
    """Actual | Referencia | Diferencia | Variación %, para mostrar o exportar."""
    filas = []
    for medida in medidas:
        filas.append({
            "Indicador": medida.etiqueta,
            "Actual": medida.actual,
            etiqueta_ref: medida.referencia,
            "Diferencia": medida.dif,
            "Variación %": medida.var,
            "_kind": medida.kind,
        })
    return pd.DataFrame(filas)
