# -*- coding: utf-8 -*-
"""Origen directo sobre BigQuery.

Es opcional: se activa sólo con `[bigquery].enabled = true` en los secrets.
Cumple el mismo contrato `DataSource` que el Excel, de modo que el resto de la
aplicación —normalización, KPIs, filtros, gráficos— no cambia.

Si la librería no está instalada, faltan credenciales o la consulta falla, la
aplicación sigue funcionando con el Excel maestro.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import pandas as pd

from .sources import DataSource, TableHeader, _dedupe

#: Consulta esperada por conjunto. Cada una debe devolver las columnas del
#: Excel (o cualquier alias declarado en config/schema.yml).
CONJUNTOS = ("ordenes", "otif", "carrier", "quiebres")


class BigQueryNoDisponible(RuntimeError):
    """El origen no se puede usar; el llamador debe caer al Excel."""


@dataclass
class BigQuerySource(DataSource):
    """Lee cada conjunto con su propia consulta."""

    consultas: dict[str, str] = field(default_factory=dict)
    project_id: str = ""
    job_project_id: str = ""
    location: str = ""
    credenciales: dict | None = None
    _cliente: object = None
    _cache: dict = field(default_factory=dict)

    # -- construcción -------------------------------------------------------
    @classmethod
    def desde_config(cls, config: dict, credenciales: dict | None = None) -> "BigQuerySource | None":
        """Devuelve el origen si está habilitado y tiene al menos una consulta."""
        config = dict(config or {})
        if not config.get("enabled"):
            return None

        consultas: dict[str, str] = {}
        for nombre in CONJUNTOS:
            query = str(config.get(f"{nombre}_query", "") or "").strip()
            tabla = str(config.get(f"{nombre}_table", "") or "").strip()
            if query:
                consultas[nombre] = query
            elif tabla:
                consultas[nombre] = f"SELECT * FROM `{tabla}`"
        if not consultas:
            return None

        project = str(config.get("project_id", "") or "").strip()
        return cls(
            consultas=consultas,
            project_id=project,
            job_project_id=str(config.get("job_project_id", "") or project).strip(),
            location=str(config.get("location", "") or "").strip(),
            credenciales=dict(credenciales) if credenciales else None,
        )

    # -- contrato DataSource ------------------------------------------------
    @property
    def label(self) -> str:
        return f"BigQuery · {self.project_id or 'sin proyecto'}"

    @property
    def fingerprint(self) -> str:
        payload = repr(sorted(self.consultas.items())).encode()
        return "bq-" + hashlib.sha1(payload).hexdigest()[:16]

    def cliente(self):
        """Cliente perezoso: sólo se crea cuando de verdad se va a consultar."""
        if self._cliente is not None:
            return self._cliente
        try:
            from google.cloud import bigquery
        except ImportError as exc:
            raise BigQueryNoDisponible(
                "Falta la librería google-cloud-bigquery. Instálela con "
                "`pip install google-cloud-bigquery` o deje [bigquery].enabled = false."
            ) from exc

        try:
            if self.credenciales:
                from google.oauth2 import service_account

                cred = service_account.Credentials.from_service_account_info(self.credenciales)
                self._cliente = bigquery.Client(
                    project=self.job_project_id or self.project_id, credentials=cred)
            else:
                self._cliente = bigquery.Client(project=self.job_project_id or self.project_id)
        except Exception as exc:
            raise BigQueryNoDisponible(f"No se pudo crear el cliente de BigQuery: {exc}") from exc
        return self._cliente

    def _consultar(self, query: str) -> pd.DataFrame:
        cliente = self.cliente()
        try:
            trabajo = cliente.query(query, location=self.location or None)
            return trabajo.result().to_dataframe()
        except Exception as exc:
            raise BigQueryNoDisponible(f"La consulta falló: {str(exc)[:200]}") from exc

    def headers(self) -> list[TableHeader]:
        """Descubre columnas con un LIMIT 0: no lee datos ni consume cuota real."""
        salida: list[TableHeader] = []
        for nombre, query in self.consultas.items():
            muestra = self._consultar(f"SELECT * FROM ({query}) AS t LIMIT 0")
            salida.append(TableHeader(
                name=nombre, columns=_dedupe([str(c) for c in muestra.columns]),
                origin=f"BigQuery · {nombre}"))
        return salida

    def load(self, name: str) -> pd.DataFrame:
        if name in self._cache:
            return self._cache[name]
        marco = self._consultar(self.consultas[name])
        marco.columns = _dedupe([str(c) for c in marco.columns])
        self._cache[name] = marco
        return marco


def leer_config(secrets) -> tuple[dict, dict | None]:
    """Extrae `[bigquery]` y `[gcp_service_account]` de los secrets."""
    try:
        config = dict(secrets.get("bigquery", {}))
    except Exception:
        config = {}
    try:
        cuenta = dict(secrets.get("gcp_service_account", {}))
    except Exception:
        cuenta = {}
    return config, (cuenta or None)
