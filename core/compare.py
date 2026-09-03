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


# ---------------------------------------------------------------------------
#  Atajos de período
# ---------------------------------------------------------------------------
#: Atajos de la barra de filtros, del más corto al más largo.
#: Se calculan sobre el último día CON DATOS del maestro, no sobre la fecha de
#: hoy: el Excel siempre va unos días atrasado y de otro modo el rango saldría
#: vacío. Las etiquetas lo dicen para que nadie tenga que adivinarlo.
ATAJOS: dict[str, str] = {
    "ultimos_7": "Últimos 7 días con datos",
    "ultimos_30": "Últimos 30 días con datos",
    "ultimos_90": "Últimos 90 días con datos",
    "mes_ultimo": "Mes del último dato",
    "mes_anterior": "Mes anterior completo",
    "anio_ultimo": "Año del último dato",
    "historico": "Todo el histórico",
    "personalizado": "Personalizado",
}

#: Atajo preferido al abrir el reporte o al cargar un archivo nuevo. Si no
#: aplica a los datos cargados se usa el histórico completo.
ATAJO_INICIAL = "ultimos_30"

#: Atajos que siempre tienen sentido, cualquiera sea el archivo.
_SIEMPRE = ("historico", "personalizado")


def rango_atajo(atajo: str, minimo, maximo) -> Periodo:
    """Ventana que corresponde a un atajo, siempre dentro de los datos cargados.

    `minimo` y `maximo` son el primer y el último día con datos. El resultado
    nunca se sale de ese intervalo: pedir «últimos 90 días» sobre un maestro de
    26 días devuelve los 26 días, no un rango vacío.
    """
    limites = _limites(minimo, maximo)
    if limites is None:
        return Periodo()
    minimo, maximo = limites

    if atajo in ("ultimos_7", "ultimos_30", "ultimos_90"):
        dias = int(atajo.split("_")[1])
        return _acotar(maximo - pd.Timedelta(days=dias - 1), maximo, minimo, maximo)
    if atajo == "mes_ultimo":
        return _acotar(maximo.replace(day=1), maximo, minimo, maximo)
    if atajo == "mes_anterior":
        fin = maximo.replace(day=1) - pd.Timedelta(days=1)
        return _acotar(fin.replace(day=1), fin, minimo, maximo)
    if atajo == "anio_ultimo":
        return _acotar(maximo.replace(month=1, day=1), maximo, minimo, maximo)
    return Periodo(minimo, maximo)          # histórico y personalizado sin valor


def atajos_disponibles(minimo, maximo) -> list[str]:
    """Atajos que de verdad recortan los datos cargados.

    Ofrecer «últimos 90 días» sobre un archivo de 26 días —o «mes anterior»
    cuando no hay mes anterior— produce rangos idénticos o vacíos y hace que el
    filtro parezca roto. Aquí se descartan de antemano.
    """
    limites = _limites(minimo, maximo)
    if limites is None:
        return list(_SIEMPRE)
    minimo, maximo = limites
    span = (maximo - minimo).days + 1

    out = []
    for clave in ATAJOS:
        if clave in _SIEMPRE:
            continue
        if clave.startswith("ultimos_") and int(clave.split("_")[1]) >= span:
            continue
        if clave == "mes_ultimo" and minimo >= maximo.replace(day=1):
            continue
        if clave == "mes_anterior" and (maximo.replace(day=1) - pd.Timedelta(days=1)) < minimo:
            continue
        if clave == "anio_ultimo" and minimo.year >= maximo.year:
            continue
        out.append(clave)
    return out + list(_SIEMPRE)


def atajo_inicial(minimo, maximo) -> str:
    """Atajo por omisión: el preferido si aplica, y si no, el histórico."""
    disponibles = atajos_disponibles(minimo, maximo)
    return ATAJO_INICIAL if ATAJO_INICIAL in disponibles else "historico"


def encajar(periodo: Periodo, minimo, maximo) -> Periodo:
    """Recorta un período a los límites de los datos disponibles.

    Se usa para que ningún calendario guarde fechas que el archivo cargado no
    tiene: Streamlit rechaza un valor fuera de su rango permitido.
    """
    limites = _limites(minimo, maximo)
    if limites is None or not periodo.valido:
        return Periodo()
    return _acotar(periodo.desde, periodo.hasta, *limites)


def cobertura(periodo: Periodo, minimo, maximo) -> tuple[int, int]:
    """Días del período que el archivo cargado realmente contiene, y su total.

    Comparar contra días que el maestro no trae produce variaciones absurdas
    (+600% en un OTIF): la interfaz usa esto para decirlo en lugar de callarlo.
    """
    if not periodo.valido:
        return 0, 0
    limites = _limites(minimo, maximo)
    if limites is None:
        return 0, periodo.dias
    inicio, fin = max(periodo.desde, limites[0]), min(periodo.hasta, limites[1])
    dentro = (fin - inicio).days + 1 if fin >= inicio else 0
    return dentro, periodo.dias


def _limites(minimo, maximo) -> tuple[pd.Timestamp, pd.Timestamp] | None:
    """Primer y último día con datos, normalizados y en orden."""
    if minimo is None or maximo is None:
        return None
    try:
        if pd.isna(minimo) or pd.isna(maximo):
            return None
    except (TypeError, ValueError):
        return None
    minimo, maximo = pd.Timestamp(minimo).normalize(), pd.Timestamp(maximo).normalize()
    return (maximo, minimo) if minimo > maximo else (minimo, maximo)


def _acotar(desde: pd.Timestamp, hasta: pd.Timestamp,
            minimo: pd.Timestamp, maximo: pd.Timestamp) -> Periodo:
    """Encaja un rango dentro de los límites de los datos disponibles."""
    if hasta < minimo or desde > maximo:     # sin intersección: todo el histórico
        return Periodo(minimo, maximo)
    return Periodo(max(desde, minimo), min(hasta, maximo))
