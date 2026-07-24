# Estado del proyecto — snapshot

> **Snapshot:** 2026-07-24 · Rama `main`
> Documento **vivo** de registro del proyecto (para el equipo). Cada acción realizada
> se anota en la **bitácora de cambios** al final (§8). Verificación de datos hecha en
> **lectura** contra Supabase producción.

---

## 1. Resumen ejecutivo

- **Ingesta (bronze):** ✅ en producción, automatizada y verde a diario.
- **dbt (silver→gold de precios):** ✅ en producción y **automatizado** desde el
  2026-07-24: `dbt.yml` corre a diario a las 22:00 UTC. Se acabó el congelamiento
  (14 días entre el 8 y el 22 de julio; 2 días más al 24).
- **ML (M4):** ✅ en producción y **automatizado**: `ml.yml` corre los lunes a las
  23:00 UTC. Sirve `naive` con bandas empíricas; Prophet quedó apagado (§8).
- **Calidad de datos:** ✅ dos correcciones el 24-jul (§8): unidad de SISAP normalizada
  a S/kg (`equiv_kg_lt`) y validación de canasta reformulada (#102 cerrada, con rangos
  de precio por producto). Test dbt `no_negativo` como guarda del mart de predicciones.
- **M5 (dashboard/API) y M6 (deploy/bot):** 🔲 sin empezar.

Frase clave: **ya no falta código ni orquestación** — dbt y ML corren solos desde el
2026-07-24. Lo que falta es producto: M5. El modelo estrella (Prophet) resultó peor
que el baseline, y al remedirlo sobre 10× más series se descubrió además que
predecía precios negativos: ver §8.

---

## 2. Verificación en producción (Supabase, solo lectura, 2026-07-24)

| Objeto | Estado | Filas | Última fecha |
|---|---|---|---|
| `bronze.*` (sisap/marketplace/osinergmin) | ✅ | 22,028 / 454,270 / 339,840 | 2026-07-24 |
| `gold.fct_precio_diario` | ✅ | **423,085** | 2026-07-23 |
| `gold.fct_precio_medias_moviles` | ✅ | 423,085 | 2026-07-23 |
| `gold.dim_fecha` | ✅ | 932 | 2026-07-23 |
| `gold.canasta_consumo_dept` | ✅ | 150 | — |
| `ml.predicciones_raw` | ✅ | 4,508 | corrida 2026-07-24 |
| `ml.anomalias_raw` | ✅ | 568 | corrida 2026-07-24 |
| `ml.backtest_metricas` | ✅ | 498 | corrida 2026-07-24 |
| `gold.fct_predicciones` | ✅ | 224 | corrida 2026-07-24 |
| `gold.fct_anomalias` | ✅ | 80 | corrida 2026-07-24 |

Todo fresco: `dbt.yml` (diario) refrescó gold al 23-jul y `ml.yml` corrió el 24-jul
con los precios ya normalizados a S/kg (§8). `bronze.sisap` va al 22-jul porque el
23 fue feriado y el 24 aún no cerraba la carga al momento de la lectura — no es un
fallo (§8).

> **Historia del congelamiento (resuelta).** Gold llegó a estar 14 días atrás (8→22
> jul) porque los marts son `table` y nadie corría `dbt build`. Se refrescó a mano el
> 22-jul, volvió a atrasarse 2 días, y desde el 24-jul el workflow `dbt.yml` lo
> mantiene al día solo. Causa raíz cerrada.

Calidad de código: **210 tests en verde** (suite completa) + dbt en verde
(`fct_predicciones` PASS=14 con el test `no_negativo`; marts de precio PASS=23).

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

### 🟢 Tier B — entregable YA materializado en prod (desde 2026-07-22, automatizado desde 24-jul) → listas para cerrar

| Issue | Título | Estado |
|---|---|---|
| #32 | Entrenamiento batch de todos los pares | `ml.predicciones_raw` poblada (4,508 filas); corre en `ml.yml` |
| #33 | Backtesting walk-forward + métricas | `ml.backtest_metricas` poblada (498 filas) |
| #35 | Tabla `fct_anomalias` **materializada** por dbt | mart materializado (80 filas) |

Pendiente solo el cierre en GitHub con el comentario de evidencia (no bloquea nada).

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
| M3 dbt medallion | ✅ | silver + gold de precios poblados (423k filas), automatizado (`dbt.yml`) y con unidad normalizada a S/kg (§8) |
| M4 ML | ✅ | automatizado (`ml.yml` semanal); sirve `naive` con bandas, Prophet apagado con evidencia (§8) |
| M5 Dashboard/API | 🔲 | sin empezar (`observatorio/dashboard/` y `/api/` no existen) |
| M6 Deploy/bot | 🔲 | sin empezar |

---

## 5. Gaps / pendientes estructurales

1. **M5 (dashboard/API)** — el siguiente hito de producto. Ya tiene de qué alimentarse:
   gold fresco y automatizado, predicciones y anomalías al día.
2. **Idempotencia de scrapers (#21):** el camino diario ya es idempotente; falta
   unificar el flag `--fecha` y un test que lo garantice de forma ejecutable.
3. **Margen estrecho entre SISAP y `carga-supabase`** (§8): la carga corre a las 21:00
   UTC y SISAP suele terminar ~20:30, pero ha tardado hasta 3 h 27 min. Riesgo
   latente, todavía no materializado. Relacionado: #110 (una corrida se colgó 24 h).

**Resueltos:**
- ~~Unidad de SISAP mezclada (cajón/millar vs kg).~~ ✅ **2026-07-24** (§8, PR #117):
  `fct_precio_diario` normaliza con `equiv_kg_lt`.
- ~~Validación de canasta mal planteada (vs-IPC).~~ ✅ **#102 cerrada** (§8, PR #116):
  solidez interna + rangos de precio por producto.
- ~~Test dbt de "precio no negativo".~~ ✅ **2026-07-24** (§8, PR #115): guarda del mart.
- ~~Falta workflow de transformación (dbt y ML).~~ ✅ **En producción desde el
  2026-07-24** (§8): mergeados, corridos en verde y con `cron` habilitado.
- ~~Correr M4 una vez para poblar `ml.*`.~~ ✅ **Hecho 2026-07-22** (§8).
- ~~No había CI de tests (push/merge no verificaba nada).~~ ✅ **Resuelto 2026-07-15**:
  workflow `ci.yml` corre pytest en cada PR y push a main (PR #109, mergeado). Ver §8.

---

## 6. Acciones

- ✅ **Cerradas en GitHub las issues Tier A** (#28, #29, #30, #34, #15) — 2026-07-15,
  cada una con comentario apuntando a su PR/commit.
- ✅ **CI de tests activo** (`ci.yml`, PR #109 mergeado) — pytest en cada PR y push a main.
- ✅ **Gold refrescado** (2026-07-22, `dbt build` a mano, 49 nodos en verde) — recuperados
  los 14 días de atraso. **No resuelve la causa**: sin workflow, se vuelve a atrasar.
- ✅ **Pipeline de ML corrido contra producción** (2026-07-22, ver §8).
- ✅ **Workflows `dbt.yml` y `ml.yml` en producción** (2026-07-24, PRs #113/#114): mergeados,
  corridos en verde y con `cron` habilitado (dbt diario, ML semanal).
- ✅ **Prophet remedido sobre 157 series** (2026-07-24): pierde en las dos fuentes; queda
  descartado para el MVP, apagado por flag (§8).
- ✅ **Test dbt `no_negativo`, canasta #102 y unidad de SISAP** (2026-07-24, PRs #115/#116/#117, §8).

---

## 7. Decisión de despliegue de M4 — ✅ RESUELTA (2026-07-24)

**Decidido:** dos workflows separados, **dbt diario** y **ML semanal**
(`.github/workflows/dbt.yml` y `ml.yml`, creados el 2026-07-24 — ver §8). Se
descartó el workflow único: el reparto evita que un fallo de la rama de ML frene
el refresco diario de precios.

Queda registro de las opciones que se evaluaron y de las consideraciones técnicas,
porque siguen valiendo para #27 (Dagster vs Actions):

### Opciones que estuvieron sobre la mesa
- **A) Correr una vez en local** (rápido, aísla fallos de código de fallos de CI;
  idempotente, poblaría prod de inmediato). Desventaja: no queda automatizado.
  → Es lo que efectivamente pasó el 2026-07-22.
- **B) Workflow-first**: crear `ml.yml` y disparar el pipeline desde ahí. Más limpio
  como destino final; evita una corrida manual desechable.
- **C) Híbrido**: smoke-test local para de-riesgar y luego el workflow como automatización.
  → **Es el camino que se siguió**: corrida manual el 22-jul, workflows el 24-jul.

### Consideraciones técnicas (se resolvieron así)
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
6. **Relación con #27** (decidir Dagster OSS vs GitHub Actions): se resuelve por
   ahora quedándose en GitHub Actions. #27 sigue abierta para el futuro.

**Estado:** ✅ **cerrado el 2026-07-24**. Workflows mergeados (PR #113), los dos
corridos a mano en verde y los `cron` habilitados (PR #114): dbt diario a las 22:00
UTC, ML los lunes a las 23:00 UTC.

---

## 8. Bitácora de cambios

Registro cronológico de cada acción realizada sobre el proyecto en estas sesiones
(lo más reciente primero).

### 2026-07-24 (3/3) — calidad de datos: test no-negativo, canasta (#102) y unidad SISAP

Tres cambios encadenados, cada uno destapado por el anterior.

**1. Test dbt `no_negativo`** (PR #115). Blindaje contra el bug de Prophet (predecía
precios negativos, ver entrada 1/3). Test genérico propio en `dbt/tests/generic/`
—sin `dbt_utils`, que el proyecto no usa— sobre `precio_pred`, `precio_pred_inf` y
`precio_pred_sup` de `fct_predicciones`. Ignora NULL (las bandas del baseline pueden
serlo). Verificado que **no es un no-op**: el SQL compilado es `... where precio_pred
< 0`, que en dbt falla si devuelve una fila. `dbt test --select fct_predicciones` →
PASS=14.

**2. Reformulación del criterio de validación de la canasta — issue #102 (PR #116),
CERRADA.** El grueso ya venía del #20 (veredicto = solidez interna, contraste vs-IPC
degradado a descriptivo). Faltaba la **propuesta 1**: el chequeo de "precios
plausibles" usaba un único rango 0.1–100/kg para todo y solo atrapaba errores de
unidad groseros (una papa a S/45/kg pasaba). Se implementaron **rangos por producto**
(`RANGOS_PLAUSIBLES_SOLKG`), calibrados sobre la distribución real de SISAP minorista
2024–2026 (p01–p99) con margen para picos de escasez. Minorista Lima sigue `CANASTA
SÓLIDA`; suite +3 tests.

**3. Normalización de unidad de SISAP a S/kg (PR #117) — cierra el hallazgo lateral
del #102.** El chequeo por producto del punto 2 destapó que `fct_precio_diario`
mezclaba unidades: SISAP mayorista cotiza varios productos por cajón/bolsa/millar, no
por kg (tomate en "Cajón chico" de 27 kg → S/63/cajón; limón en bolsa de 45 kg →
S/72). La fuente **ya publicaba el factor** en `bronze.sisap_precios.equiv_kg_lt`, y
el staging decía que la normalización se hacía "en marts (#24)" pero nunca se
implementó. Ahora el mart divide `precio_prom / equiv_kg_lt`.

| Producto | Mayorista antes | Después | Minorista (ref.) |
|---|---|---|---|
| limón | mediana S/55 | **S/1.58/kg** | S/4.36 |
| tomate | mediana S/62 | **S/2.31/kg** | S/4.48 |

- En **todos** los productos mayorista quedó por debajo de minorista, como debe ser.
- MVP minorista tiene `equiv=1.0` → sin cambios; **0 filas** priceadas con equiv NULL.
- Corrige toda la cadena: `fct_precio_medias_moviles` y el ML leen de
  `fct_precio_diario`. Se re-corrió `ml.yml` para refrescar las predicciones con los
  precios nuevos (mayorista limón S/2.13, tomate S/2.45). El chequeo de precios de la
  validación en mayorista pasó de `REVISAR` a OK (sigue `REVISAR` por cobertura, que
  es esperable: mayorista no tiene los 6 productos MVP con peso todos los meses).
- Detectado y corregido el mismo día; documentado en `docs/validacion_canasta_vs_ipc.md`
  y en el schema del staging (`equiv_kg_lt`, `unidad_medida`).

**Cierres de esta jornada:** #102 cerrada en GitHub (con mapeo DoD → evidencia).
Suite: **210 tests en verde**.

### 2026-07-24 (2/3) — crons habilitados (PR #114)

Tras ver las dos primeras corridas automáticas en verde (entrada 1/3), se
descomentaron los `cron`: **dbt diario 22:00 UTC**, **ML lunes 23:00 UTC**. Antes
eran `workflow_dispatch`-only. Ambos figuran `active` en `gh workflow list`.

### 2026-07-24 (1/3) — orquestación (dbt + ML) y veredicto final sobre Prophet

**Verificación previa (lectura en prod).** Se confirmó que el diagnóstico de §5 no
era teórico: `gold.fct_precio_diario` volvió a quedarse en `max(fecha_captura)=
2026-07-22` mientras marketplace y OSINERGMIN ya tenían bronze del 23-jul. Dos días
de atraso a los dos días del refresco manual.

**Workflows creados** (PR #113, mergeado; los `cron` se habilitaron después — ver 2/3):

| Archivo | Cadencia | Alcance |
|---|---|---|
| `.github/workflows/dbt.yml` | diaria 22:00 UTC (comentada) | `dbt build --exclude "fct_predicciones+" "fct_anomalias+"` |
| `.github/workflows/ml.yml` | lunes 23:00 UTC (comentada) | los 3 runners de `observatorio/ml/` + `dbt build --select fct_predicciones fct_anomalias` |
| `.github/actions/entorno-dbt/` | — | action compuesta: deriva los 5 `SUPABASE_DB_*` desde `SUPABASE_DB_URL` |

- **0 secrets nuevos**, como se propuso en §7: la action parsea `SUPABASE_DB_URL`
  (el único secret que existe), fuerza el puerto **5432** y enmascara la contraseña
  con `::add-mask::`. Verificado abriendo una conexión a prod con exactamente esos
  cinco parámetros.
- Ambos selectores verificados con `dbt ls` contra el proyecto real: el diario
  resuelve a los 7 modelos de precios, el semanal a los 2 marts de ML y sus tests.
- `ml.yml` **no declara `PYTHONUTF8=1`** (rompe Prophet, §8 del 22-jul) y corre en
  `ubuntu-latest`.
- Ambos nacen `workflow_dispatch`-only con el `cron` comentado, y crean issue de
  alerta on-failure reusando el patrón de `carga-supabase.yml`.

**Veredicto final sobre Prophet: pierde, y con más datos pierde más.**

El veredicto del 22-jul se había medido sobre 15 series, y el backfill histórico de
SISAP (#16) entró el 23-jul multiplicando por 10 la población modelable. Se remidió
el backtesting **en memoria, sin escribir en prod**, sobre las **157 series** que
pasan el umbral hoy:

| Fuente | series | naive | media móvil | prophet | Prophet gana |
|---|---:|---:|---:|---:|---:|
| `sisap_mayorista` | 83 | **4.05 %** | 4.95 % | 8.45 % | 5/83 (6 %) |
| `sisap_minorista` | 68 | **1.58 %** | 1.65 % | 4.48 % | 6/68 (9 %) |

`sisap_mayorista` es la familia más densa que existe (181 observaciones contra 82 de
minorista) y ahí Prophet queda **2.1× peor** que repetir el último precio. La causa
es la estructura de huecos, no el conteo: hueco mediano de 5 días y agujeros de hasta
332–378 días, con el precio moviéndose 3–5 % entre observaciones consecutivas.
**Subir el umbral queda descartado** — se probó contra las series más densas y
empeora. Detalle en `docs/ml.md`.

**Consecuencia aplicada: se sirve `naive` con bandas propias.** `config.USAR_PROPHET`
pasa a `False` y `config.MODELO_SERVIDO` a `"naive"`. Prophet no se borra: el
backtesting lo sigue midiendo, así que el veredicto es revisable con datos.

Al apagarlo aparecían dos problemas que se resolvieron en el mismo cambio:

1. **Las bandas se habrían quedado en null** (`precio_pred_inf/sup` del mart), y el
   dashboard de #38 sin nada que dibujar: Prophet era quien las producía. Ahora
   `baseline.agregar_bandas` las estima de la volatilidad de la propia serie,
   normalizada por el hueco entre observaciones y ensanchada con `σ·√h`. Verificado
   contra las 174 series de prod: solo 3 (1.7 %) quedan sin banda.
2. **La comprobación de cobertura habría abortado corridas sanas.** `run_entrenamiento`
   calculaba por su cuenta cuántas series esperaba de cada modelo, así que al apagar
   Prophet esperaba 157 series suyas, obtenía 0 y fallaba con "se perdió el 100 % de
   las series de prophet" sin escribir nada. La regla de decisión se unificó en
   `prophet_modelo.modelo_de`, que ahora usan tanto el pronóstico como la cobertura.
   Los tests lo detectaron antes de llegar a producción y quedó una regresión que lo
   cubre.

Suite: **207 tests en verde** (7 nuevos).

**Las dos primeras corridas automatizadas (mismo día, tras mergear #113):**

| Workflow | Resultado |
|---|---|
| `dbt.yml` (run 30117943903) | PASS=49, ERROR=0 en 34 s · gold a 423,085 filas, al 23-jul |
| `ml.yml` (run 30118895845) | 2,436 predicciones · 477 anomalías · 453 métricas · marts PASS=22 |

La cobertura del entrenamiento reportó `naive 174/174` (ninguna serie esperada por
Prophet, como debe ser con el flag apagado) y la del backtesting
`media_movil 151/151 · naive 151/151 · prophet 151/151`: Prophet se sigue midiendo.
Con ambos en verde se habilitaron los `cron` (PR #114).

#### 🔴 Prophet no solo perdía: predecía precios negativos

Al verificar el mart tras la corrida apareció algo que el MAPE no delataba. De las
84 filas que Prophet había dejado en `gold.fct_predicciones` el 22-jul, **40
predicen un precio negativo** (hasta **−3.84 soles**) y 48 tienen la banda inferior
bajo cero. Prophet es un modelo aditivo sin cota inferior: con series cortas y
ruidosas extrapola por debajo de cero sin inmutarse. Las 154 filas de `naive` del
24-jul no tienen ninguna (mínimo 1.33), porque repetir un precio observado no puede
salirse del rango de lo posible y la banda va recortada en 0.

Las filas malas siguen en el mart como registro histórico —el grano conserva todas
las corridas y el consumidor filtra la más reciente—, así que no se sirven. Queda
anotado que un test dbt de "precio no negativo" sería natural aquí, pero **fallaría
contra esas filas del 22-jul**: hay que borrarlas antes de añadirlo.

**Borradas el 2026-07-24.** Se eliminaron las 210 filas de Prophet de la corrida
22-jul en `ml.predicciones_raw` (origen del mart; el mart es `table` y se
reconstruye desde ahí, así que borrar solo el mart no era durable) y se reconstruyó
`fct_predicciones` con `dbt build --select fct_predicciones` (PASS=12, ERROR=0).
Respaldadas antes a CSV. La media móvil del 22-jul (70 filas en el mart) y la
corrida naive del 24-jul (154) quedan intactas. Verificado: **0 filas con precio o
banda negativa** y **0 filas modelo='prophet'** en todo el mart. El test dbt de
precio no negativo queda desbloqueado (pendiente nº1 de §5).

**Sobre la ausencia de SISAP del 23-jul: no es un fallo.** El 2026-07-23 fue feriado
en Perú (Día de la Fuerza Aérea) y el scraper lo detectó por diseño:
`📅 Thursday 23/07/2026 — día no hábil, SISAP no publica. Saltando sin error.`
Que `bronze.sisap_precios` se quedara en 22-jul mientras marketplace y OSINERGMIN
iban al 23 es **el comportamiento correcto**. Desde el 2026-06-01 falta un único día
hábil de SISAP en bronze (26-jun).

**Riesgo latente que sí conviene atender.** `carga-supabase` corre a las 21:00 UTC
asumiendo que los scrapers ya terminaron, y las corridas de SISAP tienen una
dispersión grande: la mayoría dura entre 30 s y 21 min (terminan ~20:30 UTC), pero la
del 23-jul tardó **3 h 27 min** y la del 17-jul se **canceló a las 24 h** (es la
issue #110, aún abierta). En un día hábil con ese retraso, el CSV perdería la ventana
de carga. Todavía no pasó, pero el margen es de apenas 30 minutos.
Mitigación: mover el cron de la carga o encadenarlo con `workflow_run`.

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
