# Observatorio de Precios — Canasta Básica Perú

Sistema que recolecta diariamente precios mayoristas de alimentos en Perú, detecta anomalías y publica un dashboard con el costo estimado de la canasta básica familiar por departamento.

## ¿Por qué?

Los precios de alimentos frescos (papa, limón, pollo, cebolla, huevo, tomate) fluctúan de forma brusca por estacionalidad, clima y logística. No existe un sistema público que recoja, prediga y alerte en tiempo casi real sobre estas variaciones y su traslado a la canasta básica. Este observatorio busca cubrir ese vacío.

## Stack Inicial

- **Ingesta:** Python + GitHub Actions (cron diario)
- **Almacenamiento:** Supabase Postgres + Cloudflare R2 (archivos crudos)
- **Transformación:** dbt (modelo medallion bronze/silver/gold)
- **ML:** Prophet + DuckDB (predicción y detección de anomalías)
- **Dashboard:** Streamlit · **API:** FastAPI · **Alertas:** Bot de Telegram

## Rendimiento: índices donde el dato los pedía

`bronze` no tenía **ningún** índice y los modelos `silver` son vistas encima, así
que toda consulta del dashboard hacía scan completo de la tabla contra el
`statement_timeout` de 2 minutos de Supabase. Medido sobre las consultas reales
de la app, antes y después:

| Consulta | Antes | Ahora | Mejora |
|---|---|---|---|
| Serie de un producto de supermercado | 1.30 s | **0.10 s** | **12.4×** |
| Serie de un producto (canasta) | 0.77 s | **0.11 s** | 7.1× |
| Ofertas del día | 1.56 s | **0.24 s** | 6.4× |
| Ventana de 7 días por categoría | 2.64 s | **0.47 s** | 5.6× |
| Búsqueda por nombre | 1.30 s | **0.32 s** | 4.1× |
| Índice de canasta | 0.41 s | **0.12 s** | 3.5× |

Costo: **+35 MB** sobre una base de 677 MB. Tres decisiones que valen más que los
números:

- **Los índices de `gold` no pueden ir por DDL.** Esos marts son `table` de dbt:
  cada `dbt build` los dropea y los recrea, así que un `create index` a mano
  desaparece en la corrida siguiente sin que nada avise. Van declarados en el
  `config(indexes=...)` del modelo.
- **No se indexó todo.** `bronze.osinergmin_precios` (177 MB) y
  `gold.fct_precio_medias_moviles` (113 MB) quedaron sin índice porque hoy nadie
  los consulta: sería pagar espacio por cero beneficio.
- **Un índice no arregla todo.** El total de `GET /precios` no mejoró (1.42 s →
  1.56 s): su `COUNT(*) OVER ()` obliga a leer todas las filas que matchean el
  filtro, no solo la página. El trabajo ahí es contar, no encontrar.

Detalle en [`observatorio/carga/sql/bronze_schema.sql`](observatorio/carga/sql/bronze_schema.sql).

## Estructura del proyecto (propuesta)

El repo es un monorepo: contiene todos los componentes del observatorio. Cada uno
declara sus dependencias como un grupo en `pyproject.toml` y se dockeriza por separado.

```
observatorio-precios-canasta-peru/
├── pyproject.toml            # un paquete, dependencias por grupo (ingesta/ml/dashboard/api/dbt)
├── observatorio/             # código Python compartido
│   ├── ingesta/              # scrapers (SIMA-PM, SENAMHI, OSINERGMIN, ...)
│   ├── ml/                   # modelos Prophet, detección de anomalías
│   ├── dashboard/            # app Streamlit
│   └── api/                  # API FastAPI
├── dbt/                      # proyecto dbt (modelo medallion bronze/silver/gold)
├── docker/                   # un Dockerfile por servicio
├── docker-compose.yml        # orquesta Postgres + servicios en local
├── .github/workflows/        # cron de ingesta (GitHub Actions)
├── docs/                     # documentación (fuentes de datos, etc.)
└── tests/
```

> Las carpetas se irán creando a medida que avance cada componente (ver [PLAN.md](PLAN.md)).

## Desarrollo local

```bash
# Requiere Python 3.11+
python -m venv .venv && source .venv/bin/activate

# Instalar solo el componente en el que trabajás (+ herramientas de dev):
pip install -e ".[ingesta,dev]"     # scrapers
pip install -e ".[ml,dev]"          # modelado
pip install -e ".[dashboard,dev]"   # dashboard
pip install -e ".[api,dev]"         # API
```

Grupos disponibles: `ingesta`, `ml`, `dashboard`, `api`, `dbt`, `dev`.

## Fuentes de datos

Ver [docs/sources.md](docs/sources.md).

## Licencia

MIT
