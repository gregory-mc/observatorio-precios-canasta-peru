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

La descarga del INEI es **manual y one-shot** (`www.inei.gob.pe` geo-bloquea IPs de
datacenter — mismo problema que MIDAGRI — y los microdatos pesan cientos de MB).

| Capa | Ubicación | Rol |
|---|---|---|
| Fuente de verdad | R2: `enaho/<ANIO>/*.sav` | Inmutable, reproducible por todo el equipo |
| Copia de trabajo | local: `data/enaho/<ANIO>/*.sav` (gitignored) | Velocidad; el notebook la baja de R2 si falta |

Nunca se versionan los `.sav` (ver `.gitignore`: `data/`, `*.sav`, `*.dta`).

**Flujo:** descargar `.sav` del INEI → `data/enaho/<ANIO>/` → subir a R2 una vez
(celda 4 del notebook, `SUBIR=True`) → el resto del equipo los baja de R2.

### Cómo descargar del INEI
1. `https://www.inei.gob.pe/microdatos` → *Consulta por Encuestas* →
   **ENAHO Metodología ACTUALIZADA** → Condiciones de Vida y Pobreza.
2. Elegir el **año más reciente disponible** (la ENAHO anual sale con ~1 año de rezago).
3. Descargar en formato **SPSS (`.sav`)** al menos: **Módulo 601** y **Sumaria**.

---

## Año utilizado

**Regla:** usar la ENAHO **2025** si el INEI ya la publicó; si todavía no está
disponible, caer a **2024**.

- **Año:** _(TODO: completar — 2025 o 2024)_
- **Fecha de descarga:** _(TODO)_
- **Archivos `.sav` cargados:** _(TODO: p. ej. `Enaho01-2024-601.sav`, `sumaria-2024.sav`)_

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
