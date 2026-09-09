# Dashboard (M5)

Dashboard público en Streamlit sobre la capa gold. Issues #36 (estructura) y #37
(página principal); #38–#42 pendientes.

```bash
pip install -e ".[dashboard]"
streamlit run observatorio/dashboard/app.py
```

Requiere `SUPABASE_DB_URL` (en el entorno o en `.env`), el mismo secret que usa la
carga. Si falta, la página lo dice en vez de reventar con un stack.

---

## 1. Estructura

| Archivo | Rol |
|---|---|
| `logica.py` | Núcleo **puro**: índice de canasta, variación, semáforo, resolución de ámbito. Sin streamlit ni base → se testea directo (`tests/dashboard/`). |
| `datos.py` | **Único** módulo que habla con la base. |
| `paginas/*.py` | Una función `render()` por página. |
| `app.py` | Entrypoint: `st.navigation` con las tres páginas. |

> ⚠️ Cada página expone una función llamada `render()`, y Streamlit infiere el
> pathname de la URL del nombre del callable. Sin un `url_path` explícito las tres
> colisionan y la app **no arranca**: `Multiple Pages specified with URL pathname
> render`. Está puesto en `app.py`; si agregás una página, ponéselo.

### Por qué lee Supabase directo y no la API

La API REST (`observatorio/api/`) existe pero todavía no está desplegada (#47).
Si el dashboard dependiera de ella, no funcionaría hasta resolver el deploy. Leer
gold directo lo desacopla; cuando la API esté arriba se reemplazan las funciones
de `datos.py` por llamadas HTTP y **ninguna página cambia**.

El mapeo producto crudo → slug MVP (`MAPEO_PRECIO_MVP`) y los rangos de precio
plausible se **reusan** de `observatorio.validacion.canasta_vs_ipc`: son la misma
definición que valida la canasta en #20/#102. Duplicarlos crearía una segunda
verdad que se desincroniza sola.

---

## 2. El semáforo (#37)

Mide la **variación mensual del costo de la canasta**: índice Laspeyres de base
fija sobre los 6 productos del MVP, ponderado por los pesos ENAHO del
departamento (`gold.canasta_consumo_dept`).

### Umbrales

| Nivel | Variación | Significado |
|---|---|---|
| 🟢 Verde | `< +3 %` (incluye bajas) | Mes típico |
| 🟡 Ámbar | `+3 %` a `+7.5 %` | Subiendo |
| 🔴 Rojo | `≥ +7.5 %` | Alza fuerte |

**Están calibrados, no elegidos a ojo.** Sobre la distribución real de
`|variación mensual|` del índice de Lima en `sisap_minorista` (27 variaciones,
2024-01 → 2026-09): **mediana 3.1 %**, **p80 ≈ 7.5 %**. Poner 2 % / 5 % habría
pintado de rojo uno de cada tres meses en una canasta de frescos —que se mueve así
por naturaleza, con volatilidad RMS de ±6 % (ver `validacion_canasta_vs_ipc.md`)—
y un semáforo permanentemente en rojo no informa nada.

Es **direccional**: una baja fuerte no es una alarma para el consumidor, así que
verde cubre "estable o bajando". El número con signo se muestra igual.

### Dos cuidados que el índice crudo no cubre

1. **El mes en curso se descarta.** Si hoy es 4 de septiembre, el promedio de
   septiembre son 4 días: su variación es un artefacto. Se evalúa el último mes
   cerrado.
2. **Los meses tienen que ser consecutivos de calendario.** `construir_indice`
   calcula la variación contra la entrada anterior *de la lista*, que con un hueco
   de datos puede estar meses atrás. SISAP no tiene 2026-01 a 2026-05: sin este
   control compararía junio contra diciembre y lo llamaría "mensual". Con el hueco,
   el semáforo declara **sin dato** y explica por qué.

---

## 3. La limitación que hay que tener presente

**Hoy solo Lima tiene precios propios.** SISAP se scrapea únicamente para Lima
(`cod_departamento = '15'`) y marketplace no desagrega (guarda `cod_departamento`
en NULL). Pero los **pesos** de canasta sí existen para los 25 departamentos.

`resolver_ambito()` decide qué precios usar y devuelve la aclaración que la página
muestra:

| Situación | Ámbito | Qué se muestra |
|---|---|---|
| El depto tiene precios propios | `PROPIO` | El número, sin aclaración |
| La fuente es nacional (marketplace) | `NACIONAL` | Aviso: canasta local a precios nacionales |
| Ni propios ni nacionales (Amazonas en SISAP) | `PROXY` | Aviso nombrando de qué deptos salen los precios |

Consecuencia a no perder de vista: **entre departamentos, lo que varía es la
composición del consumo, no el precio.** Amazonas y Lima dan números distintos
porque comen distinto, no porque paguen distinto. Cuando SISAP cubra más
departamentos esto se corrige solo, sin tocar el dashboard.

Es también la razón por la que el mapa coroplético (#39) hoy pintaría 24
departamentos con el mismo precio — está anotado en el stub de esa página.

---

## 4. Evolución temporal (#38)

Serie diaria de un producto con la banda de pronóstico y las anomalías, sobre
`gold.fct_predicciones` y `gold.fct_anomalias`.

- **Solo SISAP tiene pronóstico**: el batch de ML corre sobre `sisap_minorista`
  (6 productos) y `sisap_mayorista` (5 — no cotiza pollo).
- **Las corridas son semanales, con horizonte de 14 días.** Una corrida ya
  vencida trae puntos pasados, así que `proxima_prediccion()` muestra el primer
  punto que todavía está en el futuro, y si no queda ninguno lo dice en vez de
  presentar un pronóstico viejo como si fuera lo que viene.
- **El modelo es `naive` con bandas empíricas**, no Prophet ni intervalos
  bayesianos. Está escrito en la página para que nadie lea las bandas como más de
  lo que son.

### La línea se corta en los huecos

Un gráfico de líneas une dos puntos consecutivos aunque los separen meses: en el
hueco de SISAP (2026-01 → 2026-05) dibujaría una recta de cinco meses que parece
dato interpolado. `insertar_huecos()` intercala un punto nulo y plotly corta ahí
(`connectgaps=False`). El umbral es 10 días: SISAP publica en días hábiles y el
minorista de forma interdiaria, así que 1–4 días sin dato es cadencia normal.

---

## 5. Mapa por departamento (#39)

Coroplético de los 25 departamentos con dos modos:

| Modo | Qué pinta | Naturaleza del dato |
|---|---|---|
| Variación mensual de la canasta | El semáforo de §2 aplicado a cada departamento | Mixto: precios comunes × pesos locales |
| Peso de un producto en la canasta | Qué % del gasto en frescos es papa, pollo… | **Dato departamental puro** (ENAHO) |

**El primer modo lleva un aviso grande y deliberado.** Como solo Lima tiene
precios propios, los 25 departamentos se valorizan con los mismos precios: el
mapa muestra **estructura de consumo, no diferencias de precio**. Un
departamento se pinta más rojo porque consume más del producto que subió, no
porque ahí esté más caro. El segundo modo no tiene esa ambigüedad y por eso
existe: es ENAHO puro, sin precios de por medio.

Cuando SISAP cubra más departamentos, el primer modo pasa a ser un mapa de
precios de verdad sin tocar el código — `resolver_ambito` y
`semaforo_por_departamento` ya trabajan por departamento.

### Los límites geográficos no se vendorean

Se descargan en runtime de [juaneladio/peru-geojson](https://github.com/juaneladio/peru-geojson)
y se cachean 24 h. **Por licencia**: el archivo está bajo MPL-2.0 y este repo es
MIT, así que distribuirlo arrastraría la obligación de licencia por un mapa que
el PLAN marca como recortable.

Dos cosas que lo hacen seguro:

- **El join es por código, no por nombre.** El GeoJSON trae `FIRST_IDDP`, que es
  el mismo `cod_departamento` de la canasta. Verificado: los 25 códigos empatan
  exactamente, sin huérfanos de ningún lado. Matchear por nombre habría fallado
  con `Áncash`/`ANCASH` y `Apurímac`/`APURIMAC`.
- **Si la descarga falla, la página degrada a tabla** (`geojson_departamentos()`
  devuelve None en vez de propagar) — que es justo el sustituto que sugiere el
  PLAN. Verificado simulando el fallo: muestra el aviso y las 25 filas.

Se usa `plotly.express.choropleth` con `fitbounds="locations"`, que es el
renderer geo nativo: **no** hace falta un token de mapbox ni un tile server.

---

## 6. Riesgo latente: dos definiciones del slug MVP

La reducción de nombre crudo → slug del MVP está escrita **dos veces**:

| Dónde | Qué usa |
|---|---|
| `validacion/canasta_vs_ipc.py::MAPEO_PRECIO_MVP` | Patrones ILIKE en Python. Lo usa la validación y el dashboard para la serie observada |
| `dbt/macros/slug_producto_mvp.sql` | `CASE` en SQL. Lo usan `fct_predicciones` y `fct_anomalias` |

**Hoy coinciden exactamente**: verificado sobre el catálogo real de SISAP, 0
productos con slug distinto entre las dos. Pero no coinciden por construcción —
el macro excluye `'papa seca%'` y matchea `'%pollo%'`, mientras que el de Python
usa `'Papa %'` y `'Carne de pollo%'`. Si SISAP suma una variedad nueva, pueden
divergir y la página de evolución superpondría una serie observada contra una
banda calculada sobre un conjunto de productos distinto.

Vale unificarlas cuando se toque esa zona; no es urgente mientras el catálogo no
cambie.

---

## 7. Deploy en Streamlit Community Cloud (#49)

### Lo que el repo aporta

| Archivo | Para qué |
|---|---|
| `requirements.txt` | Community Cloud lo busca en la raíz. Instala `.[dashboard]`, así que **pyproject sigue siendo la única fuente de verdad** de las dependencias |
| `.streamlit/config.toml` | Tema y ajustes. Se versiona: no lleva secretos |
| `.streamlit/secrets.toml.example` | Plantilla. El `secrets.toml` real está gitignoreado |

Entrypoint: `observatorio/dashboard/app.py`.

### La credencial

`datos.url_conexion()` la busca en dos lugares, en este orden:

1. `SUPABASE_DB_URL` en el entorno o en `.env` — el camino local.
2. `st.secrets["SUPABASE_DB_URL"]` — el camino de Cloud, donde los secretos se
   pegan en Settings → Secrets.

Se leen los dos en vez de confiar en que Streamlit espeje los secretos a
variables de entorno, para no depender de ese detalle de implementación.
Verificado: la app conecta con **solo** `st.secrets`, sin `.env` ni variable de
entorno a la vista.

> ⚠️ **Se despliega con la misma credencial que la carga** (`SUPABASE_DB_URL`),
> que tiene permisos de escritura — decisión tomada a propósito para no
> multiplicar secretos. Vale saber qué implica: la credencial **no** queda
> expuesta al visitante (vive del lado del servidor), y todo el SQL del
> dashboard es SELECT parametrizado, así que no hay un camino de escritura hoy.
> Lo que se pierde es la segunda línea de defensa: si mañana alguien agrega una
> consulta con interpolación, correría con permisos de escritura sobre `gold` y
> `bronze`. Un rol `SELECT`-only lo cerraría; es la misma deuda que el review de
> #135 anotó para la API (#47/#44).

### Público vs. restringido

Community Cloud ofrece tres mecanismos distintos, y conviene no confundirlos:

| Mecanismo | Cómo funciona | Cuándo sirve |
|---|---|---|
| **Público** | Cualquiera con la URL entra, sin login. Indexable | El objetivo final del PLAN: dashboard público |
| **Allowlist de la plataforma** | Se listan emails; el visitante entra con esa cuenta. Cero código | El soft launch: #42 pide 3 usuarios externos, #53 pide 5–10 beta |
| **`st.login()` (OIDC)** | Auth real contra un proveedor de identidad | Si alguna vez hay datos por usuario |

Hay una cuarta variante —una contraseña compartida dentro de la app con
`st.text_input(type="password")`— que no recomendamos: secreto único, sin
cuentas ni rastro de quién entró, y hay que escribir y mantener el código.

**Que la app sea pública no hace público el repo.** El repositorio sigue privado;
lo único que se expone es la página renderizada.

> El tier gratuito limita las apps desplegadas desde un **repo privado** (este lo
> es). Conviene confirmar el límite vigente al conectar la cuenta.
