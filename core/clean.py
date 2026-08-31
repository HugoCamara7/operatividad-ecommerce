# -*- coding: utf-8 -*-
"""Limpieza y tipado de valores.

Corrige los problemas reales detectados en la base:
  * mojibake por doble codificación UTF-8   ('MarrÃ³n'  -> 'Marrón')
  * marcadores de vacío  ('-', '', '(en blanco)')  -> nulo
  * variantes del mismo valor ('Cuzco'/'Cusco', 'Sharff'/'Scharf')
  * fechas mezcladas: ISO, dd/mm/aaaa y seriales de Excel
"""
from __future__ import annotations

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
#: Formatos observados en las bases, en orden de frecuencia. Se prueban de forma
#: vectorizada antes de recurrir a la inferencia elemento a elemento, que sobre
#: cien mil filas es órdenes de magnitud más lenta.
_FORMATS = (
    ("%Y-%m-%dT%H:%M:%S", False),
    ("%Y-%m-%dT%H:%M:%S.%f", False),
    ("%d/%m/%Y %H:%M:%S", True),
    ("%d/%m/%Y", True),
    ("%Y-%m-%d %H:%M:%S", False),
    ("%Y-%m-%d", False),
)


def clean_datetime(series: pd.Series) -> pd.Series:
    """Convierte una columna heterogénea de fechas a datetime64.

    Maneja simultáneamente ISO ('2026-08-02T12:04:00'), formato peruano
    ('02/08/2026 14:19:51') y seriales numéricos de Excel.
    """
    if pd.api.types.is_datetime64_any_dtype(series):
        return series

    text = series.astype("string").str.strip()
    text = text.mask(text.isin(["-", "", "0"]))

    out = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    pending = text.notna()
    if not pending.any():
        return out

    for fmt, dayfirst in _FORMATS:
        if not pending.any():
            break
        parsed = pd.to_datetime(text[pending], errors="coerce", format=fmt)
        ok = parsed.notna()
        if ok.any():
            out.loc[parsed.index[ok]] = parsed[ok]
            pending.loc[parsed.index[ok]] = False

    # Resto: formatos sueltos, ya sobre un puñado de filas.
    if pending.any():
        parsed = pd.to_datetime(text[pending], errors="coerce", dayfirst=True, format="mixed")
        ok = parsed.notna()
        if ok.any():
            out.loc[parsed.index[ok]] = parsed[ok]
            pending.loc[parsed.index[ok]] = False

    # Seriales de Excel (números plausibles como fecha).
    if pending.any():
        numeric = pd.to_numeric(series[pending], errors="coerce")
        serial = numeric.between(20000, 60000)
        if serial.any():
            idx = numeric.index[serial]
            out.loc[idx] = EXCEL_EPOCH + pd.to_timedelta(numeric[serial], unit="D")
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
def apply_types(frame: pd.DataFrame, field_spec: dict, null_tokens: set[str]) -> pd.DataFrame:
    out = frame.copy()
    for column in out.columns:
        spec = field_spec.get(column, {})
        kind = spec.get("type", "str")
        # Algunas columnas del origen traen estados escritos donde debería ir un
        # dato (p. ej. "Cancelada manual" en la tienda del quiebre). Se declaran
        # por campo en schema.yml y aquí se convierten en nulos.
        vacios = null_tokens | {str(v) for v in spec.get("null_values", [])}
        try:
            if kind in ("date", "datetime"):
                out[column] = clean_datetime(out[column])
            elif kind in ("float", "int"):
                out[column] = clean_number(out[column])
            else:
                out[column] = clean_text(out[column], vacios)
        except Exception:
            out[column] = clean_text(out[column].astype("string"), vacios)
    return out


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
