# -*- coding: utf-8 -*-
"""Persistencia del modelo ya procesado.

Procesar el Excel cuesta ~25 s.  Como el archivo sólo cambia una vez al día o a
la semana, el resultado se guarda en parquet bajo la huella del archivo: la
segunda apertura del dashboard es instantánea, y la carga sólo se rehace cuando
el contenido realmente cambió.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from .normalize import DatasetReport, LoadReport
from .transform import DataModel


def _cache_dir() -> Path:
    """Directorio de caché fuera de la carpeta del proyecto.

    El proyecto vive en OneDrive: escribir aquí los parquet dispararía una
    sincronización en cada carga. Se usa el almacenamiento local del usuario.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    if base:
        return Path(base) / "OperatividadEcommerce" / "cache"
    return Path.home() / ".operatividad_ecommerce" / "cache"


CACHE_DIR = _cache_dir()
TABLES = ("ordenes", "otif", "carrier", "quiebres")

#: Subir este número invalida las cargas guardadas. Hay que hacerlo cuando cambia
#: la forma en que se procesan los datos (limpieza, campos derivados, tipos).
PIPELINE_VERSION = 1


def _schema_hash() -> str:
    """Huella del esquema: editar los aliases o los umbrales rehace la carga."""
    from .normalize import CONFIG_PATH

    try:
        return hashlib.sha1(Path(CONFIG_PATH).read_bytes()).hexdigest()[:8]
    except OSError:
        return "nofile"


def _slot(fingerprint: str) -> Path:
    # La clave combina el contenido del archivo, el esquema y la versión del
    # procesamiento: así nunca se sirve un resultado calculado con reglas viejas.
    return CACHE_DIR / f"v{PIPELINE_VERSION}-{_schema_hash()}-{fingerprint}"


def exists(fingerprint: str) -> bool:
    return (_slot(fingerprint) / "meta.json").exists()


def save(model: DataModel, fingerprint: str) -> None:
    slot = _slot(fingerprint)
    slot.mkdir(parents=True, exist_ok=True)
    for name in TABLES:
        frame = getattr(model, name)
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            _to_parquet(frame, slot / f"{name}.parquet")
    meta = {
        "source": model.report.source,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "business": model.business,
        "messages": model.report.messages,
        "datasets": {k: asdict(v) for k, v in model.report.datasets.items()},
    }
    (slot / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, default=str), encoding="utf-8")


def load(fingerprint: str) -> DataModel | None:
    slot = _slot(fingerprint)
    meta_path = slot / "meta.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        frames = {}
        for name in TABLES:
            path = slot / f"{name}.parquet"
            frames[name] = pd.read_parquet(path) if path.exists() else pd.DataFrame()
    except Exception:
        return None
    report = LoadReport(source=meta.get("source", ""), messages=meta.get("messages", []))
    for key, payload in meta.get("datasets", {}).items():
        report.datasets[key] = DatasetReport(**payload)
    return DataModel(report=report, business=meta.get("business", {}), **frames)


def saved_at(fingerprint: str) -> str:
    meta_path = _slot(fingerprint) / "meta.json"
    if not meta_path.exists():
        return ""
    try:
        return json.loads(meta_path.read_text(encoding="utf-8")).get("saved_at", "")
    except Exception:
        return ""


def list_slots() -> list[dict]:
    """Cargas guardadas, de la más reciente a la más antigua."""
    out = []
    if not CACHE_DIR.exists():
        return out
    for slot in CACHE_DIR.iterdir():
        meta_path = slot / "meta.json"
        if not meta_path.exists():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        out.append({
            "fingerprint": slot.name,
            "source": meta.get("source", ""),
            "saved_at": meta.get("saved_at", ""),
            "rows": sum(d.get("rows", 0) for d in meta.get("datasets", {}).values()),
        })
    return sorted(out, key=lambda d: d["saved_at"], reverse=True)


def prune(keep: int = 5) -> None:
    """Conserva sólo las cargas más recientes."""
    for slot in list_slots()[keep:]:
        shutil.rmtree(CACHE_DIR / slot["fingerprint"], ignore_errors=True)


def _to_parquet(frame: pd.DataFrame, path: Path) -> None:
    """Escribe a parquet tolerando columnas de tipo mixto."""
    out = frame.copy()
    for column in out.columns:
        if out[column].dtype == object:
            out[column] = out[column].astype("string")
    try:
        out.to_parquet(path, index=False)
    except Exception:
        out.astype({c: "string" for c in out.columns if out[c].dtype == object}).to_parquet(
            path, index=False
        )
