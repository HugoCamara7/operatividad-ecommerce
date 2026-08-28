# -*- coding: utf-8 -*-
"""Secciones del Operatividad Control Center.

Seis vistas, cada una con la misma gramática: indicadores comparados contra el
período de referencia, gráficos que responden una pregunta y una tabla de apoyo.
La preparación de datos vive en `ui/blocks.py`; aquí sólo se compone la pantalla.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from core import kpis
from core.compare import Medida
from ui import blocks, charts, components as c
from ui.helpers import drill_selector
from ui.theme import ACCENT, CYAN, GREEN, NAVY, RED


def _cab(ctx, titulo: str) -> None:
    c.section_header(titulo, ctx.meta(), ctx.chips())


def _serie_spark(ordenes: pd.DataFrame, puntos: int = 30) -> dict[str, list]:
    """Mini series para las tarjetas, agrupadas para no dibujar ruido."""
    serie = kpis.serie_temporal(ordenes, "D")
    if serie.empty:
        return {}
    salida: dict[str, list] = {}
    for columna in ("venta", "ordenes", "ticket", "tasa_cancelacion"):
        if columna not in serie:
            continue
        valores = serie[columna].dropna()
        if len(valores) < 3:
            continue
        if len(valores) > puntos:
            grupos = np.array_split(valores.to_numpy(), puntos)
            valores = pd.Series([float(np.mean(g)) for g in grupos if len(g)])
        salida[columna] = valores.tolist()
    return salida


# ===========================================================================
#  RESUMEN
# ===========================================================================
def resumen(ctx) -> None:
    _cab(ctx, "Resumen ejecutivo")
    ordenes = ctx.ordenes
    if ordenes.empty:
        c.empty_state("Sin pedidos en el período", "Amplíe el rango o quite filtros.")
        return

    act = kpis.ventas(ordenes)
    ref = kpis.ventas(ctx.ordenes_ref)
    cal = kpis.calidad_operativa(ordenes)
    cal_ref = kpis.calidad_operativa(ctx.ordenes_ref)
    sem = ctx.model.business.get("semaforos", {})
    chispa = _serie_spark(ordenes)

    c.kpi_medidas([
        Medida("venta", "Ventas", act.get("venta"), ref.get("venta"), "money", icono="💰"),
        Medida("ordenes", "Órdenes", act.get("ordenes"), ref.get("ordenes"), "num", icono="🧾"),
        Medida("ticket", "Ticket promedio", act.get("ticket"), ref.get("ticket"), "money", icono="🏷️"),
        Medida("cancelacion", "Tasa cancelación", cal.get("tasa_cancelacion"),
               cal_ref.get("tasa_cancelacion"), "pct", invertido=True, icono="⛔"),
    ], ctx.etiqueta_ref, chispa)

    st.write("")
    fila = [
        Medida("unidades", "Unidades", act.get("unidades"), ref.get("unidades"), "num", icono="📦"),
        Medida("perdida", "Venta perdida", cal.get("venta_perdida"),
               cal_ref.get("venta_perdida"), "money", invertido=True, icono="💸"),
        Medida("doc", "Documentado", cal.get("tasa_documentado"),
               cal_ref.get("tasa_documentado"), "pct", icono="📄"),
    ]
    if not ctx.otif.empty:
        ind, ind_ref = kpis.otif(ctx.otif), kpis.otif(ctx.otif_ref)
        fila.append(Medida("otif", "OTIF", ind.get("otif"), ind_ref.get("otif"), "pct", icono="🏆"))
    else:
        fila.append(Medida("backlog", "En proceso", cal.get("backlog"), None, "num", icono="⏳"))
    c.kpi_medidas(fila, ctx.etiqueta_ref)

    # -- evolución ----------------------------------------------------------
    c.section_label("Evolución del negocio")
    izq, der = st.columns([2.1, 1], gap="small")
    with izq:
        c.panel_open("Venta diaria", "Área: venta del día · punteada: media móvil de 7 días")
        validas = ordenes[~ordenes["es_cancelada"]] if "es_cancelada" in ordenes else ordenes
        st.plotly_chart(
            charts.tendencia(kpis.serie_temporal(validas, "D"), "periodo", "venta",
                             "Venta", "money", 268, media_movil=7),
            width="stretch", config=charts.CONFIG)
        c.panel_close()
    with der:
        c.panel_open("Cierre de pedidos", "Estado final del período")
        estados = (ordenes.groupby("grupo_estado")["orden"].nunique()
                   .reset_index(name="pedidos").sort_values("pedidos", ascending=False))
        st.plotly_chart(
            charts.dona(estados, "grupo_estado", "pedidos", 268, "órdenes",
                        c.fmt(act.get("ordenes"))),
            width="stretch", config=charts.CONFIG)
        c.panel_close()

    # -- flujo y cumplimiento ----------------------------------------------
    c.section_label("Flujo y cumplimiento")
    col1, col2, col3 = st.columns([1.2, 1, 1], gap="small")
    with col1:
        c.panel_open("Embudo del pedido", "De la compra a la entrega")
        etapas = blocks.flujo(ordenes, ctx.carrier)
        st.plotly_chart(charts.embudo(list(etapas), list(etapas.values()), 250),
                        width="stretch", config=charts.CONFIG)
        c.panel_close()
    with col2:
        c.panel_open("Cumplimiento", "Contra la meta configurada")
        if not ctx.otif.empty:
            regla = sem.get("otif", {})
            st.plotly_chart(
                charts.gauge(kpis.otif(ctx.otif).get("otif"), "OTIF global",
                             regla.get("bueno", 0.9), regla.get("alerta", 0.8), 200),
                width="stretch", config=charts.CONFIG)
        else:
            regla = sem.get("tasa_cancelacion", {})
            st.plotly_chart(
                charts.gauge(cal.get("tasa_cancelacion"), "Cancelación",
                             regla.get("bueno", .08), regla.get("alerta", .15), 200,
                             invertido=True, maximo=0.35),
                width="stretch", config=charts.CONFIG)
        c.panel_close()
    with col3:
        c.panel_open("Origen del despacho", "Centro de distribución frente a tienda")
        if "origen_despacho" in ordenes:
            origen = (ordenes.groupby("origen_despacho")["orden"]
                      .nunique().reset_index(name="pedidos"))
            st.plotly_chart(charts.dona(origen, "origen_despacho", "pedidos", 250),
                            width="stretch", config=charts.CONFIG)
        else:
            c.empty_state("Sin tienda asignada")
        c.panel_close()

    # -- concentración ------------------------------------------------------
    c.section_label("Dónde se concentra el negocio")
    izq, der = st.columns(2, gap="small")
    validas = ordenes[~ordenes["es_cancelada"]] if "es_cancelada" in ordenes else ordenes
    with izq:
        c.panel_open("Top sitios por venta")
        top = kpis.ranking(validas, "sitio", "venta", 8)
        st.plotly_chart(charts.barras_horizontales(top, "sitio", "venta", "money", 260),
                        width="stretch", config=charts.CONFIG)
        drill_selector(ctx, "sitio", top["sitio"].tolist() if not top.empty else [])
        c.panel_close()
    with der:
        c.panel_open("Top tiendas por pedidos")
        dim = "tienda_asignada" if "tienda_asignada" in ordenes else "sitio"
        top_t = kpis.ranking(ordenes, dim, "ordenes", 8)
        st.plotly_chart(charts.barras_horizontales(top_t, dim, "ordenes", "num", 260, NAVY),
                        width="stretch", config=charts.CONFIG)
        drill_selector(ctx, dim, top_t[dim].tolist() if not top_t.empty else [])
        c.panel_close()

    _lectura(ctx, act, cal)


def _lectura(ctx, act: dict, cal: dict) -> None:
    frases = []
    validas = ctx.ordenes[~ctx.ordenes["es_cancelada"]] if "es_cancelada" in ctx.ordenes else ctx.ordenes
    top = kpis.ranking(validas, "sitio", "venta", 1)
    if not top.empty:
        parte = top.iloc[0]["venta"] / max(act.get("venta", 1), 1)
        frases.append(f"<b>{top.iloc[0]['sitio']}</b> concentra el <b>{parte*100:.0f}%</b> de la venta")
    if cal.get("tasa_cancelacion"):
        frases.append(f"se cancela <b>{cal['tasa_cancelacion']*100:.1f}%</b> de los pedidos "
                      f"(<b>{c.fmt(cal.get('venta_perdida'), 'money')}</b>)")
    if not ctx.otif.empty:
        ind = kpis.otif(ctx.otif)
        if ind.get("con_demora"):
            resp = ("el operador logístico" if ind.get("demora_logistica", 0) >= ind.get("demora_tienda", 0)
                    else "la tienda")
            peso = max(ind.get("demora_logistica", 0), ind.get("demora_tienda", 0))
            frases.append(f"en los retrasos, <b>{resp}</b> explica el <b>{peso*100:.0f}%</b>")
    if frases:
        st.write("")
        c.note("En este período " + "; ".join(frases) + ".")


# ===========================================================================
#  OPERATIVIDAD
# ===========================================================================
def operatividad(ctx) -> None:
    _cab(ctx, "Operatividad")
    ordenes, otif = ctx.ordenes, ctx.otif
    if ordenes.empty:
        c.empty_state("Sin pedidos en el período")
        return

    cal = kpis.calidad_operativa(ordenes)
    cal_ref = kpis.calidad_operativa(ctx.ordenes_ref)
    ind = kpis.otif(otif) if not otif.empty else {}
    ind_ref = kpis.otif(ctx.otif_ref) if not ctx.otif_ref.empty else {}
    sem = ctx.model.business.get("semaforos", {})

    medidas = [
        Medida("doc", "Documentado", cal.get("tasa_documentado"),
               cal_ref.get("tasa_documentado"), "pct", icono="📄"),
        Medida("otif", "OTIF", ind.get("otif"), ind_ref.get("otif"), "pct", icono="🏆"),
        Medida("ot", "On Time", ind.get("on_time"), ind_ref.get("on_time"), "pct", icono="⏰"),
        Medida("if", "In Full", ind.get("in_full"), ind_ref.get("in_full"), "pct", icono="📦"),
    ]
    c.kpi_medidas(medidas, ctx.etiqueta_ref)

    # -- semáforos ----------------------------------------------------------
    c.section_label("Semáforos de cumplimiento")
    metas = [("otif", "OTIF", ind.get("otif")), ("on_time", "On Time", ind.get("on_time")),
             ("in_full", "In Full", ind.get("in_full")),
             ("documentado", "Documentado", cal.get("tasa_documentado"))]
    for col, (clave, titulo, valor) in zip(st.columns(4, gap="small"), metas):
        regla = sem.get(clave, {})
        with col:
            c.panel_open(titulo)
            st.plotly_chart(
                charts.gauge(valor, f"meta {regla.get('bueno', .9):.0%}",
                             regla.get("bueno", .9), regla.get("alerta", .8), 165),
                width="stretch", config=charts.CONFIG)
            c.panel_close()

    # -- modalidad ----------------------------------------------------------
    c.section_label("Modalidad de entrega")
    izq, der = st.columns([1, 1.5], gap="small")
    resumen_mod = blocks.resumen_modalidad(ordenes)
    with izq:
        c.panel_open("Despacho vs. Retiro")
        st.plotly_chart(
            charts.dona(resumen_mod, "modalidad", "ordenes", 240, "órdenes",
                        c.fmt(cal.get("ordenes"))),
            width="stretch", config=charts.CONFIG)
        c.panel_close()
    with der:
        c.panel_open("Evolución mensual del mix")
        evo = blocks.evolucion_participacion(ordenes, "modalidad")
        st.plotly_chart(
            charts.lineas_multiples(evo, "periodo_mes",
                                    {k: k for k in evo.columns if k != "periodo_mes"}, "pct", 240),
            width="stretch", config=charts.CONFIG)
        c.panel_close()
    c.tabla(resumen_mod, [
        ("modalidad", "Modalidad", "key"), ("ordenes", "Órdenes", "num"),
        ("participacion", "% Total", "pct"), ("finalizadas", "Finalizadas", "num"),
        ("exito", "% Éxito", "pct"), ("ticket", "Ticket Prom.", "money"),
        ("venta", "Venta", "money"),
    ], total={"modalidad": "Total", "ordenes": float(resumen_mod["ordenes"].sum()),
              "venta": float(resumen_mod["venta"].sum())}, barra="ordenes")

    # -- logística ----------------------------------------------------------
    c.section_label("Logística y operador")
    izq, der = st.columns([1, 1.35], gap="small")
    resumen_opl = blocks.resumen_opl(ordenes, ctx.carrier)
    with izq:
        c.panel_open("Participación por operador")
        if not resumen_opl.empty:
            st.plotly_chart(
                charts.dona(resumen_opl, "operador", "ordenes", 250, "pedidos",
                            c.fmt(resumen_opl["ordenes"].sum())),
                width="stretch", config=charts.CONFIG)
        else:
            c.empty_state("Sin operador logístico")
        c.panel_close()
    with der:
        c.panel_open("¿Quién causa el retraso?", "Responsable principal en pedidos con demora")
        if ind.get("con_demora"):
            resp = otif["responsable_demora"].dropna()
            resp = resp[resp.astype(str).str.strip() != ""]
            dist = resp.value_counts().reset_index()
            dist.columns = ["responsable", "pedidos"]
            st.plotly_chart(
                charts.dona(dist, "responsable", "pedidos", 250, "con demora",
                            c.fmt(ind.get("con_demora"))),
                width="stretch", config=charts.CONFIG)
        else:
            c.empty_state("Sin datos de responsable en este período")
        c.panel_close()

    if not resumen_opl.empty:
        c.tabla(resumen_opl, [
            ("operador", "Operador logístico", "key"), ("ordenes", "Pedidos", "num"),
            ("participacion", "% Pedidos", "pct"), ("envios", "Con tracking", "num"),
            ("on_time", "% On-Time", "pct"), ("venta", "Venta", "money"),
        ], barra="ordenes")

    # -- OTIF por dimensión -------------------------------------------------
    if not otif.empty:
        c.section_label("OTIF por dimensión")
        meta = sem.get("otif", {}).get("bueno", 0.9)
        pestanas = st.tabs(["Modalidad", "Tienda", "Departamento", "Operador"])
        for pestana, (columna, etiqueta, minimo) in zip(pestanas, [
                ("modalidad", "modalidad", 5), ("tienda_documenta", "tienda", 15),
                ("departamento", "departamento", 15), ("op_logistico", "operador", 5)]):
            with pestana:
                datos = kpis.tasa_por_dimension(otif, columna, "otif_ok", minimo)
                if datos.empty:
                    c.empty_state(f"Sin grupos con al menos {minimo} pedidos")
                    continue
                izq, der = st.columns([1.2, 1], gap="small")
                with izq:
                    st.plotly_chart(
                        charts.barras_desvio(datos.head(14), columna, "tasa", meta, "pct", 320),
                        width="stretch", config=charts.CONFIG)
                with der:
                    vista = datos.copy()
                    c.tabla(vista.head(14), [
                        (columna, etiqueta.title(), "key"),
                        ("tasa", "OTIF", "pct"), ("casos", "Pedidos", "num")], barra="casos")


# ===========================================================================
#  TIENDAS
# ===========================================================================
def tiendas(ctx) -> None:
    _cab(ctx, "Tiendas")
    ordenes, otif = ctx.ordenes, ctx.otif
    dim = "tienda_asignada" if "tienda_asignada" in ordenes else "tienda_despacho"
    if ordenes.empty or dim not in ordenes:
        c.empty_state("Sin datos de tienda en el período")
        return

    activas = ordenes[dim].nunique()
    flujo_tiendas = blocks.tabla_flujo(ordenes)
    cal = kpis.calidad_operativa(ordenes)
    ranking = kpis.ranking(ordenes, dim, "ordenes", 500)
    lider = ranking.iloc[0] if not ranking.empty else None
    concentracion = (ranking.head(5)["ordenes"].sum() / ranking["ordenes"].sum()
                     if not ranking.empty else None)

    c.kpi_row([
        dict(label="Tiendas activas", value=activas, kind="num", icon="🏬"),
        dict(label="Tienda líder", value=lider["ordenes"] if lider is not None else None,
             kind="num", icon="🥇", sub=str(lider[dim]) if lider is not None else ""),
        dict(label="Concentración top 5", value=concentracion, kind="pct", icon="🎯",
             sub="de los pedidos"),
        dict(label="Cancelación media", value=cal.get("tasa_cancelacion"), kind="pct",
             icon="⛔", invertido=True,
             sem=kpis.semaforo(cal.get("tasa_cancelacion"),
                               ctx.model.business.get("semaforos", {}).get("tasa_cancelacion"))),
    ])

    c.section_label("Ranking y desempeño")
    izq, der = st.columns([1, 1.2], gap="small")
    with izq:
        c.panel_open("Top 15 tiendas por pedidos")
        st.plotly_chart(
            charts.barras_horizontales(ranking.head(15), dim, "ordenes", "num", 380, NAVY),
            width="stretch", config=charts.CONFIG)
        drill_selector(ctx, dim, ranking.head(15)[dim].tolist())
        c.panel_close()
    with der:
        c.panel_open("Volumen frente a cancelación",
                     "Abajo a la derecha: mucho volumen y mucha cancelación")
        if "tasa_cancelacion" in ranking:
            media = float(ordenes["es_cancelada"].mean())
            nube = ranking.head(60).rename(columns={"tasa_cancelacion": "cancelacion"})
            st.plotly_chart(
                charts.dispersion(nube, "ordenes", "cancelacion", "venta", dim,
                                  380, "num", "pct", ref_y=media),
                width="stretch", config=charts.CONFIG)
            c.note(f"Los puntos <b>rojos</b> cancelan por encima del promedio "
                   f"(<b>{media*100:.1f}%</b>). El tamaño es la venta: priorice "
                   f"los grandes y rojos.")
        c.panel_close()

    # -- Top / Bottom -------------------------------------------------------
    c.section_label("Top y Bottom por venta")
    izq, der = st.columns(2, gap="small")
    with izq:
        c.panel_open("Mejores 8", "Por venta del período")
        top = kpis.ranking(ordenes, dim, "venta", 8)
        st.plotly_chart(charts.barras_horizontales(top, dim, "venta", "money", 250, GREEN),
                        width="stretch", config=charts.CONFIG)
        c.panel_close()
    with der:
        c.panel_open("Menores 8", "Con al menos un pedido en el período")
        bottom = kpis.ranking(ordenes, dim, "venta", 8, ascendente=True)
        st.plotly_chart(charts.barras_horizontales(bottom, dim, "venta", "money", 250, RED),
                        width="stretch", config=charts.CONFIG)
        c.panel_close()

    # -- tiempos ------------------------------------------------------------
    if not otif.empty:
        c.section_label("Tiempos de documentación")
        lentas = blocks.tiempo_tienda(otif)
        if not lentas.empty:
            c.panel_open("Tiendas más lentas en documentar",
                         "Mediana de horas · sólo tiendas con 10 o más pedidos")
            st.plotly_chart(
                charts.barras_horizontales(lentas.head(14), "tienda", "horas", "hours", 300, ACCENT),
                width="stretch", config=charts.CONFIG)
            c.panel_close()

    c.section_label("Detalle por tienda")
    c.tabla(flujo_tiendas, [
        ("centro", "Tienda / Centro", "key"), ("recibidos", "Recibidos", "num"),
        ("procesados", "Procesados", "num"), ("despachados", "Despachados", "num"),
        ("entregados", "Entregados", "num"), ("pct_proceso", "% Proceso", "pct"),
        ("pct_entrega", "% Entrega", "pct"),
    ], barra="recibidos", max_filas=30)


# ===========================================================================
#  PRODUCTOS
# ===========================================================================
def productos(ctx) -> None:
    _cab(ctx, "Productos")
    ordenes, quiebres = ctx.ordenes, ctx.quiebres
    if ordenes.empty or "sku" not in ordenes:
        c.empty_state("Sin datos de producto en el período")
        return

    validas = ordenes[~ordenes["es_cancelada"]] if "es_cancelada" in ordenes else ordenes
    act = kpis.ventas(ordenes)
    ref = kpis.ventas(ctx.ordenes_ref)
    ind_q = kpis.quiebres(quiebres, ordenes) if not quiebres.empty else {}

    c.kpi_medidas([
        Medida("skus", "SKU vendidos", validas["sku"].nunique(),
               ctx.ordenes_ref["sku"].nunique() if not ctx.ordenes_ref.empty else None,
               "num", icono="🔖"),
        Medida("unidades", "Unidades", act.get("unidades"), ref.get("unidades"), "num", icono="📦"),
        Medida("precio", "Precio medio", act.get("precio_medio"),
               ref.get("precio_medio"), "money", icono="🏷️"),
        Medida("upo", "Uds. por pedido", act.get("unidades_por_orden"),
               ref.get("unidades_por_orden"), "num2", icono="🧮"),
    ], ctx.etiqueta_ref)

    # -- ranking ------------------------------------------------------------
    c.section_label("Qué se vende")
    dim = "nombre_producto" if "nombre_producto" in validas else "sku"
    agg = {"orden": "nunique", "total": "sum"}
    if "unidades" in validas:
        agg["unidades"] = "sum"
    top = (validas.dropna(subset=[dim]).groupby(dim).agg(agg).reset_index()
           .rename(columns={"orden": "pedidos", "total": "venta"})
           .sort_values("venta", ascending=False))

    izq, der = st.columns([1, 1], gap="small")
    with izq:
        c.panel_open("Top 12 productos por venta")
        st.plotly_chart(charts.barras_horizontales(top.head(12), dim, "venta", "money", 340),
                        width="stretch", config=charts.CONFIG)
        c.panel_close()
    with der:
        c.panel_open("Venta por marca")
        if "marca" in validas:
            marca = kpis.ranking(validas, "marca", "venta", 12)
            st.plotly_chart(
                charts.barras_horizontales(marca, "marca", "venta", "money", 340, NAVY),
                width="stretch", config=charts.CONFIG)
            drill_selector(ctx, "marca", marca["marca"].tolist() if not marca.empty else [])
        c.panel_close()

    c.tabla(top.head(25), [
        (dim, "Producto", "key"), ("venta", "Venta", "money"),
        ("pedidos", "Pedidos", "num"), ("unidades", "Unidades", "num"),
    ], barra="venta", max_filas=25)

    # -- quiebres -----------------------------------------------------------
    c.section_label("Quiebres de stock")
    if quiebres.empty:
        c.empty_state("Sin quiebres registrados en este período",
                      "Esta base cubre un rango de fechas más corto que el maestro.")
        return

    c.kpi_row([
        dict(label="Quiebres", value=ind_q.get("quiebres"), kind="num", icon="⚠️",
             sub=f"{c.fmt(ind_q.get('skus_afectados'))} SKU"),
        dict(label="Tasa de quiebre", value=ind_q.get("tasa_quiebre"), kind="pct",
             icon="📉", invertido=True, sub="sobre órdenes"),
        dict(label="Venta perdida", value=ind_q.get("monto_perdido"), kind="money",
             icon="💸", sub="sin IGV"),
        dict(label="Tiempo de gestión", value=ind_q.get("tiempo_total"), kind="days",
             icon="🔁", sub="mediana hasta resolver"),
    ])

    izq, der = st.columns([1.4, 1], gap="small")
    with izq:
        c.panel_open("Evolución de quiebres")
        evo = blocks.evolucion_quiebres(quiebres)
        if not evo.empty:
            fig = charts.lineas_multiples(
                evo, "fecha", {"quiebres": "Quiebres", "recuperados": "Recuperados"}, "num", 250)
            fig.data[0].line.color = RED
            fig.data[0].marker.color = RED
            if len(fig.data) > 1:
                fig.data[1].line.color = NAVY
                fig.data[1].marker.color = NAVY
            st.plotly_chart(fig, width="stretch", config=charts.CONFIG)
        c.panel_close()
    with der:
        c.panel_open("Quiebres por marca")
        if "marca" in quiebres:
            por_marca = (quiebres.groupby("marca").size().reset_index(name="casos")
                         .sort_values("casos", ascending=False).head(8))
            st.plotly_chart(
                charts.barras_horizontales(por_marca, "marca", "casos", "num", 250, ACCENT),
                width="stretch", config=charts.CONFIG)
        c.panel_close()

    c.tabla(blocks.tabla_quiebres(quiebres), [
        ("sku", "SKU", "key"), ("marca", "Marca", "text"),
        ("tienda_quiebre", "Tienda", "text"), ("status_quiebre", "Status", "text"),
        ("dias_tienda", "Días tienda", "num2"),
        ("monto_sin_igv", "Venta perdida", "money"),
    ], barra="monto_sin_igv", max_filas=25)


# ===========================================================================
#  COMPARATIVOS
# ===========================================================================
def comparativos(ctx) -> None:
    _cab(ctx, "Comparativos")
    ordenes = ctx.ordenes
    if ordenes.empty:
        c.empty_state("Sin pedidos en el período")
        return

    if not ctx.hay_comparacion:
        c.note("No hay un período de comparación activo. Elija <b>Período anterior</b> o "
               "<b>Mismo período año anterior</b> en la barra de filtros para ver las "
               "diferencias lado a lado.")
        st.write("")

    # -- tabla comparativa --------------------------------------------------
    c.section_label(f"Actual frente a {ctx.etiqueta_ref or 'referencia'}")
    comparacion = _tabla_comparativa(ctx)
    c.tabla(comparacion, [
        ("indicador", "Indicador", "key"),
        ("actual_txt", "Actual", "text"),
        ("ref_txt", ctx.etiqueta_ref or "Referencia", "text"),
        ("dif_txt", "Diferencia", "text"),
        ("var", "Variación %", "signed_pct"),
    ], max_filas=20)

    # -- evolución mensual --------------------------------------------------
    c.section_label("Evolución mensual")
    validas = ordenes[~ordenes["es_cancelada"]] if "es_cancelada" in ordenes else ordenes
    izq, der = st.columns([1.6, 1], gap="small")
    with izq:
        c.panel_open("Ventas mensuales — comparativo anual")
        anual = blocks.comparativo_anual(validas)
        if anual is not None and len(anual.columns) > 1:
            series = {col: str(col) for col in anual.columns if col != "mes"}
            st.plotly_chart(charts.barras_comparadas(anual, "mes", series, "money", 280),
                            width="stretch", config=charts.CONFIG)
        else:
            st.plotly_chart(
                charts.barras_comparadas(blocks.por_mes(validas), "mes",
                                         {"venta": "Ventas"}, "money", 280),
                width="stretch", config=charts.CONFIG)
        c.panel_close()
    with der:
        c.panel_open("Ticket promedio mensual")
        # Barras por mes: con pocos meses un eje de fechas rotularía días.
        mensual = blocks.calendario(validas)
        ticket = (mensual.groupby("_mes")
                  .agg(venta=("total", "sum"), ordenes=("orden", "nunique")).reset_index())
        ticket["ticket"] = ticket["venta"] / ticket["ordenes"].replace(0, np.nan)
        ticket["mes"] = ticket["_mes"].map(blocks.MESES)
        st.plotly_chart(
            charts.barras_comparadas(ticket.sort_values("_mes"), "mes",
                                     {"ticket": "Ticket promedio"}, "money", 280),
            width="stretch", config=charts.CONFIG)
        c.panel_close()

    c.tabla(blocks.tabla_mensual(ordenes), [
        ("mes", "Mes", "key"),
        ("venta_actual", f"Ventas {blocks.anio(ordenes, 0)}", "money"),
        ("venta_previa", f"Ventas {blocks.anio(ordenes, 1)}", "money"),
        ("var_abs", "Var. S/", "signed"), ("var_pct", "Var. %", "signed_pct"),
        ("ordenes", "Órdenes", "num"), ("ticket", "Ticket promedio", "money"),
    ])

    # -- por dimensión ------------------------------------------------------
    c.section_label("Variación por dimensión")
    dimension = st.radio("Dimensión", ["Sitio", "Marca", "Modalidad", "Departamento"],
                         horizontal=True, label_visibility="collapsed", key="cmp_dim")
    columna = {"Sitio": "sitio", "Marca": "marca",
               "Modalidad": "modalidad", "Departamento": "departamento"}[dimension]
    detalle = _comparativo_dimension(ctx, columna)
    if detalle.empty:
        c.empty_state("Sin comparación disponible para esta dimensión")
        return

    izq, der = st.columns([1, 1.25], gap="small")
    with izq:
        c.panel_open(f"Venta actual por {dimension.lower()}")
        st.plotly_chart(
            charts.barras_horizontales(detalle.head(12), columna, "venta_actual", "money", 320),
            width="stretch", config=charts.CONFIG)
        c.panel_close()
    with der:
        c.panel_open(f"Variación frente a {ctx.etiqueta_ref or 'referencia'}",
                     "Verde: crece · rojo: cae")
        grafico = detalle.dropna(subset=["var"]).head(12)
        if not grafico.empty:
            st.plotly_chart(
                charts.barras_desvio(grafico, columna, "var", 0.0, "pct", 320),
                width="stretch", config=charts.CONFIG)
        else:
            c.empty_state("Sin variación calculable")
        c.panel_close()

    c.tabla(detalle, [
        (columna, dimension, "key"),
        ("venta_actual", "Venta actual", "money"),
        ("venta_ref", f"Venta {ctx.etiqueta_ref or 'ref.'}", "money"),
        ("dif", "Diferencia", "signed"), ("var", "Variación %", "signed_pct"),
        ("ordenes_actual", "Órdenes", "num"),
    ], max_filas=25)


def _tabla_comparativa(ctx) -> pd.DataFrame:
    """Indicadores clave con su referencia, diferencia y variación."""
    act = kpis.ventas(ctx.ordenes)
    ref = kpis.ventas(ctx.ordenes_ref)
    cal = kpis.calidad_operativa(ctx.ordenes)
    cal_ref = kpis.calidad_operativa(ctx.ordenes_ref)
    medidas = [
        Medida("venta", "Ventas", act.get("venta"), ref.get("venta"), "money"),
        Medida("neta", "Venta sin IGV", act.get("venta_neta"), ref.get("venta_neta"), "money"),
        Medida("ordenes", "Órdenes", act.get("ordenes"), ref.get("ordenes"), "num"),
        Medida("unidades", "Unidades", act.get("unidades"), ref.get("unidades"), "num"),
        Medida("ticket", "Ticket promedio", act.get("ticket"), ref.get("ticket"), "money"),
        Medida("precio", "Precio medio unitario", act.get("precio_medio"),
               ref.get("precio_medio"), "money"),
        Medida("upo", "Unidades por pedido", act.get("unidades_por_orden"),
               ref.get("unidades_por_orden"), "num2"),
        Medida("canc", "Tasa de cancelación", cal.get("tasa_cancelacion"),
               cal_ref.get("tasa_cancelacion"), "pct", invertido=True),
        Medida("perdida", "Venta perdida", cal.get("venta_perdida"),
               cal_ref.get("venta_perdida"), "money", invertido=True),
        Medida("doc", "% Documentado", cal.get("tasa_documentado"),
               cal_ref.get("tasa_documentado"), "pct"),
    ]
    if not ctx.otif.empty:
        ind, ind_ref = kpis.otif(ctx.otif), kpis.otif(ctx.otif_ref)
        medidas += [
            Medida("otif", "OTIF", ind.get("otif"), ind_ref.get("otif"), "pct"),
            Medida("ot", "On Time", ind.get("on_time"), ind_ref.get("on_time"), "pct"),
            Medida("if", "In Full", ind.get("in_full"), ind_ref.get("in_full"), "pct"),
        ]

    filas = []
    for m in medidas:
        filas.append({
            "indicador": m.etiqueta,
            "actual_txt": c.fmt(m.actual, m.kind),
            "ref_txt": c.fmt(m.referencia, m.kind),
            "dif_txt": c.fmt_dif(m.dif, m.kind) if m.dif is not None else "—",
            "var": m.var,
        })
    return pd.DataFrame(filas)


def _comparativo_dimension(ctx, columna: str) -> pd.DataFrame:
    """Venta actual y de referencia por dimensión, con su variación."""
    if columna not in ctx.ordenes:
        return pd.DataFrame()

    def agrupar(df: pd.DataFrame, sufijo: str) -> pd.DataFrame:
        if df is None or df.empty or columna not in df:
            return pd.DataFrame(columns=[columna, f"venta_{sufijo}", f"ordenes_{sufijo}"])
        validas = df[~df["es_cancelada"]] if "es_cancelada" in df else df
        return (validas.dropna(subset=[columna]).groupby(columna)
                .agg(**{f"venta_{sufijo}": ("total", "sum"),
                        f"ordenes_{sufijo}": ("orden", "nunique")}).reset_index())

    actual = agrupar(ctx.ordenes, "actual")
    if actual.empty:
        return pd.DataFrame()
    referencia = agrupar(ctx.ordenes_ref, "ref")
    out = actual.merge(referencia, on=columna, how="left")
    out["dif"] = out["venta_actual"] - out.get("venta_ref")
    out["var"] = out["dif"] / out.get("venta_ref").replace(0, np.nan)
    return out.sort_values("venta_actual", ascending=False)


# ===========================================================================
SECCIONES = {
    "Resumen": resumen,
    "Operatividad": operatividad,
    "Tiendas": tiendas,
    "Productos": productos,
    "Comparativos": comparativos,
}
