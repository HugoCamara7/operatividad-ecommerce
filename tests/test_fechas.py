# -*- coding: utf-8 -*-
"""Lectura de fechas: los formatos que aparecen de verdad en el maestro.

No necesita el Excel: comprueba `clean_datetime` valor a valor y la carga
completa sobre libros pequeños generados al vuelo.
"""
import io
import pathlib
import sys
import tempfile

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import pandas as pd

from core.clean import clean_datetime
from core.sources import ExcelSource
from core.transform import build_model

fallos = 0


def probar(titulo, entrada, esperado):
    """`esperado`: lista de textos ISO, o None donde debe quedar nulo."""
    global fallos
    obtenido = clean_datetime(pd.Series(entrada))
    ok = True
    for i, (valor, quiero) in enumerate(zip(obtenido, esperado)):
        if quiero is None:
            ok &= pd.isna(valor)
        else:
            ok &= (not pd.isna(valor)) and valor == pd.Timestamp(quiero)
        if not ok:
            print(f"    fila {i}: {entrada[i]!r} -> {valor} (esperado {quiero})")
            break
    print(f"{'OK  ' if ok else 'FALLA'} {titulo}")
    if not ok:
        fallos += 1
    assert str(obtenido.dtype) == "datetime64[ns]", f"{titulo}: dtype {obtenido.dtype}"


print("--- Formatos de fecha")
probar("ISO con hora", ["2026-08-02T12:04:00", "2026-08-03T09:00:00"],
       ["2026-08-02 12:04:00", "2026-08-03 09:00:00"])
probar("ISO con fracción", ["2026-08-02T12:04:00.500"], ["2026-08-02 12:04:00.5"])
probar("ISO simple", ["2026-08-02", "2025-12-31"], ["2026-08-02", "2025-12-31"])
probar("Peruano con hora", ["02/08/2026 14:19:51"], ["2026-08-02 14:19:51"])
probar("Peruano sin hora", ["02/08/2026", "31/12/2025"], ["2026-08-02", "2025-12-31"])
probar("Peruano con guiones", ["02-08-2026"], ["2026-08-02"])
probar("Peruano con puntos", ["02.08.2026"], ["2026-08-02"])
probar("Año de dos cifras", ["02/08/26"], ["2026-08-02"])
probar("Compacto aaaammdd", ["20260802"], ["2026-08-02"])

# Con barras y el año delante NO se puede aplicar la regla peruana: '2026/08/02'
# es 2 de agosto, no 8 de febrero. Era el error que movía las ventas de mes.
probar("Año primero con barras", ["2026/08/02", "2026/08/03"], ["2026-08-02", "2026-08-03"])
probar("Año primero con barras y hora", ["2026/08/02 14:19"], ["2026-08-02 14:19:00"])

print("\n--- Zonas horarias (Perú = UTC-5)")
probar("UTC explícito", ["2026-08-02T12:04:00Z"], ["2026-08-02 07:04:00"])
probar("Desfase local", ["2026-08-02T12:04:00-05:00"], ["2026-08-02 12:04:00"])
probar("Con y sin zona mezcladas", ["2026-08-02T12:04:00Z", "2026-08-03T09:00:00"],
       ["2026-08-02 07:04:00", "2026-08-03 09:00:00"])

print("\n--- Seriales de Excel")
probar("Serial numérico", [45871, 45872], ["2025-08-02", "2025-08-03"])
probar("Serial como texto", ["45871"], ["2025-08-02"])
probar("Serial con hora", [45871.5138], ["2025-08-02 12:19:52"])

print("\n--- Meses en español")
probar("Abreviado", ["01-ago-2026", "15-dic-2025"], ["2026-08-01", "2025-12-15"])
probar("Completo", ["3 de agosto de 2026"], ["2026-08-03"])

print("\n--- Vacíos y basura")
probar("Marcadores de vacío", ["0", "", "-", None], [None, None, None, None])
probar("Texto que no es fecha", ["Total general", "###"], [None, None])
probar("Todo mezclado",
       ["2026-08-02T12:04:00", "02/08/2026 14:19:51", 45871, "-", "2026/08/02"],
       ["2026-08-02 12:04:00", "2026-08-02 14:19:51", "2025-08-02", None, "2026-08-02"])

print("\n--- Carga completa del libro")
BASE = {
    "Order": ["c1", "c2", "c3", "c4"],
    "Sitio": ["Columbia"] * 4,
    "Estado FAPP": ["Finalizada"] * 4,
    "SKU": ["1", "2", "3", "4"],
    "Total": [100.0, 200.0, 50.0, 25.0],
}


def cargar(fechas, nombre):
    ruta = pathlib.Path(tempfile.gettempdir()) / nombre
    pd.DataFrame(dict(BASE, **{"Fecha Compra": fechas})).to_excel(
        ruta, index=False, sheet_name="datos")
    return build_model(ExcelSource(ruta))


for titulo, fechas, primero, ultimo in [
    ("texto ISO", ["2026-08-01", "2026-08-02", "2026-08-15", "2026-09-30"],
     "2026-08-01", "2026-09-30"),
    ("texto peruano", ["01/08/2026", "02/08/2026", "15/08/2026", "30/09/2026"],
     "2026-08-01", "2026-09-30"),
    ("con zona horaria", ["2026-08-01T10:00:00-05:00", "2026-08-02T10:00:00-05:00",
                          "2026-08-15T10:00:00-05:00", "2026-09-30T10:00:00-05:00"],
     "2026-08-01", "2026-09-30"),
    ("seriales de Excel", [46235, 46236, 46249, 46295], "2026-08-01", "2026-09-30"),
]:
    modelo = cargar(fechas, "fechas.xlsx")
    desde, hasta = modelo.periodo
    bien = (modelo.report.usable
            and desde == pd.Timestamp(primero) and hasta == pd.Timestamp(ultimo)
            and "fecha_dia" in modelo.ordenes and "periodo_mes" in modelo.ordenes)
    print(f"{'OK  ' if bien else 'FALLA'} maestro con {titulo}: {desde} – {hasta}")
    if not bien:
        fallos += 1
        print("     ", modelo.report.messages, modelo.report.blocking_errors)

# Fechas ilegibles: la carga no debe caerse, pero sí avisar.
modelo = cargar(["no es fecha"] * 4, "fechas_malas.xlsx")
aviso = any("interpretar" in m for m in modelo.report.messages)
print(f"{'OK  ' if aviso else 'FALLA'} fechas ilegibles: se avisa en el informe")
if not aviso:
    fallos += 1
    print("     ", modelo.report.messages)

print("\n" + ("TODAS LAS PRUEBAS DE FECHAS PASARON" if not fallos
              else f"{fallos} PRUEBAS DE FECHAS FALLARON"))
sys.exit(1 if fallos else 0)
