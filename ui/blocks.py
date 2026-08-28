# -*- coding: utf-8 -*-
"""Preparación de datos para las secciones del reporte.

Aquí sólo se transforman DataFrames: no hay nada de Streamlit ni de gráficos,
de modo que cada bloque se puede probar por separado.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

MESES = {1: "Ene", 2: "Feb", 3: "Mar", 4: "Abr", 5: "May", 6: "Jun",
         7: "Jul", 8: "Ago", 9: "Sep", 10: "Oct", 11: "Nov", 12: "Dic"}


def anio(df: pd.DataFrame, atras: int) -> str:
    años = sorted(df["fecha_compra"].dt.year.dropna().unique(), reverse=True)
    return str(int(años[atras])) if len(años) > atras else "—"


def calendario(df: pd.DataFrame) -> pd.DataFrame:
    """Copia con mes y año en columnas propias, para agrupar sin colisiones."""
    base = df.dropna(subset=["fecha_compra"]).copy()
    base["_mes"] = base["fecha_compra"].dt.month
    base["_anio"] = base["fecha_compra"].dt.year
    return base


def por_mes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    base = calendario(df)
    out = base.groupby("_mes").agg(venta=("total", "sum")).reset_index()
    out["mes"] = out["_mes"].map(MESES)
    return out.sort_values("_mes")


def comparativo_anual(df: pd.DataFrame) -> pd.DataFrame | None:
    """Venta por mes con una columna por año; None si sólo hay un año."""
    if df.empty:
        return None
    base = calendario(df)
    if base["_anio"].nunique() < 2:
        return None
    out = base.groupby(["_mes", "_anio"])["total"].sum().reset_index()
    pivot = out.pivot(index="_mes", columns="_anio", values="total").fillna(0).reset_index()
    pivot["mes"] = pivot["_mes"].map(MESES)
    pivot.columns = [str(col) for col in pivot.columns]
    return pivot.sort_values("_mes").drop(columns=["_mes"])


def tabla_mensual(ordenes: pd.DataFrame) -> pd.DataFrame:
    validas = ordenes[~ordenes["es_cancelada"]] if "es_cancelada" in ordenes else ordenes
    if validas.empty:
        return pd.DataFrame()
    base = calendario(validas)
    años = sorted(base["_anio"].dropna().unique(), reverse=True)
    actual = años[0] if años else None
    previo = años[1] if len(años) > 1 else None

    resumen = (base[base["_anio"] == actual]
               .groupby("_mes").agg(venta_actual=("total", "sum"),
                                    ordenes=("orden", "nunique")).reset_index())
    if previo is not None:
        anterior = (base[base["_anio"] == previo].groupby("_mes")["total"]
                    .sum().rename("venta_previa"))
        resumen = resumen.merge(anterior, on="_mes", how="left")
    else:
        resumen["venta_previa"] = np.nan

    resumen["var_abs"] = resumen["venta_actual"] - resumen["venta_previa"]
    resumen["var_pct"] = resumen["var_abs"] / resumen["venta_previa"].replace(0, np.nan)
    resumen["ticket"] = resumen["venta_actual"] / resumen["ordenes"].replace(0, np.nan)
    resumen["mes"] = resumen["_mes"].map(MESES)
    return resumen.sort_values("_mes")


def resumen_modalidad(ordenes: pd.DataFrame) -> pd.DataFrame:
    if ordenes.empty or "modalidad" not in ordenes:
        return pd.DataFrame(columns=["modalidad", "ordenes", "participacion",
                                     "finalizadas", "exito", "ticket", "venta"])
    base = ordenes.dropna(subset=["modalidad"])
    out = base.groupby("modalidad").agg(
        ordenes=("orden", "nunique"),
        venta=("venta_neta", "sum") if "venta_neta" in base else ("total", "sum"),
    ).reset_index()
    if "es_finalizada" in base:
        fin = base[base["es_finalizada"]].groupby("modalidad")["orden"].nunique()
        out["finalizadas"] = out["modalidad"].map(fin).fillna(0)
        out["exito"] = out["finalizadas"] / out["ordenes"].replace(0, np.nan)
    out["participacion"] = out["ordenes"] / out["ordenes"].sum()
    out["ticket"] = out["venta"] / out["ordenes"].replace(0, np.nan)
    return out.sort_values("ordenes", ascending=False)


def evolucion_participacion(df: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if df.empty or "periodo_mes" not in df or dimension not in df:
        return pd.DataFrame()
    base = (df.groupby(["periodo_mes", dimension])["orden"].nunique()
            .reset_index(name="pedidos"))
    total = base.groupby("periodo_mes")["pedidos"].transform("sum")
    base["parte"] = base["pedidos"] / total
    return base.pivot(index="periodo_mes", columns=dimension, values="parte").fillna(0).reset_index()


def resumen_pago(ordenes: pd.DataFrame) -> pd.DataFrame:
    columnas = ["metodo_pago", "transacciones", "participacion", "venta",
                "ticket", "aprobacion", "cancelacion"]
    if ordenes.empty or "metodo_pago" not in ordenes:
        return pd.DataFrame(columns=columnas)
    base = ordenes.dropna(subset=["metodo_pago"])
    if base.empty:
        return pd.DataFrame(columns=columnas)
    validas = base[~base["es_cancelada"]] if "es_cancelada" in base else base
    out = validas.groupby("metodo_pago").agg(
        transacciones=("orden", "nunique"), venta=("total", "sum")).reset_index()
    out["participacion"] = out["transacciones"] / out["transacciones"].sum()
    out["ticket"] = out["venta"] / out["transacciones"].replace(0, np.nan)
    if "es_cancelada" in base:
        cancel = base.groupby("metodo_pago")["es_cancelada"].mean()
        out["cancelacion"] = out["metodo_pago"].map(cancel).fillna(0)
        out["aprobacion"] = 1 - out["cancelacion"]
    return out.sort_values("transacciones", ascending=False)


def tiempo_tienda(otif: pd.DataFrame, minimo: int = 10) -> pd.DataFrame:
    if otif.empty:
        return pd.DataFrame()
    dimension = "tienda_documenta" if "tienda_documenta" in otif else "tienda_despacha"
    if dimension not in otif or "t_doc_calendario" not in otif:
        return pd.DataFrame()
    base = otif.dropna(subset=[dimension, "t_doc_calendario"])
    if base.empty:
        return pd.DataFrame()
    grupo = base.groupby(dimension)["t_doc_calendario"]
    out = pd.DataFrame({"horas": grupo.median(), "pedidos": grupo.count()}).reset_index()
    out = out[out["pedidos"] >= minimo].rename(columns={dimension: "tienda"})
    return out.sort_values("horas", ascending=False)


def evolucion_documentado(ordenes: pd.DataFrame) -> pd.DataFrame:
    if "es_documentado" not in ordenes or "periodo_mes" not in ordenes:
        return pd.DataFrame()
    return (ordenes.groupby("periodo_mes")["es_documentado"]
            .mean().reset_index(name="documentado"))


def tabla_documentacion(ordenes: pd.DataFrame, otif: pd.DataFrame) -> pd.DataFrame:
    dimension = "tienda_asignada" if "tienda_asignada" in ordenes else "tienda_despacho"
    if dimension not in ordenes:
        return pd.DataFrame()
    base = ordenes.dropna(subset=[dimension])
    out = base.groupby(dimension).agg(
        ordenes=("orden", "nunique"), venta=("total", "sum")).reset_index()
    if "es_documentado" in base:
        doc = base[base["es_documentado"].fillna(False)].groupby(dimension)["orden"].nunique()
        out["documentados"] = out[dimension].map(doc).fillna(0)
        out["tasa"] = out["documentados"] / out["ordenes"].replace(0, np.nan)
    tiempos = tiempo_tienda(otif, minimo=1)
    if not tiempos.empty:
        out["horas"] = out[dimension].map(tiempos.set_index("tienda")["horas"])
    return out.rename(columns={dimension: "tienda"}).sort_values("ordenes", ascending=False)


def evolucion_quiebres(quiebres: pd.DataFrame) -> pd.DataFrame:
    if "fecha_compra" not in quiebres:
        return pd.DataFrame()
    base = quiebres.dropna(subset=["fecha_compra"]).copy()
    if base.empty:
        return pd.DataFrame()
    base["fecha"] = base["fecha_compra"].dt.strftime("%d/%m")
    out = base.groupby("fecha").size().reset_index(name="quiebres")
    if "estado" in base:
        recuperados = (base[base["estado"].astype("string").str.contains("tiempo", case=False, na=False)]
                       .groupby("fecha").size())
        out["recuperados"] = out["fecha"].map(recuperados).fillna(0)
    return out


def tabla_quiebres(quiebres: pd.DataFrame) -> pd.DataFrame:
    out = quiebres.copy()
    if "fecha_quiebre" in out:
        out["fecha_quiebre"] = out["fecha_quiebre"].dt.strftime("%d/%m/%Y")
    orden = "monto_sin_igv" if "monto_sin_igv" in out else "sku"
    return out.sort_values(orden, ascending=False)


def resumen_opl(ordenes: pd.DataFrame, carrier: pd.DataFrame) -> pd.DataFrame:
    base = ordenes.dropna(subset=["operador_logistico"])
    if base.empty:
        return pd.DataFrame()
    out = base.groupby("operador_logistico").agg(
        ordenes=("orden", "nunique"), venta=("total", "sum")).reset_index()
    out = out.rename(columns={"operador_logistico": "operador"})
    out["participacion"] = out["ordenes"] / out["ordenes"].sum()

    # El tracking sólo cubre a un operador; el On-Time se calcula por operador
    # a partir del cruce real, no repartiendo la tasa global entre todos.
    if not carrier.empty and "on_time_ok" in carrier and "orden" in carrier:
        seguimiento = carrier[["orden", "on_time_ok"]].dropna(subset=["orden"])
        enlace = (base[["orden", "operador_logistico"]].drop_duplicates()
                  .merge(seguimiento, on="orden", how="inner"))
        if not enlace.empty:
            grupo = enlace.groupby("operador_logistico")
            out["envios"] = out["operador"].map(grupo["orden"].nunique()).fillna(0)
            out["on_time"] = out["operador"].map(grupo["on_time_ok"].mean())
    return out.sort_values("ordenes", ascending=False)


def distribucion_otif(base: pd.DataFrame) -> pd.DataFrame:
    ot = base["on_time_ok"].fillna(False)
    inf = base["in_full_ok"].fillna(False)
    grupos = np.select(
        [ot & inf, ot & ~inf, ~ot & inf],
        ["OTIF", "Sólo OT", "Sólo IF"], default="Ninguno")
    return (pd.Series(grupos).value_counts().reset_index()
            .set_axis(["grupo", "pedidos"], axis=1))


def tabla_otif(base: pd.DataFrame, dimension: str) -> pd.DataFrame:
    if dimension not in base:
        return pd.DataFrame()
    datos = base.dropna(subset=[dimension])
    out = datos.groupby(dimension).agg(ordenes=("orden", "nunique")).reset_index()
    for columna, nombre in (("on_time_ok", "on_time"), ("in_full_ok", "in_full"), ("otif_ok", "otif")):
        if columna in datos:
            conteo = datos[datos[columna].fillna(False)].groupby(dimension)["orden"].nunique()
            out[nombre] = out[dimension].map(conteo).fillna(0)
    out["no_ot"] = out["ordenes"] - out.get("on_time", 0)
    out["no_if"] = out["ordenes"] - out.get("in_full", 0)
    out["pct_otif"] = out.get("otif", 0) / out["ordenes"].replace(0, np.nan)
    return out.sort_values("ordenes", ascending=False)


def flujo(ordenes: pd.DataFrame, carrier: pd.DataFrame) -> dict[str, int]:
    if ordenes.empty:
        return {}
    out = {"Recibidos": int(ordenes["orden"].nunique())}
    if "es_documentado" in ordenes:
        out["Procesados"] = int(ordenes[ordenes["es_documentado"].fillna(False)]["orden"].nunique())
    if "fecha_empaque" in ordenes:
        out["Despachados"] = int(ordenes[ordenes["fecha_empaque"].notna()]["orden"].nunique())
    if "es_finalizada" in ordenes:
        out["Entregados"] = int(ordenes[ordenes["es_finalizada"]]["orden"].nunique())
    return out


def flujo_mensual(ordenes: pd.DataFrame) -> pd.DataFrame:
    if "periodo_mes" not in ordenes:
        return pd.DataFrame()
    out = (ordenes.groupby("periodo_mes")["orden"].nunique().reset_index(name="Recibidos"))
    if "es_documentado" in ordenes:
        serie = (ordenes[ordenes["es_documentado"].fillna(False)]
                 .groupby("periodo_mes")["orden"].nunique())
        out["Procesados"] = out["periodo_mes"].map(serie).fillna(0)
    if "fecha_empaque" in ordenes:
        serie = (ordenes[ordenes["fecha_empaque"].notna()]
                 .groupby("periodo_mes")["orden"].nunique())
        out["Despachados"] = out["periodo_mes"].map(serie).fillna(0)
    if "es_finalizada" in ordenes:
        serie = ordenes[ordenes["es_finalizada"]].groupby("periodo_mes")["orden"].nunique()
        out["Entregados"] = out["periodo_mes"].map(serie).fillna(0)
    return out


def tabla_flujo(ordenes: pd.DataFrame) -> pd.DataFrame:
    dimension = "tienda_asignada" if "tienda_asignada" in ordenes else "tienda_despacho"
    if dimension not in ordenes:
        return pd.DataFrame()
    base = ordenes.dropna(subset=[dimension])
    out = base.groupby(dimension)["orden"].nunique().reset_index(name="recibidos")
    for columna, nombre, condicion in (
        ("es_documentado", "procesados", lambda d: d["es_documentado"].fillna(False)),
        ("fecha_empaque", "despachados", lambda d: d["fecha_empaque"].notna()),
        ("es_finalizada", "entregados", lambda d: d["es_finalizada"]),
    ):
        if columna in base:
            serie = base[condicion(base)].groupby(dimension)["orden"].nunique()
            out[nombre] = out[dimension].map(serie).fillna(0)
    if "procesados" in out:
        out["pct_proceso"] = out["procesados"] / out["recibidos"].replace(0, np.nan)
    if "entregados" in out:
        out["pct_entrega"] = out["entregados"] / out["recibidos"].replace(0, np.nan)
    return out.rename(columns={dimension: "centro"}).sort_values("recibidos", ascending=False)
