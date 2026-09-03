# -*- coding: utf-8 -*-
"""Carga de archivos y atajos de fecha.

Cubre las dos quejas de operación: que subir el consolidado (una hoja plana,
con o sin filas de cortesía antes del encabezado) funcione igual que el libro de
tablas dinámicas, y que los atajos de período nunca se salgan de los datos.
"""
import io
import pathlib
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import openpyxl
import pandas as pd

from core import compare
from core.sources import ExcelSource
from core.transform import build_model

CONSOLIDADO = {
    "Fecha Compra": ["2026-08-01", "2026-08-15", "2026-08-26"],
    "Order": ["clb1-01", "clb2-01", "clb3-01"],
    "Sitio": ["Columbia", "Vans", "Vans"],
    "Estado FAPP": ["Finalizada", "Finalizada", "Pendiente Despacho"],
    "SKU": ["111", "222", "333"],
    "Total": [100.0, 200.0, 50.0],
    "Modalidad de Entrega": ["Despacho", "Retiro", "Despacho"],
    "Tipo de Modalidad": ["ND", "Regular", "SD"],
}

fallos = 0


def revisar(titulo: str, condicion: bool, detalle: str = "") -> None:
    global fallos
    print(f"    {'OK  ' if condicion else 'FALLA'} {titulo}{f' -> {detalle}' if detalle else ''}")
    if not condicion:
        fallos += 1


def escribir(filas_previas: int, nombre: str) -> pathlib.Path:
    """Consolidado en una hoja plana, con `filas_previas` de cortesía arriba."""
    ruta = pathlib.Path(tempfile.gettempdir()) / nombre
    book = openpyxl.Workbook()
    hoja = book.active
    hoja.title = "Consolidado"
    for i in range(filas_previas):
        hoja.append(["Reporte de operación ecommerce"] if i == 0 else [])
    hoja.append(list(CONSOLIDADO))
    for fila in zip(*CONSOLIDADO.values()):
        hoja.append(list(fila))
    book.save(ruta)
    return ruta


print("\n=== Consolidado en hoja plana ===")
for previas in (0, 1, 3):
    print(f"--- {previas} fila(s) antes del encabezado")
    modelo = build_model(ExcelSource(escribir(previas, f"consolidado_{previas}.xlsx")))
    informe = modelo.report.datasets["ordenes"]
    revisar("se reconoce el maestro", modelo.report.usable, informe.status)
    revisar("trae las 3 filas", informe.rows == 3, f"filas={informe.rows}")
    tipos = modelo.ordenes.get("tipo_entrega", pd.Series(dtype="object"))
    revisar("mapea el tipo de entrega", "tipo_entrega" in modelo.ordenes,
            ", ".join(sorted(tipos.dropna().unique())))
    desde, hasta = modelo.periodo
    revisar("el período llega al último día", str(hasta.date()) == "2026-08-26", str(hasta))

print("--- encabezado con huecos (no debe ganar una fila de datos)")
ruta = pathlib.Path(tempfile.gettempdir()) / "consolidado_huecos.xlsx"
book = openpyxl.Workbook()
hoja = book.active
hoja.title = "Consolidado"
encabezado = list(CONSOLIDADO)
encabezado[6] = None                      # una columna sin nombre en el origen
hoja.append(encabezado)
for fila in zip(*CONSOLIDADO.values()):
    hoja.append(list(fila))
book.save(ruta)
modelo = build_model(ExcelSource(ruta))
informe = modelo.report.datasets["ordenes"]
revisar("usa la primera fila como encabezado", informe.rows == 3, f"filas={informe.rows}")
revisar("sigue siendo utilizable", modelo.report.usable, informe.status)
revisar("no confunde la columna sin nombre con un dato",
        "orden" in modelo.ordenes and modelo.ordenes["orden"].nunique() == 3)

print("\n=== Atajos de período ===")
minimo, maximo = pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-26")
disponibles = compare.atajos_disponibles(minimo, maximo)
revisar("no se ofrecen atajos más largos que los datos",
        "ultimos_30" not in disponibles and "ultimos_90" not in disponibles,
        ", ".join(disponibles))
revisar("no se ofrece 'mes anterior' sin mes anterior",
        "mes_anterior" not in disponibles)
revisar("el atajo inicial cae en el histórico",
        compare.atajo_inicial(minimo, maximo) == "historico")
for atajo in disponibles:
    periodo = compare.rango_atajo(atajo, minimo, maximo)
    revisar(f"«{compare.ATAJOS[atajo]}» cabe en los datos",
            minimo <= periodo.desde <= periodo.hasta <= maximo, periodo.texto())

largo = (pd.Timestamp("2025-01-05"), pd.Timestamp("2026-08-26"))
revisar("con año y medio de datos sí se ofrecen los atajos largos",
        {"ultimos_30", "ultimos_90", "mes_anterior", "anio_ultimo"}
        <= set(compare.atajos_disponibles(*largo)))
revisar("«mes anterior completo» devuelve julio entero",
        compare.rango_atajo("mes_anterior", *largo).texto() == "01/07/2026 – 31/07/2026")
revisar("sin fechas no se rompe",
        not compare.rango_atajo("ultimos_7", None, None).valido)

print("\n=== Cobertura de la ventana de comparación ===")
actual = compare.Periodo(pd.Timestamp("2026-08-01"), pd.Timestamp("2026-08-26"))
anterior = compare.periodo_anterior(actual)
revisar("el período anterior queda fuera del archivo",
        compare.cobertura(anterior, minimo, maximo) == (0, 26),
        f"{anterior.texto()} -> {compare.cobertura(anterior, minimo, maximo)}")
revisar("el período actual está cubierto por completo",
        compare.cobertura(actual, minimo, maximo) == (26, 26))

print("\nTODAS LAS PRUEBAS DE CARGA PASARON" if not fallos else f"\n{fallos} PRUEBA(S) FALLARON")
sys.exit(1 if fallos else 0)
