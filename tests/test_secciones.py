# -*- coding: utf-8 -*-
"""Ejercita las funciones de datos de las 8 secciones bajo varios filtros."""
import contexto
import pandas as pd
from core import repository, filters
from core.sources import ExcelSource
from core.filters import FilterState
from ui import blocks

m = contexto.modelo()
lo, hi = m.periodo

class Ctx: pass
def build(st_):
    c = Ctx(); c.model = m; c.state = st_
    c.ordenes = filters.aplicar(m.ordenes, st_, 'ordenes')
    c.otif = filters.aplicar(m.otif, st_, 'otif')
    c.carrier = filters.aplicar(m.carrier, st_, 'carrier')
    c.quiebres = filters.aplicar(m.quiebres, st_, 'quiebres')
    c.ordenes_previo = m.ordenes.iloc[0:0]
    return c

FUNCS = [
    ('1 comparativo', lambda c: (blocks.tabla_mensual(c.ordenes), blocks.comparativo_anual(c.ordenes))),
    ('2 modalidad',   lambda c: (blocks.resumen_modalidad(c.ordenes), blocks.evolucion_participacion(c.ordenes, 'modalidad'))),
    ('3 pago',        lambda c: (blocks.resumen_pago(c.ordenes),)),
    ('4 documenta',   lambda c: (blocks.tabla_documentacion(c.ordenes, c.otif), blocks.tiempo_tienda(c.otif))),
    ('5 quiebres',    lambda c: (blocks.tabla_quiebres(c.quiebres), blocks.evolucion_quiebres(c.quiebres))),
    ('6 opl',         lambda c: (blocks.resumen_opl(c.ordenes, c.carrier),)),
    ('7 otif',        lambda c: (blocks.tabla_otif(c.otif, 'marca'), blocks.distribucion_otif(c.otif)) if not c.otif.empty else ()),
    ('8 logistico',   lambda c: (blocks.tabla_flujo(c.ordenes), blocks.flujo_mensual(c.ordenes))),
]

ESCENARIOS = {
    'todo':        FilterState(desde=lo, hasta=hi),
    'un sitio':    FilterState(desde=lo, hasta=hi, seleccion={'sitio': ['Columbia']}),
    'sin canc':    FilterState(desde=lo, hasta=hi, excluir_canceladas=True),
    'rango monto': FilterState(desde=lo, hasta=hi, rangos={'total': (0.0, 150.0)}),
    'un dia':      FilterState(desde=hi, hasta=hi),
    'vacio total': FilterState(desde=lo, hasta=lo, seleccion={'sitio': ['Keds']}),
}

fallos = 0
for nombre, st_ in ESCENARIOS.items():
    ctx = build(st_)
    resultados = []
    for etiqueta, fn in FUNCS:
        try:
            salida = fn(ctx)
            filas = sum(len(x) for x in salida if isinstance(x, pd.DataFrame))
            resultados.append(f'{etiqueta}={filas}')
        except Exception as e:
            resultados.append(f'{etiqueta}=ERROR({type(e).__name__}: {e})')
            fallos += 1
    print(f'{nombre:13} | ' + '  '.join(resultados))

print()
print('FALLOS:', fallos)
assert fallos == 0, 'hay secciones con error'
print('LAS 8 SECCIONES RESISTEN TODOS LOS ESCENARIOS')
