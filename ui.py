"""
ui.py — Capa visual de iMenu App.

  * cargar_estilos()      -> inyecta style.css (una vez, al inicio)
  * encabezado()          -> título + subtítulo de página
  * kpi()                 -> tarjeta KPI con sombra suave
  * grafico_matriz()      -> matriz de ingeniería de menú de un período
  * grafico_comparacion() -> movimiento de cada plato entre dos períodos
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RUTA_CSS = Path(__file__).parent / "style.css"

# Paleta de las 4 clasificaciones, elegida y validada para el fondo oscuro:
# las cuatro superan 3:1 de contraste contra la superficie del gráfico y se
# distinguen entre sí también con daltonismo. Además cada punto lleva su
# nombre escrito y la posición en el cuadrante ya dice la categoría, así que
# el color nunca es la única pista.
COLORES = {
    "Estrella": "#199e70",
    "Caballo de batalla": "#3987e5",
    "Puzzle": "#b58900",
    "Perro": "#e66767",
}
ORDEN = ("Estrella", "Caballo de batalla", "Puzzle", "Perro")
CLASE_CSS = {
    "Estrella": "tag-estrella",
    "Caballo de batalla": "tag-caballo",
    "Puzzle": "tag-puzzle",
    "Perro": "tag-perro",
}

_INK, _MUTED = "#e6e8ec", "#98a1b2"
_GRID, _BORDE = "#242a36", "#272d3a"
_SUPERFICIE, _CORTE = "#171b24", "#4b5464"


# ---------------------------------------------------------------------------
# Estilos y componentes
# ---------------------------------------------------------------------------
def cargar_estilos() -> None:
    if RUTA_CSS.exists():
        st.markdown(
            f"<style>{RUTA_CSS.read_text(encoding='utf-8')}</style>",
            unsafe_allow_html=True,
        )


# ---------------------------------------------------------------------------
# Logo
# ---------------------------------------------------------------------------
def logo_svg(tamano: int = 34, _contador=[0]) -> str:
    """Marca de la app: un plato dividido en cuatro cuadrantes, con el punto
    en el cuadrante de las estrellas. Es la matriz de ingeniería de menú
    dibujada sobre un plato.

    El id del degradado se numera porque el logo puede aparecer más de una vez
    en la misma página y dos <defs> con el mismo id se pisan.
    """
    _contador[0] += 1
    gid = f"imenu-grad-{_contador[0]}"
    return f"""
<svg width="{tamano}" height="{tamano}" viewBox="0 0 48 48" fill="none"
     xmlns="http://www.w3.org/2000/svg" role="img" aria-label="iMenu App">
  <defs>
    <linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#4a8ff0"/>
      <stop offset="100%" stop-color="#1c5cab"/>
    </linearGradient>
  </defs>
  <rect x="1.5" y="1.5" width="45" height="45" rx="13" fill="url(#{gid})"/>
  <circle cx="24" cy="24" r="13.5" fill="none" stroke="#e3ecfb" stroke-width="1.8" opacity=".92"/>
  <path d="M24 9.5 V38.5 M9.5 24 H38.5" stroke="#e3ecfb" stroke-width="1.1" opacity=".5"/>
  <circle cx="31" cy="17" r="4.4" fill="#5fd9b4"/>
</svg>""".strip()


def marca(tamano: int = 34, mostrar_texto: bool = True) -> str:
    """Logo + nombre, para la barra lateral y el encabezado."""
    texto = ('<div class="marca-texto"><span class="marca-nombre">iMenu</span>'
             '<span class="marca-sub">Ingeniería de Menú</span></div>') if mostrar_texto else ""
    return f'<div class="marca">{logo_svg(tamano)}{texto}</div>'


def encabezado(titulo: str, subtitulo: str = "", con_logo: bool = False) -> None:
    izquierda = (f'<div class="titulo-con-logo">{logo_svg(30)}<h1>{titulo}</h1></div>'
                 if con_logo else f"<div><h1>{titulo}</h1></div>")
    st.markdown(
        f"""<div class="page-header">
              {izquierda}
              <div class="subtitulo">{subtitulo}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def kpi(label: str, valor: str, pie: str = "", tono: str = "") -> None:
    """Tarjeta KPI. `tono`: "" (azul), "ok", "warn" o "bad"."""
    st.markdown(
        f"""<div class="kpi {tono}">
              <p class="kpi-label">{label}</p>
              <p class="kpi-valor">{valor}</p>
              {f'<p class="kpi-pie">{pie}</p>' if pie else ''}
            </div>""",
        unsafe_allow_html=True,
    )


def etiqueta(clasificacion: str) -> str:
    return f'<span class="tag {CLASE_CSS.get(clasificacion, "")}">{clasificacion}</span>'


def _layout_base(fig: go.Figure, alto: int = 470) -> go.Figure:
    fig.update_layout(
        height=alto,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=_SUPERFICIE,
        font=dict(family="Inter, sans-serif", size=13, color=_INK),
        margin=dict(l=10, r=10, t=54, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0,
                    title=None, bgcolor="rgba(0,0,0,0)"),
        hoverlabel=dict(bgcolor="#1d2230", bordercolor=_BORDE,
                        font=dict(family="Inter", color=_INK)),
    )
    return fig


def _ejes(fig: go.Figure, titulo_x: str, titulo_y: str) -> go.Figure:
    fig.update_xaxes(title_text=titulo_x, gridcolor=_GRID, zeroline=False,
                     linecolor=_BORDE, title_font=dict(size=12, color=_MUTED),
                     tickfont=dict(color=_MUTED))
    fig.update_yaxes(title_text=titulo_y, gridcolor=_GRID, zeroline=False,
                     linecolor=_BORDE, title_font=dict(size=12, color=_MUTED),
                     tickfont=dict(color=_MUTED))
    return fig


# ---------------------------------------------------------------------------
# Matriz de ingeniería de menú
# ---------------------------------------------------------------------------
def grafico_matriz(df: pd.DataFrame, moneda: str = "$") -> go.Figure | None:
    """Popularidad (x) contra margen de contribución unitario neto (y)."""
    requeridas = {"popularidad", "margen_unitario", "clasificacion", "item_name"}
    if df.empty or not requeridas.issubset(df.columns):
        return None

    corte_x = float(df["popularidad_minima"].iloc[0]) * 100
    corte_y = float(df["margen_promedio_ponderado"].iloc[0])

    fig = go.Figure()
    for nombre in ORDEN:
        sub = df[df["clasificacion"] == nombre]
        if sub.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=sub["popularidad"] * 100,
                y=sub["margen_unitario"],
                mode="markers+text",
                name=nombre,
                text=sub["item_name"],
                textposition="top center",
                textfont=dict(size=10, color=_MUTED),
                marker=dict(size=15, color=COLORES[nombre],
                            line=dict(color=_SUPERFICIE, width=2)),
                customdata=sub[["units_sold", "price_neto", "cost_neto", "category"]],
                hovertemplate=(
                    "<b>%{text}</b><br>%{customdata[3]}<br>"
                    "Popularidad: %{x:.1f}%<br>"
                    f"Margen unitario: {moneda}" + "%{y:,.2f}<br>"
                    "Unidades: %{customdata[0]:,.0f}<br>"
                    f"Precio neto: {moneda}" + "%{customdata[1]:,.2f} · "
                    f"Costo neto: {moneda}" + "%{customdata[2]:,.2f}"
                    "<extra></extra>"
                ),
            )
        )

    fig.add_vline(x=corte_x, line=dict(color=_CORTE, width=1, dash="dot"))
    fig.add_hline(y=corte_y, line=dict(color=_CORTE, width=1, dash="dot"))

    _layout_base(fig)
    return _ejes(
        fig,
        "Popularidad (% de unidades vendidas dentro de la categoría)",
        f"Margen de contribución unitario, sin IVA ({moneda})",
    )


# ---------------------------------------------------------------------------
# Comparación entre dos períodos
# ---------------------------------------------------------------------------
def grafico_comparacion(comp: pd.DataFrame, moneda: str = "$") -> go.Figure | None:
    """Flecha por plato: dónde estaba en el período A y dónde quedó en el B.

    Solo se dibujan los platos presentes en ambos períodos; los que aparecen
    o desaparecen no tienen punto de partida o de llegada que comparar.
    """
    necesarias = {"popularidad_a", "popularidad_b", "margen_unitario_a",
                  "margen_unitario_b", "clasificacion_b", "item_name"}
    if comp.empty or not necesarias.issubset(comp.columns):
        return None

    ambos = comp[comp["estado"] == "Se mantiene"].copy()
    if ambos.empty:
        return None

    fig = go.Figure()

    # 1. Trayectos (gris, sin leyenda): de dónde salió cada plato.
    xs, ys = [], []
    for _, r in ambos.iterrows():
        xs += [r["popularidad_a"] * 100, r["popularidad_b"] * 100, None]
        ys += [r["margen_unitario_a"], r["margen_unitario_b"], None]
    fig.add_trace(
        go.Scatter(x=xs, y=ys, mode="lines", showlegend=False, hoverinfo="skip",
                   line=dict(color="#3f4759", width=1.5))
    )

    # 2. Posición en el período A: círculo hueco.
    fig.add_trace(
        go.Scatter(
            x=ambos["popularidad_a"] * 100, y=ambos["margen_unitario_a"],
            mode="markers", name="Período A (origen)",
            marker=dict(size=9, color=_SUPERFICIE,
                        line=dict(color="#7d879a", width=2)),
            text=ambos["item_name"],
            hovertemplate="<b>%{text}</b><br>Período A<br>"
                          "Popularidad: %{x:.1f}%<br>"
                          f"Margen: {moneda}" + "%{y:,.2f}<extra></extra>",
        )
    )

    # 3. Posición en el período B: punto lleno, coloreado por su clasificación final.
    for nombre in ORDEN:
        sub = ambos[ambos["clasificacion_b"] == nombre]
        if sub.empty:
            continue
        fig.add_trace(
            go.Scatter(
                x=sub["popularidad_b"] * 100, y=sub["margen_unitario_b"],
                mode="markers+text", name=f"B · {nombre}",
                text=sub["item_name"], textposition="top center",
                textfont=dict(size=10, color=_MUTED),
                marker=dict(size=15, color=COLORES[nombre],
                            line=dict(color=_SUPERFICIE, width=2)),
                customdata=sub[["movimiento", "dif_unidades_sem"]],
                hovertemplate=(
                    "<b>%{text}</b><br>%{customdata[0]}<br>"
                    "Popularidad: %{x:.1f}%<br>"
                    f"Margen: {moneda}" + "%{y:,.2f}<br>"
                    "Unidades/semana: %{customdata[1]:+,.1f}<extra></extra>"
                ),
            )
        )

    _layout_base(fig, alto=520)
    return _ejes(
        fig,
        "Popularidad (% de unidades vendidas dentro de la categoría)",
        f"Margen de contribución unitario, sin IVA ({moneda})",
    )

# ---------------------------------------------------------------------------
# Principios de Omnes
# ---------------------------------------------------------------------------
# Rampa ordinal de una sola tonalidad para las tres gamas: más claro = más caro,
# porque sobre fondo oscuro lo más claro es lo que más resalta. Validada para
# contraste y para lectura con daltonismo.
COLORES_GAMA = {
    "Baja":  "#1c5cab",
    "Media": "#6da7ec",
    "Alta":  "#cde2fb",
}
OPACIDAD_BANDA = {"Baja": 0.10, "Media": 0.15, "Alta": 0.20}
ORDEN_GAMA = ("Baja", "Media", "Alta")


def grafico_omnes(res: dict, moneda: str = "$", titulo: str = "") -> go.Figure | None:
    """Dispersión de precios de la carta, con las tres gamas, el PMO y el PMD.

    Cada plato es un punto ubicado por su precio; el tamaño representa las
    unidades vendidas. Así se ve de una sola mirada si la carta está escalonada
    (dispersión), cuán abierta es (amplitud) y hacia qué lado se corre la
    demanda respecto de la oferta (PMD contra PMO).

    Las etiquetas van en posiciones fijas y a alturas distintas, en coordenadas
    de datos, en lugar de dejárselas a Plotly: así no se encima nada aunque el
    PMO y el PMD caigan casi en el mismo precio.
    """
    datos = res.get("datos")
    if datos is None or datos.empty:
        return None

    precio_col = "precio_cargado"
    lim = res["dispersion"]["limites"]
    od = res["oferta_demanda"]

    d = datos.sort_values(precio_col).reset_index(drop=True)
    d["_y"] = [(i % 5) - 2 for i in range(len(d))]   # escalonado determinista

    unidades = pd.to_numeric(d["units_sold"], errors="coerce").fillna(0)
    maximo = float(unidades.max()) or 1.0
    d["_tam"] = 11 + (unidades / maximo) * 23

    Y_MIN, Y_MAX = -4.6, 4.2
    Y_ETIQUETA_GAMA = 3.7
    Y_PMO, Y_PMD = -3.4, -4.2

    fig = go.Figure()

    # --- Bandas de las tres gamas -------------------------------------------
    if lim["banda"] > 0:
        bordes = [(lim["pmin"], lim["corte_bajo"], "Baja"),
                  (lim["corte_bajo"], lim["corte_alto"], "Media"),
                  (lim["corte_alto"], lim["pmax"], "Alta")]
        for x0, x1, nombre in bordes:
            fig.add_vrect(x0=x0, x1=x1, line_width=0,
                          fillcolor=COLORES_GAMA[nombre],
                          opacity=OPACIDAD_BANDA[nombre], layer="below")
            fig.add_annotation(
                x=(x0 + x1) / 2, y=Y_ETIQUETA_GAMA, text=f"GAMA {nombre.upper()}",
                showarrow=False, xanchor="center",
                font=dict(size=10, color=COLORES_GAMA[nombre], family="Inter"),
            )
        # Líneas divisorias: el corte entre gamas tiene que verse, no adivinarse.
        for corte in (lim["corte_bajo"], lim["corte_alto"]):
            fig.add_shape(type="line", x0=corte, x1=corte, y0=Y_MIN, y1=Y_ETIQUETA_GAMA - 0.5,
                          line=dict(color="#57617a", width=1), layer="below")

    # --- Platos --------------------------------------------------------------
    for nombre in ORDEN_GAMA:
        sub = d[d["gama"] == nombre]
        if sub.empty:
            continue
        fig.add_trace(go.Scatter(
            x=sub[precio_col], y=sub["_y"], mode="markers+text",
            name=f"Gama {nombre.lower()} ({len(sub)})",
            text=sub["item_name"], textposition="top center",
            textfont=dict(size=10, color="#aeb7c6"),
            marker=dict(size=sub["_tam"], color=COLORES_GAMA[nombre],
                        line=dict(color=_SUPERFICIE, width=2)),
            customdata=sub[["units_sold", "category"]],
            hovertemplate=("<b>%{text}</b><br>%{customdata[1]}<br>"
                           f"Precio: {moneda}" + "%{x:,.2f}<br>"
                           "Unidades: %{customdata[0]:,.0f}<extra></extra>"),
        ))

    # --- PMO y PMD -----------------------------------------------------------
    # Dos estilos bien distintos: el ofertado es gris y punteado fino; el
    # demandado es ámbar y continuo. Se distinguen aunque queden pegados.
    COLOR_PMO, COLOR_PMD = "#9aa3b2", "#f0a63c"
    for x, y, color, dash, ancho, texto in (
        (od["pmo"], Y_PMO, COLOR_PMO, "dot", 1.6,
         f"PMO (ofertado) {moneda}{od['pmo']:,.0f}"),
        (od["pmd"], Y_PMD, COLOR_PMD, "solid", 2.4,
         f"PMD (demandado) {moneda}{od['pmd']:,.0f}"),
    ):
        fig.add_shape(type="line", x0=x, x1=x, y0=Y_MIN, y1=Y_MAX,
                      line=dict(color=color, width=ancho, dash=dash))
        fig.add_annotation(
            x=x, y=y, text=texto, showarrow=False, xanchor="left", xshift=8,
            bgcolor="rgba(23,27,36,.92)", bordercolor=color, borderwidth=1,
            borderpad=4, font=dict(size=11, color=color, family="Inter"),
        )

    _layout_base(fig, alto=500)
    if titulo:
        fig.update_layout(title=dict(text=titulo, font=dict(size=14, color=_MUTED)))
    fig.update_xaxes(title_text=f"Precio de venta ({moneda})", gridcolor=_GRID,
                     zeroline=False, linecolor=_BORDE,
                     title_font=dict(size=12, color=_MUTED), tickfont=dict(color=_MUTED))
    fig.update_yaxes(visible=False, showgrid=False, range=[Y_MIN - 0.4, Y_MAX])
    return fig
