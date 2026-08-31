# -*- coding: utf-8 -*-
"""Autenticación del Control Center.

Las credenciales viven en `.streamlit/secrets.toml` (nunca en el código):

    [app_auth]
    username = "admin"
    password = "..."

    # o varios usuarios
    [app_auth.users]
    "hugo.camara@forus.pe" = "..."

Si no hay credenciales configuradas la app queda abierta, para no bloquear un
entorno local recién clonado.
"""
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

import streamlit as st


@dataclass
class Sesion:
    autenticado: bool
    usuario: str = ""
    abierta: bool = False        # True cuando no hay credenciales configuradas


def _limpiar(valor) -> str:
    return str(valor).strip() if valor is not None else ""


def _normalizar_usuario(valor) -> str:
    return _limpiar(valor).lower()


def usuarios_configurados() -> dict[str, str]:
    """Mapa usuario -> contraseña, desde secrets o variables de entorno."""
    try:
        config = dict(st.secrets.get("app_auth", {}))
    except Exception:
        config = {}

    tabla: dict[str, str] = {}
    for usuario, clave in dict(config.get("users", {}) or {}).items():
        if _normalizar_usuario(usuario) and _limpiar(clave):
            tabla[_normalizar_usuario(usuario)] = _limpiar(clave)

    usuario = _normalizar_usuario(config.get("username"))
    clave = _limpiar(config.get("password"))
    if usuario and clave:
        tabla[usuario] = clave

    # Respaldo por entorno, útil en despliegues sin secrets.toml.
    usuario_env = _normalizar_usuario(os.environ.get("OPS_USER"))
    clave_env = _limpiar(os.environ.get("OPS_PASSWORD"))
    if usuario_env and clave_env:
        tabla[usuario_env] = clave_env
    return tabla


def sesion_actual() -> Sesion:
    if not usuarios_configurados():
        return Sesion(autenticado=True, usuario="local", abierta=True)
    if st.session_state.get("auth_ok"):
        return Sesion(autenticado=True, usuario=st.session_state.get("auth_user", ""))
    return Sesion(autenticado=False)


def verificar(usuario: str, clave: str) -> bool:
    """Compara en tiempo constante para no filtrar información por timing."""
    tabla = usuarios_configurados()
    esperado = tabla.get(_normalizar_usuario(usuario))
    if not esperado:
        return False
    return hmac.compare_digest(_limpiar(clave), esperado)


def iniciar_sesion(usuario: str) -> None:
    st.session_state["auth_ok"] = True
    st.session_state["auth_user"] = _normalizar_usuario(usuario)


def cerrar_sesion() -> None:
    for clave in ("auth_ok", "auth_user"):
        st.session_state.pop(clave, None)
