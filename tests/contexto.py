# -*- coding: utf-8 -*-
"""Utilidades comunes a las pruebas.

Localiza el Excel maestro sin rutas fijas, para que las pruebas corran en
cualquier equipo: primero la variable `OPS_MASTER_PATH`, luego el descubrimiento
automático que ya usa la aplicación.
"""
from __future__ import annotations

import io
import os
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

# Las pruebas imprimen acentos; en Windows la consola no siempre es UTF-8.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from core.master import FuenteMaestra          # noqa: E402
from core.sources import ExcelSource           # noqa: E402


def ruta_maestro() -> pathlib.Path | None:
    ruta = os.environ.get("OPS_MASTER_PATH", "").strip()
    if ruta and pathlib.Path(ruta).exists():
        return pathlib.Path(ruta)
    return FuenteMaestra.descubrir()


def modelo(obligatorio: bool = True):
    """Modelo procesado desde la caché; None si no hay archivo ni caché."""
    from core import repository

    ruta = ruta_maestro()
    if ruta is None:
        if obligatorio:
            print("SALTADA: no se encontró el Excel maestro.\n"
                  "         Defina OPS_MASTER_PATH o deje el archivo en Descargas.")
            sys.exit(0)
        return None

    origen = ExcelSource(ruta)
    datos = repository.load(origen.fingerprint)
    if datos is None:
        from core.transform import build_model

        print(f"Procesando {ruta.name} por primera vez…")
        datos = build_model(origen)
        try:
            repository.save(datos, origen.fingerprint)
        except Exception:
            pass
    return datos


def fuente():
    ruta = ruta_maestro()
    return ExcelSource(ruta) if ruta else None
