# Capa de ML — pronósticos, anomalías y backtesting (M4)

Cómo se corre el pipeline de ML, qué garantiza y las dos trampas de entorno que
costaron una corrida en falso (2026-07-22). Para el detalle histórico ver
`docs/estado_proyecto.md` §8.

## Componentes

```
observatorio/ml/
  datos.py            # gold.fct_precio_diario → Series (una por fuente×depto×producto)
  baseline.py         # media móvil y naive
  prophet_modelo.py   # Prophet si la serie supera el umbral; si no, baseline
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
≥90 días; el resto cae a media móvil. Con los datos al 2026-07-22 eso es
**15 series de 163**.

Resultado del backtesting de esa fecha (MAPE mediano, 5 folds, horizonte 14d):

| Modelo | MAPE mediano |
|---|---|
| naive | **1.35 %** |
| media móvil 7d | 1.61 % |
| prophet | 4.49 % |

Prophet gana o iguala al mejor baseline en **2/15 series**. Las series de SISAP son
muy esparsas (la más larga: 82 observaciones en 2.5 años), justo el escenario donde
Prophet no tiene con qué estimar tendencia ni estacionalidad. **Decisión pendiente:**
degradarlo a experimento y servir baseline en el MVP, o subir el umbral de
`config.py` a series realmente densas.
