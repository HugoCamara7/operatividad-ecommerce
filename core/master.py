# -*- coding: utf-8 -*-
"""Conexión al Excel maestro.

El archivo se actualiza a diario o semanalmente, así que la aplicación lo busca
sola en lugar de exigir una subida manual cada vez.  Hay tres modos, en orden de
preferencia:

  local   ruta a la carpeta sincronizada (OneDrive/SharePoint monta el archivo
          como una ruta normal, así que basta con vigilar su fecha de
          modificación).  Es el modo más rápido y no necesita credenciales.
  url     enlace de descarga directa (OneDrive, SharePoint, Google Drive o
          cualquier HTTPS).  Es el modo para despliegues en la nube.
  upload  el usuario sube el archivo a mano.  Siempre queda como respaldo.

Configuración en `.streamlit/secrets.toml`:

    [datasource]
    modo = "local"                 # local | url | upload
    ruta = "C:/Users/.../BD Operación Ecommerce.xlsx"
    url  = "https://..."           # enlace compartido; se normaliza solo
    refrescar_cada_min = 60
"""
from __future__ import annotations

import base64
import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse

MODOS = ("local", "url", "upload")
TIEMPO_ESPERA = 60


# ---------------------------------------------------------------------------
#  Estado
# ---------------------------------------------------------------------------
@dataclass
class EstadoFuente:
    """Lo que la interfaz necesita mostrar sobre el origen de los datos."""

    modo: str = "upload"
    etiqueta: str = "Sin fuente configurada"
    conectado: bool = False
    detalle: str = ""
    actualizado: datetime | None = None
    tamano: int = 0
    huella: str = ""
    error: str = ""

    @property
    def estado(self) -> str:
        if self.error:
            return "error"
        if self.conectado:
            return "ok"
        return "pendiente"

    @property
    def actualizado_texto(self) -> str:
        if self.actualizado is None:
            return "—"
        meses = ("ene", "feb", "mar", "abr", "may", "jun",
                 "jul", "ago", "sep", "oct", "nov", "dic")
        f = self.actualizado
        return f"{f.day:02d} {meses[f.month - 1]} {f.year} · {f:%H:%M}"

    @property
    def tamano_texto(self) -> str:
        if not self.tamano:
            return "—"
        return f"{self.tamano / 1_048_576:.1f} MB"


# ---------------------------------------------------------------------------
#  Normalización de enlaces compartidos
# ---------------------------------------------------------------------------
def normalizar_url(url: str) -> str:
    """Convierte un enlace para compartir en uno de descarga directa.

    Los enlaces que entrega la interfaz de OneDrive, SharePoint o Drive
    devuelven una página HTML, no el archivo. Cada servicio tiene su forma de
    pedir el binario.
    """
    url = (url or "").strip()
    if not url:
        return ""
    dominio = (urlparse(url).netloc or "").lower()

    # Google Drive -> descarga directa por id
    if "drive.google.com" in dominio:
        match = re.search(r"/d/([A-Za-z0-9_-]{20,})", url) or re.search(r"[?&]id=([A-Za-z0-9_-]{20,})", url)
        if match:
            return f"https://drive.google.com/uc?export=download&id={match.group(1)}"
        return url

    # OneDrive personal -> API de shares
    if "onedrive.live.com" in dominio or "1drv.ms" in dominio:
        token = base64.urlsafe_b64encode(url.encode()).decode().rstrip("=")
        return f"https://api.onedrive.com/v1.0/shares/u!{token}/root/content"

    # SharePoint / OneDrive for Business -> parámetro de descarga
    if "sharepoint.com" in dominio:
        limpio = url.split("?")[0]
        return f"{limpio}?download=1"

    return url


# ---------------------------------------------------------------------------
#  Fuente maestra
# ---------------------------------------------------------------------------
@dataclass
class FuenteMaestra:
    modo: str = "upload"
    ruta: str = ""
    url: str = ""
    refrescar_cada_min: int = 60
    nombre: str = ""

    @classmethod
    def desde_config(cls, config: dict | None = None) -> "FuenteMaestra":
        """Lee secrets/entorno y, si no hay nada, busca el archivo conocido."""
        config = dict(config or {})
        modo = str(config.get("modo", "")).strip().lower()
        ruta = str(config.get("ruta", "") or os.environ.get("OPS_MASTER_PATH", "")).strip()
        url = str(config.get("url", "") or os.environ.get("OPS_MASTER_URL", "")).strip()

        if not modo:
            modo = "local" if ruta else ("url" if url else "")
        if modo not in MODOS:
            modo = ""

        fuente = cls(
            modo=modo or "upload",
            ruta=ruta,
            url=url,
            refrescar_cada_min=int(config.get("refrescar_cada_min", 60) or 60),
            nombre=str(config.get("nombre", "")).strip(),
        )
        if fuente.modo == "upload" and not ruta and not url:
            descubierta = fuente.descubrir()
            if descubierta:
                fuente.modo, fuente.ruta = "local", str(descubierta)
        return fuente

    # -- descubrimiento -----------------------------------------------------
    @staticmethod
    def descubrir() -> Path | None:
        """Busca el maestro en las ubicaciones habituales del equipo."""
        patrones = ("BD Operación Ecommerce.xlsx", "BD Operacion Ecommerce.xlsx")
        carpetas = [Path.home() / "Downloads", Path.home() / "Documents", Path.cwd()]
        for carpeta in Path.home().glob("OneDrive*"):
            carpetas.append(carpeta)
            carpetas.append(carpeta / "Documentos")
        for carpeta in carpetas:
            for nombre in patrones:
                candidato = carpeta / nombre
                if candidato.exists():
                    return candidato
        return None

    # -- estado -------------------------------------------------------------
    def estado(self) -> EstadoFuente:
        """Consulta barata: no descarga el archivo, sólo su metadato."""
        if self.modo == "local":
            return self._estado_local()
        if self.modo == "url":
            return self._estado_url()
        return EstadoFuente(modo="upload", etiqueta="Carga manual",
                            detalle="Suba el archivo para actualizar el reporte.")

    def _estado_local(self) -> EstadoFuente:
        ruta = Path(self.ruta)
        etiqueta = self.nombre or ruta.name
        if not ruta.exists():
            return EstadoFuente(modo="local", etiqueta=etiqueta, conectado=False,
                                detalle=str(ruta.parent),
                                error="No se encontró el archivo en la ruta configurada.")
        info = ruta.stat()
        return EstadoFuente(
            modo="local", etiqueta=etiqueta, conectado=True,
            detalle=str(ruta.parent),
            actualizado=datetime.fromtimestamp(info.st_mtime),
            tamano=info.st_size,
            huella=f"{info.st_size}-{int(info.st_mtime)}",
        )

    def _estado_url(self) -> EstadoFuente:
        destino = normalizar_url(self.url)
        etiqueta = self.nombre or (urlparse(self.url).netloc or "Enlace remoto")
        try:
            import requests

            respuesta = requests.head(destino, allow_redirects=True, timeout=TIEMPO_ESPERA)
            if respuesta.status_code >= 400:
                respuesta = requests.get(destino, stream=True, timeout=TIEMPO_ESPERA)
                respuesta.close()
            if respuesta.status_code >= 400:
                return EstadoFuente(modo="url", etiqueta=etiqueta, conectado=False,
                                    detalle=destino[:90],
                                    error=f"El servidor respondió {respuesta.status_code}.")
            cabeceras = respuesta.headers
            tamano = int(cabeceras.get("Content-Length") or 0)
            marca = cabeceras.get("Last-Modified") or cabeceras.get("Date") or ""
            actualizado = None
            if marca:
                try:
                    from email.utils import parsedate_to_datetime

                    actualizado = parsedate_to_datetime(marca)
                    if actualizado.tzinfo is not None:
                        actualizado = actualizado.astimezone().replace(tzinfo=None)
                except Exception:
                    actualizado = None
            return EstadoFuente(
                modo="url", etiqueta=etiqueta, conectado=True, detalle=destino[:90],
                actualizado=actualizado, tamano=tamano,
                huella=cabeceras.get("ETag") or f"{tamano}-{marca}",
            )
        except Exception as exc:
            return EstadoFuente(modo="url", etiqueta=etiqueta, conectado=False,
                                detalle=destino[:90], error=str(exc)[:160])

    # -- descarga -----------------------------------------------------------
    def leer(self) -> tuple[bytes, str]:
        """Devuelve (contenido, nombre). Lanza excepción si no se puede leer."""
        if self.modo == "local":
            ruta = Path(self.ruta)
            return ruta.read_bytes(), ruta.name
        if self.modo == "url":
            import requests

            destino = normalizar_url(self.url)
            respuesta = requests.get(destino, timeout=TIEMPO_ESPERA * 5)
            respuesta.raise_for_status()
            contenido = respuesta.content
            if not contenido[:2] == b"PK":
                raise ValueError(
                    "El enlace no devolvió un archivo .xlsx. Revise que sea de "
                    "descarga directa y que el permiso permita leerlo sin sesión.")
            return contenido, self.nombre or _nombre_desde(respuesta, destino)
        raise ValueError("La fuente está en modo manual: no hay nada que descargar.")


def _nombre_desde(respuesta, destino: str) -> str:
    disposicion = respuesta.headers.get("Content-Disposition", "")
    match = re.search(r'filename\*?=(?:UTF-8\'\')?"?([^";]+)', disposicion)
    if match:
        return match.group(1)
    nombre = Path(urlparse(destino).path).name
    return nombre or "maestro.xlsx"
