# -*- coding: utf-8 -*-
"""Limpieza y tipado de valores.

Corrige los problemas reales detectados en la base:
  * mojibake por doble codificación UTF-8   ('MarrÃ³n'  -> 'Marrón')
  * marcadores de vacío  ('-', '', '(en blanco)')  -> nulo
  * variantes del mismo valor ('Cuzco'/'Cusco', 'Sharff'/'Scharf')
  * fechas mezcladas: ISO (con o sin zona), dd/mm/aaaa, meses en español
    y seriales de Excel
"""
from __future__ import annotations

import re

import numpy as np
import pandas as pd

from .normalize import fix_mojibake

EXCEL_EPOCH = pd.Timestamp("1899-12-30")


# ---------------------------------------------------------------------------
#  Texto
# ---------------------------------------------------------------------------
#: Marcas de doble codificación UTF-8. Filtrar por ellas evita recorrer en Python
#: los millones de valores que están perfectamente bien.
_MOJIBAKE_RE = r"[ÃÂÐ]|â€"


def clean_text(series: pd.Series, null_tokens: set[str]) -> pd.Series:
    out = series.astype("string").str.strip()
    dañados = out.str.contains(_MOJIBAKE_RE, regex=True, na=False)
    if dañados.any():
        out.loc[dañados] = out[dañados].map(fix_mojibake)
    out = out.mask(out.str.casefold().isin({t.casefold() for t in null_tokens}))
    return out.mask(out.eq(""))


# ---------------------------------------------------------------------------
#  Números
# ---------------------------------------------------------------------------
def clean_number(series: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(series):
        return pd.to_numeric(series, errors="coerce")
    text = series.astype("string").str.strip()
    text = text.str.replace(r"[^\d,.\-]", "", regex=True)
    # 1.234,56 (formato local) -> 1234.56
    local = text.str.contains(r",\d{1,2}$", na=False)
    text = text.mask(local, text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    text = text.mask(~local, text.str.replace(",", "", regex=False))
    return pd.to_numeric(text, errors="coerce")


# ---------------------------------------------------------------------------
#  Fechas
# ---------------------------------------------------------------------------
#: Perú no aplica horario de verano, así que una marca con zona horaria
#: ('2026-08-02T12:04:00Z') se lleva a hora local con un desfase fijo. Sin esto
#: pandas devuelve una serie con zona y la asignación al resultado revienta:
#: la columna terminaba guardada como texto y el reporte se quedaba sin fechas.
HORAS_UTC_LOCAL = -5

#: Lo que el origen escribe cuando no hay fecha. '0' incluido: el serial 0 de
#: Excel es 1899-12-30, que no es una fecha real de un pedido.
_VACIOS_FECHA = ("-", "", "0", "0.0", "00/00/0000", "1900-01-00")

#: Formatos observados en las bases, en orden de frecuencia. Se prueban de forma
#: vectorizada antes de recurrir a la inferencia elemento a elemento, que sobre
#: cien mil filas es órdenes de magnitud más lenta.
#: Van primero los que empiezan por el año, para que un '2026/08/02' no se lea
#: nunca con la regla peruana (día primero) y acabe en el mes equivocado.
_FORMATOS = (
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d",
    "%Y%m%d",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%d-%m-%Y %H:%M:%S",
    "%d-%m-%Y",
    "%d.%m.%Y",
    "%d/%m/%y",
)

#: Una marca ISO con zona: 'Z', '+00:00' o '-0500' al final.
_CON_ZONA = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")

#: Empieza por el año: se interpreta año-mes-día, nunca día-mes-año.
_EMPIEZA_POR_ANIO = re.compile(r"^\d{4}[-/.]")

#: Meses abreviados en español, tal como los escribe Excel con locale es-PE
#: ('01-ago-2026'). Se traducen porque el intérprete de fechas sólo sabe inglés.
_MESES_ES = {
    "ene": "Jan", "feb": "Feb", "mar": "Mar", "abr": "Apr",
    "may": "May", "jun": "Jun", "jul": "Jul", "ago": "Aug",
    "set": "Sep", "sep": "Sep", "oct": "Oct", "nov": "Nov", "dic": "Dec",
    "enero": "Jan", "febrero": "Feb", "marzo": "Mar", "abril": "Apr",
    "mayo": "May", "junio": "Jun", "julio": "Jul", "agosto": "Aug",
    "setiembre": "Sep", "septiembre": "Sep", "octubre": "Oct",
    "noviembre": "Nov", "diciembre": "Dec",
}
_MES_ES_RE = re.compile(r"\b(" + "|".join(sorted(_MESES_ES, key=len, reverse=True)) + r")\b",
                        re.IGNORECASE)


def _sin_zona(valores: pd.Series) -> pd.Series:
    """Devuelve la serie en hora local y sin zona, lista para asignar."""
    if isinstance(valores.dtype, pd.DatetimeTZDtype):
        valores = valores.dt.tz_convert("UTC").dt.tz_localize(None)
        valores = valores + pd.Timedelta(hours=HORAS_UTC_LOCAL)
    return valores.astype("datetime64[ns]")


def _a_espanol(texto: pd.Series) -> pd.Series:
    """'01-ago-2026' -> '01-Aug-2026';  '3 de agosto de 2026' -> '3 Aug 2026'."""
    fuera = texto.str.replace(_MES_ES_RE, lambda m: _MESES_ES[m.group(1).lower()], regex=True)
    return fuera.str.replace(r"\s+de\s+", " ", regex=True)


def _seriales(valores: pd.Series) -> pd.Series:
    """Números de Excel plausibles como fecha (1954-2064) -> datetime."""
    numero = pd.to_numeric(valores, errors="coerce")
    dentro = numero.between(20000, 60000)
    salida = pd.Series(pd.NaT, index=valores.index, dtype="datetime64[ns]")
    if dentro.any():
        # Al segundo: el serial es un float y arrastra ruido de coma flotante.
        salida.loc[numero.index[dentro]] = (
            EXCEL_EPOCH + pd.to_timedelta(numero[dentro], unit="D")
        ).dt.round("s")
    return salida


def clean_datetime(series: pd.Series) -> pd.Series:
    """Convierte una columna heterogénea de fechas a datetime64 sin zona.

    Maneja a la vez ISO ('2026-08-02T12:04:00', con o sin zona horaria), formato
    peruano ('02/08/2026 14:19:51'), meses en español ('01-ago-2026') y seriales
    numéricos de Excel (45871).  Nunca lanza excepción y nunca devuelve una serie
    con zona horaria: cualquier valor que no se reconozca queda como nulo.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return _sin_zona(series)

    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")

    # Una columna ya numérica sólo puede ser un serial de Excel.
    if pd.api.types.is_numeric_dtype(series):
        return _seriales(series)

    text = series.astype("string").str.strip()
    text = text.mask(text.str.casefold().isin(_VACIOS_FECHA))

    pending = text.notna()
    if not pending.any():
        return out

    def _asentar(parsed: pd.Series) -> None:
        parsed = _sin_zona(parsed)
        ok = parsed.notna()
        if ok.any():
            out.loc[parsed.index[ok]] = parsed[ok]
            pending.loc[parsed.index[ok]] = False

    # -- 1. formatos conocidos, en bloque
    for formato in _FORMATOS:
        if not pending.any():
            break
        _asentar(pd.to_datetime(text[pending], errors="coerce", format=formato))

    # -- 2. marcas con zona horaria ('...Z', '...-05:00'), llevadas a hora local
    if pending.any():
        con_zona = pending & text.str.contains(_CON_ZONA, regex=True, na=False)
        if con_zona.any():
            _asentar(pd.to_datetime(text[con_zona], errors="coerce",
                                    format="ISO8601", utc=True))

    # -- 3. seriales de Excel guardados como texto ('45871')
    if pending.any():
        numerico = pending & text.str.fullmatch(r"\d{5}(?:\.\d+)?", na=False)
        if numerico.any():
            _asentar(_seriales(text[numerico]))

    # -- 4. resto: inferencia elemento a elemento, ya sobre pocas filas.
    #       El orden día/mes sólo se invierte cuando el valor NO empieza por el
    #       año; si empieza por el año es año-mes-día y forzar 'día primero'
    #       cambiaría agosto por febrero sin avisar.
    if pending.any():
        resto = _a_espanol(text[pending])
        anio_primero = resto.str.contains(_EMPIEZA_POR_ANIO, regex=True, na=False)
        for subconjunto, dia_primero in ((resto[anio_primero], False),
                                         (resto[~anio_primero], True)):
            if subconjunto.empty:
                continue
            try:
                _asentar(pd.to_datetime(subconjunto, errors="coerce",
                                        dayfirst=dia_primero, format="mixed"))
            except (ValueError, TypeError):
                # Zonas horarias mezcladas en el mismo bloque: se unifica en UTC.
                _asentar(pd.to_datetime(subconjunto, errors="coerce",
                                        dayfirst=dia_primero, utc=True))

    # -- 5. último recurso: seriales en una columna de tipo mixto
    if pending.any():
        _asentar(_seriales(series[pending]))
    return out


# ---------------------------------------------------------------------------
#  Banderas Sí/No
# ---------------------------------------------------------------------------
def to_flag(series: pd.Series, yes_values: set[str]) -> pd.Series:
    """Serie booleana nullable a partir de Sí/No, SI/NO, 1/0, True/False."""
    if pd.api.types.is_bool_dtype(series):
        return series.astype("boolean")
    text = series.astype("string").str.strip().str.upper()
    text = text.map(lambda v: fix_mojibake(v) if isinstance(v, str) else v)
    yes = {y.upper() for y in yes_values}
    no = {"NO", "N", "FALSE", "0"}
    out = pd.Series(pd.NA, index=series.index, dtype="boolean")
    out[text.isin(yes)] = True
    out[text.isin(no)] = False
    return out


# ---------------------------------------------------------------------------
#  Aplicación del esquema a un dataset
# ---------------------------------------------------------------------------
#: A partir de aquí se avisa de una columna de fecha mal leída. Por debajo son
#: nulos normales del origen (pedidos sin documentar, sin entregar, etc.).
UMBRAL_AVISO_FECHA = 0.20


def apply_types(frame: pd.DataFrame, field_spec: dict, null_tokens: set[str],
                avisos: list[str] | None = None) -> pd.DataFrame:
    """Tipa cada columna según el esquema y anota en `avisos` lo que salió mal.

    Una fecha que no se entiende no puede quedarse en silencio: el reporte se
    construye sobre ella, así que el problema se anota para mostrarlo en la
    pantalla «Fuente» en vez de aparecer como un dashboard vacío.
    """
    out = frame.copy()
    anotar = avisos if avisos is not None else []
    for column in out.columns:
        spec = field_spec.get(column, {})
        kind = spec.get("type", "str")
        # Algunas columnas del origen traen estados escritos donde debería ir un
        # dato (p. ej. "Cancelada manual" en la tienda del quiebre). Se declaran
        # por campo en schema.yml y aquí se convierten en nulos.
        vacios = null_tokens | {str(v) for v in spec.get("null_values", [])}
        try:
            if kind in ("date", "datetime"):
                fecha = clean_datetime(out[column])
                # 'date' es un día, no un instante: se recorta la hora para que
                # el mismo pedido no cambie de día según cómo venga escrito.
                out[column] = fecha.dt.normalize() if kind == "date" else fecha
                anotar.extend(_revisar_fecha(column, frame[column], out[column]))
            elif kind in ("float", "int"):
                out[column] = clean_number(out[column])
            else:
                out[column] = clean_text(out[column], vacios)
        except Exception as exc:
            out[column] = clean_text(out[column].astype("string"), vacios)
            anotar.append(f"La columna «{column}» no se pudo convertir a "
                          f"{kind}: {exc}. Se dejó como texto.")
    return out


def _revisar_fecha(column: str, crudo: pd.Series, tipado: pd.Series) -> list[str]:
    """Compara lo que traía la columna con lo que se logró interpretar."""
    con_dato = crudo.notna()
    if crudo.dtype == object or isinstance(crudo.dtype, pd.StringDtype):
        con_dato &= ~crudo.astype("string").str.strip().isin(_VACIOS_FECHA)
    total = int(con_dato.sum())
    if not total:
        return []
    perdidas = int((con_dato & tipado.isna()).sum())
    if not perdidas:
        return []
    ejemplos = crudo[con_dato & tipado.isna()].astype("string").dropna().unique()[:3]
    muestra = ", ".join(f"«{e}»" for e in ejemplos)
    if perdidas == total:
        return [f"Ninguno de los {total:,} valores de la fecha «{column}» se pudo "
                f"interpretar (por ejemplo {muestra}). El reporte se quedará sin "
                f"ese dato: revise el formato en el Excel.".replace(",", " ")]
    if perdidas / total >= UMBRAL_AVISO_FECHA:
        return [f"{perdidas:,} de {total:,} valores de la fecha «{column}» "
                f"({perdidas / total:.0%}) no se pudieron interpretar "
                f"(por ejemplo {muestra}).".replace(",", " ")]
    return []


def apply_value_maps(frame: pd.DataFrame, value_maps: dict) -> pd.DataFrame:
    """Unifica variantes del mismo valor de negocio (comparación sin tildes ni caso)."""
    out = frame.copy()
    for column, mapping in value_maps.items():
        if column.startswith("_") or column not in out.columns:
            continue
        table = {str(k).strip().upper(): v for k, v in mapping.items()}
        series = out[column].astype("string")
        key = series.str.strip().str.upper()
        out[column] = key.map(table).fillna(series)
    return out


def mask_pii(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Enmascara datos personales conservando utilidad de conteo."""
    out = frame.copy()
    for column in columns:
        if column not in out.columns:
            continue
        series = out[column].astype("string")
        if column == "cliente_mail":
            out[column] = series.str.replace(r"^(.).*?(@.*)$", r"\1•••\2", regex=True)
        else:
            out[column] = series.str.slice(0, 2).fillna("") + "•••"
            out.loc[series.isna(), column] = pd.NA
    return out
