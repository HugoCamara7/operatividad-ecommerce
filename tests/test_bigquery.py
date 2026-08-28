# -*- coding: utf-8 -*-
"""El origen directo es opcional: nunca debe impedir que la app funcione."""
import contexto

from core.bigquery import BigQuerySource, BigQueryNoDisponible, leer_config

print("=== ACTIVACION ===")
casos = {
    "sin config":            {},
    "deshabilitado":         {"enabled": False, "ordenes_query": "SELECT 1"},
    "habilitado sin query":  {"enabled": True, "project_id": "p"},
    "habilitado con tabla":  {"enabled": True, "project_id": "p",
                              "ordenes_table": "proj.ds.ordenes"},
    "habilitado con query":  {"enabled": True, "project_id": "p",
                              "ordenes_query": "SELECT * FROM t",
                              "otif_query": "SELECT * FROM o"},
}
for nombre, config in casos.items():
    origen = BigQuerySource.desde_config(config)
    detalle = f"{len(origen.consultas)} consultas · {origen.fingerprint}" if origen else "—"
    print(f"  {nombre:24} -> {'ACTIVO' if origen else 'inactivo':9} {detalle}")

print("\n=== TABLA -> CONSULTA ===")
o = BigQuerySource.desde_config({"enabled": True, "project_id": "p",
                                 "ordenes_table": "proj.ds.ordenes"})
print("  ", o.consultas["ordenes"])

print("\n=== FALLA CONTROLADA (sin credenciales ni libreria) ===")
o = BigQuerySource.desde_config({"enabled": True, "project_id": "p",
                                 "ordenes_query": "SELECT 1"})
for etiqueta, fn in (("headers()", o.headers), ("load()", lambda: o.load("ordenes"))):
    try:
        fn()
        print(f"  {etiqueta:11} -> devolvio datos (hay credenciales en el entorno)")
    except BigQueryNoDisponible as e:
        print(f"  {etiqueta:11} -> BigQueryNoDisponible: {str(e)[:70]}")
    except Exception as e:
        print(f"  {etiqueta:11} -> {type(e).__name__}: {str(e)[:70]}")

print("\n=== leer_config CON SECRETS VACIOS ===")
class SecretsFalsos(dict):
    def get(self, k, d=None): return super().get(k, d)
config, cuenta = leer_config(SecretsFalsos())
print("  config:", config, "| cuenta:", cuenta)

print("\n=== EL EXCEL SIGUE SIENDO EL RESPALDO ===")
from core import repository
from core.sources import ExcelSource
m = contexto.modelo()
print("  modelo desde Excel usable:", m.report.usable, "| ordenes:", len(m.ordenes))

print("\nORIGEN DIRECTO OPCIONAL: OK")
