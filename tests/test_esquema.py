# -*- coding: utf-8 -*-
"""Verifica la capa de normalización frente a cambios de encabezado."""
import pathlib
import sys, io, tempfile
sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8',errors='replace')
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
import pandas as pd
from pathlib import Path
from core.sources import ExcelSource
from core.transform import build_model

BASE = {
    "Fecha Compra": ["2026-08-01","2026-08-02","2026-08-02"],
    "Order": ["clb1-01","clb2-01","clb2-01"],
    "Sitio": ["Columbia","Vans","Vans"],
    "Estado FAPP": ["Finalizada","Cancelada Final","Finalizada"],
    "SKU": ["111","222","333"],
    "Total": [100.0, 200.0, 50.0],
    "Marca": ["Columbia","VANS","VANS"],
    "Modalidad de Entrega": ["Despacho","Retiro","Retiro"],
    "Departamento": ["Lima (Metropolitana)","Cuzco","Cuzco"],
    "Unidades": [1,1,2],
    "Método de Pago": ["Mercado Pago","Yape","Yape"],
}

def escribir(d, nombre):
    p = Path(tempfile.gettempdir())/nombre
    pd.DataFrame(d).to_excel(p, index=False, sheet_name="datos")
    return p

def probar(titulo, datos, esperar_ok=True):
    p = escribir(datos, "t.xlsx")
    m = build_model(ExcelSource(p))
    r = m.report.datasets["ordenes"]
    print(f"\n--- {titulo}")
    print(f"    estado={r.status} filas={r.rows}")
    if r.missing_required:
        print(f"    FALTAN CRITICAS -> {r.missing_required}")
    for e in m.report.blocking_errors:
        print(f"    mensaje: {e}")
    print(f"    usable={m.report.usable}  (esperado {esperar_ok})")
    assert m.report.usable == esperar_ok, titulo
    return m

# 1. Estructura idéntica
m = probar("Estructura original", BASE)
print("    pedidos:", m.ordenes['orden'].nunique(), "| venta:", m.ordenes['total'].sum())

# 2. Variaciones de mayúsculas/espacios/tildes/guiones
variantes = {
    "  fecha compra ": BASE["Fecha Compra"],
    "ORDER": BASE["Order"],
    "sitio": BASE["Sitio"],
    "estado_fapp": BASE["Estado FAPP"],
    "sku ": BASE["SKU"],
    "TOTAL": BASE["Total"],
    "marca": BASE["Marca"],
    "MODALIDAD DE ENTREGA": BASE["Modalidad de Entrega"],
    "departamento": BASE["Departamento"],
    "unidades": BASE["Unidades"],
    "metodo de pago": BASE["Método de Pago"],
}
m = probar("Variaciones de encabezado (caso, tildes, espacios, guiones)", variantes)
print("    columnas mapeadas:", sorted(m.ordenes.columns.intersection(
      ['orden','sitio','estado','sku','total','marca','modalidad','departamento','metodo_pago']).tolist()))
print("    normalización de valores -> marca:", m.ordenes['marca'].tolist(),
      "| depto:", m.ordenes['departamento'].tolist())

# 3. Alias alternativo declarado en el esquema
alt = dict(BASE); alt["Monto Total"] = alt.pop("Total"); alt["Orden"] = alt.pop("Order")
probar("Alias alternativos ('Monto Total', 'Orden')", alt)

# 4. Falta una columna crítica
sin_total = {k:v for k,v in BASE.items() if k != "Total"}
probar("FALTA columna crítica 'Total'", sin_total, esperar_ok=False)

# 5. Faltan varias críticas
sin_varias = {k:v for k,v in BASE.items() if k not in ("Total","SKU","Sitio")}
probar("FALTAN 'Total', 'SKU', 'Sitio'", sin_varias, esperar_ok=False)

# 6. Columnas nuevas desconocidas: deben ignorarse sin romper
extra = dict(BASE); extra["Columna Nueva 2027"] = ["a","b","c"]; extra["Otra"] = [1,2,3]
m = probar("Columnas nuevas desconocidas", extra)
print("    ignoradas:", m.report.datasets['ordenes'].unmapped_columns)

# 7. Columnas opcionales ausentes: debe seguir funcionando
minimo = {k: BASE[k] for k in ["Fecha Compra","Order","Sitio","Estado FAPP","SKU","Total"]}
m = probar("Sólo columnas críticas", minimo)
print("    opcionales ausentes:", len(m.report.datasets['ordenes'].missing_optional))

print("\nTODAS LAS PRUEBAS DE ESQUEMA PASARON")
