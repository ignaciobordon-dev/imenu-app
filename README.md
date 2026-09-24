# iMenu App — Ingeniería de Menú

Streamlit + Supabase (PostgreSQL, Auth y Row Level Security).

## Archivos

```
imenu-app/
├── app.py                   ← pantallas de la aplicación
├── supabase_client.py       ← única capa que habla con la base
├── analisis.py              ← matriz, KPIs y comparación de períodos
├── omnes.py                 ← los tres principios de Omnes
├── importador.py            ← lectura de Excel/CSV y mapeo de columnas
├── ui.py                    ← estilos y gráficos
├── style.css
├── requirements.txt
├── iniciar.bat              ← doble clic para arrancar (Windows)
├── plantilla_imenu.xlsx     ← planilla para repartir a los alumnos
├── 01_schema_supabase.sql   ← se ejecuta en el SQL Editor de Supabase
└── .streamlit/
    ├── config.toml
    └── secrets.toml         ← NO subir a GitHub
```

## Puesta en marcha

1. **Base de datos.** Supabase → SQL Editor → pegar `01_schema_supabase.sql` → Run.
   Cuidado: ese script borra y recrea restaurantes, períodos y platos. No toca
   `profiles`, así que los usuarios y los roles se conservan.
2. **Credenciales.** *Project Settings → API*: copiar `Project URL` (pelado, sin
   `/rest/v1`) y la clave `anon / public` a `.streamlit/secrets.toml`.
3. **Arrancar.** Doble clic en `iniciar.bat`, o bien:

   ```bash
   pip install -r requirements.txt
   streamlit run app.py
   ```

4. **Ser docente.** Registrarse desde la app y después, en el SQL Editor:

   ```sql
   update public.profiles set role = 'admin' where email = 'tu-mail@ejemplo.com';
   ```

## Cómo se usa

1. **Restaurantes** — crear el restaurante e indicar la alícuota de IVA, si el
   precio la incluye (lo habitual) y si el costo la incluye (habitualmente no).
   Se define una sola vez y vale para todos sus períodos.
2. **Cargar período** — elegir el rango de fechas y subir el Excel/CSV, o cargar
   la planilla a mano.
3. **Análisis** — elegir período y categoría: KPIs, matriz y detalle por plato.
4. **Omnes** — los tres principios sobre la estructura de precios de la carta,
   para un período o comparando dos.
5. **Comparar** — elegir dos períodos y ver cómo se movió cada plato.

## Decisiones de método

**El análisis siempre es sin IVA.** Los valores se guardan tal como los carga el
alumno y el neteo lo hace la vista `vw_menu_datos`, así el dato original queda
auditable. Si el precio viene con IVA, se divide por `(1 + alícuota/100)`.

**La matriz se calcula dentro de cada categoría.** Comparar una entrada con un
plato principal no tiene sentido: ni sus volúmenes ni sus márgenes son
comparables, y el resultado sería que todas las entradas parecen poco rentables.
La app permite mezclar todo, pero avisa que no es válido.

**Los períodos son de semanas completas.** En gastronomía un sábado no vende como
un martes. Un período de 10 días incluiría dos sábados y un solo martes, y el mix
de platos quedaría sesgado. Cualquier múltiplo de 7 días contiene la misma
cantidad de cada día de la semana, arranque el día que arranque. La restricción
`ck_semana_completa` lo hace cumplir en la base, no solo en la pantalla.

**Las comparaciones usan promedios semanales.** Un período de 3 semanas dividido
por 3 se vuelve comparable con uno de 1 semana. Por eso lo anterior es
indispensable: sin semanas completas, el promedio semanal mentiría.

**Clasificación (Kasavana & Smith).** Un plato es *popular* si su participación
supera el 70% de la que tendría si todos los platos de la categoría se vendieran
por igual, y es *rentable* si su margen de contribución unitario supera el margen
promedio ponderado de la categoría. De ahí salen Estrella, Caballo de batalla,
Puzzle y Perro.

**Los principios de Omnes** miran la carta, no el plato, y complementan la matriz:

1. *Dispersión de precios*: se parte el recorrido de precios en tres bandas
   iguales — `(máximo − mínimo) / 3` — y se cuenta cuántos platos caen en cada
   una. La carta está bien escalonada si la gama media tiene al menos tantos
   platos como las gamas baja y alta juntas, y la alta no supera a la baja.
2. *Amplitud de la gama*: cociente entre el plato más caro y el más barato.
   Hasta 2,5 en categorías de menos de 9 platos; hasta 3 de 9 en adelante.
3. *Precio oferta / demanda*: `PMD ÷ PMO`, donde PMO es el promedio simple de los
   precios y PMD el promedio ponderado por unidades vendidas. Debe caer entre
   0,90 y 1,00; por debajo los precios están altos para esa clientela, por encima
   están bajos.

Los umbrales están en las constantes del encabezado de `omnes.py`: si tu programa
usa otros valores, se cambian ahí y nada más. Cuando una categoría no tiene platos
suficientes, el principio se marca como *no evaluable* en vez de darse por
cumplido. Omnes usa el precio de carta tal como se cargó: los tres indicadores son
cocientes o conteos, así que netear el IVA no cambiaría ningún veredicto.

## Notas de mantenimiento

- El importador reconoce solo los nombres de columna más comunes; los sinónimos
  están en `importador.SINONIMOS` y se amplían agregando strings a esas tuplas.
- Un upsert con el mismo plato dos veces en el mismo lote falla en PostgREST, por
  eso tanto el importador como `guardar_platos()` deduplican antes de enviar.
- Los selectores CSS del tipo `[data-testid="stMetric"]` dependen del HTML interno
  de Streamlit y pueden cambiar entre versiones. Las tarjetas `.kpi` y `.panel`
  son HTML propio y no se rompen.
