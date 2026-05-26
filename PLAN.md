# Observatorio de Precios — Canasta Básica Perú

Sistema que recolecta diariamente precios mayoristas de alimentos en Perú, detecta anomalías y publica un dashboard con el costo de la canasta básica por departamento.

**Equipo:** 2 personas · **Duración:** 12 semanas · **Costo:** En Desarrollo

---

## Stack Inicial Propuesto

| Capa | Tecnología |
|---|---|
| Orquestación | **GitHub Actions** (S1–S5) → **Dagster OSS** (S6+) |
| Storage de archivos crudos | **Cloudflare R2** |
| Base de datos | **Supabase Postgres** (free tier) |
| Transformaciones | **dbt-core** |
| ML | **Python + DuckDB + Prophet** |
| API | **FastAPI** en Fly.io free tier |
| Dashboard | **Streamlit Community Cloud** |
| Alertas | **Bot Telegram** |

---

## Arquitectura

```
[GitHub Actions cron diario 04:00 UTC-5]
            │
            ├─► Scraper SIMA-PM ─┐
            ├─► SENAMHI clima   ─┤
            ├─► OSINERGMIN      ─┤
            └─► MIDAGRI         ─┤
                                  │
                                  ▼
            ┌──────────────────────────────────┐
            │  Cloudflare R2 (PDFs crudos)     │
            └──────────────────────────────────┘
                                  │
                                  ▼
            ┌──────────────────────────────────────────┐
            │  Supabase Postgres                       │
            │  bronze.* → silver.* (dbt) → gold.*      │
            └──────────────────────────────────────────┘
                                  │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
       [ML semanal]         [FastAPI]          [Streamlit Cloud]
       Prophet + DuckDB     /precios            Dashboard público
       → fct_anomalias      /canasta
       → fct_predicciones
            │
            ▼
       [Bot Telegram]  alertas diarias
```

---

## Cronograma — 12 semanas

```
Semana            1  2  3  4  5  6  7  8  9 10 11 12
─────────────────────────────────────────────────────
Setup infra       ██
Scraper SIMA         ██ ▓▓                              ← DATOS FLUYENDO desde S3
Fuentes extra              ██ ██
Datos históricos        ██ ██
Modelo medallion (dbt)        ██ ██
Canasta ENAHO              ██ ██ ██
Modelado Prophet + ML                ██ ██
Dashboard Streamlit                        ██ ██
Bot Telegram + API                            ██ ██
Deploy + monitoreo                               ██ ██

Hitos:            M1 M2          M3    M4    M5    M6
```

### Hitos
- **M1 (fin S1)** — Repo + Docker Compose + Supabase conectados.
- **M2 (fin S2)** — ⭐ **Scraper SIMA-PM en producción.** Empieza a acumular histórico.
- **M3 (fin S6)** — dbt con bronze/silver/gold + INEI/MIDAGRI cargados.
- **M4 (fin S8)** — Modelo Prophet entrenado + detección de anomalías.
- **M5 (fin S10)** — Dashboard Streamlit funcional con datos reales.
- **M6 (fin S12)** — Deploy completo: dashboard público + bot + API. ~10 semanas de histórico propio.

---

## Gestión de tareas — GitHub Projects + Issues

Trabajamos sin roles fijos: cualquiera toma cualquier tarea según interés y disponibilidad de la semana.

**Setup recomendado:**
- **1 issue = 1 tarea.** Título corto + checklist en el cuerpo + estimación en horas.
- **Labels por área:** `area:ingesta`, `area:datos`, `area:ml`, `area:frontend`, `area:devops`.
- **Labels por prioridad:** `priority:critical`, `priority:high`, `priority:medium`.
- **Milestones M1–M6** mapean a los hitos del cronograma.
- **GitHub Projects v2** con vista kanban: `Backlog → Esta semana → En curso → En review → Hecho`.

**Reglas operativas:**
- Cada uno se autoasigna las tareas que toma. **WIP máximo: 2 tareas activas por persona.**
- Standup async semanal (lunes): cada uno comenta en el issue de tracking de la semana qué planea tomar.
- Si una tarea bloquea a otro, comentar en el issue y mover a "Bloqueada".
- PRs pequeños (<400 líneas), code review obligatorio del otro antes de mergear.
- Las tareas marcadas ⭐ son críticas: deben terminarse en su semana, sí o sí.

**Alternativas si GitHub Projects no encaja:** Linear (más pulido, free <250 issues), Trello (más simple, externo al repo). Recomendamos GitHub Projects por integración con PRs y código.

---

## Detalle de tareas por semana

### S1 — Setup (≈13 h) · Milestone M1
- [ ] Crear repo + estructura inicial (`pyproject.toml`, pre-commit, GH Actions CI básico) — **3 h** · `area:devops`
- [ ] Docker Compose con Postgres local para desarrollo — **2 h** · `area:devops`
- [ ] Crear cuenta Supabase + probar conexión Python — **2 h** · `area:datos`
- [ ] ⭐ **Validar parseo de 3 PDFs SIMA-PM con `tabula-py`** (decisión go/no-go) — **4 h** · `area:ingesta`
- [ ] Documentar fuentes en `docs/sources.md` (URLs, formatos, frecuencias) — **2 h** · `area:datos`

### S2 — Scraper en producción (≈17 h) · Milestone M2 ⭐
- [ ] ⭐ Scraper SIMA-PM end-to-end (download → parse → validate → insert) — **8 h** · `area:ingesta`
- [ ] GitHub Actions con cron 04:00 UTC-5 + secrets — **4 h** · `area:devops`
- [ ] Upload de PDFs crudos a Cloudflare R2 — **3 h** · `area:datos`
- [ ] Alerta de fallo del scraper (issue auto-creado o webhook) — **2 h** · `area:devops`

### S3 — Robustez + datos históricos (≈15 h)
- [ ] Tests del scraper con fixtures de PDFs reales — **4 h** · `area:ingesta`
- [ ] Reintentos + manejo de feriados/PDFs faltantes — **3 h** · `area:ingesta`
- [ ] Descarga histórica INEI (script one-shot, base 2009-) — **4 h** · `area:datos`
- [ ] Notebook exploratorio: estructura ENAHO microdatos — **4 h** · `area:datos`

### S4 — Fuentes complementarias (≈17 h)
- [ ] Scraper SENAMHI (clima diario por estación) — **6 h** · `area:ingesta`
- [ ] Scraper OSINERGMIN (precios combustible) — **4 h** · `area:ingesta`
- [ ] Descarga histórica MIDAGRI — **3 h** · `area:datos`
- [ ] Diseño de tabla `canasta_consumo_dept` desde ENAHO — **4 h** · `area:datos`

### S5 — Validaciones + canasta (≈18 h)
- [ ] Great Expectations: setup + suite por fuente — **6 h** · `area:datos`
- [ ] Construir canasta básica representativa por departamento — **6 h** · `area:datos`
- [ ] Validar metodología canasta vs IPC histórico — **3 h** · `area:datos`
- [ ] Reescritura de scrapers para idempotencia completa — **3 h** · `area:ingesta`

### S6 — dbt completo (≈19 h) · Milestone M3
- [ ] Inicializar proyecto dbt + conectar Supabase — **2 h** · `area:datos`
- [ ] Modelos staging (silver): stg_precios_sima, stg_clima, etc. — **6 h** · `area:datos`
- [ ] Modelos marts (gold): `fct_precio_diario` + dimensiones — **6 h** · `area:datos`
- [ ] Medias móviles 7/30/90 días — **3 h** · `area:datos`
- [ ] dbt tests (uniqueness, not_null, referential integrity) — **2 h** · `area:datos`

### S7 — Modelado baseline (≈14 h)
- [ ] Decidir si migrar a Dagster OSS o quedarse en GH Actions — **1 h** · `area:devops`
- [ ] Baseline naive + media móvil como referencia — **3 h** · `area:ml`
- [ ] Notebook Prophet PoC con 1 producto × 1 mercado — **4 h** · `area:ml`
- [ ] Pipeline reusable de entrenamiento por (producto, mercado) — **5 h** · `area:ml`
- [ ] *(Opcional)* Setup Dagster + `dagster-dbt` si se decidió migrar — **+5 h** · `area:devops`

### S8 — ML completo (≈17 h) · Milestone M4
- [ ] Entrenamiento batch de todos los pares (producto × mercado) — **5 h** · `area:ml`
- [ ] Backtesting walk-forward + métricas MAPE/RMSE — **5 h** · `area:ml`
- [ ] Detección de anomalías (residuo normalizado > 2.5σ) — **4 h** · `area:ml`
- [ ] Tabla `fct_anomalias` materializada por dbt — **3 h** · `area:datos`

### S9 — Dashboard (≈18 h)
- [ ] Estructura Streamlit (multipage) — **3 h** · `area:frontend`
- [ ] Página principal: selector dept + semáforo canasta — **4 h** · `area:frontend`
- [ ] Página evolución temporal con bandas Prophet — **5 h** · `area:frontend`
- [ ] Mapa coroplético (Folium) — **4 h** · `area:frontend`
- [ ] Caché con `st.cache_data` + vistas materializadas — **2 h** · `area:frontend`

### S10 — Dashboard pulido + API (≈15 h) · Milestone M5
- [ ] Refactor y mejoras UX dashboard — **4 h** · `area:frontend`
- [ ] Pruebas de usabilidad con 3 usuarios externos — **3 h** · `area:frontend`
- [ ] FastAPI scaffold + endpoints `/precios`, `/canasta` — **5 h** · `area:frontend`
- [ ] Auth básica con API keys + rate limiting — **3 h** · `area:devops`

### S11 — Bot + alertas (≈16 h)
- [ ] Bot Telegram (suscripciones + DB schema) — **5 h** · `area:frontend`
- [ ] Job que dispara alertas desde `fct_anomalias` — **4 h** · `area:ml`
- [ ] Deploy FastAPI en Fly.io — **4 h** · `area:devops`
- [ ] Monitoreo bot (Healthchecks.io) — **3 h** · `area:devops`

### S12 — Deploy final + soft launch (≈16 h) · Milestone M6
- [ ] Deploy Streamlit en Community Cloud + dominio custom — **4 h** · `area:devops`
- [ ] Backups automáticos Supabase → R2 — **3 h** · `area:devops`
- [ ] Uptime Kuma o equivalente — **3 h** · `area:devops`
- [ ] README + runbook básico — **3 h** · `area:devops`
- [ ] Soft launch con 5–10 usuarios beta — **3 h** · `area:frontend`

---

## Riesgos principales

| Riesgo | Mitigación |
|---|---|
| SIMA-PM cambia formato de PDF | Tests de schema; bronze inmutable permite reparsear |
| Scraper falla en silencio | Alerta "sin inserciones hoy" desde S2 |
| Modelo Prophet con pocos datos propios | Usar histórico INEI como base; Prophet aporta detección de anomalías short-term |
| Free tier de Supabase se llena | Migrar a Hetzner self-hosted (~€4/mes) cuando pase |
| Capacidad real < estimada | Recortables: scrapers regionales (S3–S4), bot Telegram (S11), mapa coroplético (sustituir por tabla) |

---

## Costos

| Servicio | Plan | Costo |
|---|---|---|
| GitHub Actions | Public repo | $0 |
| Cloudflare R2 | <10 GB | $0 |
| Supabase | Free tier | $0 |
| Fly.io | Free tier | $0 |
| Streamlit Community Cloud | Free | $0 |
| Telegram Bot | Free | $0 |
| **Total mensual** | | **$0** |

---

