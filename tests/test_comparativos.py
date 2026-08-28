# -*- coding: utf-8 -*-
"""Comparativos: períodos, contexto y bloques de cada sección."""
import contexto

import pandas as pd
from core import compare, filters, repository
from core.compare import Periodo
from core.filters import FilterState
from core.sources import ExcelSource
from ui import blocks
from ui.helpers import Context

m = contexto.modelo()
assert m is not None, "no hay carga en cache"
lo, hi = m.periodo

print("=== PERIODOS ===")
p = Periodo(pd.Timestamp('2026-08-01'), pd.Timestamp('2026-08-26'))
for modo in ("anterior", "ly", "ninguno"):
    print(f"  {modo:10} -> {compare.resolver(p, modo).texto()}")
print(f"  personaliz -> {compare.resolver(p,'personalizado',Periodo(pd.Timestamp('2026-06-01'),pd.Timestamp('2026-06-26'))).texto()}")

print("\n=== CONTEXTO CON COMPARACION ===")
for modo in ("anterior", "ly", "ninguno"):
    st_ = FilterState(desde=p.desde, hasta=p.hasta)
    ctx = Context.build(m, st_, modo)
    print(f"  {modo:10} act={len(ctx.ordenes):>6}  ref={len(ctx.ordenes_ref):>6}  "
          f"etiqueta={ctx.etiqueta_ref or '-':10} hay_cmp={ctx.hay_comparacion}")

print("\n=== SECCIONES (bloques de datos) ===")
ESCENARIOS = {
    'agosto vs anterior': (FilterState(desde=p.desde, hasta=p.hasta), 'anterior'),
    'agosto vs LY':       (FilterState(desde=p.desde, hasta=p.hasta), 'ly'),
    'todo sin cmp':       (FilterState(desde=lo, hasta=hi), 'ninguno'),
    'un sitio':           (FilterState(desde=lo, hasta=hi, seleccion={'sitio': ['Columbia']}), 'anterior'),
    'rango vacio':        (FilterState(desde=lo, hasta=lo, seleccion={'sitio': ['Keds']}), 'anterior'),
}
fallos = 0
for nombre, (st_, modo) in ESCENARIOS.items():
    ctx = Context.build(m, st_, modo)
    salida = []
    pruebas = [
        ('modalidad', lambda: blocks.resumen_modalidad(ctx.ordenes)),
        ('pago',      lambda: blocks.resumen_pago(ctx.ordenes)),
        ('opl',       lambda: blocks.resumen_opl(ctx.ordenes, ctx.carrier)),
        ('otif',      lambda: blocks.tabla_otif(ctx.otif, 'marca')),
        ('tiendas',   lambda: blocks.tabla_flujo(ctx.ordenes)),
        ('mensual',   lambda: blocks.tabla_mensual(ctx.ordenes)),
        ('quiebres',  lambda: blocks.tabla_quiebres(ctx.quiebres)),
        ('doc',       lambda: blocks.tabla_documentacion(ctx.ordenes, ctx.otif)),
    ]
    for etiqueta, fn in pruebas:
        try:
            salida.append(f"{etiqueta}={len(fn())}")
        except Exception as e:
            salida.append(f"{etiqueta}=ERR({type(e).__name__})"); fallos += 1
    # funciones de comparación de la sección Comparativos
    from ui import report
    for etiqueta, fn in (('cmp_tabla', lambda: report._tabla_comparativa(ctx)),
                         ('cmp_dim',   lambda: report._comparativo_dimension(ctx, 'sitio'))):
        try:
            salida.append(f"{etiqueta}={len(fn())}")
        except Exception as e:
            salida.append(f"{etiqueta}=ERR({type(e).__name__}: {e})"); fallos += 1
    print(f"  {nombre:20} " + "  ".join(salida))

print("\nFALLOS:", fallos)
assert fallos == 0
print("COMPARATIVOS Y SECCIONES OK")
