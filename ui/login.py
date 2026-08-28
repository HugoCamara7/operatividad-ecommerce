# -*- coding: utf-8 -*-
"""Pantalla de acceso al Operatividad Control Center."""
from __future__ import annotations

import base64
from pathlib import Path

import streamlit as st

from core import auth

LOGO = Path(__file__).resolve().parent.parent / "assets" / "forus_logo.png"

CSS = """
<style>
[data-testid="stSidebar"], [data-testid="stToolbar"], .stDeployButton { display:none !important; }
/* La barra superior de Streamlit dejaba una franja clara sobre el fondo. */
[data-testid="stHeader"] { display:none !important; }
#MainMenu, footer { visibility:hidden; }

/* Fondo: degradado profundo con dos halos, sin imágenes externas */
[data-testid="stAppViewContainer"] {
  background:
    radial-gradient(760px 420px at 14% 6%, rgba(35,103,255,.30) 0%, rgba(35,103,255,0) 62%),
    radial-gradient(680px 400px at 88% 92%, rgba(34,184,220,.22) 0%, rgba(34,184,220,0) 60%),
    linear-gradient(158deg,#0A1F49 0%,#0F2A5F 48%,#071633 100%);
}
.main .block-container { padding-top:7vh; max-width:640px; }

/* Malla sutil de fondo */
[data-testid="stAppViewContainer"]::before {
  content:""; position:fixed; inset:0; pointer-events:none; opacity:.28;
  background-image:
    linear-gradient(rgba(255,255,255,.05) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255,255,255,.05) 1px, transparent 1px);
  background-size:46px 46px;
}

.st-key-login_card {
  width:min(432px, calc(100vw - 32px)); margin:0 auto; overflow:hidden;
  border-radius:18px; background:#fff; color-scheme:light;
  box-shadow:0 34px 90px rgba(3,12,32,.55), 0 0 0 1px rgba(255,255,255,.10);
}

.login-head {
  padding:30px 32px 28px; text-align:center; position:relative;
  background:linear-gradient(140deg,#1650CC 0%,#2367FF 55%,#3C82FF 100%);
  color:#fff;
}
.login-head::after {
  content:""; position:absolute; inset:auto 0 0 0; height:3px;
  background:linear-gradient(90deg,#22B8DC,#7C5CFF,transparent);
}
.login-logo {
  width:60px; height:60px; margin:0 auto 16px; border-radius:16px;
  background:rgba(255,255,255,.14); border:1px solid rgba(255,255,255,.28);
  display:grid; place-items:center; backdrop-filter:blur(6px);
}
.login-logo img { max-width:42px; max-height:42px; object-fit:contain; }
.login-logo .mark { font-size:22px; font-weight:900; letter-spacing:-.04em; color:#fff; }
.login-head .title { margin:0; font-size:22px; line-height:1.16; font-weight:850; letter-spacing:-.02em; }
.login-head p {
  margin:8px 0 0; color:#D6E5FF; font-size:11px; font-weight:600;
  letter-spacing:.18em; text-transform:uppercase;
  font-family:'IBM Plex Mono',monospace;
}

.st-key-login_form { padding:26px 32px 10px; background:#fff; color-scheme:light; }
.st-key-login_form label {
  color:#41527A !important; font-weight:700 !important; font-size:10px !important;
  letter-spacing:.13em !important; text-transform:uppercase !important;
  font-family:'IBM Plex Mono',monospace !important;
}
.st-key-login_form .stTextInput input {
  border-radius:10px; min-height:46px; background:#F7F9FC !important;
  border:1px solid #D5DFEC !important; font-size:14.5px; color:#0B1B46 !important;
  caret-color:#0B1B46 !important; -webkit-text-fill-color:#0B1B46 !important;
  color-scheme:light !important;
}
.st-key-login_form .stTextInput input:focus {
  border-color:#2367FF !important; box-shadow:0 0 0 3px rgba(35,103,255,.16) !important;
}
.st-key-login_form .stTextInput input::placeholder {
  color:#94A3B8 !important; -webkit-text-fill-color:#94A3B8 !important; opacity:1 !important;
}
.st-key-login_form div[data-baseweb="input"], .st-key-login_form div[data-baseweb="base-input"] {
  background:#F7F9FC !important; color:#0B1B46 !important; color-scheme:light !important;
}
.st-key-login_form .stTextInput input:-webkit-autofill {
  -webkit-text-fill-color:#0B1B46 !important;
  -webkit-box-shadow:0 0 0 1000px #F7F9FC inset !important;
  transition:background-color 9999s ease-out 0s;
}
.st-key-login_form .stTextInput button, .st-key-login_form .stTextInput svg {
  color:#64748B !important; fill:currentColor !important;
}
.st-key-login_form .stButton button, .st-key-login_form button[kind="primaryFormSubmit"] {
  width:100%; min-height:46px; border-radius:10px; margin-top:.35rem;
  background:linear-gradient(120deg,#2367FF,#1650CC); border:none; color:#fff;
  font-weight:800; font-size:14px; letter-spacing:.01em;
  box-shadow:0 12px 26px -12px rgba(35,103,255,.95);
  white-space:nowrap !important;
}
.st-key-login_form button[kind="primaryFormSubmit"]:hover { filter:brightness(1.08); color:#fff; }

.login-note {
  padding:6px 32px 26px; text-align:center; color:#8494AE;
  font-size:11px; font-weight:600; letter-spacing:.04em;
  font-family:'IBM Plex Mono',monospace;
}
.login-foot {
  margin:22px auto 0; width:min(432px, calc(100vw - 32px)); text-align:center;
  color:#A9C4EE; font-size:12px; line-height:1.7;
}
.login-foot strong { display:block; color:#fff; font-size:13px; font-weight:750; margin-bottom:2px; }
.login-foot span { font-family:'IBM Plex Mono',monospace; font-size:10.5px; letter-spacing:.12em; }
</style>
"""


def _logo_html() -> str:
    """Logo desde assets si existe; si no, la marca tipográfica."""
    try:
        if LOGO.exists():
            datos = base64.b64encode(LOGO.read_bytes()).decode()
            return f'<img src="data:image/png;base64,{datos}" alt="Forus">'
    except OSError:
        pass
    return '<div class="mark">OC</div>'


def render() -> bool:
    """Dibuja el acceso. Devuelve True si la sesión ya está iniciada."""
    sesion = auth.sesion_actual()
    if sesion.autenticado:
        return True

    st.markdown(CSS, unsafe_allow_html=True)

    with st.container(key="login_card"):
        st.markdown(
            f'<div class="login-head">'
            f'<div class="login-logo">{_logo_html()}</div>'
            f'<div class="title">Operatividad Control Center</div>'
            f'<p>Ecommerce · Perú</p>'
            f'</div>',
            unsafe_allow_html=True)

        with st.container(key="login_form"):
            with st.form("form_login", clear_on_submit=False):
                usuario = st.text_input("Usuario", placeholder="nombre.apellido@forus.pe")
                clave = st.text_input("Contraseña", type="password", placeholder="••••••••")
                enviado = st.form_submit_button("Ingresar", type="primary")

        st.markdown('<div class="login-note">Acceso exclusivo para personal autorizado</div>',
                    unsafe_allow_html=True)

    st.markdown(
        '<div class="login-foot"><strong>Centro de control de la operación ecommerce</strong>'
        '<span>VENTAS · FULFILLMENT · LOGÍSTICA · OTIF</span></div>',
        unsafe_allow_html=True)

    if enviado:
        if auth.verificar(usuario, clave):
            auth.iniciar_sesion(usuario)
            st.rerun()
        st.error("Usuario o contraseña incorrectos.", icon="🔒")
    return False
