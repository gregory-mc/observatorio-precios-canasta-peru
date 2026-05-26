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
