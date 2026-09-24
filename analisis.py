"""
analisis.py — Lógica de ingeniería de menú de iMenu App.

Este módulo no sabe nada de Streamlit ni de Supabase: recibe DataFrames y
devuelve DataFrames. Eso lo hace fácil de probar y de reutilizar.

Conceptos clave
---------------
* El análisis se hace SIEMPRE sobre valores netos de IVA. El neteo ya viene
  resuelto desde la vista `vw_menu_datos`.
* La matriz se calcula DENTRO de cada categoría. Comparar una entrada con un
  plato principal distorsiona el resultado: sus volúmenes y sus márgenes no
  son comparables.
* Para comparar períodos de distinta duración se usan promedios SEMANALES.
  Un período de 3 semanas dividido por 3 se vuelve comparable con uno de 1.
* Por eso los períodos deben ser de semanas completas: cualquier múltiplo de
  7 días contiene la misma cantidad de lunes, de martes y de sábados, así que
  el mix no queda sesgado por el fin de semana.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

CLASIFICACIONES = ("Estrella", "Caballo de batalla", "Puzzle", "Perro")

#: Regla de Kasavana & Smith: un plato es popular si supera el 70% de la
#: participación que tendría si todos los platos se vendieran por igual.
FACTOR_POPULARIDAD = 0.70


# ---------------------------------------------------------------------------
# Períodos
# ---------------------------------------------------------------------------
def validar_periodo(desde: date, hasta: date) -> tuple[bool, int, int, str]:
    """Valida que el rango sea de semanas completas.

    Devuelve (es_valido, dias, semanas, mensaje).
    """
    if desde is None or hasta is None:
        return False, 0, 0, "Indicá las dos fechas."
    if hasta < desde:
        return False, 0, 0, "La fecha *hasta* no puede ser anterior a *desde*."

    dias = (hasta - desde).days + 1
    semanas, resto = divmod(dias, 7)

    if resto != 0:
        faltan = 7 - resto
        return (
            False,
            dias,
            semanas,
            f"El período tiene {dias} días, que no son semanas completas. "
            f"Quitá {resto} día(s) o agregá {faltan} para llegar a "
            f"{semanas + 1} semana(s).",
        )

    etiqueta = "semana" if semanas == 1 else "semanas"
    return True, dias, semanas, f"{dias} días = {semanas} {etiqueta} completas."


def nombre_periodo(fila) -> str:
    """Texto corto para mostrar un período en un selector."""
    base = f"{fila['fecha_desde']} → {fila['fecha_hasta']} ({fila['semanas']} sem)"
    etiqueta = fila.get("etiqueta")
    if etiqueta and str(etiqueta).strip() and str(etiqueta) != "nan":
        base = f"{etiqueta} · {base}"
    items = fila.get("items")
    if items is not None and not pd.isna(items):
        base += f" · {int(items)} platos"
    return base


# ---------------------------------------------------------------------------
# Clasificación
# ---------------------------------------------------------------------------
def clasificar(df: pd.DataFrame, por_categoria: bool = True) -> pd.DataFrame:
    """Agrega popularidad, umbrales y clasificación de la matriz.

    `por_categoria=True` agrupa dentro de cada categoría (lo correcto).
    `por_categoria=False` mezcla todo el menú: se ofrece solo como
    contraejemplo didáctico.
    """
    if df.empty:
        return df.copy()

    d = df.copy()
    for col in ("units_sold", "margen_unitario", "margen_total"):
        d[col] = pd.to_numeric(d[col], errors="coerce").fillna(0)

    claves = ["periodo_id"]
    if por_categoria:
        claves.append("category")
    g = d.groupby(claves, dropna=False)

    d["unidades_grupo"] = g["units_sold"].transform("sum")
    d["items_grupo"] = g["item_name"].transform("count")
    d["margen_grupo"] = g["margen_total"].transform("sum")

    d["popularidad"] = _dividir(d["units_sold"], d["unidades_grupo"])
    d["popularidad_minima"] = _dividir(FACTOR_POPULARIDAD, d["items_grupo"])
    d["margen_promedio_ponderado"] = _dividir(d["margen_grupo"], d["unidades_grupo"])

    d["es_popular"] = d["popularidad"] >= d["popularidad_minima"]
    d["es_rentable"] = d["margen_unitario"] >= d["margen_promedio_ponderado"]

    d["clasificacion"] = np.select(
        [
            d["es_popular"] & d["es_rentable"],
            d["es_popular"] & ~d["es_rentable"],
            ~d["es_popular"] & d["es_rentable"],
        ],
        ["Estrella", "Caballo de batalla", "Puzzle"],
        default="Perro",
    )
    return d


def _dividir(numerador, denominador) -> pd.Series:
    """División segura: 0 donde el denominador es 0 o nulo."""
    den = pd.to_numeric(pd.Series(denominador), errors="coerce")
    if np.isscalar(numerador):
        num = pd.Series(float(numerador), index=den.index)
    else:
        num = pd.to_numeric(pd.Series(numerador), errors="coerce")
    res = num / den.replace(0, np.nan)
    return res.replace([np.inf, -np.inf], np.nan).fillna(0.0)


# ---------------------------------------------------------------------------
# Indicadores
# ---------------------------------------------------------------------------
def kpis(df: pd.DataFrame) -> dict:
    """Indicadores de un período ya clasificado."""
    if df.empty:
        return {
            "platos": 0, "unidades": 0, "ingreso": 0.0, "margen": 0.0,
            "margen_pct": 0.0, "semanas": 0,
            "unidades_semanales": 0.0, "ingreso_semanal": 0.0, "margen_semanal": 0.0,
            "ticket_promedio": 0.0, "conteo": {c: 0 for c in CLASIFICACIONES},
        }

    ingreso = float(df["ingreso_total"].sum())
    margen = float(df["margen_total"].sum())
    unidades = int(df["units_sold"].sum())
    semanas = int(df["semanas"].iloc[0]) if "semanas" in df else 1
    semanas = max(semanas, 1)

    return {
        "platos": int(len(df)),
        "unidades": unidades,
        "ingreso": ingreso,
        "margen": margen,
        "margen_pct": (margen / ingreso * 100) if ingreso else 0.0,
        "semanas": semanas,
        "unidades_semanales": unidades / semanas,
        "ingreso_semanal": ingreso / semanas,
        "margen_semanal": margen / semanas,
        "ticket_promedio": (ingreso / unidades) if unidades else 0.0,
        "conteo": {
            c: int((df["clasificacion"] == c).sum()) for c in CLASIFICACIONES
        },
    }


# ---------------------------------------------------------------------------
# Comparación entre dos períodos
# ---------------------------------------------------------------------------
COLS_COMPARAR = [
    "category", "item_name", "clasificacion", "units_sold", "unidades_semanales",
    "price_neto", "cost_neto", "margen_unitario", "margen_semanal",
    "ingreso_semanal", "popularidad",
]


def comparar(df_a: pd.DataFrame, df_b: pd.DataFrame) -> pd.DataFrame:
    """Cruza dos períodos ya clasificados, plato por plato.

    Todo lo comparable se expresa en promedio SEMANAL, así dos períodos de
    distinta cantidad de semanas quedan en la misma escala.
    """
    a = _preparar_lado(df_a, "_a")
    b = _preparar_lado(df_b, "_b")

    comp = a.merge(b, on=["category", "item_name"], how="outer")

    for col in ("unidades_semanales", "margen_semanal", "ingreso_semanal",
                "margen_unitario", "price_neto", "cost_neto", "units_sold",
                "popularidad"):
        for suf in ("_a", "_b"):
            if f"{col}{suf}" in comp:
                comp[f"{col}{suf}"] = comp[f"{col}{suf}"].fillna(0)

    presente_a = comp["clasificacion_a"].notna()
    presente_b = comp["clasificacion_b"].notna()
    comp["estado"] = np.select(
        [presente_a & presente_b, ~presente_a & presente_b, presente_a & ~presente_b],
        ["Se mantiene", "Nuevo", "Dado de baja"],
        default="—",
    )

    comp["clasificacion_a"] = comp["clasificacion_a"].fillna("—")
    comp["clasificacion_b"] = comp["clasificacion_b"].fillna("—")

    comp["movimiento"] = np.where(
        comp["estado"] == "Se mantiene",
        np.where(
            comp["clasificacion_a"] == comp["clasificacion_b"],
            "Sin cambio",
            comp["clasificacion_a"] + " → " + comp["clasificacion_b"],
        ),
        comp["estado"],
    )

    comp["dif_unidades_sem"] = comp["unidades_semanales_b"] - comp["unidades_semanales_a"]
    comp["dif_margen_unit"] = comp["margen_unitario_b"] - comp["margen_unitario_a"]
    comp["dif_margen_sem"] = comp["margen_semanal_b"] - comp["margen_semanal_a"]
    comp["dif_margen_sem_pct"] = _dividir(
        comp["dif_margen_sem"], comp["margen_semanal_a"].abs()
    ) * 100

    return comp.sort_values(
        ["category", "dif_margen_sem"], ascending=[True, False]
    ).reset_index(drop=True)


def _preparar_lado(df: pd.DataFrame, sufijo: str) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(
            columns=["category", "item_name"]
            + [f"{c}{sufijo}" for c in COLS_COMPARAR if c not in ("category", "item_name")]
        )
    cols = [c for c in COLS_COMPARAR if c in df.columns]
    lado = df[cols].copy()
    renombres = {
        c: f"{c}{sufijo}" for c in cols if c not in ("category", "item_name")
    }
    return lado.rename(columns=renombres)


def resumen_comparacion(df_a: pd.DataFrame, df_b: pd.DataFrame) -> pd.DataFrame:
    """Tabla chica de KPIs semanales lado a lado, con la variación."""
    ka, kb = kpis(df_a), kpis(df_b)
    filas = [
        ("Ingreso semanal (sin IVA)", ka["ingreso_semanal"], kb["ingreso_semanal"], "moneda"),
        ("Margen semanal", ka["margen_semanal"], kb["margen_semanal"], "moneda"),
        ("Margen sobre ventas", ka["margen_pct"], kb["margen_pct"], "pct"),
        ("Unidades por semana", ka["unidades_semanales"], kb["unidades_semanales"], "num"),
        ("Margen promedio por unidad",
         _seguro(ka["margen_semanal"], ka["unidades_semanales"]),
         _seguro(kb["margen_semanal"], kb["unidades_semanales"]), "moneda"),
        ("Platos analizados", ka["platos"], kb["platos"], "num"),
        ("Estrellas", ka["conteo"]["Estrella"], kb["conteo"]["Estrella"], "num"),
        ("Perros", ka["conteo"]["Perro"], kb["conteo"]["Perro"], "num"),
    ]
    out = pd.DataFrame(filas, columns=["Indicador", "Período A", "Período B", "formato"])
    out["Variación"] = out["Período B"] - out["Período A"]
    out["Variación %"] = [
        (v / a * 100) if a else 0.0
        for v, a in zip(out["Variación"], out["Período A"])
    ]
    return out


def _seguro(num: float, den: float) -> float:
    return num / den if den else 0.0
