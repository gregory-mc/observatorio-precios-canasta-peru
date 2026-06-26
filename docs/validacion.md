# Validación de calidad de datos (issue #18)

Chequeos de calidad por fuente, integrados en la carga a bronze. Es una
**alternativa liviana a Great Expectations**: motor declarativo en Python puro
(solo `pandas`, ya dependencia base), sin servicios ni config externa, que corre
en cualquier Python soportado por el repo. Los mismos invariantes migran 1:1 a
**dbt tests** en S6 (#26), así que esto no es trabajo desechable: es el contrato
de calidad escrito una vez, ejecutable hoy en el pipeline y mañana en dbt.

> Decisión (vs. Great Expectations): GE suma `great-expectations` + `sqlalchemy`
> (deps pesadas, soporte dudoso en Python 3.14) y se solapa con los dbt tests que
> llegan en S6. Para un proyecto lean de $0 no compensa; este módulo cubre los
> mismos invariantes con cero deps nuevas.

## Componentes

```
observatorio/validacion/
  runner.py    # motor: expectativas declarativas + Reporte + validar()/validar_o_error()
  suites.py    # una Suite por fuente bronze (+ registro SUITES)
  __init__.py  # API pública
```

### Expectativas disponibles (`runner.py`)

| Expectativa | Qué chequea |
|---|---|
| `ColumnasPresentes(cols)` | Todas las columnas requeridas existen |
| `MinFilas(n)` | Al menos `n` filas (detecta cargas vacías) |
| `NoNulo(col)` | Sin nulos; `""`/espacios cuentan como ausente (el CSV crudo escribe None como `""`) |
| `EnRango(col, min, max)` | Valores numéricos en `[min, max]`; coacciona texto a número |
| `EnConjunto(col, valores)` | Dominio cerrado (p.ej. `tipo_mercado ∈ {minorista, mayorista}`) |
| `ClaveUnica(cols)` | La clave natural no tiene duplicados |
| `Predicado(nombre, fn)` | Escape hatch para invariantes a medida (p.ej. "los pesos suman 1.0") |

### Severidad

- **`error`** → hace fallar el reporte (`Reporte.ok == False`) y **aborta la carga**
  de ese archivo (no se inserta nada).
- **`advertencia`** → se registra en el log pero **no bloquea** (p.ej. un precio
  absurdamente alto que probablemente sea error de unidad, o celdas de baja
  confianza muestral en la canasta).

## Suites por fuente

Una suite por tabla bronze, llaveadas igual que `FUENTES` en la carga
(`marketplace`, `sisap`, `inei`, `osinergmin`). Son **conservadoras a propósito**:
la filosofía medallion dice que *bronze guarda lo crudo tal cual* y la
normalización fina es trabajo de silver/dbt. Por eso chequean lo que delata un
parser roto o una carga corrupta —estructura, clave natural duplicada, precios
negativos, dominios y rangos imposibles— y no más.

## Integración en el pipeline

`observatorio/carga/r2_a_supabase.py` valida **antes del `COPY`**: tras parsear el
CSV arma un `DataFrame` y corre la suite de la fuente. Si hay errores lanza
`ValidacionError` y el archivo se omite sin tocar la base (la transacción ni
empieza); el manejador existente lo cuenta como fallo y dispara la alerta diaria.
Las advertencias se loguean y la carga continúa.

```python
from observatorio.validacion import SUITES, validar

reporte = validar(df, SUITES["sisap"])
print(reporte.resumen())   # OK/FALLÓ + detalle por chequeo
reporte.ok                 # False si hubo errores (advertencias no cuentan)
```

## Tests

`tests/validacion/test_suites.py` — corre solo con pandas (sin red ni base):
cubre cada tipo de expectativa, la lógica de severidad, y cada suite real con
casos buenos y corruptos (precio negativo, `tipo_mercado` inválido, clave
duplicada, mes fuera de rango, precio absurdo → advertencia).
