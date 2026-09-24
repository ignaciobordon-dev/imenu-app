"""
omnes.py — Los tres principios de Omnes.

Mientras la matriz de Kasavana & Smith mira POPULARIDAD y MARGEN de cada plato,
los principios de Omnes miran la ESTRUCTURA DE PRECIOS de la carta: si está bien
escalonada, si no es demasiado abierta, y si el precio que pedís coincide con el
que tus clientes efectivamente eligen. Son dos lecturas complementarias.

Los tres principios
-------------------
1. **Dispersión de precios.** Se parte el recorrido de precios de la categoría en
   tres bandas iguales — banda = (precio máximo − precio mínimo) / 3 — y se cuenta
   cuántos platos caen en cada una. La carta está bien dispersa cuando la gama
   media concentra al menos tantos platos como las gamas baja y alta juntas, y la
   gama alta no supera a la baja. Una carta con todo arriba espanta; con todo
   abajo, deja plata sobre la mesa.

2. **Amplitud de la gama.** Es el cociente entre el plato más caro y el más barato
   de la categoría. Se acepta hasta 2,5 en cartas de menos de 9 platos y hasta 3
   en cartas de 9 o más. Si se abre demasiado, el plato barato canibaliza al caro
   y el caro parece fuera de lugar.

3. **Precio oferta / demanda.** Compara lo que ofrecés con lo que la gente compra:
      PMO = precio medio ofertado  = promedio simple de los precios de la carta
      PMD = precio medio demandado = Σ(precio × unidades) ÷ Σ unidades
   El cociente PMD/PMO debe caer entre 0,90 y 1,00. Por debajo, tus precios están
   altos para tu clientela (eligen lo barato). Por encima, estás vendiendo por
   debajo de lo que tu público está dispuesto a pagar.

Nota sobre el IVA: acá se usa el PRECIO DE CARTA, tal como se cargó, porque Omnes
razona sobre lo que el cliente ve. De todos modos los tres indicadores son
cocientes o conteos, así que netear el IVA no cambiaría ningún veredicto: solo
cambiarían los valores absolutos que se muestran.

Los umbrales de abajo son los más difundidos; si tu programa usa otros, se cambian
únicamente acá.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# --- Umbrales (modificables) ------------------------------------------------
AMPLITUD_MAX_CARTA_CHICA = 2.5   # menos de 9 platos en la categoría
AMPLITUD_MAX_CARTA_GRANDE = 3.0  # 9 platos o más
CANTIDAD_CARTA_GRANDE = 9
RATIO_MIN = 0.90
RATIO_MAX = 1.00
RATIO_OBJETIVO = 0.95            # centro de la banda, usado para sugerir precios

GAMAS = ("Baja", "Media", "Alta")
COLUMNA_PRECIO = "precio_cargado"


# ---------------------------------------------------------------------------
# 1. Dispersión de precios
# ---------------------------------------------------------------------------
def clasificar_gamas(df: pd.DataFrame, columna: str = COLUMNA_PRECIO):
    """Asigna cada plato a una gama y devuelve (df_con_gama, limites)."""
    d = df.copy()
    precios = pd.to_numeric(d[columna], errors="coerce").fillna(0)
    d[columna] = precios
    pmin, pmax = float(precios.min()), float(precios.max())
    banda = (pmax - pmin) / 3

    if banda <= 0:  # todos los platos al mismo precio
        d["gama"] = "Media"
        return d, {"pmin": pmin, "pmax": pmax, "banda": 0.0,
                   "corte_bajo": pmin, "corte_alto": pmax}

    corte_bajo = pmin + banda
    corte_alto = pmin + 2 * banda
    d["gama"] = np.select(
        [precios < corte_bajo, precios < corte_alto], ["Baja", "Media"], default="Alta"
    )
    return d, {"pmin": pmin, "pmax": pmax, "banda": banda,
               "corte_bajo": corte_bajo, "corte_alto": corte_alto}


def principio_dispersion(df: pd.DataFrame, columna: str = COLUMNA_PRECIO) -> dict:
    d, lim = clasificar_gamas(df, columna)
    conteo = {g: int((d["gama"] == g).sum()) for g in GAMAS}
    extremos = conteo["Baja"] + conteo["Alta"]

    # Sin al menos 3 platos y con algún recorrido de precios no hay nada que
    # repartir en tres gamas: el principio no es evaluable, que no es lo mismo
    # que decir que se cumple.
    if len(d) < 3 or lim["banda"] <= 0:
        motivo = ("todos los platos están al mismo precio: no hay dispersión que medir"
                  if lim["banda"] <= 0 else
                  f"la categoría tiene {len(d)} plato(s); hacen falta al menos 3 para "
                  "repartirlos en tres gamas")
        return {"cumple": False, "evaluable": False, "conteo": conteo, "limites": lim,
                "media_suficiente": False, "alta_contenida": False,
                "diagnostico": f"No se puede evaluar: {motivo}.", "datos": d}

    media_suficiente = conteo["Media"] >= extremos
    alta_contenida = conteo["Alta"] <= conteo["Baja"]
    cumple = media_suficiente and alta_contenida

    if cumple:
        diagnostico = ("La carta está bien escalonada: el grueso de los platos está "
                       "en la gama media y los extremos quedan equilibrados.")
    elif not media_suficiente and conteo["Alta"] > conteo["Baja"]:
        diagnostico = (f"La gama media tiene {conteo['Media']} plato(s) y los extremos "
                       f"suman {extremos}, con más platos caros que baratos. La carta "
                       "está corrida hacia arriba y sin un centro claro donde apoyar "
                       "la decisión del cliente.")
    elif not media_suficiente:
        diagnostico = (f"La gama media tiene {conteo['Media']} plato(s) frente a "
                       f"{extremos} en los extremos: falta cuerpo en el centro de la "
                       "carta, que es donde se concentra la mayoría de las decisiones.")
    else:
        diagnostico = (f"Hay {conteo['Alta']} plato(s) en la gama alta contra "
                       f"{conteo['Baja']} en la baja. Conviene no tener más platos "
                       "caros que baratos.")

    return {
        "cumple": cumple, "evaluable": True, "conteo": conteo, "limites": lim,
        "media_suficiente": media_suficiente, "alta_contenida": alta_contenida,
        "diagnostico": diagnostico, "datos": d,
    }


# ---------------------------------------------------------------------------
# 2. Amplitud de la gama
# ---------------------------------------------------------------------------
def principio_amplitud(df: pd.DataFrame, columna: str = COLUMNA_PRECIO) -> dict:
    precios = pd.to_numeric(df[columna], errors="coerce").fillna(0)
    precios = precios[precios > 0]
    n = int(len(precios))

    if n < 2:
        return {"cumple": False, "evaluable": False, "ratio": 1.0 if n else 0.0,
                "limite": AMPLITUD_MAX_CARTA_CHICA,
                "pmin": float(precios.min()) if n else 0.0,
                "pmax": float(precios.max()) if n else 0.0, "platos": n,
                "diagnostico": ("No se puede evaluar: hace falta más de un plato con "
                                "precio para medir cuán abierta es la gama.")}

    pmin, pmax = float(precios.min()), float(precios.max())
    ratio = pmax / pmin if pmin else 0.0
    limite = AMPLITUD_MAX_CARTA_GRANDE if n >= CANTIDAD_CARTA_GRANDE else AMPLITUD_MAX_CARTA_CHICA
    cumple = ratio <= limite

    if cumple:
        diagnostico = (f"El plato más caro vale {ratio:.2f} veces el más barato, "
                       f"dentro del máximo de {limite} para una categoría de {n} platos.")
    else:
        precio_sugerido = pmin * limite
        diagnostico = (f"El plato más caro vale {ratio:.2f} veces el más barato y el "
                       f"máximo recomendado es {limite}. Con una carta tan abierta, el "
                       "plato barato le come las ventas al caro. Para cerrarla, el tope "
                       f"debería bajar a {precio_sugerido:,.2f} o el piso subir a "
                       f"{pmax / limite:,.2f}.")

    return {"cumple": cumple, "evaluable": True, "ratio": ratio, "limite": limite,
            "pmin": pmin, "pmax": pmax, "platos": n, "diagnostico": diagnostico}


# ---------------------------------------------------------------------------
# 3. Precio oferta / demanda
# ---------------------------------------------------------------------------
def principio_oferta_demanda(
    df: pd.DataFrame, columna: str = COLUMNA_PRECIO, col_unidades: str = "units_sold"
) -> dict:
    precios = pd.to_numeric(df[columna], errors="coerce").fillna(0)
    unidades = pd.to_numeric(df[col_unidades], errors="coerce").fillna(0)
    total_unidades = float(unidades.sum())

    pmo = float(precios.mean()) if len(precios) else 0.0
    pmd = float((precios * unidades).sum() / total_unidades) if total_unidades else 0.0
    ratio = (pmd / pmo) if pmo else 0.0

    nuevo_pmo = (pmd / RATIO_OBJETIVO) if RATIO_OBJETIVO else pmo
    ajuste_pct = ((nuevo_pmo / pmo - 1) * 100) if pmo else 0.0

    if total_unidades <= 0 or ratio == 0:
        return {"cumple": False, "evaluable": False, "pmo": pmo, "pmd": pmd,
                "ratio": ratio, "estado": "sin datos", "nuevo_pmo": pmo,
                "ajuste_pct": 0.0,
                "diagnostico": ("No se puede evaluar: no hay unidades vendidas con las "
                                "que ponderar la demanda.")}
    if False:
        estado = diagnostico = ""
    elif ratio < RATIO_MIN:
        estado = "precios altos"
        diagnostico = (f"El cociente es {ratio:.2f}, por debajo de {RATIO_MIN:.2f}: tus "
                       "clientes se están yendo sistemáticamente a los platos más baratos "
                       "de la carta. La oferta está cara para este público. Llevar el "
                       f"precio medio ofertado a {nuevo_pmo:,.2f} ({ajuste_pct:+.1f}%) "
                       "alinearía la carta con lo que realmente consumen.")
    elif ratio > RATIO_MAX:
        estado = "precios bajos"
        diagnostico = (f"El cociente es {ratio:.2f}, por encima de {RATIO_MAX:.2f}: la "
                       "gente elige los platos caros de la carta, así que estás vendiendo "
                       "por debajo de lo que tu público está dispuesto a pagar. Hay margen "
                       f"para llevar el precio medio ofertado a {nuevo_pmo:,.2f} "
                       f"({ajuste_pct:+.1f}%).")
    else:
        estado = "adecuado"
        diagnostico = (f"El cociente es {ratio:.2f}, dentro de la banda "
                       f"{RATIO_MIN:.2f}–{RATIO_MAX:.2f}: lo que ofrecés y lo que tu "
                       "clientela elige están alineados.")

    return {"cumple": RATIO_MIN <= ratio <= RATIO_MAX, "evaluable": True,
            "pmo": pmo, "pmd": pmd,
            "ratio": ratio, "estado": estado, "nuevo_pmo": nuevo_pmo,
            "ajuste_pct": ajuste_pct, "diagnostico": diagnostico}


# ---------------------------------------------------------------------------
# Todo junto
# ---------------------------------------------------------------------------
def analizar(df: pd.DataFrame, columna: str = COLUMNA_PRECIO) -> dict | None:
    """Corre los tres principios sobre una categoría. None si no hay datos."""
    if df is None or df.empty:
        return None
    res = {
        "dispersion": principio_dispersion(df, columna),
        "amplitud": principio_amplitud(df, columna),
        "oferta_demanda": principio_oferta_demanda(df, columna),
    }
    res["datos"] = res["dispersion"]["datos"]
    evaluables = [k for k in PRINCIPIOS if res[k].get("evaluable", True)]
    res["cumplidos"] = sum(1 for k in evaluables if res[k]["cumple"])
    res["total"] = len(evaluables)
    res["no_evaluables"] = [k for k in PRINCIPIOS if k not in evaluables]
    return res


PRINCIPIOS = ("dispersion", "amplitud", "oferta_demanda")


# ---------------------------------------------------------------------------
# Comparación entre dos períodos
# ---------------------------------------------------------------------------
def comparar(res_a: dict, res_b: dict, moneda: str = "$") -> pd.DataFrame:
    """Tabla con los indicadores de Omnes de dos períodos y su variación."""
    def fila(nombre, va, vb, formato, cumple_a, cumple_b, mejor_alto=None):
        return {
            "Indicador": nombre,
            "Período A": va, "Período B": vb,
            "formato": formato,
            "Cumple A": "Sí" if cumple_a else "No",
            "Cumple B": "Sí" if cumple_b else "No",
        }

    da, db = res_a["dispersion"], res_b["dispersion"]
    aa, ab = res_a["amplitud"], res_b["amplitud"]
    oa, ob = res_a["oferta_demanda"], res_b["oferta_demanda"]

    filas = [
        fila("Amplitud de la gama (máx ÷ mín)", aa["ratio"], ab["ratio"], "ratio",
             aa["cumple"], ab["cumple"]),
        fila("Precio mínimo", aa["pmin"], ab["pmin"], "moneda", True, True),
        fila("Precio máximo", aa["pmax"], ab["pmax"], "moneda", True, True),
        fila("Platos en gama baja", da["conteo"]["Baja"], db["conteo"]["Baja"], "entero",
             True, True),
        fila("Platos en gama media", da["conteo"]["Media"], db["conteo"]["Media"], "entero",
             da["media_suficiente"], db["media_suficiente"]),
        fila("Platos en gama alta", da["conteo"]["Alta"], db["conteo"]["Alta"], "entero",
             da["alta_contenida"], db["alta_contenida"]),
        fila("Precio medio ofertado (PMO)", oa["pmo"], ob["pmo"], "moneda", True, True),
        fila("Precio medio demandado (PMD)", oa["pmd"], ob["pmd"], "moneda", True, True),
        fila("Cociente PMD ÷ PMO", oa["ratio"], ob["ratio"], "ratio",
             oa["cumple"], ob["cumple"]),
    ]
    out = pd.DataFrame(filas)
    out["Variación"] = out["Período B"] - out["Período A"]
    return out
