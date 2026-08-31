# -*- coding: utf-8 -*-
"""Normalización de encabezados y validación de estructura.

Reglas de oro:
  * Nunca se lee una columna por posición, siempre por nombre.
  * El emparejamiento tolera mayúsculas, tildes, espacios, guiones y signos.
  * Si falta una columna crítica se informa exactamente cuál, sin romper la app.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "schema.yml"


# ---------------------------------------------------------------------------
#  Configuración
# ---------------------------------------------------------------------------
def load_schema(path: Path | str = CONFIG_PATH) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
#  Clave de comparación de encabezados
# ---------------------------------------------------------------------------
_PUNCT = re.compile(r"[^a-z0-9]+")


def slug(name: object) -> str:
    """Clave canónica de un encabezado.

    'SKU', 'Sku', ' sku ', 'S.K.U.'  ->  'sku'
    'Método de Pago', 'Metodo_de_Pago' -> 'metododepago'
    """
    text = "" if name is None else str(name)
    text = text.replace("_x000a_", " ").replace("\n", " ").replace("\r", " ")
    # Repara mojibake típico de doble codificación UTF-8 (Ã©, Â¿, ...).
    text = fix_mojibake(text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return _PUNCT.sub("", text.lower())


_MOJIBAKE_HINTS = ("Ã", "Â", "â€", "Ð")


def fix_mojibake(text: str) -> str:
    """Deshace texto UTF-8 leído como latin-1 ('MÃ©todo' -> 'Método')."""
    if not isinstance(text, str) or not any(h in text for h in _MOJIBAKE_HINTS):
        return text
    try:
        return text.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text


# ---------------------------------------------------------------------------
#  Resultado de la validación
# ---------------------------------------------------------------------------
@dataclass
class DatasetReport:
    """Qué se encontró (y qué faltó) al mapear un conjunto de datos."""

    key: str
    label: str
    found: bool = False
    origin: str = ""
    rows: int = 0
    mapped: dict[str, str] = field(default_factory=dict)      # canónico -> encabezado real
    missing_required: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    unmapped_columns: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.found and not self.missing_required

    @property
    def status(self) -> str:
        if not self.found:
            return "ausente"
        if self.missing_required:
            return "error"
        if self.missing_optional:
            return "parcial"
        return "ok"


@dataclass
class LoadReport:
    """Informe global de una carga."""

    source: str = ""
    datasets: dict[str, DatasetReport] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)

    @property
    def blocking_errors(self) -> list[str]:
        out = []
        for report in self.datasets.values():
            if report.found and report.missing_required:
                cols = ", ".join(f"'{c}'" for c in report.missing_required)
                out.append(
                    f"[{report.label}] Falta la columna crítica {cols}. "
                    f"Agregue el encabezado real a 'aliases' en config/schema.yml."
                )
        return out

    @property
    def usable(self) -> bool:
        """Hay al menos el maestro de órdenes utilizable."""
        orders = self.datasets.get("ordenes")
        return bool(orders and orders.ok)


# ---------------------------------------------------------------------------
#  Mapeo de una tabla cruda a un conjunto canónico
# ---------------------------------------------------------------------------
class SchemaMapper:
    def __init__(self, schema: dict):
        self.schema = schema
        self.datasets = schema["datasets"]
        # slug(alias) -> [campos canónicos candidatos], en orden de definición.
        # Es una lista porque encabezados distintos pueden compartir clave: al
        # ignorar espacios y guiones, 'Fecha Compra' y 'Fecha_Compra' colisionan.
        # Se resuelven por orden de aparición al mapear.
        self._index: dict[str, dict[str, list[str]]] = {}
        for key, spec in self.datasets.items():
            table: dict[str, list[str]] = {}
            for canonical, cfg in spec["fields"].items():
                keys = [slug(a) for a in cfg.get("aliases", [])] + [slug(canonical)]
                for alias_key in dict.fromkeys(keys):
                    table.setdefault(alias_key, []).append(canonical)
            self._index[key] = table

    # -- identificación -----------------------------------------------------
    def score(self, key: str, columns: list[str]) -> int:
        """Cuántas columnas 'firma' del dataset aparecen en la tabla."""
        spec = self.datasets[key]
        present = {slug(c) for c in columns}
        return sum(1 for sig in spec.get("signature", []) if slug(sig) in present)

    def identify(self, headers: list) -> dict[str, object]:
        """Asigna cada dataset al encabezado que mejor lo representa.

        Se elige por columnas firma, luego por columnas mapeables.  A igualdad se
        prefiere el candidato más barato de leer: Excel suele duplicar el mismo
        cache y no tiene sentido pagar por el más pesado.
        """
        chosen: dict[str, object] = {}
        for key, spec in self.datasets.items():
            minimum = spec.get("signature_min", len(spec.get("signature", [])) or 1)
            best, best_rank = None, None
            for header in headers:
                columns = list(header.columns)
                hits = self.score(key, columns)
                if hits < minimum:
                    continue
                mappable = sum(1 for c in columns if slug(c) in self._index[key])
                rank = (hits, mappable, -header.cost)
                if best_rank is None or rank > best_rank:
                    best, best_rank = header, rank
            if best is not None:
                chosen[key] = best
        return chosen

    # -- mapeo --------------------------------------------------------------
    def apply(self, key: str, frame: pd.DataFrame, origin: str = "") -> tuple[pd.DataFrame, DatasetReport]:
        """Renombra a nombres canónicos y produce el informe del dataset."""
        spec = self.datasets[key]
        report = DatasetReport(key=key, label=spec.get("label", key))
        report.found = True
        report.origin = origin

        lookup = self._index[key]
        rename: dict[str, str] = {}
        taken: set[str] = set()
        for column in frame.columns:
            candidates = lookup.get(slug(column), [])
            canonical = next((c for c in candidates if c not in taken), None)
            if canonical:
                rename[column] = canonical
                taken.add(canonical)
            else:
                report.unmapped_columns.append(str(column))

        out = frame.rename(columns=rename)[list(rename.values())].copy()
        report.mapped = {v: k for k, v in rename.items()}
        report.rows = len(out)

        for canonical, cfg in spec["fields"].items():
            if canonical in taken:
                continue
            expected = cfg.get("aliases", [canonical])[0]
            if cfg.get("required"):
                report.missing_required.append(expected)
            else:
                report.missing_optional.append(expected)
        return out, report

    def missing_report(self, key: str) -> DatasetReport:
        spec = self.datasets[key]
        return DatasetReport(key=key, label=spec.get("label", key), found=False)
