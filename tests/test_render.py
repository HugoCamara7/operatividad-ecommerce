# -*- coding: utf-8 -*-
"""Dibuja las cinco secciones sobre un maestro sintético.

No comprueba estética: comprueba que ninguna sección se cae, que es lo que le
pasa al reporte cuando se cambia un bloque de datos y no se prueba la pantalla.
Se ejecuta sin `streamlit run`; Streamlit funciona en modo suelto y las
advertencias que emite no son fallos.
"""
import io
import logging
import pathlib
import sys
import warnings

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
warnings.filterwarnings("ignore")
logging.getLogger("streamlit").setLevel(logging.ERROR)   # corre sin servidor

import numpy as np
import pandas as pd

from core.filters import FilterState
from core.transform import DataModel, _derive_ordenes, _derive_otif
from core.normalize import DatasetReport, LoadReport, load_schema
from ui import blocks, report
from ui.helpers import Context

DIAS = pd.date_range("2026-07-15", "2026-08-26", freq="D")
azar = np.random.default_rng(7)
N = len(DIAS) * 6

ordenes = pd.DataFrame({
    "fecha_compra": np.repeat(DIAS, 6),
    "orden": [f"ord-{i // 2:04d}" for i in range(N)],
    "sitio": azar.choice(["Columbia", "Vans", "Parfois"], N),
    "marca": azar.choice(["Columbia", "Vans", "Parfois"], N),
    "estado": azar.choice(["Finalizada", "Cancelada Final", "Pendiente Despacho"], N),
    "sku": [f"sku-{i % 40}" for i in range(N)],
    "total": azar.uniform(50, 900, N).round(2),
    "unidades": azar.integers(1, 4, N),
    "modalidad": azar.choice(["Despacho", "Retiro"], N),
    "tipo_modalidad": azar.choice(["MW", "Regular", "ND", "SD"], N),
    "departamento": azar.choice(["Lima Metropolitana", "Cusco", "Piura"], N),
    "tienda_asignada": azar.choice(["Jockey", "Mega Plaza", "BODEGA ECOMMERCE"], N),
    "operador_logistico": azar.choice(["Urbano", "Chazki", "Scharf"], N),
    "metodo_pago": azar.choice(["Mercado Pago", "Yape"], N),
    "reporte": azar.choice(["DOCUMENTADO", "SIN DOCUMENTAR"], N),
    "mw": azar.choice(["SÍ", "NO"], N),
})
otif = pd.DataFrame({
    "fecha_compra": ordenes["fecha_compra"],
    "orden": ordenes["orden"],
    "sitio": ordenes["sitio"],
    "marca": ordenes["marca"],
    "modalidad": ordenes["modalidad"],
    "departamento": ordenes["departamento"],
    "tienda_documenta": ordenes["tienda_asignada"],
    "op_logistico": ordenes["operador_logistico"],
    "otif": azar.choice(["SÍ", "NO"], N),
    "on_time": azar.choice(["SÍ", "NO"], N),
    "in_full": azar.choice(["SÍ", "NO"], N),
    "responsable_demora": azar.choice(["Tienda", "Logístico"], N),
    "t_doc_calendario": azar.uniform(1, 40, N),
    "t_total": azar.uniform(10, 120, N),
})

esquema = load_schema()
informe = LoadReport(source="sintético")
for clave in ("ordenes", "otif"):
    informe.datasets[clave] = DatasetReport(key=clave, label=clave, found=True, rows=N)
modelo = DataModel(ordenes=ordenes, otif=otif, report=informe,
                   business=esquema.get("business", {}))
_derive_ordenes(modelo, modelo.business)
_derive_otif(modelo, modelo.business)

fallos = 0


def revisar(titulo: str, condicion: bool, detalle: str = "") -> None:
    global fallos
    print(f"    {'OK  ' if condicion else 'FALLA'} {titulo}{f' -> {detalle}' if detalle else ''}")
    if not condicion:
        fallos += 1


print("\n=== Bloques del mix de entrega ===")
mix = blocks.resumen_tipo_entrega(modelo.ordenes)
revisar("aparecen los cuatro tipos", set(mix["tipo_entrega"]) == {"MW", "Regular", "ND", "SD"},
        ", ".join(mix["tipo_entrega"]))
revisar("la participación suma 100%", abs(mix["participacion"].sum() - 1) < 1e-9)
cruce = blocks.mix_modalidad_tipo(modelo.ordenes)
revisar("el cruce modalidad × tipo tiene 8 combinaciones", len(cruce) == 8, str(len(cruce)))
revisar("el cruce cuadra con el total de pedidos",
        cruce["pedidos"].sum() >= modelo.ordenes["orden"].nunique())
revisar("sin la columna, el bloque devuelve vacío",
        blocks.resumen_tipo_entrega(modelo.ordenes.drop(columns=["tipo_entrega"])).empty)

print("\n=== La meta del OTIF ===")
meta = esquema["business"]["semaforos"]["otif"]
revisar("la meta del OTIF es 97%", meta["bueno"] == 0.97, str(meta))

print("\n=== Secciones ===")
for nombre, seccion in report.SECCIONES.items():
    estado = FilterState(desde=pd.Timestamp("2026-08-01"), hasta=pd.Timestamp("2026-08-26"))
    ctx = Context.build(modelo, estado)
    try:
        seccion(ctx)
        revisar(f"«{nombre}» se dibuja", True)
    except Exception as exc:                    # noqa: BLE001 - se reporta tal cual
        revisar(f"«{nombre}» se dibuja", False, f"{type(exc).__name__}: {exc}")

print("\n=== Aviso de comparación sin datos ===")
estado = FilterState(desde=pd.Timestamp("2026-08-01"), hasta=pd.Timestamp("2026-08-26"))
ctx = Context.build(modelo, estado)
revisar("la cabecera avisa que la referencia está incompleta",
        "parcial" in ctx.meta() or "sin datos" in ctx.meta(), ctx.meta())

print("\nTODAS LAS PRUEBAS DE PANTALLA PASARON" if not fallos else f"\n{fallos} PRUEBA(S) FALLARON")
sys.exit(1 if fallos else 0)
