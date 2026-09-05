# dbt — Observatorio de Precios

Transformaciones de la arquitectura medallion sobre Supabase Postgres:

```
bronze.*  (cargado por observatorio.carga)  →  silver.*  (staging, dbt)  →  gold.*  (marts, dbt)
```

Este proyecto se inicializa en #22. Los modelos **`staging` (silver)** ya están
(#23): uno por fuente en bronze — `stg_marketplace_precios`, `stg_sisap_precios`,
`stg_osinergmin_precios`, `stg_ipc_inei` — deduplicados, tipados y filtrados a
observaciones válidas. Los **`marts` (gold)** también (#24): `fct_precio_diario`
(hecho de precio diario conformado SISAP+Marketplace, grain fecha×fuente×depto×
producto), `fct_precio_medias_moviles` (medias móviles 7/30/90 días de calendario,
#25) y `dim_fecha`. Clima (SENAMHI, #14) se sumará como `stg_clima` cuando
exista esa fuente.

Los marts de **ML** (#35) leen la salida del batch de `observatorio/ml/`:
`fct_predicciones` y `fct_anomalias`, ambos reducidos a los 6 slugs del MVP desde
`ml.predicciones_raw` / `ml.anomalias_raw`. Requieren que el batch haya corrido
antes (ver [docs/ml.md](../docs/ml.md)); si las tablas `ml.*` no existen todavía,
excluirlos:

```bash
dbt build --exclude "fct_predicciones+" "fct_anomalias+"
```

> Las tablas `gold.canasta_consumo_dept` y `gold.dim_departamento` las construye
> Python desde la ENAHO (`observatorio/canasta/`, #19), no dbt. Conviven en el
> mismo schema; el cruce precios × pesos (costo canasta) será un mart posterior.

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

> **No hace falta crear esas 5 variables.** Ni el `.env` ni los secrets del repo
> las tienen: lo único que existe es `SUPABASE_DB_URL`. Se derivan de ahí
> parseando la URL antes de invocar dbt (verificado contra prod el 2026-07-22),
> lo que deja una sola fuente de verdad y 0 secrets nuevos para el futuro
> workflow. Hay que forzar el puerto **5432**: la URL apunta al pooler (6543).

> **Nota sobre el pooler de Supabase.** dbt funciona mejor contra el puerto de
> sesión / conexión directa (`5432`) que contra el *transaction pooler* (`6543`),
> que no soporta prepared statements. La carga usa `6543`; para dbt se usa `5432`.

## Uso

```bash
export DBT_PROFILES_DIR=dbt        # profiles.yml vive dentro del proyecto
cd dbt

dbt debug     # verifica conexión a Supabase
dbt parse     # valida que el proyecto compila (sin conectar)
dbt build     # construye modelos + corre sus tests
```

> ⚠️ **Los marts son `table`**: solo se refrescan cuando corre `dbt build`. Entre el
> 2026-07-08 y el 2026-07-22 nadie lo corrió y `gold` quedó 14 días atrás mientras
> bronze y silver (que son `view`) seguían al día. Ver `docs/estado_proyecto.md` §5.

> **Tras un backfill de precios (issue #16), reconstruí también los dependientes.**
> `fct_precio_diario` alimenta `dim_fecha` (spine de calendario derivado de su rango de
> fechas) y `fct_precio_medias_moviles`. Si reconstruís solo el hecho
> (`dbt build --select fct_precio_diario`), `dim_fecha` queda con el calendario viejo y el
> test de integridad referencial `relationships_…_dim_fecha` falla (fechas huérfanas). Usá
> el operador `+` para arrastrar los dependientes:
>
> ```bash
> dbt build --select fct_precio_diario+   # el hecho + dim_fecha + medias_moviles + sus tests
> ```
>
> No incluye los marts de ML (`fct_predicciones`/`fct_anomalias`): esos cuelgan de
> `source('ml', …)`, no de `fct_precio_diario`.

## Automatización

Desde el 2026-07-24 hay dos workflows que se reparten los modelos:

| Workflow | Cadencia | Construye |
|---|---|---|
| `.github/workflows/dbt.yml` | diaria, 22:00 UTC | todo **menos** los marts de ML (`--exclude "fct_predicciones+" "fct_anomalias+"`) |
| `.github/workflows/ml.yml` | semanal, lunes | solo `fct_predicciones` y `fct_anomalias`, después del batch de `observatorio/ml/` |

El reparto es deliberado: las fuentes `ml.*` solo cambian cuando corre el batch
semanal, y así un fallo en la rama de ML nunca frena el refresco diario de precios.

Ambos derivan la conexión con la action compartida `.github/actions/entorno-dbt`,
que parsea `SUPABASE_DB_URL` y fuerza el puerto 5432 (ver la nota del pooler abajo).
