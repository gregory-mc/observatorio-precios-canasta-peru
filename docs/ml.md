# Capa de ML — pronósticos, anomalías y backtesting (M4)

Cómo se corre el pipeline de ML, qué garantiza y las dos trampas de entorno que
costaron una corrida en falso (2026-07-22). Para el detalle histórico ver
`docs/estado_proyecto.md` §8.

## Componentes

```
observatorio/ml/
  datos.py            # gold.fct_precio_diario → Series (una por fuente×depto×producto)
  baseline.py         # media móvil, naive y las bandas empíricas
  prophet_modelo.py   # elige el modelo (`modelo_de`) y normaliza la salida
  backtesting.py      # walk-forward: Prophet vs los dos baselines sobre los mismos cortes
  anomalias.py        # residuo normalizado > UMBRAL_SIGMA
  cobertura.py        # techo a la resiliencia del batch (ver abajo)
  conexion.py         # conexión Postgres a prueba del pooler (ver abajo)
  persistencia.py     # escritura idempotente por fecha_corrida a ml.*
  run_*.py            # los tres entrypoints batch
  config.py           # umbrales de historia, horizonte, sigma
```

## Cómo se corre

Requiere `pip install -e ".[ml]"` y `SUPABASE_DB_URL`. En orden:

```bash
python -m observatorio.ml.run_entrenamiento   # → ml.predicciones_raw
python -m observatorio.ml.run_anomalias       # → ml.anomalias_raw
python -m observatorio.ml.run_backtesting     # → ml.backtest_metricas
```

Y después dbt materializa los marts gold:

```bash
dbt build --select fct_predicciones fct_anomalias
```

Los tres runners son **idempotentes por `fecha_corrida`**: volver a correrlos el
mismo día borra las filas de esa corrida y las reescribe. Se pueden repetir sin
ensuciar nada.

## ⚠️ Dos trampas de entorno

### 1. `PYTHONUTF8=1` rompe Prophet en Windows

Con la UTF-8 mode activa, `cmdstanpy` ejecuta `where.exe tbb.dll` y decodifica su
salida como UTF-8; en un Windows en español la respuesta viene en cp850 y revienta
con `UnicodeDecodeError`. Prophet se lo traga y lo reemite como
`AttributeError: 'Prophet' object has no attribute 'stan_backend'`, de modo que
**todas** las series modelables fallan.

* En local: usar `PYTHONIOENCODING=utf-8` (suficiente para los emojis del log)
  y **no** `PYTHONUTF8=1`.
* En Actions: `ubuntu-latest` no se ve afectado (no hay `where.exe`). **Pero los
  workflows que corren en el runner self-hosted Windows sí declaran
  `PYTHONUTF8: "1"`** (`ingesta_sisap.yml`, `ingesta-inei.yml`,
  `ingesta-osinergmin.yml`): si algún día el ML corre ahí, no copiar esa variable.

### 2. `SUPABASE_DB_URL` apunta al pooler (6543)

El transaction pooler no soporta prepared statements y la escritura usa
`executemany`, así que psycopg fallaba con `DuplicatePreparedStatement`. Por eso
toda la capa abre conexión con `conexion.conectar()`, que pasa
`prepare_threshold=None`. **No usar `psycopg.connect` directamente en este
paquete** — hay un test que lo prohíbe (`tests/ml/test_conexion.py`).

El resto del proyecto no necesita esto porque escribe con `COPY FROM STDIN`.

## Techo a la resiliencia (`cobertura.py`)

Una serie que falla no tumba el batch (mismo criterio que los scrapers), pero esa
tolerancia tiene un límite. Antes de escribir, `run_entrenamiento` y
`run_backtesting` comparan las series que **se esperaba** producir por modelo
contra las que salieron, y la corrida **falla (exit 1) sin escribir** si:

* un modelo entero se cae (se esperaban N>0 series suyas y salieron 0), o
* se pierde más del `UMBRAL_FALLO_TOLERADO` (30 %) de las series.

El desglose se loguea siempre, incluso cuando todo va bien:

```
📊 Cobertura por modelo (series obtenidas/esperadas): media_movil 148/148 · prophet 15/15
```

Sin este techo, el fallo del 2026-07-22 pasó desapercibido: exit 0 y "2072 filas
escritas", todas de baseline. `run_anomalias` no necesita el mecanismo porque no
captura excepciones — un fallo suyo aborta el proceso de forma ruidosa.

## Qué modela hoy (y qué tan bien)

`config.FUENTES_MODELADAS` = SISAP minorista y mayorista: las únicas con backfill
histórico. Una serie va a Prophet solo si tiene ≥60 observaciones repartidas en
≥90 días; el resto cae a media móvil.

### Veredicto: Prophet pierde contra el baseline (verificado dos veces)

La primera corrida (2026-07-22) midió **15 series**, todas minorista de Lima, y dio
un MAPE mediano de 1.35 % (naive) · 1.61 % (media móvil) · **4.49 % (prophet)**.
El backfill histórico de SISAP (#16) entró al día siguiente y multiplicó por 10 la
población modelable, así que ese veredicto se remidió el **2026-07-24** sobre las
**157 series** que pasan el umbral hoy (MAPE mediano, 5 folds, horizonte 14d):

| Fuente | series | naive | media móvil 7d | prophet | Prophet gana |
|---|---:|---:|---:|---:|---:|
| `sisap_mayorista` | 83 | **4.05 %** | 4.95 % | 8.45 % | 5/83 (6 %) |
| `sisap_minorista` | 68 | **1.58 %** | 1.65 % | 4.48 % | 6/68 (9 %) |

**Más datos no mejoraron a Prophet: lo empeoraron.** `sisap_mayorista` es la familia
más densa que existe (181 observaciones contra 82 de minorista) y ahí Prophet queda
2.1× peor que repetir el último precio.

La causa no es el número de observaciones sino **la estructura de los huecos**: SISAP
publica con un hueco mediano de **5 días** (p90 de 7 días en mayorista, 25 en
minorista) y agujeros de hasta **332–378 días**. Prophet estima tendencia y
estacionalidad semanal/anual; con ~1 observación cada 5 días y huecos de un año no
tiene con qué estimarlas. Al mismo tiempo el precio se mueve 3–5 % entre
observaciones consecutivas y cambia en el 88–92 % de ellas: es casi un paseo
aleatorio, el régimen donde "repetir el último valor" es difícil de batir a 14 días.

**Por eso subir el umbral no rescata a Prophet** — se probó contra las series más
densas disponibles y el resultado empeora. Haría falta una fuente de muestreo
regular, no una submuestra más larga de la misma fuente esparsa.

> `marketplace` sí es diaria (hueco mediano de 1 día) y cruza las 60 observaciones a
> comienzos de agosto de 2026, pero tampoco es el rescate: el **94.9 %** de los días
> repite exactamente el precio del día anterior (variación media 0.66 %), o sea el
> régimen donde naive es aún más imbatible.

### Qué se sirve en su lugar

`config.USAR_PROPHET = False` y `config.MODELO_SERVIDO = "naive"`: **todas** las
series se pronostican repitiendo el último precio observado. Prophet no se borró —
`run_backtesting` lo sigue midiendo en cada corrida, así que el veredicto se puede
revisar con datos si algún día entra una fuente de muestreo regular. Para volver a
encenderlo basta cambiar el flag.

La decisión de qué modelo le toca a cada serie vive en **un solo sitio**,
`prophet_modelo.modelo_de`. `run_entrenamiento` la usa también para calcular cuántas
series espera de cada modelo: si se calculara por separado, apagar Prophet haría que
`cobertura` echase de menos series que ya nadie produce y abortase una corrida sana.

### Bandas de incertidumbre del baseline

Prophet traía sus propias bandas y el baseline no, así que al apagarlo
`fct_predicciones.precio_pred_inf/sup` se habría quedado en null y el dashboard (#38)
sin nada que dibujar. Ahora `baseline.agregar_bandas` las estima de la serie misma:

- `volatilidad_diaria` mide cuánto se mueve el precio **por día**, dividiendo cada
  cambio por la raíz del hueco que lo separa del anterior — necesario porque entre
  dos observaciones pueden haber pasado 1 día o 40. Usa la MAD en vez de la
  desviación típica para que los saltos atípicos no inflen la banda de todos los días.
- La banda se ensancha con `σ·√h`, el escalado de un paseo aleatorio, que es
  justamente el comportamiento que el backtesting le encontró a estas series. Un
  intervalo de ancho constante daría una falsa sensación de precisión a 14 días.
- Nivel del 80 %, el mismo default de Prophet, para no cambiar la lectura al apagarlo.
- El límite inferior se recorta en 0 (no existe un precio negativo) y las series
  planas se quedan sin banda antes que inventar un intervalo de ancho cero.

Verificado en memoria contra las 174 series de producción: solo **3 (1.7 %)** quedan
sin banda. Ejemplo real (`Aji escabeche`, mayorista, 182 obs, último precio S/ 9.25):
día +1 `[9.06 – 9.44]`, día +14 `[8.55 – 9.95]`.
