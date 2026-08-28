# -*- coding: utf-8 -*-
"""Identidad visual del Operatividad Control Center."""
from __future__ import annotations

import streamlit as st

# ---------------------------------------------------------------------------
#  Paleta
# ---------------------------------------------------------------------------
NAVY = "#0F2A5F"
NAVY_DEEP = "#0A1F49"
NAVY_BAR = "#132E63"
ACCENT = "#2367FF"
ACCENT_SOFT = "#4F8BFF"
ACCENT_PALE = "#E8F0FF"
CYAN = "#22B8DC"
INK = "#0B1B46"
MUTED = "#64748B"
GREEN = "#0EA06A"
RED = "#E1364C"
AMBER = "#E08A0B"
LINE = "#E4EAF3"
SURFACE = "#FFFFFF"
CANVAS = "#F3F6FB"

#: Secuencia categórica: azules del sistema y apoyos de contraste.
SERIES = [NAVY, ACCENT, CYAN, "#7C5CFF", GREEN, AMBER, RED,
          "#8FA6C7", "#0E7490", "#C026D3"]

#: Alias por rol, usados por gráficos y semáforos.
GOOD, WARN, BAD = GREEN, AMBER, RED
ACCENT_DEEP = "#1650CC"

SEMAFORO_COLOR = {"bueno": GREEN, "alerta": AMBER, "critico": RED, "": MUTED}
SEMAFORO_TEXTO = {"bueno": "En meta", "alerta": "En riesgo", "critico": "Fuera de meta", "": ""}


def page_config() -> None:
    st.set_page_config(
        page_title="Operatividad Control Center",
        page_icon="◧",
        layout="wide",
        initial_sidebar_state="collapsed",
    )


# ---------------------------------------------------------------------------
#  Hoja de estilos
# ---------------------------------------------------------------------------
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap');

:root {{
  --navy:{NAVY}; --navy-deep:{NAVY_DEEP}; --navy-bar:{NAVY_BAR};
  --accent:{ACCENT}; --accent-soft:{ACCENT_SOFT}; --accent-pale:{ACCENT_PALE};
  --cyan:{CYAN}; --ink:{INK}; --muted:{MUTED};
  --good:{GREEN}; --bad:{RED}; --warn:{AMBER};
  --line:{LINE}; --surface:{SURFACE}; --canvas:{CANVAS};
  --mono:'IBM Plex Mono',ui-monospace,Menlo,monospace;
  --r-lg:16px; --r-md:12px; --r-sm:9px;
  --sh-sm:0 1px 2px rgba(11,27,70,.05);
  --sh-md:0 1px 3px rgba(11,27,70,.05), 0 10px 26px -14px rgba(11,27,70,.30);
  --sh-lg:0 20px 46px -22px rgba(11,27,70,.42);
}}

html, body, [class*="css"] {{ font-family:'Inter',system-ui,sans-serif; -webkit-font-smoothing:antialiased; }}
.stApp {{ background:var(--canvas); }}
#MainMenu, footer, [data-testid="stToolbar"], .stDeployButton {{ display:none !important; }}
/* La barra superior de Streamlit flota sobre el contenido: se retira para que
   la cabecera propia empiece en el borde de la ventana. */
[data-testid="stHeader"] {{ display:none !important; }}
[data-testid="stAppViewContainer"] > .main {{ padding-top:0; }}
section[data-testid="stSidebar"] {{ display:none; }}
.block-container {{ padding:0 2rem 4.5rem; max-width:1660px; }}

/* ==================================================================
   CABECERA
   ================================================================== */
.hdr {{
  position:relative;
  width:100vw; max-width:none; margin-left:calc(50% - 50vw); margin-bottom:0;
  padding:.85rem max(2rem, calc(50vw - 830px)) .9rem;
  background:linear-gradient(112deg,var(--navy-deep) 0%,var(--navy) 52%,#123A82 100%);
  box-shadow:0 6px 22px -10px rgba(10,31,73,.6);
}}
.hdr::after {{
  content:""; position:absolute; inset:auto 0 0 0; height:2px;
  background:linear-gradient(90deg,var(--accent),var(--cyan),transparent);
}}
.hdr-row {{ display:flex; align-items:center; justify-content:space-between; gap:1.4rem; flex-wrap:wrap; }}
.hdr-brand {{ display:flex; align-items:center; gap:.7rem; }}
.hdr-mark {{
  width:38px; height:38px; border-radius:11px; flex:none; display:grid; place-items:center;
  background:linear-gradient(140deg,var(--accent),#7C5CFF);
  box-shadow:0 8px 20px -7px rgba(35,103,255,.85);
  color:#fff; font-weight:900; font-size:.86rem; letter-spacing:-.03em;
}}
.hdr-brand .title {{ margin:0; font-size:1.02rem; font-weight:800; color:#fff; letter-spacing:-.022em; line-height:1.15; }}
.hdr-brand span {{
  font-family:var(--mono); font-size:.58rem; letter-spacing:.19em;
  text-transform:uppercase; color:#8FB2E8;
}}
.hdr-side {{ display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; }}

/* Píldora de estado de la fuente */
.src {{
  display:flex; align-items:center; gap:.5rem;
  background:rgba(255,255,255,.09); border:1px solid rgba(255,255,255,.16);
  border-radius:999px; padding:.3rem .75rem .3rem .55rem;
}}
.src .led {{ width:8px; height:8px; border-radius:50%; flex:none; }}
.src .led.ok      {{ background:#2BD98C; box-shadow:0 0 0 3px rgba(43,217,140,.22); }}
.src .led.error   {{ background:#FF6B7D; box-shadow:0 0 0 3px rgba(255,107,125,.22); }}
.src .led.pendiente {{ background:#F0B429; box-shadow:0 0 0 3px rgba(240,180,41,.22); }}
.src b {{ color:#EAF2FF; font-size:.72rem; font-weight:650; }}
.src small {{ font-family:var(--mono); color:#93B4E8; font-size:.63rem; display:block; }}
.hdr-user {{ font-family:var(--mono); font-size:.66rem; color:#93B4E8; }}

/* ==================================================================
   NAVEGACIÓN POR PESTAÑAS
   ================================================================== */
.st-key-nav {{
  width:100vw; max-width:none !important;
  margin-left:calc(50% - 50vw); margin-bottom:1.15rem;
  padding:.42rem max(2rem, calc(50vw - 830px)) 0;
  background:linear-gradient(180deg,#0C2454 0%,#0A1F49 100%);
}}
.st-key-nav div[role="radiogroup"] {{
  gap:.2rem; background:transparent; border:none; padding:0;
  display:flex; flex-wrap:wrap;
}}
.st-key-nav div[role="radiogroup"] > label {{
  margin:0; padding:.44rem .9rem; border-radius:9px 9px 0 0;
  border:1px solid transparent; border-bottom:none;
  transition:background .14s ease, color .14s ease;
}}
.st-key-nav div[role="radiogroup"] > label:hover {{ background:rgba(255,255,255,.09); }}
.st-key-nav div[role="radiogroup"] > label p {{
  font-size:.795rem !important; font-weight:600; color:#A8C4EE !important;
  letter-spacing:-.005em; margin:0;
}}
.st-key-nav div[role="radiogroup"] > label:has(input:checked) {{
  background:var(--canvas); border-color:var(--line);
}}
.st-key-nav div[role="radiogroup"] > label:has(input:checked) p {{
  color:var(--navy) !important; font-weight:750;
}}
.st-key-nav div[role="radiogroup"] input {{ display:none; }}

/* ==================================================================
   BARRA DE FILTROS
   ================================================================== */
.st-key-filtros {{
  background:var(--surface); border:1px solid var(--line); border-radius:var(--r-md);
  box-shadow:var(--sh-sm); padding:.65rem .85rem .3rem; margin-bottom:.9rem;
}}
.filtro-tag {{
  font-family:var(--mono); font-size:.6rem; font-weight:600; letter-spacing:.12em;
  text-transform:uppercase; color:var(--muted); margin-bottom:.15rem; display:block;
}}
.vs-pill {{
  display:inline-flex; align-items:center; gap:.4rem; font-family:var(--mono);
  font-size:.685rem; color:var(--navy); background:var(--accent-pale);
  border:1px solid #CFE0FF; border-radius:8px; padding:.3rem .6rem; white-space:nowrap;
}}
.vs-pill i {{ font-style:normal; color:var(--accent); font-weight:700; }}

/* ==================================================================
   TÍTULO DE SECCIÓN
   ================================================================== */
.sec {{ display:flex; align-items:flex-end; justify-content:space-between; gap:1rem; margin:.15rem 0 .8rem; }}
.sec-title {{ display:flex; align-items:center; gap:.55rem; }}
.sec-title .bar {{ width:3px; height:19px; border-radius:2px; flex:none;
  background:linear-gradient(180deg,var(--accent),var(--cyan)); }}
.sec-title .title {{ margin:0; font-size:1.14rem; font-weight:750; color:var(--ink); letter-spacing:-.024em; }}
.sec-meta {{ font-family:var(--mono); font-size:.67rem; color:var(--muted); }}
.sec-chips {{ display:flex; gap:.3rem; flex-wrap:wrap; justify-content:flex-end; }}
.sec-chip {{
  font-family:var(--mono); font-size:.63rem; color:var(--accent-deep, #1650CC);
  background:var(--accent-pale); border:1px solid #CFE0FF; border-radius:6px; padding:.16rem .46rem;
}}
.sec-chip.ghost {{ color:var(--muted); background:#EFF3F9; border-color:var(--line); }}

.section-label {{
  font-family:var(--mono); font-size:.63rem; font-weight:600; letter-spacing:.15em;
  text-transform:uppercase; color:var(--muted); margin:1.35rem 0 .55rem;
  display:flex; align-items:center; gap:.6rem;
}}
.section-label::after {{ content:""; flex:1; height:1px;
  background:linear-gradient(90deg,var(--line),rgba(228,234,243,0)); }}

/* ==================================================================
   TARJETAS KPI
   ================================================================== */
.kpi {{
  position:relative; background:var(--surface); border:1px solid var(--line);
  border-radius:var(--r-md); padding:.82rem .92rem .72rem; box-shadow:var(--sh-md);
  height:100%; overflow:hidden;
  transition:transform .17s cubic-bezier(.2,.8,.3,1), box-shadow .17s ease, border-color .17s ease;
}}
.kpi::before {{
  content:""; position:absolute; inset:0 0 auto 0; height:3px;
  background:linear-gradient(90deg,var(--accent),var(--cyan));
}}
.kpi.good::before {{ background:linear-gradient(90deg,var(--good),#34D9A0); }}
.kpi.warn::before {{ background:linear-gradient(90deg,var(--warn),#F5C048); }}
.kpi.bad::before  {{ background:linear-gradient(90deg,var(--bad),#FF7C8E); }}
.kpi:hover {{ transform:translateY(-3px); box-shadow:var(--sh-lg); border-color:#D2E0F4; }}

.kpi-top {{ display:flex; align-items:center; gap:.5rem; margin:.2rem 0 .5rem; }}
.kpi .ico {{
  width:29px; height:29px; border-radius:8px; flex:none; display:grid; place-items:center;
  font-size:.86rem; background:var(--accent-pale); border:1px solid #D8E6FF;
}}
.kpi .label {{
  font-family:var(--mono); font-size:.6rem; font-weight:600; letter-spacing:.12em;
  text-transform:uppercase; color:var(--muted); line-height:1.3;
}}
.kpi .value {{
  font-size:clamp(1.2rem,1.85vw,1.62rem); font-weight:800; color:var(--ink);
  letter-spacing:-.035em; line-height:1.06; font-variant-numeric:tabular-nums; white-space:nowrap;
}}

/* Fila de comparación: referencia · diferencia · variación */
.kpi-cmp {{
  display:flex; align-items:center; gap:.4rem; flex-wrap:wrap;
  margin-top:.5rem; padding-top:.45rem; border-top:1px dashed var(--line);
}}
.kpi-cmp .ref {{ font-family:var(--mono); font-size:.645rem; color:var(--muted); }}
.kpi-cmp .ref b {{ color:#41527A; font-weight:600; }}
.delta {{
  display:inline-flex; align-items:center; gap:.15rem; font-family:var(--mono);
  font-size:.655rem; font-weight:700; padding:.09rem .34rem; border-radius:5px;
  font-variant-numeric:tabular-nums;
}}
.delta.up   {{ color:#046C4E; background:#E1F7EF; }}
.delta.down {{ color:#9F1239; background:#FDE8EC; }}
.delta.flat {{ color:var(--muted); background:#EFF3F9; }}
.kpi .foot {{ font-family:var(--mono); font-size:.645rem; color:var(--muted); margin-top:.35rem; }}
.spark {{ position:absolute; right:.7rem; top:.68rem; opacity:.5; pointer-events:none; }}
@media (max-width:1150px) {{ .spark {{ display:none; }} }}

/* ==================================================================
   PANELES
   ================================================================== */
.block-container [data-testid="stVerticalBlockBorderWrapper"]:has(> div > div > div > .panel-head) {{
  background:var(--surface); border:1px solid var(--line); border-radius:var(--r-lg);
  box-shadow:var(--sh-md); padding:.85rem 1rem .9rem;
  transition:box-shadow .17s ease, border-color .17s ease;
}}
.block-container [data-testid="stVerticalBlockBorderWrapper"]:has(> div > div > div > .panel-head):hover {{
  box-shadow:var(--sh-lg); border-color:#D8E3F2;
}}
.panel-head {{ margin-bottom:.35rem; }}
.panel-head .title {{
  margin:0; font-size:.83rem; font-weight:700; color:var(--ink); letter-spacing:-.012em;
  display:flex; align-items:center; gap:.4rem;
}}
.panel-head .hint {{ font-family:var(--mono); font-size:.645rem; color:var(--muted); margin-top:.14rem; }}

/* ==================================================================
   TABLAS
   ================================================================== */
.tbl-wrap {{
  background:var(--surface); border:1px solid var(--line); border-radius:var(--r-md);
  box-shadow:var(--sh-md); overflow:hidden;
}}
.tbl-scroll {{ overflow-x:auto; }}
table.rep {{ width:100%; border-collapse:collapse; font-family:var(--mono); font-size:.685rem; }}
table.rep thead th {{
  position:sticky; top:0; background:var(--navy-bar); color:#fff; font-weight:600;
  letter-spacing:.04em; text-align:left; padding:.56rem .78rem; white-space:nowrap; font-size:.655rem;
}}
table.rep tbody td {{
  padding:.48rem .78rem; color:#33415C; border-bottom:1px solid #F1F4F9; white-space:nowrap;
}}
table.rep tbody tr:nth-child(even) {{ background:#FAFBFE; }}
table.rep tbody tr:hover {{ background:var(--accent-pale); }}
table.rep tbody tr:last-child td {{ border-bottom:none; }}
table.rep td.key {{ color:var(--accent); font-weight:600; }}
table.rep td.num {{ text-align:right; }}
table.rep td.pos {{ color:var(--good); font-weight:700; }}
table.rep td.neg {{ color:var(--bad);  font-weight:700; }}
table.rep tfoot td {{
  background:#EEF3FA; font-weight:700; color:var(--navy);
  padding:.5rem .78rem; border-top:1px solid var(--line);
}}
/* Barra de magnitud dentro de la celda */
.cellbar {{ position:relative; display:block; }}
.cellbar i {{
  position:absolute; left:0; top:50%; transform:translateY(-50%); height:15px;
  background:linear-gradient(90deg,rgba(35,103,255,.20),rgba(34,184,220,.14));
  border-radius:3px; z-index:0;
}}
.cellbar span {{ position:relative; z-index:1; }}

/* ==================================================================
   VARIOS
   ================================================================== */
.note {{
  background:linear-gradient(96deg,#F5F9FF,#FFFFFF 65%);
  border:1px solid #DAE7FB; border-left:3px solid var(--accent);
  border-radius:10px; padding:.62rem .85rem; font-size:.79rem; color:#26436E; line-height:1.55;
}}
.note b {{ color:var(--navy); font-weight:700; }}

.sem {{ font-family:var(--mono); font-size:.6rem; font-weight:700; padding:.11rem .38rem; border-radius:5px; }}
.sem.bueno   {{ color:#046C4E; background:#E1F7EF; }}
.sem.alerta  {{ color:#8A5B0B; background:#FDF3E0; }}
.sem.critico {{ color:#9F1239; background:#FDE8EC; }}

.empty {{
  text-align:center; padding:2rem 1rem; color:var(--muted); font-size:.77rem;
  background:var(--surface); border:1px dashed #D6E0EE; border-radius:var(--r-md);
  font-family:var(--mono);
}}
.empty b {{ display:block; color:var(--ink); font-size:.86rem; margin-bottom:.25rem; font-family:'Inter',sans-serif; }}

/* Controles */
.stButton > button, .stDownloadButton > button {{
  border-radius:9px; font-size:.75rem; font-weight:650; font-family:'Inter',sans-serif;
  background:var(--surface); border:1px solid var(--line); color:var(--ink);
  padding:.34rem .85rem; transition:all .14s ease;
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
  border-color:var(--accent); color:var(--accent); background:#F7FAFF; transform:translateY(-1px);
}}
.stButton > button[kind="primary"] {{
  background:linear-gradient(120deg,var(--accent),#1650CC); border-color:transparent; color:#fff;
  box-shadow:0 8px 20px -10px rgba(35,103,255,.9);
}}
.stButton > button[kind="primary"]:hover {{ color:#fff; filter:brightness(1.07); }}

.block-container div[role="radiogroup"]:not(.st-key-nav *) {{
  gap:.22rem; background:#EBF0F8; padding:.2rem; border-radius:8px;
  display:inline-flex; border:1px solid var(--line);
}}
.block-container div[role="radiogroup"]:not(.st-key-nav *) > label {{ padding:.2rem .68rem; border-radius:6px; margin:0; }}
.block-container div[role="radiogroup"]:not(.st-key-nav *) > label p {{
  font-family:var(--mono); font-size:.69rem !important; font-weight:500; color:var(--muted);
}}
.block-container div[role="radiogroup"]:not(.st-key-nav *) > label:has(input:checked) {{
  background:#fff; box-shadow:var(--sh-sm);
}}
.block-container div[role="radiogroup"]:not(.st-key-nav *) > label:has(input:checked) p {{
  color:var(--navy) !important; font-weight:700;
}}
.block-container div[role="radiogroup"]:not(.st-key-nav *) input {{ display:none; }}

/* ==================================================================
   MARCADOR DE LOS RADIOS
   Streamlit dibuja un círculo de 16x16 antes del texto de cada opción.
   En este panel los radios funcionan como pestañas, así que sólo debe
   verse la etiqueta. El texto vive en el hermano stMarkdownContainer.
   ================================================================== */
label[data-testid="stRadioOption"] > div > div > div:first-child {{
  display:none !important;
}}
label[data-testid="stRadioOption"] > div > div {{ gap:0 !important; }}

[data-baseweb="select"] > div, [data-baseweb="input"] > div {{
  border-radius:8px; border-color:var(--line); font-size:.76rem; min-height:34px;
}}
[data-baseweb="select"] > div:hover {{ border-color:var(--accent-soft); }}
.stMultiSelect label, .stSelectbox label, .stDateInput label, .stSlider label, .stTextInput label {{
  font-family:var(--mono); font-size:.6rem !important; font-weight:600; letter-spacing:.12em;
  text-transform:uppercase; color:var(--muted) !important;
}}
[data-baseweb="tag"] {{ background:var(--navy) !important; border-radius:5px; font-size:.65rem; }}

[data-testid="stFileUploader"] {{
  background:linear-gradient(180deg,#FBFDFF,#fff); border:1.5px dashed #C4D8F2;
  border-radius:var(--r-md); padding:.5rem;
}}
[data-testid="stFileUploader"]:hover {{ border-color:var(--accent); background:#F7FBFF; }}
[data-testid="stDataFrame"] {{ border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
[data-testid="stExpander"] {{ border:1px solid var(--line); border-radius:10px; background:#fff; }}
[data-testid="stExpander"] summary p {{ font-family:var(--mono); font-size:.71rem; font-weight:600; }}

.status-row {{ display:flex; align-items:center; gap:.5rem; font-size:.75rem; padding:.4rem .1rem; border-bottom:1px dashed var(--line); }}
.status-row:last-child {{ border-bottom:none; }}
.status-pill {{ font-family:var(--mono); font-size:.6rem; font-weight:700; text-transform:uppercase; padding:.11rem .4rem; border-radius:5px; flex:none; }}
.status-pill.ok      {{ color:#046C4E; background:#E1F7EF; }}
.status-pill.parcial {{ color:#8A5B0B; background:#FDF3E0; }}
.status-pill.error   {{ color:#9F1239; background:#FDE8EC; }}
.status-pill.ausente {{ color:#475569; background:#EEF2F7; }}
.mono {{ font-family:var(--mono); font-size:.7rem; }}

/* Tarjeta de fuente de datos */
.srccard {{
  background:var(--surface); border:1px solid var(--line); border-radius:var(--r-lg);
  box-shadow:var(--sh-md); padding:1rem 1.1rem; height:100%;
}}
.srccard .title {{ margin:0 0 .7rem; font-size:.8rem; font-weight:700; color:var(--ink);
  display:flex; align-items:center; gap:.42rem; }}
.srccard .row {{ display:flex; justify-content:space-between; gap:1rem; padding:.36rem 0;
  border-bottom:1px dashed var(--line); font-size:.735rem; }}
.srccard .row:last-child {{ border-bottom:none; }}
.srccard .row span {{ color:var(--muted); }}
.srccard .row b {{ font-family:var(--mono); color:var(--ink); font-weight:600; font-size:.7rem;
  text-align:right; word-break:break-all; }}

hr {{ margin:.7rem 0; border-color:var(--line); }}
[data-testid="stSpinner"] > div {{ border-top-color:var(--accent) !important; }}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
#  Plantilla común de gráficos
# ---------------------------------------------------------------------------
def plotly_layout(height: int = 300, legend: bool = True, margin_top: int = 10) -> dict:
    return dict(
        height=height,
        margin=dict(l=4, r=8, t=margin_top, b=4),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="IBM Plex Mono, monospace", size=10.5, color=INK),
        hoverlabel=dict(
            bgcolor="white", bordercolor=LINE,
            font=dict(family="IBM Plex Mono, monospace", size=11, color=INK),
        ),
        legend=dict(
            orientation="h", yanchor="top", y=-0.06, xanchor="center", x=0.5,
            font=dict(size=9.5, color=MUTED), title_text="",
        ) if legend else dict(visible=False),
        xaxis=dict(showgrid=False, linecolor=LINE, tickfont=dict(color=MUTED, size=9.5), title_text=""),
        yaxis=dict(gridcolor="#EDF1F7", zerolinecolor="#EDF1F7",
                   tickfont=dict(color=MUTED, size=9.5), title_text=""),
    )
