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

- **Año:** _(TODO: completar — 2023 por defecto; 2024/2025 si se consigue el código)_
- **Fecha de descarga:** _(TODO)_
- **Archivos `.dta` cargados:** _(TODO: p. ej. `enaho01-2024-601.dta`, `sumaria-2024.dta`)_

El año está parametrizado en el notebook (`ANIO`); cambiarlo cuando el INEI publique
uno más reciente.

---

## Módulos relevantes

| Módulo | Contenido | Granularidad | Uso |
|---|---|---|---|
| **601** — Gastos en Alimentos y Bebidas | gasto, cantidad y código por ítem alimentario | 1 fila por (hogar × producto) | Central: pesos de la canasta |
| **Sumaria** | totales de gasto/ingreso por hogar | 1 fila por hogar | Normalización y validación |

---

## Columnas clave (Módulo 601)

> **TODO:** confirmar los nombres reales con el diccionario que imprime el notebook
> (celda 1.1). Varían algo entre años. Candidatos esperados:

| Rol | Columna (candidata) | Notas |
|---|---|---|
| Identificador de hogar | `CONGLOME`, `VIVIENDA`, `HOGAR` | Llave compuesta del hogar |
| Geografía | `UBIGEO` (6 díg.), `DOMINIO` | Departamento = 2 primeros dígitos del UBIGEO |
| Código de producto | `P601A` | Mapea al catálogo de alimentos (etiquetas de valor) |
| Gasto / cantidad | `I601*` / `D601*` / `G601*` | _(TODO: confirmar cuál es el gasto en soles)_ |
| **Factor de expansión** | `FACTORA07` o `FACTOR07` | **Imprescindible** para cifras representativas |

### Factor de expansión
Cada hogar de la muestra representa a muchos de la población. **Siempre** ponderar por
el factor de expansión al agregar (no promediar en crudo). La agregación por
departamento usa los 2 primeros dígitos del `UBIGEO`.

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
