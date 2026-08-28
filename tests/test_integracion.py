# -*- coding: utf-8 -*-
"""Prueba de integración sin servidor: ejercita KPIs, filtros, gráficos y export."""
import contexto
import io
import time

import pandas as pd
from core.sources import ExcelSource
from core.transform import build_model
from core import repository, filters, kpis, export
from core.filters import FilterState

src=contexto.fuente()
if src is None:
    print('SALTADA: no se encontró el Excel maestro.'); raise SystemExit(0)
fp=src.fingerprint
t=time.time()
m=repository.load(fp)
if m is None:
    m=build_model(src); repository.save(m,fp); print('procesado y cacheado')
else:
    print('recuperado del cache')
print('carga:',round(time.time()-t,2),'s')

# --- caché round-trip
t=time.time(); m2=repository.load(fp); print('lectura cache:',round(time.time()-t,2),'s',
      '| filas ordenes:',len(m2.ordenes),'| iguales:',len(m2.ordenes)==len(m.ordenes))
assert m2.report.datasets['ordenes'].status=='ok'

# --- contexto simulando app
class Ctx:
    pass
def build_ctx(state):
    ctx=Ctx(); ctx.model=m; ctx.state=state
    ctx.ordenes=filters.aplicar(m.ordenes,state,'ordenes')
    ctx.otif=filters.aplicar(m.otif,state,'otif')
    ctx.carrier=filters.aplicar(m.carrier,state,'carrier')
    ctx.quiebres=filters.aplicar(m.quiebres,state,'quiebres')
    prev=kpis.periodo_anterior(m.ordenes,state.desde,state.hasta) if state.desde is not None else m.ordenes.iloc[0:0]
    ctx.ordenes_previo=prev
    return ctx

lo,hi=m.periodo
escenarios={
 'todo': FilterState(desde=lo,hasta=hi),
 'ultimos30': FilterState(desde=hi-pd.Timedelta(days=29),hasta=hi),
 'un sitio': FilterState(desde=lo,hasta=hi,seleccion={'sitio':['Columbia']}),
 'drill tienda': FilterState(desde=lo,hasta=hi,drill={'tienda_asignada':'BODEGA ECOMMERCE'}),
 'sin canceladas': FilterState(desde=lo,hasta=hi,excluir_canceladas=True),
 'lineas unicas': FilterState(desde=lo,hasta=hi,solo_lineas_unicas=True),
 'combinado': FilterState(desde=hi-pd.Timedelta(days=60),hasta=hi,
        seleccion={'sitio':['Columbia','Vans'],'modalidad':['Despacho']},excluir_canceladas=True),
 'vacio': FilterState(desde=lo,hasta=lo),
}
print('\n=== ESCENARIOS DE FILTRO ===')
ctxs={}
for nombre,st_ in escenarios.items():
    ctx=build_ctx(st_); ctxs[nombre]=ctx
    v=kpis.ventas(ctx.ordenes); q=kpis.calidad_operativa(ctx.ordenes)
    o=kpis.otif(ctx.otif) if not ctx.otif.empty else {}
    print(f"{nombre:16} lineas={len(ctx.ordenes):>7} ped={v.get('ordenes',0):>6} "
          f"venta={v.get('venta',0):>12,.0f} canc={q.get('tasa_cancelacion',0):.3f} otif={o.get('otif',float('nan')):.3f}")

# --- páginas: se ejercitan las funciones puras que usan
print('\n=== GRAFICOS ===')
from ui import charts
ctx=ctxs['todo']
val=ctx.ordenes[~ctx.ordenes['es_cancelada']]
figs={}
figs['tendencia']=charts.tendencia(kpis.serie_temporal(val,'D'),'periodo','venta','Venta','money')
figs['dona']=charts.dona(ctx.ordenes.groupby('grupo_estado')['orden'].nunique().reset_index(name='p'),'grupo_estado','p')
figs['barrasH']=charts.barras_horizontales(kpis.ranking(val,'sitio','venta',10),'sitio','venta','money')
figs['gauge']=charts.gauge(kpis.otif(ctx.otif).get('otif'),'OTIF',0.9,0.8)
figs['desvio']=charts.barras_desvio(kpis.tasa_por_dimension(ctx.otif,'modalidad','otif_ok',5),'modalidad','tasa',0.9)
figs['apiladas']=charts.barras_apiladas_100(ctx.ordenes.groupby(['periodo_mes','modalidad'])['orden'].nunique().reset_index(name='p'),'periodo_mes','modalidad','p')
figs['heatmap']=charts.heatmap(val.pivot_table(index='sitio',columns='metodo_pago',values='orden',aggfunc='nunique').fillna(0))
figs['embudo']=charts.embudo(['A','B','C'],[100,80,60])
sc=kpis.ranking(ctx.ordenes,'tienda_asignada','ordenes',40).rename(columns={'tasa_cancelacion':'canc'})
figs['dispersion']=charts.dispersion(sc,'ordenes','canc','venta','tienda_asignada',ref_y=0.16)
figs['lineas']=charts.lineas_multiples(ctx.otif.groupby('periodo_mes')[['otif_ok','on_time_ok']].mean().reset_index(),'periodo_mes',{'otif_ok':'OTIF','on_time_ok':'OT'})
figs['comparadas']=charts.barras_comparadas(pd.DataFrame({'x':['a','b'],'s1':[1,2],'s2':[2,3]}),'x',{'s1':'S1','s2':'S2'})
figs['vacio']=charts.vacio()
for k,f in figs.items():
    assert f is not None and hasattr(f,'to_dict'), k
    f.to_dict()
print('OK', len(figs), 'graficos renderizan:', ', '.join(figs))

# --- export
print('\n=== EXPORT ===')
t=time.time(); xls=export.construir_excel(ctxs['combinado'],True)
print('excel bytes:',len(xls),'en',round(time.time()-t,1),'s')
t=time.time(); csv=export.csv_detalle(ctxs['ultimos30'].ordenes)
print('csv bytes:',len(csv),'en',round(time.time()-t,1),'s')
import zipfile
with zipfile.ZipFile(io.BytesIO(xls)) as z:
    hojas=[n for n in z.namelist() if 'sheet' in n]
print('hojas en el libro:',len(hojas))

# --- componentes de formato
from ui import components as comp
print('\n=== FORMATO ===')
for v,k in [(27577623.17,'money'),(0.1612,'pct'),(12.7,'hours'),(66408,'num'),(None,'money'),(float('nan'),'pct')]:
    print(f'  {k:6} {v} -> {comp.fmt(v,k)}')
print('\nTODO OK')
