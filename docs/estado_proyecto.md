# Estado del proyecto — snapshot

> **Snapshot:** 2026-09-05 · Rama `main`
> Documento **vivo** de registro del proyecto (para el equipo). Cada acción realizada
> se anota en la **bitácora de cambios** al final (§8). Verificación de datos hecha en
> **lectura** contra Supabase producción.

---

## 1. Resumen ejecutivo

- **Ingesta (bronze):** ✅ en producción y verde a diario (SISAP, Marketplace,
  OSINERGMIN, Clima). Endurecida el 2026-09-05: todos los jobs con `timeout-minutes`
  y alertas que se deduplican y se cierran solas (§8).
- **dbt (silver→gold de precios):** ✅ automatizado, `dbt.yml` diario. Gold al día.
- **ML (M4):** ✅ automatizado, `ml.yml` semanal. Sirve `naive` con bandas; Prophet
  sigue apagado y el backtest lo confirma corrida a corrida (§2).
- **M5 (dashboard/API):** 🟡 **arrancado.** La API REST está en `main` (#43 cerrada):
  `GET /health`, `/precios`, `/canasta` sobre gold, con paginación y orden estables.
  Falta el dashboard Streamlit (#36–#42) y el deploy (#47).
- **M6 (deploy/bot):** 🔲 sin empezar.

Frase clave: **M5 dejó de ser una hoja en blanco.** El backend de producto ya existe
y está probado contra prod; lo que falta es la cara visible (Streamlit) y sacar la
API de `main` a un host (#47).

---

## 2. Verificación en producción (Supabase, solo lectura, 2026-09-04/05)

| Objeto | Estado | Filas | Última fecha |
|---|---|---|---|
| `bronze.sisap_precios` | ✅ | 25,527 | 2026-09-04 |
| `bronze.marketplace_precios` | ✅ | 777,795 | 2026-09-04 |
| `bronze.osinergmin_precios` | ✅ | 787,678 | 2026-09-04 |
| `bronze.clima` | ✅ | 198 | 2026-09-04 |
| `bronze.inei_ipc` | ⚠️ | 389 | último mes **2026-05** (§5) |
| `gold.fct_precio_diario` | ✅ | **725,518** | 2026-09-04 |
| `gold.fct_precio_medias_moviles` | ✅ | 725,518 | 2026-09-04 |
| `gold.dim_fecha` | ✅ | 975 | 2026-09-04 |
| `gold.canasta_consumo_dept` | ✅ | 150 | ENAHO 2023 |
| `ml.predicciones_raw` | ✅ | 19,124 | corrida 2026-08-31 |
| `ml.anomalias_raw` | ✅ | 3,596 | corrida 2026-08-31 |
| `ml.backtest_metricas` | ✅ | 3,246 | corrida 2026-08-31 |
| `gold.fct_predicciones` | ✅ | 1,148 | corrida 2026-08-31 |
| `gold.fct_anomalias` | ✅ | 458 | corrida 2026-08-31 |

Gold creció de 423k a 725k filas desde el snapshot anterior: la automatización
sostuvo el ritmo sin intervención manual durante seis semanas.

**El backtest sigue dándole la razón al apagado de Prophet.** Última corrida
(2026-08-31, 156 pares por modelo):

| modelo | MAPE promedio |
|---|---|
| `naive` | **6.33** |
| `media_movil` | 6.56 |
| `prophet` | 9.44 |

Se sirve solo `naive`: las 2,436 filas de la última corrida en `ml.predicciones_raw`
y las 154 de `gold.fct_predicciones` son todas de ese modelo. El backtest mide los
tres a propósito — es su función, no un residuo del modelo descartado.

Calidad de código: **249 tests en verde** (suite completa; eran 210 en el snapshot
anterior). dbt no se re-verificó en esta lectura.

---

## 3. Clasificación de issues verificadas

Las tablas Tier A / Tier B del snapshot anterior ya no aplican: **todo lo que
estaba pendiente de cierre se cerró.** #32, #33 y #35 (los entregables de M4 que
esperaban materialización en prod) están cerradas, igual que #21, #102, #16, #20,
#14 y #43.

**Abiertas hoy: 19**, y todas son backlog real, no deuda de cierre:

| Grupo | Issues |
|---|---|
| M5 — dashboard y API | #36, #37, #38, #39, #40, #41, #42, #44 |
| M6 — deploy, bot, monitoreo | #45, #46, #47, #48, #49, #50, #51, #52, #53 |
| Orquestación (a futuro) | #27 (Dagster vs Actions), #31 (setup Dagster, opcional) |

> **Nota sobre #27.** La decisión de hecho ya se tomó —se sigue en GitHub Actions,
> con `dbt.yml` y `ml.yml` en producción desde el 24-jul— pero la issue sigue
> abierta como decisión formal a futuro. Ver §7.

---

## 4. Milestones (estado real)

| Hito | Estado | Nota |
|---|---|---|
| M1 Setup | ✅ | Repo + Supabase |
| M2 Ingesta | ✅ | SISAP + Marketplace + INEI + OSINERGMIN + Clima en prod |
| M3 dbt medallion | ✅ | gold poblado (725k filas), automatizado (`dbt.yml`) |
| M4 ML | ✅ | automatizado (`ml.yml` semanal); sirve `naive`, Prophet apagado con evidencia |
| M5 Dashboard/API | 🟡 | **API lista** (`observatorio/api/`, #43 cerrada); falta Streamlit (#36–#42) y deploy (#47) |
| M6 Deploy/bot | 🔲 | sin empezar |

---

## 5. Gaps / pendientes estructurales

1. **Dashboard Streamlit (#36–#42)** — es lo único entre el proyecto y un producto
   visible. Todo lo que necesita ya existe: gold fresco, canasta, predicciones,
   anomalías y una API que las sirve.
2. **Hueco de SISAP 2026-01 → 2026-05.** Cinco meses sin dato en `bronze.sisap_precios`
   (hay 2025-10..12 y después recién 2026-06). El workflow `backfill-sisap.yml` ya
   existe y lo cubre: es un `workflow_dispatch` con `desde=2026-01-01`,
   `hasta=2026-05-31` y `dry_run=false`. **Cero código, nadie lo corrió.**
3. **INEI/IPC congelado.** `silver.stg_ipc_inei` llega hasta **2026-05**; la última
   ingesta fue el 2026-06-13. Cualquier contraste con el IPC trabaja con dato de
   hace tres meses.
4. **Deuda de la API antes del deploy (#47/#44)** — del review de #135, sin resolver
   porque no bloquea a #36:
   - una conexión Postgres nueva por request, sin pool y sin `connect_timeout`;
   - la API "solo-lectura" usa `SUPABASE_DB_URL`, la credencial con permisos de
     escritura: es una convención del código, no una restricción;
   - `/health` no toca la base — como readiness probe reporta sano con la base caída.
5. **Un runner apagado a mitad de job sigue sin detectarse.** Las alertas nuevas
   cubren fallo y cancelación, pero si el runner self-hosted desaparece no corre
   ningún step, ni con `if: always()`. Haría falta un watchdog externo (un workflow
   programado que mire la última corrida exitosa de cada pipeline).
6. **Margen estrecho entre SISAP y `carga-supabase`.** La carga corre a las 21:00
   UTC y SISAP suele terminar ~20:30, pero el tope nuevo le permite estirarse hasta
   90 min: el timeout acota el cuelgue, no el solapamiento. Si SISAP se pasa, la
   carga del día falla con "sin archivos cargados" (ya no genera una issue nueva por
   día, pero sigue siendo un hueco de dato). Sin materializar todavía.
7. **ENAHO 2024/2025** — la canasta sigue con pesos de ENAHO 2023. Depende de
   conseguir el código INEI del año nuevo; es externo al equipo.

**Resueltos desde el snapshot anterior:**
- ~~Jobs sin `timeout-minutes` (OSINERGMIN llegó a 1440 min y SISAP a 299).~~
  ✅ **2026-09-05** (PR #143): tope por workflow.
- ~~Alertas que no cubrían la cancelación, no se deduplicaban y no se cerraban.~~
  ✅ **2026-09-05** (PR #143): composite action `.github/actions/alerta`.
- ~~Corridas que se colgaban sin tope (#110, 24 h).~~ ✅ **2026-09-05** (PR #143):
  el `timeout-minutes` las acota.
- ~~Idempotencia de scrapers (#21).~~ ✅ **cerrada** (PR #123: `--fecha` unificado + test).
- ~~Unidad de SISAP mezclada.~~ ✅ 2026-07-24 (PR #117).
- ~~Validación de canasta mal planteada.~~ ✅ #102 cerrada (PR #116).
- ~~Test dbt de "precio no negativo".~~ ✅ 2026-07-24 (PR #115).
- ~~Falta workflow de transformación (dbt y ML).~~ ✅ 2026-07-24 (PRs #113/#114).
- ~~Correr M4 una vez para poblar `ml.*`.~~ ✅ 2026-07-22.
- ~~No había CI de tests.~~ ✅ 2026-07-15 (PR #109).

---

## 6. Acciones

- ✅ **API REST mergeada** (2026-09-05, PRs #135 y #144): `observatorio/api/` con
  `/health`, `/precios` y `/canasta`; #43 cerrada. Primer entregable de M5.
- ✅ **Alertas y timeouts endurecidos** (2026-09-05, PR #143) — ver §8.
- ✅ **7 issues de alerta cerradas** (#136–#142): eran ruido acumulado, todas ya
  resueltas solas. El tablero volvió a tener señal.
- ✅ **Docs del canasto ampliado publicadas** (2026-09-05, PR #145): un commit del
  23-jul que había quedado sin pushear en un clon local.
- ✅ **Workflows `dbt.yml` y `ml.yml` en producción** (2026-07-24, PRs #113/#114).
- ✅ **Prophet remedido sobre 157 series** (2026-07-24): descartado para el MVP.
- ✅ **CI de tests activo** (`ci.yml`, PR #109) — pytest en cada PR y push a main.

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

### 2026-09-05 — desatasco de M5, endurecimiento de alertas y limpieza del tablero

Sesión de revisión de estado que terminó en cuatro merges. El punto de partida:
**17 días sin mergear nada** y un solo PR en vuelo, parado por falta de review.

**1. API REST mergeada — M5 arranca (PRs #135 y #144).**
`#135` llevaba 17 días abierta, con CI verde y sin conflictos, esperando review.
Se revisó y se mergeó (`07c9a8e`); #43 quedó cerrada — había seguido abierta porque
el PR decía "Cierra #43" y GitHub solo reconoce las keywords en inglés.

Del review salieron 8 hallazgos. Los cuatro que bloqueaban el consumo desde el
dashboard se corrigieron en `#144` (`723fb2d`), todos verificados contra prod:

- **`count` era el tamaño de página, no el total** → la respuesta pasa a
  `{total, count, limit, offset, results}`, con el total vía `COUNT(*) OVER ()`
  en la misma query (sin segundo viaje, que hoy sería una segunda conexión).
- **El `ORDER BY` no era un orden total** → LIMIT/OFFSET podía duplicar y saltear
  filas. Ambos endpoints ordenan ahora por todo el grano/PK. Muerde recién con un
  segundo departamento o un segundo año ENAHO, que es la dirección del proyecto.
- **Comodines de ILIKE sin escapar** → `?producto=%` devolvía la tabla entera.
  Verificado en prod: ahora devuelve 13,339 filas (las que contienen un `%`
  literal, tipo "100% Puro") en vez de 725,518.
- **`if anio:` descartaba `anio=0`** y devolvía todos los años → `is not None` +
  `ge=2000, le=2100`.

Los otros cuatro hallazgos son de deploy, no de uso, y quedan para #47/#44: sin
pool ni timeouts de conexión, credencial con permisos de escritura, y `/health`
que no toca la base. Anotados en §5.

**2. Alertas y timeouts (PR #143, `b254c32`).**
Al revisar las últimas 30 corridas de cada workflow contra la API de Actions
aparecieron tres fallas del sistema de alertas:

- **Ningún job tenía `timeout-minutes`** salvo `ml.yml`. OSINERGMIN llegó a correr
  **1440 min (24 h)** —el cuelgue que había quedado anotado como #110— y SISAP
  **299 min**, contra medianas de 20 y 0 min. Ahora cada workflow tiene tope.
- **`if: failure()` no cubre `cancelled()`**, que es justo el estado en que muere un
  job cuando se agota el timeout o el runner self-hosted desaparece. El 2026-09-01
  SISAP murió así (`KeyboardInterrupt` dentro del `time.sleep` de reintento en
  `run_ingesta_sisap.py:95`) y **no generó alerta**: la levantó `Carga Bronze` con
  "sin archivos cargados", señalando la consecuencia y no la causa. Ahora el step
  corre con `if: always()` y recibe `job.status`.
- **Las alertas no se deduplicaban ni se cerraban**: una issue nueva por día de
  falla, ninguna cerrada al recuperarse. Con un marcador HTML por fuente, ahora se
  comenta en la issue abierta y se cierra sola al volver a verde.

Los 8 bloques de alerta duplicados (bash en unos, PowerShell en otros) quedaron en
una composite action única, `.github/actions/alerta` sobre `actions/github-script@v9`,
que corre igual en el runner Windows y en `ubuntu-latest` — mismo patrón que
`entorno-dbt`. Tasas de fallo previas: Carga Bronze 4/17, SISAP 3/13, OSINERGMIN 2/17.

**3. Limpieza del tablero.** Cerradas #136–#142, las 7 issues de alerta que estaban
abiertas sin motivo (los pipelines llevaban días en verde). Las abiertas bajaron de
27 a 19, y las 19 son backlog real.

**4. Docs rescatadas (PR #145, `ab96581`).** El commit `2f7a413` del 23-jul —el
hallazgo de que ampliar el canasto cierra la magnitud del contraste con el IPC pero
no el timing, más la nota de reconstruir dependientes con `dbt build --select
fct_precio_diario+`— había quedado sin pushear en un clon local y nunca llegó a
`main`. Rebasado y mergeado; el conflicto en `dbt/README.md` (upstream había metido
ahí la sección "Automatización") se resolvió conservando ambos lados.

**Corrección de una lectura previa.** Durante la sesión se afirmó que el pipeline de
ML seguía publicando predicciones de Prophet peores que el baseline. Es falso:
Prophet está apagado desde el 2026-07-24 y en prod solo se sirve `naive` (§2). El
error vino de leer un clon local desactualizado en 10 commits, sin acceso a GitHub.

**Nota operativa.** El acceso a GitHub desde el clon local estaba roto: `gh` y git
autenticados con una cuenta sin permisos sobre el repo (404 en `fetch`). Se resolvió
logueando la cuenta correcta y ampliando el token con el scope `workflow`, necesario
para pushear cambios en `.github/workflows/`.

**Pendiente de verificar en la próxima corrida:** que la alerta nueva se cree y se
cierre sola en un ciclo real. Se puede forzar con `workflow_dispatch` +
`simular_fallo=true` y después un dispatch normal.

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
