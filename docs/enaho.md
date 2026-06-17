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

## Códigos ENAHO de los productos del MVP

> **TODO:** completar con los códigos exactos hallados en la celda 1.3 del notebook.
> Decidir qué presentaciones se agrupan por producto (p. ej. papa blanca + amarilla).

| Producto MVP | Código(s) ENAHO | Descripción en catálogo | Presentaciones agrupadas |
|---|---|---|---|
| Papa | _(TODO)_ | | |
| Limón | _(TODO)_ | | |
| Pollo | _(TODO)_ | | |
| Cebolla | _(TODO)_ | | |
| Huevo | _(TODO)_ | | |
| Tomate | _(TODO)_ | | |

---

## Decisiones y dudas pendientes (para #17)

- _(TODO)_ ¿Qué columna de gasto se usa como peso de la canasta?
- _(TODO)_ ¿Se agregan presentaciones de un mismo producto? ¿Cómo?
- _(TODO)_ Granularidad final de `canasta_consumo_dept` (¿por departamento × producto?).
