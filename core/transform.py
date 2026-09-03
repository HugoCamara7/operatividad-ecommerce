# -*- coding: utf-8 -*-
"""Construcción del modelo de datos canónico.

Orquesta:  origen -> identificación -> mapeo de nombres -> tipado -> limpieza
           -> campos derivados -> `DataModel`

`DataModel` es lo único que consumen los KPIs, los filtros y la interfaz.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import clean
from .normalize import LoadReport, SchemaMapper, load_schema
from .sources import DataSource


@dataclass
class DataModel:
    """Modelo canónico listo para analizar."""

    ordenes: pd.DataFrame = field(default_factory=pd.DataFrame)
    otif: pd.DataFrame = field(default_factory=pd.DataFrame)
    carrier: pd.DataFrame = field(default_factory=pd.DataFrame)
    quiebres: pd.DataFrame = field(default_factory=pd.DataFrame)
    report: LoadReport = field(default_factory=LoadReport)
    business: dict = field(default_factory=dict)

    def has(self, name: str) -> bool:
        frame = getattr(self, name, None)
        return isinstance(frame, pd.DataFrame) and not frame.empty

    @property
    def periodo(self) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
        if not self.has("ordenes") or "fecha_compra" not in self.ordenes:
            return None, None
        serie = self.ordenes["fecha_compra"].dropna()
        return (serie.min(), serie.max()) if len(serie) else (None, None)


# ---------------------------------------------------------------------------
#  Construcción
# ---------------------------------------------------------------------------
def build_model(source: DataSource, schema: dict | None = None, mask_pii: bool = True) -> DataModel:
    schema = schema or load_schema()
    mapper = SchemaMapper(schema)
    business = schema.get("business", {})
    value_maps = schema.get("value_maps", {})
    null_tokens = set(value_maps.get("_null_tokens", ["-", ""]))

    headers = source.headers()
    report = LoadReport(source=source.label)
    if not headers:
        report.messages.append("No se encontraron tablas con datos en el archivo.")
        return DataModel(report=report, business=business)

    chosen = mapper.identify(headers)
    frames: dict[str, pd.DataFrame] = {}

    for key, spec in mapper.datasets.items():
        header = chosen.get(key)
        if header is None:
            report.datasets[key] = mapper.missing_report(key)
            continue
        try:
            raw = source.load(header.name)          # sólo aquí se paga la lectura
        except Exception as exc:
            missing = mapper.missing_report(key)
            missing.origin = header.origin
            report.datasets[key] = missing
            report.messages.append(f"No se pudo leer {header.origin}: {exc}")
            continue
        if raw.empty:
            report.datasets[key] = mapper.missing_report(key)
            continue
        frame, dataset_report = mapper.apply(key, raw, header.origin)
        frame = clean.apply_types(frame, spec["fields"], null_tokens)
        frame = clean.apply_value_maps(frame, value_maps)
        if mask_pii:
            pii = [c for c, cfg in spec["fields"].items() if cfg.get("pii")]
            frame = clean.mask_pii(frame, pii)
        frames[key] = frame
        report.datasets[key] = dataset_report

    model = DataModel(
        ordenes=frames.get("ordenes", pd.DataFrame()),
        otif=frames.get("otif", pd.DataFrame()),
        carrier=frames.get("carrier", pd.DataFrame()),
        quiebres=frames.get("quiebres", pd.DataFrame()),
        report=report,
        business=business,
    )

    # Los campos derivados se calculan sólo sobre los conjuntos completos. Si a
    # uno le falta una columna crítica se conserva tal cual y el informe dice
    # exactamente cuál falta, en lugar de romper la carga entera.
    derivaciones = {
        "ordenes": lambda: _derive_ordenes(model, business),
        "otif": lambda: _derive_otif(model, business),
        "carrier": lambda: _derive_carrier(model, business),
        "quiebres": lambda: _derive_quiebres(model),
    }
    for key, derivar in derivaciones.items():
        item = report.datasets.get(key)
        if item is None or not item.ok:
            continue
        try:
            derivar()
        except Exception as exc:                 # nunca debe tumbar la carga
            report.messages.append(
                f"No se pudieron calcular los campos derivados de "
                f"«{item.label}»: {exc}")
            item.missing_required.append("(cálculo de campos derivados)")
    return model


# ---------------------------------------------------------------------------
#  Campos derivados
# ---------------------------------------------------------------------------
def _yes(business: dict) -> set[str]:
    return set(business.get("valores_si", ["SÍ", "SI"]))


def _add_calendar(frame: pd.DataFrame, column: str = "fecha_compra") -> None:
    if column not in frame:
        return
    fecha = frame[column]
    frame["fecha_dia"] = fecha.dt.normalize()
    frame["periodo_mes"] = fecha.dt.to_period("M").astype("string")
    frame["mes_num"] = fecha.dt.month
    frame["anio_num"] = fecha.dt.year
    frame["dia_semana"] = fecha.dt.dayofweek
    frame["hora"] = fecha.dt.hour
    frame["semana"] = fecha.dt.isocalendar().week.astype("Int64")


def _derive_ordenes(model: DataModel, business: dict) -> None:
    df = model.ordenes
    if df.empty:
        return

    # -- calendario. Se prefiere la marca con hora para el análisis horario.
    if "fecha_compra_ts" in df and df["fecha_compra_ts"].notna().any():
        df["fecha_compra"] = df["fecha_compra"].fillna(df["fecha_compra_ts"].dt.normalize())
        base = df["fecha_compra_ts"].fillna(df["fecha_compra"])
    else:
        base = df["fecha_compra"]
    df["_ts"] = base
    _add_calendar(df, "_ts")
    df["fecha_dia"] = df["fecha_compra"].dt.normalize().fillna(df["fecha_dia"])

    # -- estado del pedido
    cancelados = {s.upper() for s in business.get("estados_cancelados", [])}
    completados = {s.upper() for s in business.get("estados_completados", [])}
    backlog = {s.upper() for s in business.get("estados_backlog", [])}
    estado = df["estado"].astype("string").str.strip().str.upper()
    df["es_cancelada"] = estado.isin(cancelados)
    df["es_finalizada"] = estado.isin(completados)
    df["es_backlog"] = estado.isin(backlog)
    df["grupo_estado"] = np.select(
        [df["es_finalizada"], df["es_cancelada"], df["es_backlog"]],
        ["Finalizada", "Cancelada", "En proceso"],
        default="Otro",
    )

    # -- dedup de líneas: 'Duplicado' = 1 marca la línea que se debe contar.
    if "duplicado" in df:
        flag = clean.to_flag(df["duplicado"], {"1", "SI", "SÍ", "TRUE"})
        df["linea_unica"] = flag.fillna(True).astype(bool)
    else:
        df["linea_unica"] = True

    # -- peso de orden: '# Ordenes' reparte 1 pedido entre sus líneas.
    if "peso_orden" in df and df["peso_orden"].notna().any():
        df["peso_orden"] = df["peso_orden"].fillna(0.0)
    else:
        conteo = df.groupby("orden")["orden"].transform("size")
        df["peso_orden"] = (1.0 / conteo).replace([np.inf, -np.inf], 0.0)

    # -- montos
    for column in ("total", "total_sin_igv", "subtotal", "descuento", "shipping", "unidades"):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0.0)
    if "total_sin_igv" not in df or not df["total_sin_igv"].any():
        igv = float(business.get("igv", 0.18))
        df["total_sin_igv"] = df.get("total", 0.0) / (1 + igv)
    df["venta_neta"] = df["total"].where(~df["es_cancelada"], 0.0)
    df["venta_perdida"] = df["total"].where(df["es_cancelada"], 0.0)
    if "subtotal" in df and "descuento" in df:
        base_desc = df["subtotal"].replace(0, np.nan)
        df["tasa_descuento"] = (df["descuento"] / base_desc).clip(0, 1)

    # -- banderas
    yes = _yes(business)
    if "mw" in df:
        df["es_mw"] = clean.to_flag(df["mw"], yes).fillna(False).astype(bool)
    _derive_tipo_entrega(df)
    if "nombre_descuento" in df:
        df["uso_cupon"] = df["nombre_descuento"].notna()

    # -- origen del despacho: centro de distribución vs. tienda
    cds = {c.upper() for c in business.get("centros_distribucion", [])}
    tienda = df.get("tienda_asignada")
    if tienda is None:
        tienda = df.get("tienda_despacho")
    if tienda is not None:
        upper = tienda.astype("string").str.strip().str.upper()
        df["origen_despacho"] = np.where(upper.isin(cds), "Centro de Distribución", "Tienda")
        df.loc[upper.isna(), "origen_despacho"] = "Sin asignar"

    # -- documentación
    if "reporte" in df:
        df["es_documentado"] = df["reporte"].astype("string").str.upper().eq("DOCUMENTADO")

    model.ordenes = df


def _derive_tipo_entrega(df: pd.DataFrame) -> None:
    """Tipo de entrega dentro de la modalidad: MW, SD, ND o Regular.

    Es la pregunta que operación hace sobre el mix («¿cuánto pesa MW?»). El
    valor viene en 'Tipo de Modalidad', ya unificado a siglas por los mapas de
    valores; cuando esa columna no está o viene vacía se recurre a la marca MW
    del maestro, que es el único corte que siempre existe.
    """
    etiquetas = pd.Series(pd.NA, index=df.index, dtype="string")
    if "tipo_modalidad" in df:
        etiquetas = df["tipo_modalidad"].astype("string").str.strip()
        etiquetas = etiquetas.mask(etiquetas.eq(""))
    if "es_mw" in df:
        respaldo = pd.Series("Regular", index=df.index, dtype="string").mask(df["es_mw"], "MW")
        etiquetas = etiquetas.fillna(respaldo)
    if etiquetas.notna().any():
        df["tipo_entrega"] = etiquetas.fillna("Sin clasificar")


def _derive_otif(model: DataModel, business: dict) -> None:
    df = model.otif
    if df.empty:
        return
    yes = _yes(business)
    for source_col, target in (("otif", "otif_ok"), ("on_time", "on_time_ok"), ("in_full", "in_full_ok")):
        if source_col in df:
            df[target] = clean.to_flag(df[source_col], yes)
    _add_calendar(df, "fecha_compra")
    if "duplicado" in df:
        df["linea_unica"] = clean.to_flag(df["duplicado"], {"1", "SI", "SÍ"}).fillna(True).astype(bool)
    else:
        df["linea_unica"] = True
    for column in ("t_doc_calendario", "t_doc_operativo", "t_despacho", "t_entrega_log",
                   "t_total", "t_tienda", "t_logistico", "pct_demora_tienda", "pct_demora_log",
                   "sla_objetivo_hrs"):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    # Cumplimiento del SLA objetivo en horas, cuando ambos datos existen.
    if "t_total" in df and "sla_objetivo_hrs" in df:
        df["cumple_sla_hrs"] = (df["t_total"] <= df["sla_objetivo_hrs"]).where(
            df["t_total"].notna() & df["sla_objetivo_hrs"].notna()
        )
    model.otif = df


def _derive_carrier(model: DataModel, business: dict) -> None:
    df = model.carrier
    if df.empty:
        return
    yes = _yes(business)
    for source_col, target in (("on_time", "on_time_ok"), ("otif", "otif_ok"), ("in_full", "in_full_ok")):
        if source_col in df:
            flag = df[source_col].astype("string").str.strip().str.upper()
            out = pd.Series(pd.NA, index=df.index, dtype="boolean")
            out[flag.isin({y.upper() for y in yes})] = True
            out[flag.eq("NO")] = False
            df[target] = out                      # 'REVISAR' queda como nulo, no como fallo
            df[f"{source_col}_revisar"] = flag.eq("REVISAR")
    if "fecha_solicitud" in df:
        _add_calendar(df, "fecha_solicitud")
    for column in ("sla", "time_real", "nro_visitas", "peso", "piezas", "dias_demora"):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    if "sla" in df and "time_real" in df:
        df["desvio_dias"] = df["time_real"] - df["sla"]
    if "estado_actual" in df:
        df["entregado"] = df["estado_actual"].astype("string").str.upper().eq("ENTREGADO")
    if "nro_visitas" in df:
        df["reintento"] = df["nro_visitas"] > 1
    model.carrier = df


def _derive_quiebres(model: DataModel) -> None:
    df = model.quiebres
    if df.empty:
        return
    _add_calendar(df, "fecha_compra")
    for column in ("monto_con_igv", "monto_sin_igv", "dias_tienda", "dias_gestion", "tiempo_total"):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    model.quiebres = df
