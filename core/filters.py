# -*- coding: utf-8 -*-
"""Estado de filtros y su aplicación.

Un único `FilterState` se aplica a las cuatro tablas del modelo.  Como no todas
comparten las mismas dimensiones, cada filtro declara sobre qué columna actúa y
simplemente se omite donde esa columna no existe.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

#: Filtros categóricos ofrecidos en la barra lateral.
#: clave -> (etiqueta, columna en `ordenes`)
DIMENSIONES: dict[str, tuple[str, str]] = {
    "sitio": ("Sitio", "sitio"),
    "marca": ("Marca", "marca"),
    "estado": ("Estado del pedido", "estado"),
    "modalidad": ("Modalidad de entrega", "modalidad"),
    "tipo_modalidad": ("Tipo de modalidad", "tipo_modalidad"),
    "zona": ("Zona", "zona"),
    "departamento": ("Departamento", "departamento"),
    "tienda_asignada": ("Tienda", "tienda_asignada"),
    "operador_logistico": ("Operador logístico", "operador_logistico"),
    "metodo_pago": ("Medio de pago", "metodo_pago"),
    "origen_despacho": ("Origen de despacho", "origen_despacho"),
}

#: Equivalencias de columna en las tablas secundarias, para que un mismo filtro
#: se propague a OTIF, carrier y quiebres cuando allí existe la dimensión.
EQUIVALENCIAS: dict[str, dict[str, str]] = {
    "otif": {
        "sitio": "sitio", "marca": "marca", "modalidad": "modalidad",
        "zona": "zona", "departamento": "departamento",
        "tienda_asignada": "tienda_documenta", "operador_logistico": "op_logistico",
    },
    "carrier": {"departamento": "departamento"},
    "quiebres": {
        "sitio": "sitio", "marca": "marca", "modalidad": "modalidad",
        "tienda_asignada": "tienda_quiebre", "metodo_pago": "metodo_pago",
    },
}


@dataclass
class FilterState:
    desde: pd.Timestamp | None = None
    hasta: pd.Timestamp | None = None
    seleccion: dict[str, list[str]] = field(default_factory=dict)
    #: Filtros numéricos: columna -> (mínimo, máximo)
    rangos: dict[str, tuple[float, float]] = field(default_factory=dict)
    excluir_canceladas: bool = False
    solo_lineas_unicas: bool = False
    #: Selección puntual proveniente de un clic en un gráfico (drill-down).
    drill: dict[str, str] = field(default_factory=dict)

    # -- estado -------------------------------------------------------------
    @property
    def activos(self) -> dict[str, list[str]]:
        return {k: v for k, v in self.seleccion.items() if v}

    @property
    def n_activos(self) -> int:
        return (len(self.activos) + len(self.drill) + len(self.rangos)
                + int(self.excluir_canceladas) + int(self.solo_lineas_unicas))

    def resumen(self) -> list[str]:
        out = []
        if self.desde is not None and self.hasta is not None:
            out.append(f"{self.desde:%d/%m/%Y} – {self.hasta:%d/%m/%Y}")
        for key, values in self.activos.items():
            label = DIMENSIONES.get(key, (key, key))[0]
            texto = values[0] if len(values) == 1 else f"{len(values)} valores"
            out.append(f"{label}: {texto}")
        for key, value in self.drill.items():
            out.append(f"{DIMENSIONES.get(key, (key, key))[0]}: {value}")
        for key, (bajo, alto) in self.rangos.items():
            out.append(f"{key}: {bajo:,.0f}–{alto:,.0f}".replace(",", " "))
        if self.excluir_canceladas:
            out.append("sin canceladas")
        if self.solo_lineas_unicas:
            out.append("líneas únicas")
        return out

    def resumen_dimensiones(self) -> list[str]:
        """Como `resumen`, pero sin el rango de fechas: la cabecera ya lo muestra."""
        return [t for t in self.resumen() if "–" not in t or ":" in t]

    def con_drill(self, dimension: str, valor: str) -> "FilterState":
        nuevo = FilterState(
            desde=self.desde, hasta=self.hasta,
            seleccion=dict(self.seleccion), rangos=dict(self.rangos),
            excluir_canceladas=self.excluir_canceladas,
            solo_lineas_unicas=self.solo_lineas_unicas,
            drill=dict(self.drill),
        )
        nuevo.drill[dimension] = valor
        return nuevo


# ---------------------------------------------------------------------------
#  Aplicación
# ---------------------------------------------------------------------------
def _fecha_columna(tabla: str) -> str:
    return "fecha_solicitud" if tabla == "carrier" else "fecha_compra"


def aplicar(df: pd.DataFrame, state: FilterState, tabla: str = "ordenes") -> pd.DataFrame:
    """Devuelve el subconjunto que cumple el estado de filtros."""
    if df is None or df.empty:
        return df if df is not None else pd.DataFrame()

    mask = pd.Series(True, index=df.index)

    # -- rango de fechas
    columna_fecha = _fecha_columna(tabla)
    if columna_fecha in df and (state.desde is not None or state.hasta is not None):
        fecha = df[columna_fecha]
        if state.desde is not None:
            mask &= fecha >= state.desde
        if state.hasta is not None:
            mask &= fecha <= state.hasta + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
        mask &= fecha.notna()

    # -- dimensiones (incluye el drill-down, que es un filtro más)
    combinado: dict[str, list[str]] = {k: list(v) for k, v in state.activos.items()}
    for key, value in state.drill.items():
        combinado.setdefault(key, []).append(value)

    for key, values in combinado.items():
        columna = _resolver_columna(key, tabla)
        if not columna or columna not in df:
            continue
        mask &= df[columna].astype("string").isin([str(v) for v in values])

    # -- rangos numéricos (sólo donde la columna existe)
    for columna, (bajo, alto) in state.rangos.items():
        if columna not in df:
            continue
        valores = pd.to_numeric(df[columna], errors="coerce")
        mask &= valores.between(bajo, alto) | valores.isna()

    # -- banderas
    if state.excluir_canceladas and "es_cancelada" in df:
        mask &= ~df["es_cancelada"].fillna(False)
    if state.solo_lineas_unicas and "linea_unica" in df:
        mask &= df["linea_unica"].fillna(True)

    return df[mask]


def _resolver_columna(key: str, tabla: str) -> str | None:
    if tabla == "ordenes":
        return DIMENSIONES.get(key, (None, None))[1]
    return EQUIVALENCIAS.get(tabla, {}).get(key)


def opciones(df: pd.DataFrame, key: str) -> list[str]:
    """Valores disponibles para un filtro, ordenados por frecuencia."""
    columna = DIMENSIONES.get(key, (None, None))[1]
    if not columna or df.empty or columna not in df:
        return []
    serie = df[columna].dropna().astype("string")
    return serie.value_counts().index.tolist()
