# Estado del proyecto — snapshot

> **Snapshot:** 2026-07-15 · Rama `main`
> Documento **vivo** de registro del proyecto (para el equipo). Cada acción realizada
> se anota en la **bitácora de cambios** al final (§8). Verificación de datos hecha en
> **lectura** contra Supabase producción.

---

## 1. Resumen ejecutivo

- **Ingesta + dbt (bronze→silver→gold de precios):** ✅ en producción, con datos reales.
- **ML (M4):** 🟡 **código completo y testeado, pero NUNCA ejecutado en producción.**
- **M5 (dashboard/API) y M6 (deploy/bot):** 🔲 sin empezar.

Frase clave: **M4 está "hecho" pero no "desplegado"** — modelo construido y probado
que aún no ha tocado los 292k registros de precios que lo esperan.

---

## 2. Verificación en producción (Supabase, solo lectura)

| Objeto | Estado | Filas |
|---|---|---|
| `gold.fct_precio_diario` | ✅ existe | **292,502** |
| `ml.predicciones_raw` | ❌ no existe | — |
| `ml.anomalias_raw` | ❌ no existe | — |
| `ml.backtest_metricas` | ❌ no existe | — |
| `gold.fct_predicciones` | ❌ no existe | — |
| `gold.fct_anomalias` | ❌ no existe | — |

Causa raíz: **no hay workflow que dispare el ML** (los crons son solo `ingesta-*` y
`carga-supabase`), y tampoco se corrió a mano. Las tablas `ml.*` se autocrean al
primer `insert`, por eso no existen aún.

Calidad de código: **170 tests en verde** (suite completa).

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
| M4 ML | 🟡 | **código completo + testeado, sin ejecución en prod** |
| M5 Dashboard/API | 🔲 | sin empezar (`observatorio/dashboard/` y `/api/` no existen) |
| M6 Deploy/bot | 🔲 | sin empezar |

---

## 5. Gaps / pendientes estructurales

1. **Falta workflow de ML** (`ml.yml`) — es la causa de que M4 no tenga huella en prod.
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
