# Estado del proyecto — snapshot

> **Snapshot:** 2026-07-22 · Rama `main`
> Documento **vivo** de registro del proyecto (para el equipo). Cada acción realizada
> se anota en la **bitácora de cambios** al final (§8). Verificación de datos hecha en
> **lectura** contra Supabase producción.

---

## 1. Resumen ejecutivo

- **Ingesta (bronze):** ✅ en producción, automatizada y verde a diario.
- **dbt (silver→gold de precios):** ✅ en producción con datos reales, pero **corre a
  mano**: sin workflow, gold se congela (pasó 14 días entre el 8 y el 22 de julio).
- **ML (M4):** ✅ **corrido en producción el 2026-07-22** (predicciones, anomalías y
  backtesting materializados). Corre a mano, como dbt.
- **M5 (dashboard/API) y M6 (deploy/bot):** 🔲 sin empezar.

Frase clave: **ya no falta código, falta orquestación** — dbt y ML funcionan y
tienen datos en prod, pero ninguno de los dos corre solo. Y el modelo estrella
(Prophet) resultó peor que el baseline: ver el veredicto del backtesting en §8.

---

## 2. Verificación en producción (Supabase, solo lectura)

| Objeto | Estado | Filas | Última fecha |
|---|---|---|---|
| `bronze.*` (sisap/marketplace/osinergmin) | ✅ | 6,257 / 438,952 / 313,193 | 2026-07-22 |
| `silver.stg_*` (vistas) | ✅ | 5,571 / 403,482 / 311,534 | 2026-07-22 |
| `gold.fct_precio_diario` | ✅ | **400,680** | 2026-07-22 |
| `gold.fct_precio_medias_moviles` | ✅ | 400,680 | 2026-07-22 |
| `gold.dim_fecha` | ✅ | 916 | 2026-07-22 |
| `gold.canasta_consumo_dept` | ✅ | 150 | — |
| `ml.predicciones_raw` | ✅ | 2,282 | corrida 2026-07-22 |
| `ml.anomalias_raw` | ✅ | 90 | corrida 2026-07-22 |
| `ml.backtest_metricas` | ✅ | 45 | corrida 2026-07-22 |
| `gold.fct_predicciones` | ✅ | 154 | corrida 2026-07-22 |
| `gold.fct_anomalias` | ✅ | 22 | corrida 2026-07-22 |

Las tablas `ml.*` y los marts de ML **existen desde el 2026-07-22**: primera corrida
del pipeline M4 en producción (§8). Sigue sin haber workflow: la corrida fue manual.

**Gold estuvo congelado 14 días** (detectado y corregido el 2026-07-22, ver §8): los
marts son `table` y solo se materializan cuando alguien corre `dbt build` a mano.
Entre el 8 y el 22 de julio nadie lo corrió, así que bronze/silver avanzaban a diario
y gold se quedó en `max(fecha_captura)=2026-07-08` / 292,502 filas. Mismo origen que
el gap de M4: **no existe workflow de dbt**. Mientras no lo haya, gold vuelve a
atrasarse un día por día.

Calidad de código: **170 tests en verde** (suite completa) + **49 nodos dbt en verde**
(`dbt build`, 0 errores).

---

## 3. Clasificación de issues verificadas

### 🟢 Tier A — implementación 100% (código + tests). ✅ CERRADAS en GitHub (2026-07-15)

| Issue | Título | Entregable | Evidencia |
|---|---|---|---|
| #28 | Baseline naive + media móvil | código | `observatorio/ml/baseline.py` + test |
| #29 | Notebook Prophet PoC | notebook | `notebooks/02_prophet_poc.ipynb` (279 líneas) |
| #30 | Pipeline reusable entrenamiento | código | `run_entrenamiento.py` + `prophet_modelo.py` + test |
| #34 | Detección anomalías >2.5σ (algoritmo) | código | `observatorio/ml/anomalias.py` + test |
| #15 | Scraper OSINERGMIN | código + workflow | módulo `ingesta/osinergmin/` + `ingesta-osinergmin.yml` (⚠️ dato en prod no verificado en este snapshot) |

### 🟡 Tier B — código listo pero el entregable EXIGE ejecución/materialización que NO ocurrió en prod → NO cerrar aún

| Issue | Título | Falta para estar 100% |
|---|---|---|
| #32 | Entrenamiento batch de todos los pares | el batch **nunca corrió** → `ml.predicciones_raw` no existe |
| #33 | Backtesting walk-forward + métricas | `ml.backtest_metricas` **no existe** (código listo, sin datos) |
| #35 | Tabla `fct_anomalias` **materializada** por dbt | el mart **no está materializado** en prod |

### Mapeo issue → PR (para el comentario de cierre, cuando se autorice)

- ML (#28, #30, #32, #33, #34): PRs #106 / #107
- dbt marts ML (#35): PR #108
- OSINERGMIN (#15): PRs #83 / #97 / #98

---

## 4. Milestones (estado real)

| Hito | Estado | Nota |
|---|---|---|
| M1 Setup | ✅ | Repo + Supabase |
| M2 Ingesta | ✅ | SISAP + Marketplace + INEI + OSINERGMIN en prod |
| M3 dbt medallion | ✅ | silver + gold de precios poblados (292k filas) |
| M4 ML | ✅ | **corrido en prod el 2026-07-22**; falta automatizarlo y decidir qué hacer con Prophet (pierde contra el baseline, §8) |
| M5 Dashboard/API | 🔲 | sin empezar (`observatorio/dashboard/` y `/api/` no existen) |
| M6 Deploy/bot | 🔲 | sin empezar |

---

## 5. Gaps / pendientes estructurales

1. **Falta workflow de transformación** (dbt y ML) — es la causa de que M4 no tenga
   huella en prod **y** de que gold se congele (§2). Es el pendiente estructural nº1:
   hoy la única forma de refrescar gold es que una persona corra `dbt build` a mano.
2. **Correr M4 una vez** (entrenamiento → anomalías → backtesting → `dbt build`) para
   poblar `ml.*` y los marts gold, y comprobar si Prophet le gana al baseline.
3. **Deuda metodológica de canasta:** issues #20 / #102 / #21 (validación canasta y
   idempotencia de scrapers).
4. M5 no puede mostrar predicciones/anomalías hasta que M4 corra al menos una vez.

**Resueltos:**
- ~~No había CI de tests (push/merge no verificaba nada).~~ ✅ **Resuelto 2026-07-15**:
  workflow `ci.yml` corre pytest en cada PR y push a main (PR #109, mergeado). Ver §8.

---

## 6. Acciones

- ✅ **Cerradas en GitHub las issues Tier A** (#28, #29, #30, #34, #15) — 2026-07-15,
  cada una con comentario apuntando a su PR/commit.
- ✅ **CI de tests activo** (`ci.yml`, PR #109 mergeado) — pytest en cada PR y push a main.
- ✅ **Gold refrescado** (2026-07-22, `dbt build` a mano, 49 nodos en verde) — recuperados
  los 14 días de atraso. **No resuelve la causa**: sin workflow, se vuelve a atrasar.
- ⏸️ Correr el pipeline de ML contra producción — **en pausa, a debatir con el equipo** (ver §7).
- ⏸️ Crear el workflow `ml.yml` — **en pausa, a debatir con el equipo** (ver §7).

---

## 7. Decisión pendiente: cómo desplegar M4 (a debatir con el equipo)

**Pregunta a decidir:** cómo se ejecuta por primera vez (y luego de forma
recurrente) el pipeline de ML para poblar `ml.*` y materializar los marts gold.
De esto depende cerrar las issues Tier B (#32, #33, #35).

### Opciones sobre la mesa
- **A) Correr una vez en local** (rápido, aísla fallos de código de fallos de CI;
  idempotente, poblaría prod de inmediato). Desventaja: no queda automatizado.
- **B) Workflow-first**: crear `ml.yml` y disparar el pipeline desde ahí. Más limpio
  como destino final; evita una corrida manual desechable.
- **C) Híbrido**: smoke-test local para de-riesgar y luego el workflow como automatización.

### Consideraciones técnicas (relevantes para decidir)
1. **Secrets — el punto clave.** El pipeline tiene dos tramos con conexiones distintas:
   - ML batch (`run_entrenamiento/anomalias/backtesting`) usa `SUPABASE_DB_URL` →
     **el secret YA existe** (confirmado con `gh secret list`).
   - dbt (`build fct_predicciones/fct_anomalias`) usa `SUPABASE_DB_HOST/PORT/USER/
     PASSWORD/NAME` → **ninguno existe como secret** (dbt hasta hoy solo ha corrido
     en local desde `.env`; por eso `fct_precio_diario` está poblado pero se
     materializó a mano, no en CI).
   - **Opción para no crear 5 secrets:** el workflow puede **parsear `SUPABASE_DB_URL`**
     (que ya existe) y exportar las 5 variables para dbt en un step → 0 secrets nuevos,
     una sola fuente de verdad.
2. **Prophet en CI:** instalación pesada (baja cmdstan). Es el punto más probable de
   fallo en la primera corrida; mitigable con `cache: pip`.
3. **Runner:** `ubuntu-latest` sirve (Supabase es público, sin geo-bloqueo, igual que
   `carga-supabase.yml`). No requiere el self-hosted.
4. **Alcance del workflow:** ¿uno solo que haga ML batch + dbt de los 2 marts, o dbt
   en su propio workflow? Hoy **no existe ningún workflow de dbt** (corre a mano).
5. **Prudencia sugerida:** empezar `workflow_dispatch`-only (disparo manual), verificar
   verde, y recién después agregar `cron`. Reusar el patrón de "issue de alerta on-failure"
   de `carga-supabase.yml`.
6. **Relación con #27** (decidir Dagster OSS vs GitHub Actions): esta decisión de
   orquestación del ML se solapa con #27; conviene resolverlas juntas.

**Estado:** ninguna acción ejecutada. Pendiente de decisión del equipo.

---

## 8. Bitácora de cambios

Registro cronológico de cada acción realizada sobre el proyecto en estas sesiones.

### 2026-07-22 (2/2) — primera corrida de M4 en producción

Se ejecutó el pipeline completo de ML a mano (opción **A** de §7). M4 pasa de
"hecho pero no desplegado" a **desplegado**.

**Instalación:** `pip install -e ".[ml]"` (prophet 1.3.0, cmdstanpy 1.3.0, duckdb,
scikit-learn, statsmodels). No estaban en el `.venv`.

**Resultado de la corrida (fecha_corrida = 2026-07-22):**

| Tabla | Filas |
|---|---|
| `ml.predicciones_raw` | 2,282 (2,072 media móvil · 210 Prophet) |
| `ml.anomalias_raw` | 90 |
| `ml.backtest_metricas` | 45 (15 series × 3 modelos) |
| `gold.fct_predicciones` | 154 (reducidas a los 6 slugs MVP) |
| `gold.fct_anomalias` | 22 (5 productos, 2024-01-24 → 2026-07-22) |

`dbt build --select fct_predicciones fct_anomalias` → **PASS=22, ERROR=0**.

#### 🔴 Veredicto del backtesting: Prophet PIERDE contra los baselines

| Modelo | Series | MAPE mediano |
|---|---|---|
| naive | 15 | **1.35 %** |
| media móvil 7d | 15 | 1.61 % |
| **prophet** | 15 | **4.49 %** |

Prophet gana o iguala al mejor baseline en **2 de 15 series**. Es ~3× peor que
repetir el último precio. Contexto: las series SISAP son muy esparsas (la mejor
tiene 82 observaciones repartidas en 2.5 años), que es justo el escenario donde
Prophet no tiene con qué estimar tendencia ni estacionalidad. **Decisión a tomar:**
degradar Prophet a experimento y servir baseline en el MVP, o subir el umbral de
`config.py` a series realmente densas. Afecta a #29/#30 y a lo que muestre M5.

#### 🐛 Dos fallos encontrados al ejecutar (no los cubría ningún test)

1. **✅ MITIGADO el 2026-07-22 — `PYTHONUTF8=1` rompe Prophet en Windows.** Con esa variable —que el README y
   nuestras notas recomiendan por la consola cp1252— cmdstanpy corre
   `where.exe tbb.dll` y decodifica su salida como UTF-8; en un Windows en español
   la respuesta trae acentos en cp850 y revienta con `UnicodeDecodeError`, que
   Prophet traga y convierte en `AttributeError: 'Prophet' object has no attribute
   'stan_backend'`. **Las 15 series de Prophet fallaron y el batch terminó en éxito**
   con 2,072 filas de solo baseline y 15 WARNING. Workaround: usar
   `PYTHONIOENCODING=utf-8` **sin** `PYTHONUTF8=1`. No afecta a `ubuntu-latest`,
   pero **sí a los workflows del runner self-hosted Windows**, que hoy declaran
   `PYTHONUTF8: "1"` (`ingesta_sisap.yml`, `ingesta-inei.yml`, `ingesta-osinergmin.yml`):
   si el ML llega a correr ahí, no se debe copiar esa variable. Documentado en
   `docs/ml.md`.
   El riesgo de fondo —**el batch degradaba en silencio** (exit 0) cuando el modelo
   fallaba— está resuelto con `observatorio/ml/cobertura.py`: `run_entrenamiento` y
   `run_backtesting` comparan las series esperadas por modelo contra las obtenidas y
   **fallan sin escribir** si se cae un modelo entero o si se pierde más del 30% de
   las series; el desglose (`prophet 15/15 · media_movil 148/148`) se loguea siempre.
   `run_anomalias` no lo necesita: no captura excepciones, así que ya falla ruidoso.
   **Verificado reproduciendo el incidente**: con `PYTHONUTF8=1` la corrida ahora
   termina en `exit 1` con "🚨 Se perdió el 100% de las series de: prophet" y no
   escribe nada; sin la variable, `exit 0` y 2,282 filas.
2. **✅ RESUELTO el 2026-07-22 — `SUPABASE_DB_URL` apunta al pooler (6543) y
   `ml.persistencia` no funcionaba ahí.**
   `run_anomalias` abortó con `DuplicatePreparedStatement: prepared statement
   "_pg3_0" already exists`: psycopg3 usa prepared statements en `executemany` y el
   transaction pooler no los soporta (mismo motivo por el que dbt usa 5432). Se
   resolvió reescribiendo el puerto a **5432**. `run_entrenamiento` había pasado por
   casualidad → el fallo era intermitente. Habría roto el workflow de §7, porque el
   secret `SUPABASE_DB_URL` es el del pooler.
   **Arreglo aplicado:** nuevo módulo `observatorio/ml/conexion.py` con
   `conectar(db_url)`, que abre la conexión con `prepare_threshold=None` (psycopg
   deja de preparar; ver `psycopg/_preparing.py:63`). `ml/datos.py` y
   `ml/persistencia.py` ya no llaman a `psycopg.connect` directamente. El resto del
   proyecto no necesitaba el arreglo porque escribe con `COPY FROM STDIN`.
   **Verificado corriendo los tres runners contra el pooler (6543) sin reescribir
   el puerto:** entrenamiento 2,282 filas · anomalías 90 · backtesting 45, los tres
   OK. Suite: **176 tests en verde** (6 nuevos en `tests/ml/test_conexion.py`,
   incluida una guarda de regresión que prohíbe `psycopg.connect` en la capa ML).

**Issues Tier B (#32, #33, #35):** ya tienen el entregable materializado en prod.
Quedan pendientes de cierre a criterio del equipo (no se cerraron en esta sesión).

### 2026-07-22 (1/2) — refresco de gold

**Hallazgo: gold congelado desde el 2026-07-08.**
- Verificado en prod (lectura): bronze y silver frescos hasta el 22-jul (ingesta y
  `carga-supabase` verdes a diario), pero `gold.fct_precio_diario` seguía con
  292,502 filas y `max(fecha_captura)=2026-07-08`. Staging es `view` (se refresca
  solo); los marts son `table` y nadie corría `dbt build` desde el 8-9 de julio.

**Acción: refresco de gold (`dbt build`, primera corrida desde el 9-jul).**
- `pip install -e ".[dbt]"` (dbt-postgres 1.11 / dbt-core 1.12; no estaba en el `.venv`).
- Conexión resuelta **parseando `SUPABASE_DB_URL`** para exportar las 5 variables que
  pide `profiles.yml` — `.env` solo tiene `SUPABASE_DB_URL`, y los 5 `SUPABASE_DB_*`
  no existían ni en local ni como secrets. Es el mismo truco propuesto para el
  workflow en §7: una sola fuente de verdad, 0 secrets nuevos. Puerto **5432**
  (conexión directa), no el pooler 6543.
- `dbt build --exclude "fct_predicciones+" "fct_anomalias+"` (se excluyen los marts de
  ML y sus tests: dependen de `ml.*`, que aún no existe).
- Resultado: **PASS=49, WARN=0, ERROR=0** en 54s — 4 vistas silver + 3 tablas gold + 42 tests.

**Estado de gold tras el refresco:**

| Tabla | Antes | Después |
|---|---|---|
| `gold.fct_precio_diario` | 292,502 · hasta 2026-07-08 | **400,680 · hasta 2026-07-22** |
| `gold.fct_precio_medias_moviles` | 292,502 | 400,680 |
| `gold.dim_fecha` | 902 | 916 |

Cobertura por fuente: marketplace 395,109 · sisap_mayorista 3,200 · sisap_minorista
2,371, las tres al 22-jul.

**Dato para M4 (§7):** de las **163 series SISAP** (fuente × depto × producto) solo
**15** superan el umbral de `config.py` (≥60 observaciones y span ≥90 días) → las otras
148 caerían al baseline. Conviene tenerlo presente al leer los resultados de la
primera corrida de ML: el grueso del batch no será Prophet.

**Sin cambios:** no se corrió el pipeline de ML ni se creó ningún workflow (§7 sigue
en pausa, pendiente de decisión del equipo).

### 2026-07-15

**Verificación y clasificación (lectura, sin cambios):**
- Verificado contra Supabase prod (solo lectura): `gold.fct_precio_diario` = 292,502 filas;
  tablas `ml.*` y marts `gold.fct_predicciones/fct_anomalias` NO existen → M4 sin ejecución en prod.
- Auditado el código de M4 + OSINERGMIN (#15) contra los títulos de las issues; suite completa
  **170 tests en verde**. Clasificación Tier A / Tier B (ver §3).

**Issues (GitHub):**
- ✅ Cerradas Tier A con comentario al PR/commit: **#28, #29, #30, #34, #15**.
- 💬 Comentadas (siguen abiertas a propósito) Tier B con el contexto de la decisión pendiente:
  **#32, #33, #35**.

**CI de tests — NUEVO:**
- Creado `.github/workflows/ci.yml`: pytest en cada `pull_request` y `push` a `main`.
  Instala solo `.[ingesta,carga,dev]` (omite el grupo `ml`/Prophet, innecesario en tests).
- Rama `ci/pytest-on-pr` → **PR #109** → CI verde en el PR (29s).
- **Mergeado a main** (squash, commit `689d40a`); CI en main verde (32s). Rama borrada.
- Resultado: primer workflow disparado por push/PR del repo. Mergear ahora **sí verifica**.
- Pendiente menor (no urgente): las actions usan Node 20 (deprecado) → actualizar versiones.

**En pausa (decisión de equipo):** despliegue de M4 (ver §7). Sin acción ejecutada.
