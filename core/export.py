# -*- coding: utf-8 -*-
"""Exportación del análisis.

Genera un libro Excel con el detalle filtrado y los indicadores calculados, para
que el análisis salga del dashboard tal como se está viendo en pantalla.
"""
from __future__ import annotations

import io
from datetime import datetime

import pandas as pd

from . import kpis


def _hoja_indicadores(ctx) -> pd.DataFrame:
    filas: list[dict] = []

    def agregar(bloque: str, datos: dict, formatos: dict[str, str]) -> None:
        for clave, valor in datos.items():
            filas.append({
                "Bloque": bloque,
                "Indicador": _ETIQUETAS.get(clave, clave.replace("_", " ").title()),
                "Valor": round(valor, 4) if isinstance(valor, float) else valor,
                "Formato": formatos.get(clave, "número"),
            })

    agregar("Venta", kpis.ventas(ctx.ordenes), _FORMATOS)
    agregar("Operación", kpis.calidad_operativa(ctx.ordenes), _FORMATOS)
    if not ctx.otif.empty:
        agregar("OTIF", kpis.otif(ctx.otif), _FORMATOS)
    if not ctx.carrier.empty:
        agregar("Carrier", kpis.carrier(ctx.carrier), _FORMATOS)
    if not ctx.quiebres.empty:
        agregar("Quiebres", kpis.quiebres(ctx.quiebres, ctx.ordenes), _FORMATOS)
    return pd.DataFrame(filas)


def _hoja_filtros(ctx) -> pd.DataFrame:
    filas = [{"Filtro": "Período", "Valor": _periodo(ctx)}]
    for clave, valores in ctx.state.activos.items():
        filas.append({"Filtro": clave.replace("_", " ").title(), "Valor": ", ".join(map(str, valores))})
    for clave, valor in ctx.state.drill.items():
        filas.append({"Filtro": f"{clave.replace('_',' ').title()} (drill)", "Valor": valor})
    if ctx.state.excluir_canceladas:
        filas.append({"Filtro": "Canceladas", "Valor": "excluidas"})
    filas.append({"Filtro": "Origen de datos", "Valor": ctx.model.report.source})
    filas.append({"Filtro": "Generado", "Valor": datetime.now().strftime("%d/%m/%Y %H:%M")})
    return pd.DataFrame(filas)


def _periodo(ctx) -> str:
    if ctx.state.desde is None or ctx.state.hasta is None:
        return "todo el histórico"
    return f"{ctx.state.desde:%d/%m/%Y} – {ctx.state.hasta:%d/%m/%Y}"


def construir_excel(ctx, incluir_detalle: bool = True, max_filas: int = 100_000) -> bytes:
    """Libro Excel con indicadores, resúmenes y detalle filtrado."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        _hoja_indicadores(ctx).to_excel(writer, sheet_name="Indicadores", index=False)
        _hoja_filtros(ctx).to_excel(writer, sheet_name="Filtros aplicados", index=False)

        ordenes = ctx.ordenes
        if not ordenes.empty:
            validas = ordenes[~ordenes["es_cancelada"]] if "es_cancelada" in ordenes else ordenes
            serie = kpis.serie_temporal(validas, "D")
            if not serie.empty:
                serie.to_excel(writer, sheet_name="Serie diaria", index=False)
            for dimension, hoja in (("sitio", "Por sitio"), ("marca", "Por marca"),
                                    ("tienda_asignada", "Por tienda"),
                                    ("departamento", "Por departamento"),
                                    ("metodo_pago", "Por medio de pago")):
                if dimension in ordenes:
                    tabla = kpis.ranking(validas, dimension, "venta", 500)
                    if not tabla.empty:
                        tabla.to_excel(writer, sheet_name=hoja[:31], index=False)

        if not ctx.otif.empty:
            for dimension, hoja in (("modalidad", "OTIF modalidad"),
                                    ("tienda_documenta", "OTIF tienda"),
                                    ("departamento", "OTIF departamento")):
                tabla = kpis.tasa_por_dimension(ctx.otif, dimension, "otif_ok", 5)
                if not tabla.empty:
                    tabla.to_excel(writer, sheet_name=hoja[:31], index=False)

        if not ctx.quiebres.empty:
            ctx.quiebres.head(max_filas).to_excel(writer, sheet_name="Quiebres", index=False)

        if incluir_detalle and not ctx.ordenes.empty:
            detalle = _detalle(ctx.ordenes).head(max_filas)
            detalle.to_excel(writer, sheet_name="Detalle pedidos", index=False)

        _formatear(writer)
    return buffer.getvalue()


def _detalle(df: pd.DataFrame) -> pd.DataFrame:
    columnas = [c for c in _COLUMNAS_DETALLE if c in df.columns]
    out = df[columnas].copy()
    return out.rename(columns={c: _ETIQUETAS.get(c, c.replace("_", " ").title()) for c in columnas})


def _formatear(writer) -> None:
    """Encabezados con estilo y anchos legibles en todas las hojas."""
    book = writer.book
    cabecera = book.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": "#0B1F3F",
        "border": 0, "align": "left", "valign": "vcenter", "font_size": 10,
    })
    for sheet in writer.sheets.values():
        sheet.set_row(0, 22, cabecera)
        sheet.freeze_panes(1, 0)
        sheet.set_column(0, 0, 26)
        sheet.set_column(1, 40, 16)


def csv_detalle(df: pd.DataFrame) -> bytes:
    """CSV del detalle, con separador y codificación que Excel abre bien."""
    return _detalle(df).to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")


# ---------------------------------------------------------------------------
_COLUMNAS_DETALLE = [
    "fecha_compra", "orden", "sitio", "marca", "estado", "grupo_estado", "reporte",
    "tienda_asignada", "tienda_despacho", "origen_despacho", "modalidad",
    "tipo_modalidad", "tipo_entrega", "zona", "departamento", "metodo_pago",
    "operador_logistico", "tracking",
    "sku", "nombre_producto", "talla", "color", "unidades", "precio_unitario",
    "subtotal", "descuento", "shipping", "total", "total_sin_igv",
]

_ETIQUETAS = {
    "fecha_compra": "Fecha compra", "orden": "Orden", "sitio": "Sitio", "marca": "Marca",
    "estado": "Estado", "grupo_estado": "Grupo estado", "reporte": "Reporte",
    "tienda_asignada": "Tienda asignada", "tienda_despacho": "Tienda despacho",
    "origen_despacho": "Origen despacho", "modalidad": "Modalidad",
    "tipo_modalidad": "Tipo modalidad", "tipo_entrega": "Tipo de entrega",
    "zona": "Zona", "departamento": "Departamento",
    "metodo_pago": "Medio de pago", "operador_logistico": "Operador logístico",
    "tracking": "Tracking", "sku": "SKU", "nombre_producto": "Producto", "talla": "Talla",
    "color": "Color", "unidades": "Unidades", "precio_unitario": "Precio unitario",
    "subtotal": "Subtotal", "descuento": "Descuento", "shipping": "Shipping",
    "total": "Total", "total_sin_igv": "Total sin IGV",
    "ordenes": "Pedidos", "ordenes_validas": "Pedidos no cancelados", "lineas": "Líneas",
    "venta": "Venta con IGV", "venta_neta": "Venta sin IGV", "unidades": "Unidades",
    "ticket": "Ticket promedio", "unidades_por_orden": "Unidades por pedido",
    "precio_medio": "Precio medio unitario", "lineas_por_orden": "Líneas por pedido",
    "descuento_total": "Descuento total", "tasa_descuento": "Tasa de descuento",
    "pct_cupon": "% pedidos con cupón", "shipping_total": "Shipping total",
    "canceladas": "Pedidos cancelados", "tasa_cancelacion": "Tasa de cancelación",
    "venta_perdida": "Venta perdida", "tasa_finalizacion": "Tasa de finalización",
    "backlog": "Pedidos en proceso", "tasa_documentado": "% documentado",
    "pct_mw": "% multiwarehouse",
    "otif": "OTIF", "on_time": "On Time", "in_full": "In Full",
    "t_documentacion": "Horas hasta documentar", "t_despacho": "Horas de despacho",
    "t_total": "Horas totales compra-entrega", "t_tienda": "Horas en tienda",
    "t_logistico": "Horas en logística", "demora_tienda": "% demora por tienda",
    "demora_logistica": "% demora por logística", "con_demora": "Pedidos con demora",
    "envios": "Envíos", "entregados": "Entregados", "tasa_entrega": "% entregado",
    "en_transito": "En tránsito", "desvio_medio": "Desvío medio vs SLA",
    "fuera_sla": "Envíos fuera de SLA", "reintentos": "Reintentos",
    "tasa_reintento": "% reintento", "por_revisar": "Por revisar",
    "quiebres": "Quiebres", "ordenes_afectadas": "Pedidos afectados",
    "skus_afectados": "SKU afectados", "monto_perdido": "Venta perdida (sin IGV)",
    "tasa_quiebre": "Tasa de quiebre", "dias_tienda": "Días en tienda",
    "dias_gestion": "Días de gestión", "tiempo_total": "Días totales",
}

_FORMATOS = {
    "venta": "moneda", "venta_neta": "moneda", "ticket": "moneda", "precio_medio": "moneda",
    "descuento_total": "moneda", "venta_perdida": "moneda", "monto_perdido": "moneda",
    "shipping_total": "moneda",
    "tasa_cancelacion": "porcentaje", "tasa_finalizacion": "porcentaje",
    "tasa_documentado": "porcentaje", "pct_mw": "porcentaje", "tasa_descuento": "porcentaje",
    "pct_cupon": "porcentaje", "otif": "porcentaje", "on_time": "porcentaje",
    "in_full": "porcentaje", "tasa_entrega": "porcentaje", "tasa_reintento": "porcentaje",
    "tasa_quiebre": "porcentaje", "demora_tienda": "porcentaje", "demora_logistica": "porcentaje",
    "t_documentacion": "horas", "t_despacho": "horas", "t_total": "horas",
    "t_tienda": "horas", "t_logistico": "horas",
}
