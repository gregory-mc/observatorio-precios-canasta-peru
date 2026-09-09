# ENAHO — microdatos de gasto de hogares

Documentación de la estructura de los microdatos de la **ENAHO** (Encuesta Nacional
de Hogares, INEI) que usamos para derivar la canasta básica de consumo por
departamento. Destila los hallazgos del notebook
[`notebooks/01_enaho_exploracion.ipynb`](../notebooks/01_enaho_exploracion.ipynb).

> El notebook es el **cómo lo averigüé** (ejecutable); este doc es el **qué encontré**
> (se lee sin correr nada). Es lo que alimenta el diseño de `canasta_consumo_dept`
> (issue #17) y la construcción de la canasta (#19).

**Productos objetivo del MVP:** papa, limón, pollo, cebolla, huevo, tomate.

---

## Almacenamiento de los crudos

La descarga se hace con la librería **`enahodata`** (celda del notebook), que baja y
descomprime los módulos directamente del INEI. **Funciona desde una IP peruana** — el
geo-bloqueo del INEI (`inei.gob.pe`, mismo problema que MIDAGRI) solo afecta a los
runners de GitHub, no a la máquina local.

| Capa | Ubicación | Rol |
|---|---|---|
| Adquisición | `enahodata` → `data/enaho/` (gitignored) | Descarga reproducible desde IP peruana |
| Respaldo (opcional) | R2: `enaho/<ANIO>/*.dta` | Para que #17/#19 corran en CI (geo-bloqueo) |

Nunca se versionan los crudos (ver `.gitignore`: `data/`, `*.sav`, `*.dta`).

### Códigos de módulo en el INEI
En el sistema de microdatos los módulos se identifican **por número**, no por el "601":

| Módulo | Nº | Archivo | Uso |
|---|---|---|---|
| Gastos en Alimentos y Bebidas | **07** | `...-601.dta` | Central: pesos de la canasta |
| Sumaria (variables calculadas) | **34** | `sumaria-<anio>.dta` | Normalización / validación |

`enahodata` baja en formato **`.dta` (Stata)**; `pyreadstat.read_dta` lo lee preservando
las etiquetas de valor. Nombres de columna en `.dta` suelen ir en **minúscula** (el
notebook los resuelve con un helper `col()` insensible a mayúsculas).

### Flujo
1. Notebook celda de descarga → `enahodata(modulos=["07","34"], anios=["<ANIO>"], ...)`.
2. (Opcional) `SUBIR=True` para respaldar los `.dta` en R2.
3. Alternativa manual: portal `https://proyectos.inei.gob.pe/microdatos/` →
   *Consulta por Encuestas* → ENAHO Metodología ACTUALIZADA → Módulo **07** y **34**.

---

## Año utilizado

**Regla:** usar la ENAHO más reciente posible (2025 si está, si no 2024).

⚠️ **Limitación de `enahodata` (v0.0.3):** su tabla interna de códigos solo llega
hasta **2023**. Para 2024/2025 hay que aportar el "código INEI" del año e inyectarlo
en `CODIGOS_INEI` (celda de descarga del notebook). Cómo obtenerlo desde una IP
peruana: en `proyectos.inei.gob.pe/microdatos` elegir ENAHO Metodología ACTUALIZADA
→ año → Módulo 07; la URL de descarga es `.../STATA/<CODIGO>-Modulo07.zip`.
Referencia: 2021→759, 2022→784, 2023→906. Para la issue #13 (estructura), 2023 es
equivalente; el año solo importa para los pesos de la canasta (#19).

- **Año:** **2023** (default; 2024/2025 cuando se consiga el código INEI).
- **Archivos `.dta` cargados:** módulo 07 (`enaho01-2023-601.dta`) y módulo 34 (sumaria).

El año está parametrizado en el notebook (`ANIO`); cambiarlo cuando el INEI publique
uno más reciente.

---

## Módulos relevantes

| Módulo | Contenido | Granularidad | Uso |
|---|---|---|---|
| **601** — Gastos en Alimentos y Bebidas | gasto, cantidad y código por ítem alimentario | 1 fila por (hogar × producto) | Central: pesos de la canasta |
| **Sumaria** | totales de gasto/ingreso por hogar | 1 fila por hogar | Normalización y validación |

---

## Columnas clave (Módulo 601, confirmadas en ENAHO 2023)

Nombres en **minúscula** (Stata). El notebook los resuelve con el helper `col()`.

| Rol | Columna | Notas |
|---|---|---|
| Identificador de hogar | `conglome`, `vivienda`, `hogar` | Llave compuesta del hogar |
| Geografía | `ubigeo` (6 díg.), `dominio`, `estrato` | Departamento = 2 primeros dígitos del `ubigeo` |
| Periodo | `año`, `mes` | Año y mes de la encuesta |
| **Código de producto** | `p601a` | El **nombre** está en la columna `p601x` (no en etiquetas de valor) |
| Nombre de producto | `p601x` | Texto descriptivo del ítem |
| Gasto (compra) | `p601c` → **`i601c`** (imputado, anualizado), `d601c` (deflactado) | `i601c` es el monto de compra anualizado en soles |
| Gasto (autoconsumo/otros) | `i601e` | Monto estimado anualizado de lo obtenido sin compra |
| Cantidades | `i601b2` (kg comprado), `i601d2` (kg obtenido) | Imputadas y anualizadas |
| **Factor de expansión** | `factor07` | Factor anual (proyecciones CPV-2007). **Imprescindible** |

### Gasto a usar para la canasta (decisión para #17/#19)
- **Gasto monetario / precios de mercado:** `i601c` (monto comprado anualizado) + `i601b2` (kg). Es lo más alineado con nuestro tracking de precios minoristas (SISAP/Marketplace).
- **Consumo total del hogar:** `i601c` + `i601e` (incluye autoconsumo valorizado). Útil si se quiere el peso real en la dieta, no solo lo comprado.

### Factor de expansión
Cada hogar de la muestra representa a muchos de la población. **Siempre** ponderar por
`factor07` al agregar (no promediar en crudo). La agregación por departamento usa los
2 primeros dígitos del `ubigeo`.

---

## Códigos ENAHO de los productos de la canasta

> **El nombre del producto está en el propio archivo.** El módulo 601 trae
> `p601x` = "Nombre del producto" (25 caracteres) junto al código `p601a`, así
> que el mapeo grupo → producto **no depende de adivinar códigos ni de conseguir
> el codebook**: se lee del dato. Los nombres de grupo de abajo son las etiquetas
> reales del código agregado en la ENAHO 2023.

### La canasta ampliada a 13 productos (#155)

| Producto | Grupo | Etiqueta ENAHO del agregado | % del gasto en alimentos |
|---|---|---|---|
| pollo | `09` | CARNE DE POLLO Y OTRAS AVES | 10.9 % |
| arroz | `03` | ARROZ (CORRIENTE Y SUPERIOR) | 5.6 % |
| papa | `05` | PAPA (BLANCA Y OTRAS) | 4.3 % |
| carne_res | `08` | CARNES DE RES Y OTRAS ROJAS | 4.2 % |
| pescado | `20` | PESCADO FRESCO | 4.0 % |
| leche | `04` | LECHE (EVAPORADA, FRESCA…) | 3.8 % |
| huevo | `07` | HUEVO | 3.6 % |
| azucar | `06` | AZUCAR (BLANCA Y RUBIA) | 2.5 % |
| aceite | `23` | ACEITE (BOTELLA Y A GRANEL) | 2.4 % |
| menestras | `31` | LENTEJA, ARVEJA, HABA, FRIJOL | 2.1 % |
| cebolla | `32` | CEBOLLA (ROJA, BLANCA, ETC) | 1.5 % |
| tomate | `33` | TOMATE (ITALIANO, ROJO) | 1.1 % |
| limon | `38` | LIMON | 1.1 % |

**Cobertura: 47.1 % del gasto en alimentos** (era 22.5 % con 6 productos).

### Grupos que quedaron afuera, y por qué

| Grupo | Etiqueta | % | Motivo |
|---|---|---|---|
| `01` | PAN FRANCES Y OTROS PANES | 5.0 % | sin serie diaria en SISAP |
| `37` | OTRAS HORTALIZAS Y LEGUMBRES | 4.7 % | agregado heterogéneo, sin precio equivalente |
| `41` | OTRAS FRUTAS | 4.3 % | ídem |
| `47` | COMIDAS PREPARADAS | 3.5 % | no es un producto con precio de mercado |
| `19` | FIDEOS | 2.3 % | **SISAP lo publica solo en mayorista** |
| `24` | QUESO FRESCO | 2.1 % | sin serie diaria |
| `16` | TRIGO, HARINA DE TRIGO | 2.0 % | **solo en mayorista** |

Fideos y harina entran el día que SISAP los publique en minorista: la canasta se
valoriza a precio minorista porque es el ámbito que cruza con los pesos ENAHO y
con el IPC, y mezclar fuentes rompería la comparabilidad.

---

## Códigos ENAHO de los 6 productos originales del MVP

**Hallazgo clave:** el código `p601a` tiene 4 dígitos donde los **2 primeros = grupo
del producto**. Cada producto del MVP cae en un único grupo. Buscar por nombre da
falsos positivos (SALSA DE TOMATE, PAN DE HUEVO, HOJA DE LIMÓN, PESCADO POLLO,
FRIJOL HUEVO DE PALOMA...), así que el mapeo correcto es **por grupo de 2 dígitos**,
no por substring del nombre. Dentro del grupo, `XX00` es el agregado y `XX01+` son
presentaciones.

| Producto MVP | Grupo | Código agregado | Presentaciones frescas relevantes |
|---|---|---|---|
| **Papa** | `05` | `0500` (PAPA BLANCA Y OTRAS) | `0501` blanca, `0502` amarilla, `0503` huayro, `0504` color/rosada, `0506` nativas/variedades |
| **Huevo** | `07` | `0700` (HUEVO) | `0701` gallina a granel (principal), `0704` envasado |
| **Pollo** | `09` | `0900` (CARNE DE POLLO Y OTRAS AVES) | `0901` eviscerado, `0902` en pie/vivo, `0904` pechuga, `0905` pierna |
| **Cebolla** | `32` | `3200` (CEBOLLA ROJA, BLANCA, ETC) | `3201` roja de cabeza (principal), `3202` china, `3203` de cola |
| **Tomate** | `33` | `3300` (TOMATE ITALIANO, ROJO) | `3301` regional, `3302` italiano, `3303` redondo |
| **Limón** | `38` | `3800` (LIMÓN) | `3801`/`3802` sutil/agrio (principal), `3804` sutil |

### Códigos a EXCLUIR (no son el producto fresco)
- **Pollo:** grupo `10` = menudencia/vísceras de pollo; grupo `11` (`1107`–`1109`) = pollo en conserva/enlatado; salchicha/jamonada de pollo. Son derivados, no carne fresca.
- **Papa:** `0507` "PAPA SECA", `1804` "HARINA DE PAPA" → procesados.
- **Huevo:** `1804`/`1805` "HARINA DE HUEVO", `1905` "FIDEOS AL HUEVO", `0108`/`0109` "PAN DE HUEVO" → procesados.
- **Tomate:** grupo `30` (`3010`–`3024`) "SALSA/PASTA DE TOMATE" → procesado.
- **Limón:** grupo `42` "HOJA DE LIMÓN PARA INFUSIÓN", `3904`–`4116` "LIMÓN DULCE" (otra fruta) → no es el limón ácido de cocina.

---

## Decisiones de diseño (#17 — resueltas)

Resueltas en [`docs/canasta_consumo_dept.md`](canasta_consumo_dept.md) (diseño de la tabla).
Resumen:

1. **Gasto a usar como peso:** ✅ `i601c` (compra monetaria anualizada), por alineación
   con el tracking de precios de mercado. `i601e` (autoconsumo) **no** entra en el peso por
   defecto pero se persiste en `gasto_total_anual` para poder recalcular sin reprocesar.
2. **Presentaciones a agrupar:** ✅ se **suma todo el grupo de 2 dígitos excluyendo los
   códigos procesados** listados arriba.
3. **Granularidad de `canasta_consumo_dept`:** ✅ `(anio_enaho, cod_departamento, producto)`,
   peso ponderado por `factor07` y **normalizado dentro del MVP** (Σ pesos = 1.0 por depto).
   `anio_enaho` entra en la clave para no colisionar entre años de encuesta.
