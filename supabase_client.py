"""
supabase_client.py — Capa de conexión entre Streamlit y Supabase (iMenu App).

Toda la app habla con la base a través de este archivo. Ninguna pantalla
debería importar `supabase` directamente.

Credenciales: se leen de st.secrets (.streamlit/secrets.toml en local, o el
panel "Secrets" en Streamlit Community Cloud).

    [supabase]
    url      = "https://xxxxxxxx.supabase.co"
    anon_key = "eyJhbGciOi..."

Ojo con la URL: va el Project URL pelado, sin /rest/v1 ni nada detrás.
La librería agrega sola el camino que corresponde.

Y nunca la service_role key: ignora todas las políticas RLS. Con la anon
key alcanza, porque la seguridad la aplica la base de datos.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd
import streamlit as st
from supabase import Client, create_client


# ---------------------------------------------------------------------------
# 1. CLIENTE
# ---------------------------------------------------------------------------
def _credenciales() -> tuple[str, str]:
    try:
        url = str(st.secrets["supabase"]["url"]).strip().rstrip("/")
        for sufijo in ("/rest/v1", "/auth/v1"):
            if url.endswith(sufijo):
                url = url[: -len(sufijo)]
        return url, str(st.secrets["supabase"]["anon_key"]).strip()
    except (KeyError, FileNotFoundError):
        st.error(
            "Faltan las credenciales de Supabase. Creá el archivo "
            "`.streamlit/secrets.toml` con la sección [supabase] "
            "(mirá `secrets.example.toml`)."
        )
        st.stop()


def get_client() -> Client:
    """Cliente de Supabase de ESTA sesión del navegador.

    No usamos @st.cache_resource a propósito: ese decorador comparte un mismo
    objeto entre todos los usuarios conectados al servidor, y como el cliente
    guarda adentro el token de sesión, dos alumnos conectados a la vez podrían
    terminar viendo los datos del otro. st.session_state es privado de cada
    pestaña del navegador.
    """
    if "sb_client" not in st.session_state:
        url, key = _credenciales()
        st.session_state.sb_client = create_client(url, key)
    return st.session_state.sb_client


# ---------------------------------------------------------------------------
# 2. AUTENTICACIÓN
# ---------------------------------------------------------------------------
def sign_up(email: str, password: str, full_name: str = "") -> tuple[bool, str]:
    """Registra un alumno y, si Supabase no exige confirmación, lo deja adentro.

    El mensaje se adapta a la configuración real del proyecto en lugar de
    suponerla: cuando "Confirm email" está apagado, Supabase devuelve una
    sesión en el mismo registro y no hay ningún correo que revisar; cuando
    está encendido, devuelve usuario sin sesión.
    """
    try:
        res = get_client().auth.sign_up(
            {
                "email": email.strip().lower(),
                "password": password,
                "options": {"data": {"full_name": full_name.strip()}},
            }
        )
        if res.user is None:
            return False, "No se pudo crear la cuenta. Probá de nuevo."

        # Supabase, para no revelar qué correos existen, devuelve un usuario
        # sin identidades en vez de un error cuando el mail ya está registrado.
        identidades = getattr(res.user, "identities", None)
        if identidades is not None and len(identidades) == 0:
            return False, "Ese correo ya está registrado. Iniciá sesión con tu contraseña."

        if res.session is not None:
            perfil = _leer_perfil(res.user.id)
            if perfil is not None:
                st.session_state.perfil = perfil
                nombre = perfil.get("full_name") or perfil["email"]
                return True, f"Cuenta creada. ¡Bienvenido/a, {nombre}!"
            return True, "Cuenta creada. Ya podés iniciar sesión."

        return True, ("Cuenta creada. Te enviamos un correo de confirmación: "
                      "abrilo y después volvé a iniciar sesión.")
    except Exception as exc:  # noqa: BLE001
        return False, _mensaje_error(exc)


def sign_in(email: str, password: str) -> tuple[bool, str]:
    try:
        res = get_client().auth.sign_in_with_password(
            {"email": email.strip().lower(), "password": password}
        )
        if res.user is None:
            return False, "Usuario o contraseña incorrectos."

        perfil = _leer_perfil(res.user.id)
        if perfil is None:
            sign_out()
            return False, "No se encontró el perfil del usuario."
        if not perfil.get("is_active", False):
            sign_out()
            return False, "Tu cuenta está desactivada. Contactá al docente."

        st.session_state.perfil = perfil
        return True, f"Bienvenido/a, {perfil.get('full_name') or perfil['email']}."
    except Exception as exc:  # noqa: BLE001
        return False, _mensaje_error(exc)


def sign_out() -> None:
    try:
        get_client().auth.sign_out()
    except Exception:  # noqa: BLE001
        pass
    for clave in ("perfil", "sb_client"):
        st.session_state.pop(clave, None)


def usuario_actual() -> dict[str, Any] | None:
    return st.session_state.get("perfil")


def es_admin() -> bool:
    perfil = usuario_actual()
    return bool(perfil and perfil.get("role") == "admin")


def requiere_login() -> dict[str, Any]:
    perfil = usuario_actual()
    if perfil is None:
        st.warning("Necesitás iniciar sesión para ver esta página.")
        st.stop()
    return perfil


def _leer_perfil(user_id: str) -> dict[str, Any] | None:
    res = (
        get_client()
        .table("profiles")
        .select("id, email, full_name, role, is_active, created_at")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


# ---------------------------------------------------------------------------
# 3. RESTAURANTES
# ---------------------------------------------------------------------------
def listar_restaurantes(solo_propios: bool = True) -> pd.DataFrame:
    perfil = requiere_login()
    try:
        q = get_client().table("restaurantes").select("*")
        if solo_propios:
            q = q.eq("user_id", perfil["id"])
        res = q.order("nombre").execute()
        return pd.DataFrame(res.data or [])
    except Exception as exc:  # noqa: BLE001
        st.error(_mensaje_error(exc))
        return pd.DataFrame()


def crear_restaurante(
    nombre: str,
    pais: str = "",
    moneda: str = "$",
    iva_alicuota: float = 0.0,
    precio_incluye_iva: bool = True,
    costo_incluye_iva: bool = False,
) -> tuple[bool, str]:
    perfil = requiere_login()
    if not nombre.strip():
        return False, "El nombre del restaurante no puede estar vacío."
    try:
        get_client().table("restaurantes").insert(
            {
                "user_id": perfil["id"],
                "nombre": nombre.strip(),
                "pais": pais.strip() or None,
                "moneda": (moneda or "$").strip()[:5],
                "iva_alicuota": round(float(iva_alicuota), 2),
                "precio_incluye_iva": bool(precio_incluye_iva),
                "costo_incluye_iva": bool(costo_incluye_iva),
            }
        ).execute()
        return True, f"Restaurante «{nombre.strip()}» creado."
    except Exception as exc:  # noqa: BLE001
        return False, _mensaje_error(exc)


def actualizar_restaurante(restaurante_id: int, **campos) -> tuple[bool, str]:
    requiere_login()
    permitidos = {
        "nombre", "pais", "moneda", "iva_alicuota",
        "precio_incluye_iva", "costo_incluye_iva",
    }
    datos = {k: v for k, v in campos.items() if k in permitidos}
    if not datos:
        return False, "No hay nada para actualizar."
    try:
        get_client().table("restaurantes").update(datos).eq("id", restaurante_id).execute()
        return True, "Restaurante actualizado."
    except Exception as exc:  # noqa: BLE001
        return False, _mensaje_error(exc)


def borrar_restaurante(restaurante_id: int) -> tuple[bool, str]:
    requiere_login()
    try:
        get_client().table("restaurantes").delete().eq("id", restaurante_id).execute()
        return True, "Restaurante eliminado junto con sus períodos y platos."
    except Exception as exc:  # noqa: BLE001
        return False, _mensaje_error(exc)


# ---------------------------------------------------------------------------
# 4. PERÍODOS
# ---------------------------------------------------------------------------
def listar_periodos(restaurante_id: int | None = None) -> pd.DataFrame:
    requiere_login()
    try:
        q = get_client().table("vw_periodos").select("*")
        if restaurante_id is not None:
            q = q.eq("restaurante_id", int(restaurante_id))
        res = q.order("fecha_desde", desc=True).execute()
        return pd.DataFrame(res.data or [])
    except Exception as exc:  # noqa: BLE001
        st.error(_mensaje_error(exc))
        return pd.DataFrame()


def crear_periodo(
    restaurante_id: int, desde: date, hasta: date, etiqueta: str = ""
) -> tuple[bool, str, int | None]:
    """Crea un período. La base rechaza los que no son de semanas completas."""
    perfil = requiere_login()
    try:
        res = (
            get_client()
            .table("periodos")
            .insert(
                {
                    "user_id": perfil["id"],
                    "restaurante_id": int(restaurante_id),
                    "etiqueta": etiqueta.strip() or None,
                    "fecha_desde": desde.isoformat(),
                    "fecha_hasta": hasta.isoformat(),
                }
            )
            .execute()
        )
        nuevo = (res.data or [{}])[0]
        return True, "Período creado.", nuevo.get("id")
    except Exception as exc:  # noqa: BLE001
        return False, _mensaje_error(exc), None


def borrar_periodo(periodo_id: int) -> tuple[bool, str]:
    requiere_login()
    try:
        get_client().table("periodos").delete().eq("id", periodo_id).execute()
        return True, "Período eliminado junto con sus platos."
    except Exception as exc:  # noqa: BLE001
        return False, _mensaje_error(exc)


# ---------------------------------------------------------------------------
# 5. PLATOS
# ---------------------------------------------------------------------------
#: Columnas que se escriben. El resto las calcula la base o la vista.
COLUMNAS_ESCRIBIBLES = ("item_name", "category", "cost", "price", "units_sold")


def guardar_platos(periodo_id: int, df: pd.DataFrame) -> tuple[bool, str]:
    """Guarda (o actualiza) los platos de un período.

    Hace UPSERT sobre la constraint uq_plato_periodo, así que volver a guardar
    el mismo plato lo actualiza en vez de duplicarlo.
    """
    perfil = requiere_login()
    if df is None or df.empty:
        return False, "No hay platos para guardar."

    datos = df.copy()
    datos["item_name"] = datos["item_name"].astype(str).str.strip()
    datos = datos[datos["item_name"] != ""]
    if datos.empty:
        return False, "No hay platos con nombre para guardar."

    # PostgREST rechaza un upsert con la misma clave dos veces en el lote.
    duplicados = datos["item_name"].str.lower().duplicated(keep="last")
    repetidos = int(duplicados.sum())
    datos = datos[~duplicados]

    filas: list[dict[str, Any]] = []
    for _, r in datos.iterrows():
        categoria = str(r.get("category") or "").strip() or "Sin categoría"
        filas.append(
            {
                "user_id": perfil["id"],
                "periodo_id": int(periodo_id),
                "item_name": str(r["item_name"]).strip(),
                "category": categoria,
                "cost": round(float(r.get("cost") or 0), 2),
                "price": round(float(r.get("price") or 0), 2),
                "units_sold": int(r.get("units_sold") or 0),
            }
        )

    try:
        get_client().table("menu_data").upsert(
            filas, on_conflict="periodo_id,item_name"
        ).execute()
        msg = f"{len(filas)} plato(s) guardado(s)."
        if repetidos:
            msg += f" Ignoré {repetidos} repetido(s), me quedé con la última aparición."
        return True, msg
    except Exception as exc:  # noqa: BLE001
        return False, _mensaje_error(exc)


def borrar_platos_del_periodo(periodo_id: int) -> tuple[bool, str]:
    requiere_login()
    try:
        get_client().table("menu_data").delete().eq("periodo_id", int(periodo_id)).execute()
        return True, "Platos del período eliminados."
    except Exception as exc:  # noqa: BLE001
        return False, _mensaje_error(exc)


def cargar_platos_crudos(periodo_id: int) -> pd.DataFrame:
    """Platos tal como se cargaron (sin netear IVA). Para editarlos."""
    requiere_login()
    try:
        res = (
            get_client()
            .table("menu_data")
            .select("id, item_name, category, cost, price, units_sold")
            .eq("periodo_id", int(periodo_id))
            .order("category")
            .order("item_name")
            .execute()
        )
        return pd.DataFrame(res.data or [])
    except Exception as exc:  # noqa: BLE001
        st.error(_mensaje_error(exc))
        return pd.DataFrame()


def cargar_datos(
    periodo_id: int | None = None,
    periodo_ids: list[int] | None = None,
    restaurante_id: int | None = None,
) -> pd.DataFrame:
    """Lee la vista vw_menu_datos: platos ya neteados de IVA.

    El RLS filtra solo: un alumno recibe únicamente lo suyo.
    """
    requiere_login()
    try:
        q = get_client().table("vw_menu_datos").select("*")
        if periodo_id is not None:
            q = q.eq("periodo_id", int(periodo_id))
        if periodo_ids:
            q = q.in_("periodo_id", [int(p) for p in periodo_ids])
        if restaurante_id is not None:
            q = q.eq("restaurante_id", int(restaurante_id))
        res = q.execute()
        df = pd.DataFrame(res.data or [])
        if df.empty:
            return df
        numericas = [
            "cost_neto", "price_neto", "margen_unitario", "margen_total",
            "ingreso_total", "unidades_semanales", "margen_semanal",
            "ingreso_semanal", "margen_pct", "units_sold", "semanas",
            "costo_cargado", "precio_cargado", "iva_alicuota",
        ]
        for col in numericas:
            if col in df:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        return df
    except Exception as exc:  # noqa: BLE001
        st.error(_mensaje_error(exc))
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# 6. ADMIN (docente)
# ---------------------------------------------------------------------------
def listar_alumnos() -> pd.DataFrame:
    requiere_login()
    try:
        res = (
            get_client()
            .table("profiles")
            .select("id, email, full_name, role, is_active, created_at")
            .order("email")
            .execute()
        )
        return pd.DataFrame(res.data or [])
    except Exception as exc:  # noqa: BLE001
        st.error(_mensaje_error(exc))
        return pd.DataFrame()


def cargar_todo_admin() -> pd.DataFrame:
    """Todos los platos de todos los alumnos, con el mail de cada uno."""
    requiere_login()
    if not es_admin():
        st.error("Esta sección es solo para administradores.")
        return pd.DataFrame()

    datos = cargar_datos()
    alumnos = listar_alumnos()
    if datos.empty or alumnos.empty:
        return datos
    return datos.merge(
        alumnos[["id", "email", "full_name"]].rename(columns={"id": "user_id"}),
        on="user_id",
        how="left",
    )


def cambiar_estado_alumno(user_id: str, activo: bool) -> tuple[bool, str]:
    requiere_login()
    if not es_admin():
        return False, "Solo un administrador puede hacer esto."
    try:
        get_client().table("profiles").update({"is_active": activo}).eq("id", user_id).execute()
        return True, "Estado actualizado."
    except Exception as exc:  # noqa: BLE001
        return False, _mensaje_error(exc)


# ---------------------------------------------------------------------------
# 7. UTILIDADES
# ---------------------------------------------------------------------------
def _mensaje_error(exc: Exception) -> str:
    """Traduce los errores más típicos a algo legible."""
    texto = str(exc)
    bajo = texto.lower()

    if "invalid login credentials" in bajo:
        return "Usuario o contraseña incorrectos."
    if "user already registered" in bajo:
        return "Ese correo ya está registrado. Iniciá sesión con tu contraseña."
    if ("rate limit" in bajo or "email_send_rate" in bajo
            or "email send rate" in bajo
            or "you can only request this after" in bajo):
        return ("El servicio de correo de Supabase llegó a su límite por hora "
                "(el incluido solo permite 2). Avisale al docente: hay que "
                "desactivar la confirmación por correo en Supabase, o esperar "
                "una hora.")
    if "password should be at least" in bajo or "weak password" in bajo:
        return "La contraseña es demasiado corta: usá al menos 6 caracteres."
    if "invalid email" in bajo or ("email address" in bajo and "invalid" in bajo):
        return "Ese correo no parece válido."
    if "ck_semana_completa" in bajo:
        return ("El período no abarca semanas completas. La cantidad de días "
                "tiene que ser múltiplo de 7.")
    if "ck_periodo_orden" in bajo:
        return "La fecha *hasta* no puede ser anterior a la fecha *desde*."
    if "uq_periodo" in bajo:
        return "Ya existe un período con esas mismas fechas para este restaurante."
    if "uq_restaurante_por_usuario" in bajo:
        return "Ya tenés un restaurante con ese nombre."
    if "uq_plato_periodo" in bajo or "duplicate key" in bajo:
        return "Ese plato ya existe en el período."
    if "cannot affect row a second time" in bajo:
        return ("El archivo trae el mismo plato más de una vez en el período. "
                "Dejá una sola fila por plato.")
    if "row-level security" in bajo or "42501" in texto:
        return "No tenés permisos para esta operación (RLS)."
    if "infinite recursion" in bajo:
        return "Error de configuración en las políticas RLS: revisá la función is_admin()."
    if "invalid path specified in request url" in bajo:
        return ("La URL de Supabase está mal en secrets.toml: tiene que ser el "
                "Project URL pelado, sin /rest/v1 al final.")
    return f"Error: {texto}"
