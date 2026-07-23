# Validación de la canasta (issues #20 y #102)

Cómo validamos la **metodología de la canasta** (pesos derivados de la ENAHO,
ver [`canasta_consumo_dept.md`](canasta_consumo_dept.md)). Implementado en
[`observatorio/validacion/canasta_vs_ipc.py`](../observatorio/validacion/canasta_vs_ipc.py).

> El script es un **reporte de solo lectura**: nunca escribe a la base.

> **#20 → #102.** El #20 preguntaba "¿valida la canasta comparar su índice contra el
> IPC?" y la respuesta empírica fue **no** (ver §"Por qué la correlación con el IPC no
> valida"). El #102 reformuló el criterio: el veredicto pasó a ser la **solidez
> interna** del índice (no la correlación con el IPC), y el chequeo de precios se
> endureció a **rangos por producto** (antes un único rango 0.1–100/kg para todo).

---

## Enfoque de validación (opción B — decidido 2026-07-22)

> **El criterio de validación es la SOLIDEZ INTERNA del índice, NO su correlación
> con el IPC oficial.** El contraste con el IPC se conserva como contexto
> descriptivo, pero no aprueba ni reprueba nada. El porqué está en §"Por qué la
> correlación con el IPC no valida" más abajo.

**Se valida** (`evaluar_solidez`) que el índice propio sea internamente sano —lo
que sí delataría una canasta rota—:

1. **Pesos suman 1.0** (± 1e-6) sobre los productos del MVP con precio.
2. **Cobertura de productos estable**: ≥ 90% de los meses con todos los productos
   presentes (evita saltos artificiales por entradas/salidas de productos).
3. **Precios plausibles** (#102, propuesta 1): cada precio mensual dentro del rango
   esperado **de su producto**, no de un rango único para todos. Antes el límite era
   0.1–100/kg para todo, que solo atrapaba errores de unidad groseros (una papa a
   S/ 45/kg —≈10× lo normal— pasaba). Los rangos por producto (abajo) se calibraron
   sobre la distribución real de SISAP minorista 2024–2026 (percentiles 1–99) con
   margen para picos de escasez genuinos.
4. **Serie continua**: sin huecos mensuales (solo **aviso**, no bloquea).

Los tres primeros son el gate → veredicto `CANASTA SÓLIDA` / `REVISAR`.

### Rangos de precio plausible por producto (S/kg, minorista)

Referencias conocidas de precio minorista en Lima. Se listan en
`canasta_vs_ipc.py::RANGOS_PLAUSIBLES_SOLKG`; un slug sin rango propio cae al
fallback amplio (`RANGO_PLAUSIBLE_DEFAULT` = 0.1–100).

| Producto | Rango S/kg | p01–p99 observado |
|---|---|---|
| papa | 0.3 – 15 | 1.86 – 6.21 |
| cebolla | 0.4 – 12 | 2.71 – 4.44 |
| huevo | 2.5 – 16 | 6.07 – 10.06 |
| pollo | 4 – 22 | 8.50 – 12.19 |
| tomate | 1.0 – 18 | 3.39 – 6.17 |
| limon | 1.0 – 30 | 3.74 – 7.06 (pico de escasez hasta ~20) |

> **Los rangos son de precio MINORISTA** (el ámbito canónico de la validación: es el
> que cruza con los pesos ENAHO y el IPC), pero desde que el mart normaliza la unidad
> (ver nota siguiente) también sirven para mayorista: el mayoreo cae por debajo del
> menudeo, como debe ser (limón mayorista mediana S/1.58 vs S/4.36 minorista; tomate
> S/2.31 vs S/4.48).

> **Normalización de unidad (resuelta 2026-07-24).** SISAP mayorista cotiza varios
> productos por cajón/bolsa/millar, no por kg: el tomate venía en "Cajón chico" de
> 27 kg (S/63/cajón), el limón en bolsa de 45 kg. El mart `fct_precio_diario` ahora
> divide `precio_prom` por `equiv_kg_lt` —el factor de conversión que la propia
> fuente publica en bronze— dejando todo en S/kg. Antes el hecho mezclaba unidades
> (tomate mayorista a S/63 convivía con el minorista a S/4.6/kg) y `--fuente
> sisap_mayorista` daba `REVISAR` por precios "fuera de rango"; ahora el chequeo de
> precios pasa. (Mayorista sigue dando `REVISAR` por **cobertura**: no tiene los 6
> productos MVP con peso todos los meses — es esperable, no es su ámbito.)

## Contexto descriptivo: contraste con el IPC (no valida)

Aún así construimos un índice de precios propio y comparamos su variación mensual
contra el IPC oficial, como **señal descriptiva**. La idea original era: si los
pesos y el tracking son sanos, el índice propio debería **seguir la variación**
del IPC. Resultó que no —y no por un defecto nuestro— como explica §"Por qué…".

## Insumos

| Fuente | Tabla | Rol |
|---|---|---|
| Pesos de canasta | `gold.canasta_consumo_dept` | `peso_canasta` por (depto, producto), de la ENAHO |
| Precios | `gold.fct_precio_diario` | precio diario por (fuente, depto, producto) |
| IPC oficial | `silver.stg_ipc_inei` | índice mensual de Lima Metropolitana (base Dic2021) |

## Diseño de la comparación

1. **Precio mensual por producto MVP.** Se promedian las presentaciones de cada
   producto (mapeo `MAPEO_PRECIO_MVP`, ver abajo) sobre los días del mes, para
   una `fuente` y un `departamento` dados. Default: `sisap_minorista`, Lima
   (dep 15) — el ámbito que coincide con el IPC disponible.
2. **Índice tipo Laspeyres de base fija:**
   `I_t = 100 · Σ_p w_p · (P_{p,t} / P_{p,0})`
   con `w_p` los pesos de la canasta del departamento, **renormalizados** sobre
   los productos con precio disponible (Σ w = 1). Base = primer mes con datos.
3. **Variación mensual propia** `var% = I_t/I_{t-1} − 1`, comparada contra
   `var_mensual` del IPC en los **meses en común**.
4. **Métricas** (cuando hay ≥3 meses en común): correlación de Pearson,
   *tracking error* (desvío de las diferencias propia−IPC) y diferencia absoluta
   media.

### Veredicto

El veredicto lo da la **solidez interna** (ver arriba): `CANASTA SÓLIDA` o
`REVISAR`. La correlación y el *tracking error* contra el IPC se **reportan como
referencia** (0.6 y 1.5 pp) pero **no gatillan** el veredicto — ver la sección
siguiente sobre por qué.

## Por qué la correlación con el IPC no valida (hallazgo empírico 2026-07-22)

Se corrió la comparación contra tres benchmarks oficiales y tres lentes, sobre
23–24 meses en común (ene-2024 a dic-2025, gracias al backfill histórico de
SISAP). **Todas dieron NO CONCLUYENTE:**

| Comparación | correlación | tracking error | resultado |
|---|---|---|---|
| MoM vs IPC **general** de Lima | 0.54 | 5.5 pp | no sigue |
| MoM vs subíndice **Alimentos y Bebidas** (BCRP `PN01313PM`) | 0.44 | 5.4 pp | no sigue |
| **Interanual** vs Alimentos | 0.53 | 3.9 pp | no sigue |
| **Niveles/tendencia** vs Alimentos | −0.20 | — | van en sentido opuesto |

**Causa (no es un defecto de método):** nuestro índice son 6 alimentos frescos
(papa, pollo, huevo, cebolla, tomate, limón), de los **más volátiles** de cualquier
canasta — se mueve ±10% mes a mes. Ningún índice oficial mide ese mismo canasto: el
general y hasta el subíndice de Alimentos promedian cientos de productos, la mayoría
estables (arroz, aceite, pan, comidas fuera del hogar) → se mueven ±1%. Comparar 6
frescos volátiles contra un agregado suave **no puede correlacionar**, sea cual sea
el índice o la lente. Además, en 2024–2025 nuestros frescos **bajaron** (~8% anual)
mientras el agregado de alimentos **subió** (~2%): tendencias opuestas, probablemente
reales (buenas cosechas de frescos vs. encarecimiento del resto).

Verificado que **no es un artefacto de datos**: la cobertura es completa (los 6
productos todos los meses) y los precios promedio son plausibles. Los saltos son
volatilidad genuina de los frescos.

**Opción A descartada:** validar producto-por-producto contra una **serie oficial**
(nuestra papa vs. la papa del INEI, mes a mes) exigiría una serie mensual y
machine-readable por producto para Lima. El BCRP solo publica agregados; el INEI
publica precios por producto solo en PDFs mensuales (scraping frágil). No hay base
confiable → se adoptó la opción B (validación por solidez interna).

> Ojo con no confundir la opción A con la **propuesta 1 del #102**, que sí se
> implementó: la propuesta 1 no compara contra una serie oficial mes a mes, solo
> exige que el precio caiga en un **rango plausible conocido** por producto — que se
> fija con un puñado de cotas, no con una serie completa. Es la versión factible y
> es lo que hoy endurece el chequeo de "precios plausibles".

### Ampliar el canasto cierra la MAGNITUD, no el timing (hallazgo 2026-07-22)

Tras backfillear el catálogo completo de SISAP a bronze (issue #16 — arroz, aceite,
azúcar, leche… con histórico 2024–2025), se re-corrió el contraste con el subíndice
de Alimentos (`PN01313PM`) para canastos cada vez más amplios (pesos iguales, proxy):

| Canasto (Lima, sisap_minorista) | Volatilidad RMS MoM | Tracking error | Correlación |
|---|---|---|---|
| 6 frescos (MVP) | ±6.0% | 5.8 pp | 0.33 |
| 14 (frescos + staples + carnes) | ±2.9% | **2.8 pp** | 0.34 |
| solo 5 staples estables | ±0.5% | **0.63 pp** | 0.02 |

**Conclusión:** ampliar el canasto **resuelve el problema de magnitud** — el tracking
error se desploma (5.8 → 2.8 → 0.63 pp) y la volatilidad deja de ser ±10% para parecerse
a la del índice oficial. Con un canasto representativo, la metodología reproduce la
*escala* de la inflación oficial de alimentos. Lo que **no** se cierra es la
**correlación** (~0.3): las variaciones mes-a-mes no van sincronizadas. Es una limitación
de **datos**, no de método:
- **Muestreo ralo** (~6 días/mes) → ruido en la variación mensual, que es justo lo que
  mide la correlación.
- **Alcance** → el índice oficial mezcla cientos de ítems y servicios (comidas fuera del
  hogar) cuyo vaivén mensual no rastreamos.

Los staples solos tienen correlación ~0 porque casi no se mueven (±0.5%): su micro-variación
es ruido no correlacionado. La poca señal correlacionada la aportan los frescos. Confirma
mantener el veredicto por **solidez interna** (opción B): la metodología es sólida; el
timing mensual exacto no es replicable con esta granularidad de muestreo.

> Pendiente para afinar (no bloquea): pesos reales de la ENAHO en vez de proxy (Paso #19
> ampliado) y muestreo más denso de SISAP para reducir el ruido de la correlación.

### Mapeo de productos (precio → slug MVP)

`gold.fct_precio_diario` trae nombres crudos; se reducen a los 6 slugs del MVP
con patrones `ILIKE` (en `canasta_vs_ipc.py::MAPEO_PRECIO_MVP`):

| Slug | Patrón | Nota |
|---|---|---|
| papa | `Papa %` | el espacio excluye "Papaya" |
| pollo | `Carne de pollo%` | eviscerado |
| huevo | `Huevos%` | huevos rosados |
| cebolla | `Cebolla%` | cabeza roja |
| tomate | `Tomate%` | |
| limon | `Limon%`, `Limón%` | sutil |

Las variedades de un mismo producto (p.ej. las papas) se **promedian por igual**
(no hay sub-pesos por variedad).

---

## Caveats (leer antes de interpretar)

1. **6 frescos ≠ cualquier IPC agregado.** Ya probado con el IPC general y con el
   subíndice de Alimentos: no correlaciona por naturaleza (ver §"Por qué…"). Por eso
   el contraste con el IPC es descriptivo, no criterio.
2. **Geografía.** SISAP se scrapea solo para Lima (dep 15). Para otros departamentos
   no hay precios propios, así que el contraste con el IPC solo aplica a Lima.
3. **Niveles no comparables.** Nuestra base es el primer mes con datos; la del
   IPC es Dic2021. El contraste descriptivo usa **variaciones**, nunca niveles.
4. **Mes parcial.** Si el último mes de precios está incompleto (corre a mitad de
   mes), su promedio y su variación son parciales — tomar el mes en curso como
   preliminar.

---

## Uso

```bash
# Lima, sisap_minorista (default):
python -m observatorio.validacion.canasta_vs_ipc

# Otro departamento / fuente:
python -m observatorio.validacion.canasta_vs_ipc --dep 04
python -m observatorio.validacion.canasta_vs_ipc --fuente marketplace --dep nacional
```

Requiere `SUPABASE_DB_URL` (en el entorno o en `.env`).

---

## Estado al 2026-07-22 (verificado en prod, lectura)

- ✅ **Datos listos**: `gold.fct_precio_diario` poblado (precios Lima ene-2024 →
  jul-2026); `gold.canasta_consumo_dept` con ENAHO 2023 (150 filas, 25 deptos × 6
  productos, Σpesos=1 por depto).
- ✅ **VEREDICTO: `CANASTA SÓLIDA`** (Lima, `sisap_minorista`). Los 3 chequeos del
  gate pasan: pesos suman 1.0; cobertura 100% de meses con los 6 productos; todos
  los precios dentro del rango **por producto** (#102). Único aviso: hueco 2026-01→05
  sin datos SISAP (no bloquea). Reverificado el 2026-07-24 tras endurecer el chequeo.
- 📌 **Contexto descriptivo** (NO es la validación): el contraste MoM contra el IPC
  general da correlación 0.54 / TE 5.5 pp — divergencia **esperable** (frescos
  volátiles vs. agregado suave), no un defecto. Detalle y evidencia multi-benchmark
  en §"Por qué la correlación con el IPC no valida".
- 🧪 **Backfill del catálogo completo (#16) + prueba de canasto ampliado**: con arroz,
  aceite, azúcar, leche… ya en histórico, un canasto ampliado baja el tracking error de
  5.8 a 2.8 pp (y a 0.63 pp con solo staples) → **la magnitud sí se cierra**; la
  correlación (~0.3) no, por muestreo ralo y alcance. Ver §"Ampliar el canasto cierra la
  MAGNITUD, no el timing".
- 🔎 **Nota de dato antiguo**: una versión previa de este doc decía "0 meses en
  común / esperar a ago-sep 2026". Era incorrecto: el backfill histórico de SISAP da
  24 meses de solape. Corregido.
