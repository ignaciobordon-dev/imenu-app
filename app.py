"""
app.py — iMenu App: ingeniería de menú por períodos.

Ejecutar con:  streamlit run app.py   (o doble clic en iniciar.bat)
"""

from __future__ import annotations

import re
import unicodedata
from datetime import date, timedelta

import pandas as pd
import streamlit as st

import analisis
import importador
import omnes
import supabase_client as db
import ui

st.set_page_config(
    page_title="iMenu App · Ingeniería de Menú",
    page_icon="🍽️",
    layout="wide",
    initial_sidebar_state="expanded",
)
ui.cargar_estilos()

OPCION_TODAS = "Todas las categorías (no recomendado)"


# ---------------------------------------------------------------------------
# Acceso
# ---------------------------------------------------------------------------
def pantalla_login() -> None:
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        ui.encabezado("iMenu App", "Ingeniería de Menú")
        tab_login, tab_registro = st.tabs(["Iniciar sesión", "Crear cuenta"])

        with tab_login:
            with st.form("login"):
                email = st.text_input("Correo electrónico")
                password = st.text_input("Contraseña", type="password")
                if st.form_submit_button("Entrar", type="primary", use_container_width=True):
                    ok, msg = db.sign_in(email, password)
                    (st.success if ok else st.error)(msg)
                    if ok:
                        st.rerun()

        with tab_registro:
            with st.form("registro"):
                nombre = st.text_input("Nombre y apellido")
                email_r = st.text_input("Correo electrónico", key="email_r")
                pass_r = st.text_input("Contraseña (mínimo 6 caracteres)",
                                       type="password", key="pass_r")
                if st.form_submit_button("Registrarme", type="primary", use_container_width=True):
                    ok, msg = db.sign_up(email_r, pass_r, nombre)
                    (st.success if ok else st.error)(msg)


# ---------------------------------------------------------------------------
# Selectores reutilizables
# ---------------------------------------------------------------------------
def _selector_por_id(label, ids, textos, key, preferido=None):
    """Desplegable cuyo VALOR es el id, no el texto.

    Es importante que sea así: el texto de un período incluye la cantidad de
    platos, y cambia cada vez que se guarda algo. Si el valor guardado fuera
    el texto, al cambiar la etiqueta Streamlit perdería la selección y saltaría
    a otro período sin avisar — que es exactamente cómo se termina cargando un
    archivo en el período equivocado.
    """
    if preferido is not None and int(preferido) in ids:
        st.session_state[key] = int(preferido)
    elif key in st.session_state and st.session_state[key] not in ids:
        del st.session_state[key]
    return st.selectbox(label, ids, format_func=lambda i: textos.get(i, str(i)), key=key)


def _sel_restaurante(key: str, label: str = "Restaurante"):
    rest = db.listar_restaurantes()
    if rest.empty:
        st.info("Todavía no tenés restaurantes. Creá uno en la pestaña **Restaurantes**.")
        return None
    ids = [int(x) for x in rest["id"].tolist()]
    textos = {int(r.id): str(r.nombre) for r in rest.itertuples()}
    elegido = _selector_por_id(label, ids, textos, key)
    return rest[rest["id"] == elegido].iloc[0]


def _sel_periodo(restaurante_id: int, key: str, label: str = "Período",
                 preferido: int | None = None):
    periodos = db.listar_periodos(restaurante_id)
    if periodos.empty:
        st.info("Este restaurante todavía no tiene períodos cargados.")
        return None
    ids = [int(x) for x in periodos["id"].tolist()]
    textos = {int(p["id"]): analisis.nombre_periodo(p) for _, p in periodos.iterrows()}
    elegido = _selector_por_id(label, ids, textos, key, preferido)
    return periodos[periodos["id"] == elegido].iloc[0]


def _sel_categoria(datos: pd.DataFrame, key: str) -> tuple[str | None, bool]:
    """Devuelve (categoría elegida o None, por_categoria)."""
    categorias = sorted(datos["category"].dropna().unique().tolist())
    opciones = categorias + [OPCION_TODAS]
    elegida = st.selectbox("Categoría a analizar", opciones, key=key)
    if elegida == OPCION_TODAS:
        return None, False
    return elegida, True


def _aviso_todas() -> None:
    st.warning(
        "Estás mezclando todas las categorías. La matriz compara cada plato "
        "contra el promedio del menú completo, así que una entrada barata va a "
        "parecer poco rentable frente a un plato principal, y un postre va a "
        "parecer poco popular frente a algo que se pide en cada mesa. "
        "Sirve como contraejemplo en clase, no para tomar decisiones."
    )


# ---------------------------------------------------------------------------
# Pantalla: Restaurantes
# ---------------------------------------------------------------------------
def pantalla_restaurantes() -> None:
    st.caption(
        "El IVA se configura acá una sola vez y se aplica a todos los períodos "
        "del restaurante. El análisis siempre se hace sobre valores sin IVA."
    )

    rest = db.listar_restaurantes()
    if not rest.empty:
        vista = rest[["nombre", "pais", "moneda", "iva_alicuota",
                      "precio_incluye_iva", "costo_incluye_iva"]].copy()
        vista.columns = ["Restaurante", "País", "Moneda", "IVA %",
                         "Precio con IVA", "Costo con IVA"]
        st.dataframe(vista, use_container_width=True, hide_index=True)

    with st.expander("➕ Crear un restaurante nuevo", expanded=rest.empty):
        with st.form("nuevo_restaurante"):
            c1, c2, c3 = st.columns([2, 1, 1])
            nombre = c1.text_input("Nombre *", placeholder="La Parrilla del Centro")
            pais = c2.text_input("País", placeholder="Uruguay")
            moneda = c3.text_input("Símbolo de moneda", value="$", max_chars=5)

            st.markdown("**Configuración de IVA**")
            c4, c5, c6 = st.columns([1, 1, 1])
            iva = c4.number_input(
                "Alícuota de IVA (%)", min_value=0.0, max_value=99.0,
                value=0.0, step=0.5,
                help="La que corresponde a gastronomía en tu país. Verificá la vigente.",
            )
            precio_con = c5.checkbox("El precio incluye IVA", value=True,
                                     help="Lo habitual: el precio de carta ya lo incluye.")
            costo_con = c6.checkbox("El costo incluye IVA", value=False,
                                    help="Lo habitual es que el costo ya venga neto.")

            if st.form_submit_button("Crear restaurante", type="primary"):
                ok, msg = db.crear_restaurante(
                    nombre, pais, moneda, iva, precio_con, costo_con
                )
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()

    if rest.empty:
        return

    with st.expander("✏️ Editar o eliminar un restaurante"):
        opciones = {r.nombre: int(r.id) for r in rest.itertuples()}
        elegido = st.selectbox("Restaurante a editar", list(opciones), key="edit_rest")
        fila = rest[rest["id"] == opciones[elegido]].iloc[0]

        with st.form("editar_restaurante"):
            c1, c2, c3 = st.columns([2, 1, 1])
            nombre_e = c1.text_input("Nombre", value=fila["nombre"])
            pais_e = c2.text_input("País", value=fila.get("pais") or "")
            moneda_e = c3.text_input("Moneda", value=fila.get("moneda") or "$", max_chars=5)
            c4, c5, c6 = st.columns(3)
            iva_e = c4.number_input("IVA (%)", min_value=0.0, max_value=99.0,
                                    value=float(fila["iva_alicuota"]), step=0.5)
            precio_e = c5.checkbox("El precio incluye IVA",
                                   value=bool(fila["precio_incluye_iva"]))
            costo_e = c6.checkbox("El costo incluye IVA",
                                  value=bool(fila["costo_incluye_iva"]))

            g1, g2 = st.columns([1, 1])
            if g1.form_submit_button("Guardar cambios", type="primary"):
                ok, msg = db.actualizar_restaurante(
                    int(fila["id"]), nombre=nombre_e.strip(), pais=pais_e.strip() or None,
                    moneda=moneda_e.strip() or "$", iva_alicuota=round(float(iva_e), 2),
                    precio_incluye_iva=bool(precio_e), costo_incluye_iva=bool(costo_e),
                )
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
            if g2.form_submit_button("Eliminar restaurante"):
                ok, msg = db.borrar_restaurante(int(fila["id"]))
                (st.success if ok else st.error)(msg)
                if ok:
                    st.rerun()
        st.caption("Eliminar un restaurante borra también sus períodos y sus platos.")


# ---------------------------------------------------------------------------
# Pantalla: Cargar período
# ---------------------------------------------------------------------------
def _fechas_sugeridas() -> tuple[date, date]:
    """Últimas 4 semanas completas terminadas el domingo pasado."""
    hoy = date.today()
    ultimo_domingo = hoy - timedelta(days=hoy.weekday() + 1)
    return ultimo_domingo - timedelta(days=27), ultimo_domingo


def _flash(texto: str) -> None:
    """Guarda un mensaje para mostrarlo después del rerun."""
    st.session_state["flash"] = texto


def _mostrar_flash() -> None:
    texto = st.session_state.pop("flash", None)
    if texto:
        st.success(texto)


def pantalla_cargar() -> None:
    _mostrar_flash()
    restaurante = _sel_restaurante("carga_rest")
    if restaurante is None:
        return

    sugerido_desde, sugerido_hasta = _fechas_sugeridas()
    with st.expander("➕ Crear un período nuevo", expanded=True):
        c1, c2, c3 = st.columns([1, 1, 1.4])
        desde = c1.date_input("Desde", value=sugerido_desde, format="DD/MM/YYYY")
        hasta = c2.date_input("Hasta", value=sugerido_hasta, format="DD/MM/YYYY")
        etiqueta = c3.text_input("Etiqueta (opcional)",
                                 placeholder="Antes del rediseño de carta")

        ok_periodo, dias, semanas, mensaje = analisis.validar_periodo(desde, hasta)
        (st.success if ok_periodo else st.error)(mensaje)
        st.caption(
            "El período tiene que abarcar semanas completas. En gastronomía un "
            "sábado no vende como un martes: cualquier múltiplo de 7 días "
            "contiene la misma cantidad de cada día, arranque el día que arranque, "
            "y así el mix no queda sesgado."
        )

        if st.button("Crear período", type="primary", disabled=not ok_periodo):
            ok, msg, nuevo_id = db.crear_periodo(
                int(restaurante["id"]), desde, hasta, etiqueta
            )
            (st.success if ok else st.error)(msg)
            if ok:
                # Dejar el período recién creado seleccionado abajo, para que
                # el archivo no termine cargándose en el período anterior.
                st.session_state["periodo_recien_creado"] = nuevo_id
                st.rerun()

    periodo = _sel_periodo(
        int(restaurante["id"]), "carga_periodo",
        "Período en el que voy a cargar los platos",
        preferido=st.session_state.pop("periodo_recien_creado", None),
    )
    if periodo is None:
        return

    st.markdown(
        f"<div class='panel'>Vas a cargar en <b>{restaurante['nombre']}</b> · "
        f"<b>{periodo['fecha_desde']} → {periodo['fecha_hasta']}</b> "
        f"({periodo['semanas']} semana/s, {int(periodo['items'])} platos ya cargados) · "
        f"IVA {restaurante['iva_alicuota']}% — precio "
        f"{'con' if restaurante['precio_incluye_iva'] else 'sin'} IVA, costo "
        f"{'con' if restaurante['costo_incluye_iva'] else 'sin'} IVA</div>",
        unsafe_allow_html=True,
    )

    tab_archivo, tab_manual = st.tabs(["📄 Importar archivo", "✍️ Planilla manual"])
    with tab_archivo:
        _importar_archivo(periodo)
    with tab_manual:
        _planilla_manual(periodo)

    with st.expander("🗑️ Eliminar este período"):
        st.caption("Borra el período y todos sus platos. No se puede deshacer.")
        if st.button("Eliminar período"):
            ok, msg = db.borrar_periodo(int(periodo["id"]))
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()


def _destino(periodo) -> str:
    return f"{periodo['fecha_desde']} → {periodo['fecha_hasta']}"


def _importar_archivo(periodo) -> None:
    periodo_id = int(periodo["id"])
    c1, c2 = st.columns([3, 1])
    c1.caption(
        "Subí un Excel (.xlsx) o un CSV con una fila por plato. La app reconoce "
        "sola los nombres de columna más comunes; si no acierta, los corregís abajo."
    )
    c2.download_button(
        "📥 Plantilla de ejemplo",
        data=importador.plantilla_bytes(),
        file_name="plantilla_imenu.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    archivo = st.file_uploader("Archivo", type=["xlsx", "xls", "csv", "txt"],
                               key=f"up_{periodo_id}")
    if archivo is None:
        return

    try:
        hojas = importador.listar_hojas(archivo)
        hoja = st.selectbox("Hoja", hojas) if len(hojas) > 1 else (hojas[0] if hojas else None)
        crudo = importador.leer(archivo, hoja)
    except Exception as exc:  # noqa: BLE001
        st.error(f"No pude leer el archivo: {exc}")
        return

    if crudo.empty:
        st.error("El archivo está vacío o no pude encontrar la fila de encabezados.")
        return

    st.markdown("**¿Qué columna es cada cosa?**")
    detectado = importador.detectar_columnas(crudo)
    columnas = ["— ninguna —"] + list(crudo.columns)
    mapeo: dict[str, str | None] = {}
    cols = st.columns(len(importador.TODOS_LOS_CAMPOS))
    for caja, campo in zip(cols, importador.TODOS_LOS_CAMPOS):
        actual = detectado.get(campo)
        indice = columnas.index(actual) if actual in columnas else 0
        elegido = caja.selectbox(
            importador.ETIQUETAS[campo], columnas, index=indice,
            key=f"map_{periodo_id}_{campo}",
        )
        mapeo[campo] = None if elegido == "— ninguna —" else elegido

    listo, mensajes = importador.preparar(crudo, mapeo)
    for nivel, texto in mensajes:
        (st.error if nivel == "error" else st.warning)(texto)
    if listo.empty:
        return

    st.markdown(f"**Vista previa — {len(listo)} plato(s) listos para guardar**")
    st.dataframe(
        listo.rename(columns={
            "item_name": "Plato", "category": "Categoría", "cost": "Costo",
            "price": "Precio", "units_sold": "Unidades",
        }),
        use_container_width=True, hide_index=True, height=300,
    )

    modo = st.radio(
        "¿Cómo guardo?",
        ["Agregar o actualizar", "Reemplazar todo el período"],
        horizontal=True, key=f"modo_{periodo_id}",
        help=("Agregar o actualizar mantiene los platos que ya estaban y pisa los "
              "que se repiten. Reemplazar borra primero todo lo cargado en el período."),
    )

    if st.button(f"Guardar en el período {_destino(periodo)}", type="primary",
                 key=f"save_{periodo_id}"):
        if modo.startswith("Reemplazar"):
            ok, msg = db.borrar_platos_del_periodo(periodo_id)
            if not ok:
                st.error(msg)
                return
        ok, msg = db.guardar_platos(periodo_id, listo)
        if ok:
            _flash(f"{msg} Quedaron en el período {_destino(periodo)}.")
            st.session_state["periodo_recien_creado"] = periodo_id
            st.rerun()
        else:
            st.error(msg)


def _planilla_manual(periodo) -> None:
    periodo_id = int(periodo["id"])
    existentes = db.cargar_platos_crudos(periodo_id)
    columnas = ["item_name", "category", "cost", "price", "units_sold"]
    base = existentes[columnas] if not existentes.empty else pd.DataFrame(columns=columnas)

    editado = st.data_editor(
        base, num_rows="dynamic", use_container_width=True,
        column_config={
            "item_name": st.column_config.TextColumn("Plato", required=True),
            "category": st.column_config.TextColumn("Categoría"),
            "cost": st.column_config.NumberColumn("Costo", min_value=0.0, format="%.2f"),
            "price": st.column_config.NumberColumn("Precio", min_value=0.0, format="%.2f"),
            "units_sold": st.column_config.NumberColumn("Unidades vendidas",
                                                        min_value=0, step=1),
        },
        key=f"editor_{periodo_id}",
    )
    if st.button("Guardar planilla", type="primary", key=f"save_man_{periodo_id}"):
        ok, msg = db.guardar_platos(periodo_id, editado)
        if ok:
            _flash(f"{msg} Quedaron en el período {_destino(periodo)}.")
            st.session_state["periodo_recien_creado"] = periodo_id
            st.rerun()
        else:
            st.error(msg)


# ---------------------------------------------------------------------------
# Pantalla: Análisis
# ---------------------------------------------------------------------------
def pantalla_analisis() -> None:
    restaurante = _sel_restaurante("an_rest")
    if restaurante is None:
        return
    periodo = _sel_periodo(int(restaurante["id"]), "an_periodo")
    if periodo is None:
        return

    datos = db.cargar_datos(periodo_id=int(periodo["id"]))
    if datos.empty:
        st.info("Este período todavía no tiene platos cargados.")
        return

    categoria, por_categoria = _sel_categoria(datos, "an_cat")
    if not por_categoria:
        _aviso_todas()
    else:
        datos = datos[datos["category"] == categoria]

    clasificado = analisis.clasificar(datos, por_categoria=por_categoria)
    k = analisis.kpis(clasificado)
    moneda = restaurante.get("moneda") or "$"

    st.caption(
        f"Valores netos de IVA ({restaurante['iva_alicuota']}%). "
        f"Período de {k['semanas']} semana/s."
    )

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        ui.kpi("Ingreso semanal", f"{moneda}{k['ingreso_semanal']:,.0f}",
               f"{moneda}{k['ingreso']:,.0f} en el período")
    with c2:
        ui.kpi("Margen semanal", f"{moneda}{k['margen_semanal']:,.0f}",
               f"{k['margen_pct']:.1f}% sobre ventas", "ok")
    with c3:
        ui.kpi("Unidades por semana", f"{k['unidades_semanales']:,.0f}",
               f"{k['unidades']:,} en total")
    with c4:
        perros = k["conteo"]["Perro"]
        ui.kpi("Estrellas / Perros",
               f"{k['conteo']['Estrella']} / {perros}",
               f"{k['platos']} platos analizados", "warn" if perros else "ok")

    st.markdown("### Matriz de Ingeniería de Menú")
    fig = ui.grafico_matriz(clasificado, moneda)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
    if por_categoria:
        st.caption(
            f"Umbrales de esta categoría: popularidad mínima "
            f"{clasificado['popularidad_minima'].iloc[0] * 100:.1f}% · margen "
            f"promedio ponderado {moneda}"
            f"{clasificado['margen_promedio_ponderado'].iloc[0]:,.2f}"
        )
        if len(clasificado) < 4:
            st.info(
                f"Esta categoría tiene solo {len(clasificado)} plato(s). Con tan "
                f"pocos, el umbral de popularidad queda en "
                f"{clasificado['popularidad_minima'].iloc[0] * 100:.0f}% y casi "
                "cualquier plato lo supera, así que la mitad izquierda de la matriz "
                "queda vacía. La clasificación recién se vuelve informativa con "
                "unos 5 o 6 platos por categoría."
            )

    st.markdown("### Detalle por plato")
    tabla = clasificado[[
        "item_name", "category", "cost_neto", "price_neto", "margen_unitario",
        "margen_pct", "units_sold", "unidades_semanales", "margen_total",
        "popularidad", "clasificacion",
    ]].copy()
    tabla["popularidad"] = (tabla["popularidad"] * 100).round(1)
    tabla = tabla.rename(columns={
        "item_name": "Plato", "category": "Categoría", "cost_neto": "Costo neto",
        "price_neto": "Precio neto", "margen_unitario": "Margen unit.",
        "margen_pct": "Margen %", "units_sold": "Unidades",
        "unidades_semanales": "Unid./semana", "margen_total": "Margen total",
        "popularidad": "Popularidad %", "clasificacion": "Clasificación",
    }).sort_values(["Categoría", "Margen total"], ascending=[True, False])
    st.dataframe(tabla, use_container_width=True, hide_index=True)

    st.download_button(
        "📥 Descargar este análisis en CSV",
        tabla.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"analisis_{restaurante['nombre']}_{periodo['fecha_desde']}.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Pantalla: Comparar períodos
# ---------------------------------------------------------------------------
def pantalla_comparar() -> None:
    restaurante = _sel_restaurante("cmp_rest")
    if restaurante is None:
        return

    periodos = db.listar_periodos(int(restaurante["id"]))
    if len(periodos) < 2:
        st.info("Necesitás al menos dos períodos cargados para poder comparar.")
        return

    etiquetas = {analisis.nombre_periodo(p): int(p["id"]) for _, p in periodos.iterrows()}
    nombres = list(etiquetas)
    c1, c2 = st.columns(2)
    nombre_a = c1.selectbox("Período A (referencia)", nombres,
                            index=min(1, len(nombres) - 1), key="cmp_a")
    nombre_b = c2.selectbox("Período B (comparación)", nombres, index=0, key="cmp_b")

    if etiquetas[nombre_a] == etiquetas[nombre_b]:
        st.warning("Elegí dos períodos distintos.")
        return

    datos_a = db.cargar_datos(periodo_id=etiquetas[nombre_a])
    datos_b = db.cargar_datos(periodo_id=etiquetas[nombre_b])
    if datos_a.empty or datos_b.empty:
        st.info("Alguno de los dos períodos no tiene platos cargados.")
        return

    juntos = pd.concat([datos_a, datos_b])
    categoria, por_categoria = _sel_categoria(juntos, "cmp_cat")
    if not por_categoria:
        _aviso_todas()
    else:
        datos_a = datos_a[datos_a["category"] == categoria]
        datos_b = datos_b[datos_b["category"] == categoria]
        if datos_a.empty or datos_b.empty:
            st.info(f"La categoría «{categoria}» no está en los dos períodos.")
            return

    cla_a = analisis.clasificar(datos_a, por_categoria=por_categoria)
    cla_b = analisis.clasificar(datos_b, por_categoria=por_categoria)
    moneda = restaurante.get("moneda") or "$"

    sem_a = int(cla_a["semanas"].iloc[0])
    sem_b = int(cla_b["semanas"].iloc[0])
    st.caption(
        f"Período A: {sem_a} semana/s · Período B: {sem_b} semana/s. "
        "Todos los valores comparados son promedios semanales, para que dos "
        "períodos de distinta duración sean comparables."
    )

    resumen = analisis.resumen_comparacion(cla_a, cla_b)
    st.markdown("### Indicadores semanales")
    c = st.columns(4)
    for caja, (_, fila) in zip(c, resumen.head(4).iterrows()):
        variacion = fila["Variación %"]
        tono = "ok" if variacion > 0 else ("bad" if variacion < 0 else "")
        if fila["formato"] == "moneda":
            valor = f"{moneda}{fila['Período B']:,.0f}"
        elif fila["formato"] == "pct":
            valor = f"{fila['Período B']:.1f}%"
        else:
            valor = f"{fila['Período B']:,.0f}"
        with caja:
            ui.kpi(fila["Indicador"], valor, f"{variacion:+.1f}% vs. período A", tono)

    vista = resumen[["Indicador", "Período A", "Período B", "Variación", "Variación %"]].copy()
    for col in ("Período A", "Período B", "Variación"):
        vista[col] = vista[col].map(lambda v: f"{v:,.2f}")
    vista["Variación %"] = resumen["Variación %"].map(lambda v: f"{v:+.1f}%")
    st.dataframe(vista, use_container_width=True, hide_index=True)

    comp = analisis.comparar(cla_a, cla_b)

    st.markdown("### Cómo se movió cada plato")
    fig = ui.grafico_comparacion(comp, moneda)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "El círculo hueco es la posición en el período A y el punto lleno la "
            "del período B. Solo se dibujan los platos presentes en ambos períodos."
        )

    movimientos = comp[comp["movimiento"] != "Sin cambio"]
    if not movimientos.empty:
        conteo = movimientos["movimiento"].value_counts()
        st.markdown("**Cambios de clasificación:** " + " · ".join(
            f"{mov} ({n})" for mov, n in conteo.items()
        ))

    tabla = comp[[
        "category", "item_name", "estado", "clasificacion_a", "clasificacion_b",
        "unidades_semanales_a", "unidades_semanales_b", "dif_unidades_sem",
        "margen_unitario_a", "margen_unitario_b", "dif_margen_unit",
        "margen_semanal_a", "margen_semanal_b", "dif_margen_sem",
    ]].rename(columns={
        "category": "Categoría", "item_name": "Plato", "estado": "Estado",
        "clasificacion_a": "Clasif. A", "clasificacion_b": "Clasif. B",
        "unidades_semanales_a": "Unid./sem A", "unidades_semanales_b": "Unid./sem B",
        "dif_unidades_sem": "Δ Unid./sem",
        "margen_unitario_a": "Margen unit. A", "margen_unitario_b": "Margen unit. B",
        "dif_margen_unit": "Δ Margen unit.",
        "margen_semanal_a": "Margen/sem A", "margen_semanal_b": "Margen/sem B",
        "dif_margen_sem": "Δ Margen/sem",
    })
    st.dataframe(tabla, use_container_width=True, hide_index=True)
    st.download_button(
        "📥 Descargar la comparación en CSV",
        tabla.to_csv(index=False).encode("utf-8-sig"),
        file_name=f"comparacion_{restaurante['nombre']}.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Pantalla: Principios de Omnes
# ---------------------------------------------------------------------------
def _datos_omnes(restaurante, clave: str):
    """Selector de período + categoría. Devuelve (periodo, datos_filtrados)."""
    periodo = _sel_periodo(int(restaurante["id"]), f"om_periodo_{clave}",
                           "Período" if clave == "uno" else f"Período {clave.upper()}")
    if periodo is None:
        return None, None
    datos = db.cargar_datos(periodo_id=int(periodo["id"]))
    if datos.empty:
        st.info("Este período todavía no tiene platos cargados.")
        return periodo, None
    return periodo, datos


def _tarjeta_principio(titulo: str, bloque: dict, valor: str, pie: str) -> None:
    """Un principio que no se puede evaluar se muestra neutro, nunca como incumplido."""
    if not bloque.get("evaluable", True):
        ui.kpi(titulo, "—", "no evaluable en esta categoría", "")
    else:
        ui.kpi(titulo, valor, pie, "ok" if bloque["cumple"] else "bad")


def _tarjetas_omnes(res: dict, moneda: str) -> None:
    disp, amp, od = res["dispersion"], res["amplitud"], res["oferta_demanda"]
    c = disp["conteo"]
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        _tarjeta_principio("Dispersión de precios", disp,
                           f"{c['Baja']} · {c['Media']} · {c['Alta']}",
                           "platos en gama baja · media · alta")
    with k2:
        _tarjeta_principio("Amplitud de la gama", amp, f"{amp['ratio']:.2f}×",
                           f"máximo recomendado {amp['limite']} para {amp['platos']} platos")
    with k3:
        _tarjeta_principio("Precio oferta / demanda", od, f"{od['ratio']:.2f}",
                           f"PMO {moneda}{od['pmo']:,.0f} · PMD {moneda}{od['pmd']:,.0f}")
    with k4:
        cumplidos, total = res["cumplidos"], res["total"]
        pie = ("sobre la categoría elegida" if total == 3
               else f"{3 - total} principio(s) no evaluable(s) acá")
        ui.kpi("Principios cumplidos", f"{cumplidos} de {total}" if total else "—",
               pie, "ok" if total and cumplidos == total else ("warn" if cumplidos else "bad"))


def _diagnosticos_omnes(res: dict) -> None:
    etiquetas = {
        "dispersion": "Dispersión de precios",
        "amplitud": "Amplitud de la gama",
        "oferta_demanda": "Precio oferta / demanda",
    }
    for clave, titulo in etiquetas.items():
        bloque = res[clave]
        texto = f"**{titulo}.** {bloque['diagnostico']}"
        if not bloque.get("evaluable", True):
            st.info(texto)
        else:
            (st.success if bloque["cumple"] else st.warning)(texto)


def _omnes_un_periodo(restaurante) -> None:
    periodo, datos = _datos_omnes(restaurante, "uno")
    if datos is None:
        return
    categoria, por_categoria = _sel_categoria(datos, "om_cat")
    if not por_categoria:
        st.warning(
            "Omnes se aplica sobre platos que compiten entre sí dentro de la misma "
            "sección de la carta. Mezclando entradas con principales, la amplitud se "
            "dispara y las gamas pierden sentido."
        )
    else:
        datos = datos[datos["category"] == categoria]

    res = omnes.analizar(datos)
    if res is None:
        st.info("No hay datos para analizar.")
        return
    if len(datos) < 4:
        st.info(
            f"La categoría tiene {len(datos)} plato(s). Omnes razona sobre la forma de "
            "una carta: con tan pocos platos las tres gamas y el promedio ofertado "
            "dicen poco. Se vuelve informativo a partir de 5 o 6 platos por categoría."
        )

    moneda = restaurante.get("moneda") or "$"
    st.caption(
        f"Precios de venta tal como se cargaron "
        f"({'con' if restaurante['precio_incluye_iva'] else 'sin'} IVA). "
        "Los tres indicadores son cocientes o conteos, así que netear el IVA no "
        "cambiaría ningún veredicto."
    )
    _tarjetas_omnes(res, moneda)

    fig = ui.grafico_omnes(res, moneda)
    if fig is not None:
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Cada punto es un plato, ubicado por su precio; el tamaño son las unidades "
            "vendidas. La línea gris punteada es el precio medio ofertado y la ámbar "
            "continua el precio medio demandado: cuando la ámbar queda a la izquierda de "
            "la gris, tus clientes eligen sistemáticamente por debajo de lo que ofrecés."
        )

    _diagnosticos_omnes(res)

    st.markdown("### Detalle por plato")
    tabla = res["datos"][["item_name", "category", "gama", "precio_cargado",
                          "units_sold", "margen_unitario"]].copy()
    tabla = tabla.rename(columns={
        "item_name": "Plato", "category": "Categoría", "gama": "Gama",
        "precio_cargado": "Precio", "units_sold": "Unidades",
        "margen_unitario": "Margen unit. (sin IVA)",
    }).sort_values("Precio", ascending=False)
    st.dataframe(tabla, use_container_width=True, hide_index=True)


def _omnes_comparar(restaurante) -> None:
    periodos = db.listar_periodos(int(restaurante["id"]))
    if len(periodos) < 2:
        st.info("Necesitás al menos dos períodos cargados para comparar.")
        return

    ids = [int(x) for x in periodos["id"].tolist()]
    textos = {int(p["id"]): analisis.nombre_periodo(p) for _, p in periodos.iterrows()}
    c1, c2 = st.columns(2)
    with c1:
        id_a = _selector_por_id("Período A (referencia)", ids, textos, "om_cmp_a")
    with c2:
        id_b = _selector_por_id("Período B (comparación)", ids, textos, "om_cmp_b")
    if id_a == id_b:
        st.warning("Elegí dos períodos distintos.")
        return

    datos_a = db.cargar_datos(periodo_id=id_a)
    datos_b = db.cargar_datos(periodo_id=id_b)
    if datos_a.empty or datos_b.empty:
        st.info("Alguno de los dos períodos no tiene platos cargados.")
        return

    categoria, por_categoria = _sel_categoria(pd.concat([datos_a, datos_b]), "om_cmp_cat")
    if not por_categoria:
        st.warning("Mezclando categorías la amplitud se dispara y las gamas pierden sentido.")
    else:
        datos_a = datos_a[datos_a["category"] == categoria]
        datos_b = datos_b[datos_b["category"] == categoria]
        if datos_a.empty or datos_b.empty:
            st.info(f"La categoría «{categoria}» no está en los dos períodos.")
            return

    res_a, res_b = omnes.analizar(datos_a), omnes.analizar(datos_b)
    moneda = restaurante.get("moneda") or "$"

    c1, c2 = st.columns(2)
    with c1:
        ui.kpi("Período A · principios cumplidos", f"{res_a['cumplidos']} de {res_a['total']}",
               textos[id_a], "ok" if res_a["cumplidos"] == res_a["total"] else "warn")
    with c2:
        mejora = res_b["cumplidos"] - res_a["cumplidos"]
        ui.kpi("Período B · principios cumplidos", f"{res_b['cumplidos']} de {res_b['total']}",
               f"{mejora:+d} respecto de A" if mejora else "sin cambios",
               "ok" if mejora > 0 else ("bad" if mejora < 0 else ""))

    st.markdown("### Indicadores lado a lado")
    comp = omnes.comparar(res_a, res_b, moneda)

    def formatear(valor, formato):
        if formato == "moneda":
            return f"{moneda}{valor:,.2f}"
        if formato == "ratio":
            return f"{valor:.2f}"
        return f"{valor:,.0f}"

    vista = pd.DataFrame({
        "Indicador": comp["Indicador"],
        "Período A": [formatear(v, f) for v, f in zip(comp["Período A"], comp["formato"])],
        "Período B": [formatear(v, f) for v, f in zip(comp["Período B"], comp["formato"])],
        "Variación": [formatear(v, f) if f != "entero" else f"{v:+,.0f}"
                      for v, f in zip(comp["Variación"], comp["formato"])],
        "Cumple A": comp["Cumple A"],
        "Cumple B": comp["Cumple B"],
    })
    st.dataframe(vista, use_container_width=True, hide_index=True)

    st.markdown("### Cómo cambió la estructura de precios")
    g1, g2 = st.columns(2)
    with g1:
        fig_a = ui.grafico_omnes(res_a, moneda, titulo=f"A · {textos[id_a]}")
        if fig_a is not None:
            st.plotly_chart(fig_a, use_container_width=True)
    with g2:
        fig_b = ui.grafico_omnes(res_b, moneda, titulo=f"B · {textos[id_b]}")
        if fig_b is not None:
            st.plotly_chart(fig_b, use_container_width=True)

    st.markdown("### Lectura del período B")
    _diagnosticos_omnes(res_b)


def pantalla_omnes() -> None:
    st.caption(
        "Mientras la matriz mira la popularidad y el margen de cada plato, Omnes mira "
        "la estructura de precios de la carta: si está bien escalonada, si no es "
        "demasiado abierta, y si lo que ofrecés coincide con lo que tus clientes eligen."
    )
    restaurante = _sel_restaurante("om_rest")
    if restaurante is None:
        return
    tab_uno, tab_comp = st.tabs(["Un período", "Comparar períodos"])
    with tab_uno:
        _omnes_un_periodo(restaurante)
    with tab_comp:
        _omnes_comparar(restaurante)


# ---------------------------------------------------------------------------
# Pantalla: Panel docente
# ---------------------------------------------------------------------------
def pantalla_admin() -> None:
    st.markdown("#### Alumnos")
    alumnos = db.listar_alumnos()
    if alumnos.empty:
        st.info("Todavía no hay alumnos registrados.")
        return

    vista = alumnos[["email", "full_name", "role", "is_active", "created_at"]].copy()
    vista.columns = ["Correo", "Nombre", "Rol", "Activo", "Alta"]
    st.dataframe(vista, use_container_width=True, hide_index=True)

    with st.expander("Activar o desactivar un alumno"):
        opciones = {f"{a.email}": a.id for a in alumnos.itertuples()}
        elegido = st.selectbox("Alumno", list(opciones), key="adm_alumno")
        fila = alumnos[alumnos["id"] == opciones[elegido]].iloc[0]
        activo = st.checkbox("Cuenta activa", value=bool(fila["is_active"]))
        if st.button("Aplicar"):
            ok, msg = db.cambiar_estado_alumno(fila["id"], activo)
            (st.success if ok else st.error)(msg)
            if ok:
                st.rerun()
        st.caption(
            "Un alumno desactivado no puede leer ni cargar datos: el bloqueo lo "
            "aplica la base de datos, no la app."
        )

    st.markdown("### Datos de todos los alumnos")
    todo = db.cargar_todo_admin()
    if todo.empty:
        st.info("Ningún alumno cargó platos aún.")
        return

    c1, c2, c3 = st.columns(3)
    with c1:
        ui.kpi("Alumnos con datos", f"{todo['user_id'].nunique()}")
    with c2:
        ui.kpi("Restaurantes", f"{todo['restaurante_id'].nunique()}")
    with c3:
        ui.kpi("Platos cargados", f"{len(todo):,}")

    tabla = todo[[
        "email", "restaurante", "fecha_desde", "fecha_hasta", "semanas",
        "category", "item_name", "units_sold", "margen_unitario", "margen_semanal",
    ]].rename(columns={
        "email": "Alumno", "restaurante": "Restaurante", "fecha_desde": "Desde",
        "fecha_hasta": "Hasta", "semanas": "Sem", "category": "Categoría",
        "item_name": "Plato", "units_sold": "Unidades",
        "margen_unitario": "Margen unit.", "margen_semanal": "Margen/sem",
    })
    st.dataframe(tabla, use_container_width=True, hide_index=True)
    st.download_button(
        "📥 Descargar todo en CSV",
        tabla.to_csv(index=False).encode("utf-8-sig"),
        file_name="imenu_datos_alumnos.csv",
        mime="text/csv",
    )


# ---------------------------------------------------------------------------
# Enrutado
# ---------------------------------------------------------------------------
def _slug(texto: str) -> str:
    """'Análisis Estático' -> 'analisis_estatico', para la clave del botón."""
    base = unicodedata.normalize("NFKD", texto.lower())
    base = "".join(c for c in base if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "_", base).strip("_")


def main() -> None:
    perfil = db.usuario_actual()
    if perfil is None:
        pantalla_login()
        return

    secciones = {
        "Restaurantes": (pantalla_restaurantes, "Tus locales y su configuración de IVA"),
        "Cargar período": (pantalla_cargar, "Importar o editar los platos de un período"),
        "Análisis Estático": (pantalla_analisis,
                              "Matriz de ingeniería de menú de un período"),
        "Análisis Dinámico": (pantalla_comparar,
                              "Cómo se movió cada plato entre dos períodos"),
        "Omnes": (pantalla_omnes, "Estructura de precios de la carta"),
    }
    if db.es_admin():
        secciones["Panel docente"] = (pantalla_admin, "Alumnos y datos de la clase")

    # Estructura del menú. Los dos análisis cuelgan de "Matriz K&S", que es un
    # encabezado y no una sección: por eso la navegación son botones y no un
    # st.radio, que no admite títulos intercalados entre las opciones.
    menu: list[tuple[str, str]] = [
        ("item", "Restaurantes"),
        ("item", "Cargar período"),
        ("grupo", "Matriz K&S"),
        ("sub", "Análisis Estático"),
        ("sub", "Análisis Dinámico"),
        ("item", "Omnes"),
    ]
    if db.es_admin():
        menu.append(("item", "Panel docente"))

    if st.session_state.get("nav") not in secciones:
        st.session_state["nav"] = "Restaurantes"

    with st.sidebar:
        st.markdown(ui.marca(32), unsafe_allow_html=True)

        for tipo, etiqueta in menu:
            if tipo == "grupo":
                st.markdown(f'<div class="nav-grupo">{etiqueta}</div>',
                            unsafe_allow_html=True)
                continue
            activo = st.session_state["nav"] == etiqueta
            if st.button(etiqueta, key=f"nav_{_slug(etiqueta)}",
                         use_container_width=True,
                         type="primary" if activo else "secondary"):
                st.session_state["nav"] = etiqueta
                st.rerun()

        st.markdown('<div class="sidebar-pie">', unsafe_allow_html=True)
        st.markdown(
            f'<div class="usuario">'
            f'<span class="usuario-nombre">{perfil.get("full_name") or perfil["email"]}</span>'
            f'<span class="usuario-rol">{"Docente" if db.es_admin() else "Alumno"}</span>'
            f"</div>",
            unsafe_allow_html=True,
        )
        if st.button("Cerrar sesión", key="cerrar_sesion", use_container_width=True):
            db.sign_out()
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)

    eleccion = st.session_state["nav"]
    pantalla, subtitulo = secciones[eleccion]
    ui.encabezado(eleccion, subtitulo)
    pantalla()


if __name__ == "__main__":
    main()
