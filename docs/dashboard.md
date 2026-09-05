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
