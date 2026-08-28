# -*- coding: utf-8 -*-
"""Contexto compartido por las secciones."""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import streamlit as st

from core import compare, filters
from core.compare import Periodo
from core.filters import FilterState
from core.transform import DataModel
from ui import components as c

#: Meses en español: strftime depende del locale del sistema y en Windows
#: devolvería abreviaturas en inglés.
_MESES = ("ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic")


def fecha_es(fecha) -> str:
    """Fecha corta en español: '26 ago 2026'."""
    if fecha is None:
        return "—"
    return f"{fecha.day:02d} {_MESES[fecha.month - 1]} {fecha.year}"


@dataclass
class Context:
    """Todo lo que una sección necesita: datos filtrados y su comparación."""

    model: DataModel
    state: FilterState
    periodo: Periodo = field(default_factory=Periodo)
    referencia: Periodo = field(default_factory=Periodo)
    modo_comparacion: str = "anterior"

    ordenes: pd.DataFrame = field(default_factory=pd.DataFrame)
    otif: pd.DataFrame = field(default_factory=pd.DataFrame)
    carrier: pd.DataFrame = field(default_factory=pd.DataFrame)
    quiebres: pd.DataFrame = field(default_factory=pd.DataFrame)
    #: Mismo universo de filtros, pero en la ventana de comparación.
    ordenes_ref: pd.DataFrame = field(default_factory=pd.DataFrame)
    otif_ref: pd.DataFrame = field(default_factory=pd.DataFrame)

    @classmethod
    def build(cls, model: DataModel, state: FilterState,
              modo: str = "anterior", personalizado: Periodo | None = None) -> "Context":
        periodo = Periodo(state.desde, state.hasta)
        referencia = compare.resolver(periodo, modo, personalizado)

        ctx = cls(model=model, state=state, periodo=periodo,
                  referencia=referencia, modo_comparacion=modo)
        ctx.ordenes = filters.aplicar(model.ordenes, state, "ordenes")
        ctx.otif = filters.aplicar(model.otif, state, "otif")
        ctx.carrier = filters.aplicar(model.carrier, state, "carrier")
        ctx.quiebres = filters.aplicar(model.quiebres, state, "quiebres")

        if referencia.valido:
            # Mismos filtros de dimensión, otra ventana de tiempo.
            sin_fecha = FilterState(
                desde=None, hasta=None, seleccion=state.seleccion, rangos=state.rangos,
                excluir_canceladas=state.excluir_canceladas,
                solo_lineas_unicas=state.solo_lineas_unicas, drill=state.drill)
            ctx.ordenes_ref = filters.aplicar(
                compare.recortar(model.ordenes, referencia), sin_fecha, "ordenes")
            ctx.otif_ref = filters.aplicar(
                compare.recortar(model.otif, referencia), sin_fecha, "otif")
        return ctx

    # -- utilidades ---------------------------------------------------------
    @property
    def etiqueta_ref(self) -> str:
        if not self.referencia.valido:
            return ""
        return {"anterior": "Per. ant.", "ly": "Año ant."}.get(
            self.modo_comparacion, "Referencia")

    @property
    def hay_comparacion(self) -> bool:
        return self.referencia.valido and not self.ordenes_ref.empty

    def meta(self) -> str:
        """Texto de contexto para la cabecera de sección."""
        partes = [self.periodo.texto()]
        if self.periodo.valido:
            partes.append(f"{self.periodo.dias} días")
        if not self.ordenes.empty and "orden" in self.ordenes:
            partes.append(f"{self.ordenes['orden'].nunique():,} pedidos".replace(",", " "))
        if self.referencia.valido:
            partes.append(f"vs {self.referencia.texto()}")
        return "  ·  ".join(partes)

    def chips(self) -> list[str]:
        return self.state.resumen_dimensiones()[:3]


def drill_selector(ctx: Context, dimension: str, valores: list[str]) -> None:
    """Baja el análisis a un valor concreto de una dimensión.

    Plotly no entrega eventos de clic de forma fiable en todas las versiones de
    Streamlit, así que el drill-down se ofrece como selector: mismo efecto y
    funciona siempre.
    """
    if not valores:
        return
    etiqueta = filters.DIMENSIONES.get(dimension, (dimension, dimension))[0]
    actual = ctx.state.drill.get(dimension, "— todos —")
    opciones = ["— todos —"] + [str(v) for v in valores]
    if actual not in opciones:
        opciones.insert(1, actual)
    elegido = st.selectbox(
        f"Profundizar en {etiqueta.lower()}", opciones, index=opciones.index(actual),
        key=f"drill_{dimension}", label_visibility="collapsed")
    if elegido != actual:
        drill = dict(ctx.state.drill)
        if elegido == "— todos —":
            drill.pop(dimension, None)
        else:
            drill[dimension] = elegido
        st.session_state["drill"] = drill
        st.rerun()


def contexto_periodo(ctx: Context) -> str:
    return ctx.meta()


def tabla_detalle(df: pd.DataFrame, columnas: dict[str, str], height: int = 420) -> None:
    """Tabla legible con nombres de negocio en lugar de nombres técnicos."""
    disponibles = {k: v for k, v in columnas.items() if k in df.columns}
    if df.empty or not disponibles:
        c.empty_state("Sin registros para el filtro actual")
        return
    st.dataframe(df[list(disponibles)].rename(columns=disponibles),
                 hide_index=True, width="stretch", height=height)
