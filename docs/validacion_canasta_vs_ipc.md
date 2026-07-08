# Validación de la canasta contra el IPC (issue #20)

Cómo validamos que la **metodología de la canasta** (pesos derivados de la ENAHO,
ver [`canasta_consumo_dept.md`](canasta_consumo_dept.md)) produce un índice de
precios coherente con el **IPC oficial** del INEI. Implementado en
[`observatorio/validacion/canasta_vs_ipc.py`](../observatorio/validacion/canasta_vs_ipc.py).

> El script es un **reporte de solo lectura**: nunca escribe a la base. Se puede
> correr en cualquier momento; degrada con elegancia cuando todavía no hay datos
> suficientes.

---

## Idea

Si nuestros pesos de canasta y nuestro tracking de precios son metodológicamente
sanos, un índice de precios propio construido con ellos debería **seguir la
variación** del IPC oficial. No buscamos que los niveles coincidan (bases
distintas), sino que las **variaciones mensuales** se muevan juntas.

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

Sobre los meses en común, la metodología se considera **VALIDADA** si
`correlación ≥ 0.6` y `tracking error ≤ 1.5 pp`; si no, **NO CONCLUYENTE**.
Sin meses en común suficientes, el estado es **PENDIENTE POR DATOS** (no es un
fracaso: es falta de solape temporal).

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

1. **Alcance: 6 alimentos vs IPC general.** El `stg_ipc_inei` disponible es el
   IPC **general** de Lima (una sola serie, base Dic2021), no el subíndice de
   *Alimentos y Bebidas*. Nuestro índice es de 6 alimentos frescos, más volátiles
   que la canasta total → esperar tracking más flojo. **Mejora futura:** ingestar
   el subíndice de alimentos del INEI para una comparación como-con-como.
2. **Geografía.** SISAP se scrapea solo para Lima (dep 15), que **coincide** con
   el ámbito del IPC (Lima Metropolitana). Para otros departamentos no hay serie
   de IPC ingestada, así que la validación por-depto queda pendiente de esos
   datos.
3. **Niveles no comparables.** Nuestra base es el primer mes con datos; la del
   IPC es Dic2021. Por eso se comparan **variaciones**, nunca niveles.
4. **Solape temporal.** La comparación necesita al menos un mes en el que
   coexistan nuestros precios y el IPC ya publicado (el IPC sale con ~1 mes de
   rezago).
5. **Mes parcial.** Si el último mes de precios está incompleto (p.ej. corre a
   mitad de mes), su promedio y su variación son parciales — tomar la variación
   del mes en curso como preliminar.

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

## Estado al 2026-07

- ✅ **Prerequisitos de datos listos**: `dbt build` materializó
  `gold.fct_precio_diario`; `gold.canasta_consumo_dept` cargada desde la
  ENAHO 2023 (150 filas, 25 deptos × 6 productos, Σpesos=1 por depto).
- ⏳ **PENDIENTE por solape temporal**: los precios van de **jun–jul 2026** y el
  IPC publicado llega a **may 2026** → **cero meses en común**. Con solo 2 meses
  de precios (y julio parcial) hay a lo sumo 1 punto de variación propia.
- 📌 **Señal descriptiva** (no es la validación): índice propio de Lima
  jun→jul 2026 ≈ **+5.7%** (julio parcial, sobreestima el mes completo).
- 🔜 **Rehacer** cuando el INEI publique un mes que solape con nuestros precios
  (~ago–sep 2026) y tengamos ≥3 meses en común; ahí el script produce el
  veredicto automáticamente.
