# -*- coding: utf-8 -*-
"""Lector de pivot caches de un archivo .xlsx.

El libro de Operatividad Ecommerce guarda sus tablas dinámicas sobre hojas que
viven en libros externos: en el archivo sólo quedan los resultados visibles y el
*pivot cache*, que sí contiene el detalle registro a registro.  Este módulo lee
ese cache directamente desde el XML comprimido.

Como los caches se construyen sobre rangos de hoja completa (A1:CC1048576),
arrastran ~1M de registros de relleno; se detectan y descartan sin materializarlos.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import unescape

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

_TOKEN = re.compile(rb'<([xnsdbe])(?:\s+v="([^"]*)")?\s*/?>|<(m)\s*/>')
# Un registro contiene datos con certeza si trae un número, una fecha o un texto no vacío.
_HAS_DATA = re.compile(rb'<[nd] v="|<s v="[^"]')
_ENTITIES = {"&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&apos;": "'"}
_EMPTY = (None, "", "-")


def _number(text: str):
    try:
        value = float(text)
    except ValueError:
        return text
    return int(value) if value.is_integer() and abs(value) < 2**53 else value


def _text(raw: bytes) -> str:
    value = raw.decode("utf-8", "replace")
    return unescape(value, _ENTITIES) if "&" in value else value


def list_caches(zf: zipfile.ZipFile) -> list[int]:
    """Índices de los pivot caches presentes en el libro."""
    found = set()
    for name in zf.namelist():
        match = re.fullmatch(r"xl/pivotCache/pivotCacheDefinition(\d+)\.xml", name)
        if match:
            found.add(int(match.group(1)))
    return sorted(found)


def cache_fields(zf: zipfile.ZipFile, index: int) -> tuple[list[str], list[list]]:
    """Nombres de campo y listas de ítems compartidos de un pivotCacheDefinition."""
    root = ET.fromstring(zf.read(f"xl/pivotCache/pivotCacheDefinition{index}.xml"))
    names: list[str] = []
    shared: list[list] = []
    for field in root.find(f"{NS}cacheFields"):
        names.append(field.get("name"))
        node = field.find(f"{NS}sharedItems")
        items = []
        if node is not None:
            for item in node:
                tag, value = item.tag[len(NS):], item.get("v")
                if tag == "m":
                    items.append(None)
                elif tag == "n":
                    items.append(_number(value))
                else:
                    items.append(value)
        shared.append(items)
    return names, shared


def _parse_record(body: bytes, n_fields: int, shared: list[list]) -> list:
    row = [None] * n_fields
    position = 0
    for match in _TOKEN.finditer(body):
        if position >= n_fields:
            break
        kind, value, missing = match.group(1, 2, 3)
        if missing:                              # <m/> -> valor ausente
            position += 1
            continue
        if kind == b"x":                         # referencia a ítem compartido
            column = shared[position]
            idx = int(value)
            row[position] = column[idx] if idx < len(column) else None
        elif kind == b"n":
            row[position] = _number(value.decode())
        elif kind == b"b":
            row[position] = value in (b"1", b"true")
        elif kind == b"e":                       # error de fórmula
            row[position] = None
        else:                                    # s (texto) | d (fecha)
            row[position] = _text(value)
        position += 1
    return row


def read_records(
    zf: zipfile.ZipFile,
    index: int,
    names: list[str],
    shared: list[list],
    chunk: int = 1 << 22,
) -> list[list]:
    """Registros reales del pivotCacheRecords indicado, sin las filas de relleno."""
    n_fields = len(names)
    rows: list[list] = []
    buffer = b""
    # Las filas de relleno de un mismo cache son idénticas byte a byte. Se guarda
    # su forma la primera vez y luego se descartan comparando, en vez de
    # tokenizar ~90 campos un millón de veces.
    blank_shapes: set[bytes] = set()
    with zf.open(f"xl/pivotCache/pivotCacheRecords{index}.xml") as handle:
        while True:
            data = handle.read(chunk)
            if not data:
                break
            buffer += data
            parts = buffer.split(b"</r>")
            buffer = parts.pop()
            for part in parts:
                start = part.rfind(b"<r>")
                if start < 0:
                    continue
                body = part[start + 3:]
                if body in blank_shapes:
                    continue
                if _HAS_DATA.search(body) is None:
                    row = _parse_record(body, n_fields, shared)
                    if not any(v not in _EMPTY for v in row):
                        if len(blank_shapes) < 32:   # cota por si hubiese variantes
                            blank_shapes.add(body)
                        continue
                else:
                    row = _parse_record(body, n_fields, shared)
                rows.append(row)
    return rows
