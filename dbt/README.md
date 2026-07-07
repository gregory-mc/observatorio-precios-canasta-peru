# dbt — Observatorio de Precios

Transformaciones de la arquitectura medallion sobre Supabase Postgres:

```
bronze.*  (cargado por observatorio.carga)  →  silver.*  (staging, dbt)  →  gold.*  (marts, dbt)
```

Este proyecto se inicializa en el issue #22. Los modelos `staging` (silver) y
`marts` (gold) se agregan en #23 y #24 respectivamente; por ahora solo están
declaradas las **fuentes bronze** (`models/staging/_sources.yml`).

## Conexión

`profiles.yml` está versionado (no contiene secretos, solo referencias a env vars)
y usa el perfil `observatorio`. Variables requeridas:

| Variable              | Default    | Descripción                                        |
|-----------------------|------------|----------------------------------------------------|
| `SUPABASE_DB_HOST`    | —          | Host del Postgres de Supabase.                     |
| `SUPABASE_DB_PORT`    | `5432`     | Puerto. Ver nota sobre el pooler abajo.            |
| `SUPABASE_DB_USER`    | —          | Usuario (p.ej. `postgres.<project-ref>`).          |
| `SUPABASE_DB_PASSWORD`| —          | Contraseña de la base.                             |
| `SUPABASE_DB_NAME`    | `postgres` | Nombre de la base.                                 |
| `DBT_TARGET`          | `prod`     | Target del perfil.                                 |
| `DBT_SCHEMA`          | `silver`   | Schema por defecto (los modelos lo sobreescriben). |

Son los mismos datos de conexión que `SUPABASE_DB_URL` (usado por la carga vía
psycopg), pero dbt-postgres necesita los campos por separado.

> **Nota sobre el pooler de Supabase.** dbt funciona mejor contra el puerto de
> sesión / conexión directa (`5432`) que contra el *transaction pooler* (`6543`),
> que no soporta prepared statements. La carga usa `6543`; para dbt preferí `5432`.

## Uso

```bash
export DBT_PROFILES_DIR=dbt        # profiles.yml vive dentro del proyecto
cd dbt

dbt debug     # verifica conexión a Supabase
dbt parse     # valida que el proyecto compila (sin conectar)
dbt run       # (cuando existan modelos — #23/#24)
dbt test      # (#26)
```
