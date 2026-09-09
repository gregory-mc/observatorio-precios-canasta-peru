"""Mapeo de los códigos `p601a` de la ENAHO a los productos de la canasta.

Destila las decisiones de docs/enaho.md y docs/canasta_consumo_dept.md:

  * El código `p601a` tiene 4 dígitos; los **2 primeros = grupo** del producto.
    Cada producto cae en un único grupo (mapear por grupo evita los falsos
    positivos de buscar por nombre: SALSA DE TOMATE, PAN DE HUEVO, HOJA DE
    LIMÓN…).
  * Dentro del grupo, `XX00` es el **agregado** y `XX01+` son las presentaciones.
    Se usan **solo las presentaciones** — ver abajo.

## El agregado `XX00` NO se suma (issue #155)

`docs/canasta_consumo_dept.md` había asumido que cada fila del módulo era una
línea de compra distinta y que por lo tanto sumar `XX00` junto a las `XX0n` no
duplicaba, dejando la verificación empírica pendiente. **La verificación se
corrió contra la ENAHO 2023 y la asunción era falsa:** en 22,242 de 22,242
hogares con arroz (100 %), la fila `XX00` es exactamente igual a la suma de las
específicas. Un hogar tiene a la vez:

    0300  ARROZ (CORRIENTE Y SUPERIOR)   S/ 220.03   60 kg
    0304  Arroz Extra a Granel           S/ 220.03   60 kg   <- la misma compra

Sumar los dos duplicaba todo el gasto y toda la cantidad. Dos consecuencias:

1. `gasto_*_anual` y `cantidad_kg_anual` quedaban **al doble**. El `peso_canasta`
   no se veía afectado porque se normaliza dentro de la canasta y el factor 2 era
   uniforme, así que el semáforo y la validación seguían siendo correctos.
2. **Las exclusiones de procesados no servían de nada.** Excluir `0507` (papa
   seca) de las específicas no la sacaba, porque `0500` ya la contenía. Al usar
   solo las presentaciones, las exclusiones empiezan a funcionar de verdad.
"""

from __future__ import annotations

import math

# producto (slug) → grupo de 2 dígitos de p601a. El nombre entre paréntesis es
# la etiqueta del código agregado en la propia ENAHO, y el % es la porción del
# gasto total en alimentos que representa el grupo (ENAHO 2023).
CANASTA_GRUPOS: dict[str, str] = {
    # --- Los 6 originales del MVP -----------------------------------------
    "pollo": "09",  # CARNE DE POLLO Y OTRAS AVES        10.9 %
    "papa": "05",  # PAPA (BLANCA Y OTRAS)                4.3 %
    "huevo": "07",  # HUEVO                               3.6 %
    "cebolla": "32",  # CEBOLLA (ROJA, BLANCA, ETC)       1.5 %
    "tomate": "33",  # TOMATE (ITALIANO, ROJO)            1.1 %
    "limon": "38",  # LIMON                               1.1 %
    # --- Ampliación (issue #155) ------------------------------------------
    # Entran los grupos que cumplen las dos condiciones: la ENAHO permite
    # ponderarlos por departamento Y SISAP publica su precio a diario.
    "arroz": "03",  # ARROZ (CORRIENTE Y SUPERIOR)        5.6 %
    "carne_res": "08",  # CARNES DE RES Y OTRAS ROJAS     4.2 %
    "pescado": "20",  # PESCADO FRESCO                    4.0 %
    "leche": "04",  # LECHE (EVAPORADA, FRESCA…)          3.8 %
    "azucar": "06",  # AZUCAR (BLANCA Y RUBIA)            2.5 %
    "aceite": "23",  # ACEITE (BOTELLA Y A GRANEL)        2.4 %
    "menestras": "31",  # LENTEJA, ARVEJA, HABA, FRIJOL   2.1 %
}

# NO entran, y por qué:
#   fideos (grupo 19, 2.3 % del gasto) y harina de trigo (grupo 16, 2.0 %):
#   SISAP los publica solo en el mercado MAYORISTA, y la canasta se valoriza a
#   precio MINORISTA (es el ámbito que cruza con los pesos ENAHO y con el IPC —
#   ver docs/validacion_canasta_vs_ipc.md). Mezclar fuentes rompería la
#   comparabilidad. Entran el día que SISAP los publique en minorista.
#   pan (01, 5.0 %), otras hortalizas (37, 4.7 %), otras frutas (41, 4.3 %),
#   comidas preparadas (47, 3.5 %) y queso (24, 2.1 %): sin serie de precio
#   diaria en SISAP.

# Inverso: grupo → producto. (Los grupos son únicos por producto.)
GRUPO_A_PRODUCTO: dict[str, str] = {grupo: prod for prod, grupo in CANASTA_GRUPOS.items()}

# Códigos que caen en un grupo de la canasta pero NO son el alimento fresco
# equivalente al que cotiza SISAP. Cada exclusión se justifica sola:
EXCLUIDOS: frozenset[str] = frozenset(
    {
        # Papa: procesada, no es papa fresca.
        "0507",  # PAPA SECA
        # Leche: no son leche de vaca ni comparables con su precio.
        "0406",  # LECHE DE SOYA
        "0409",  # LECHE CHOCOLATADA
        # Azúcar: endulzante, no azúcar.
        "0603",  # ENDULZANTE NATURAL STEVIA
        "0604",  # ENDULZANTE NATURAL STEVIA
        # Aceite: grasa animal, no aceite vegetal.
        "2306",  # MANTECA DE CHANCHO
        # Carnes rojas: animales vivos (el precio en pie no es precio de carne)
        # y carne de monte, que no tiene serie de precios de mercado.
        "0809",  # CUY EN PIE O VIVO
        "0811",  # CARNE DE CARACHUPA
        "0812",  # CARNE DE MONO
        "0813",  # CARNE DE VENADO
        "0814",  # MONO EN PIE
        "0815",  # BOA EN PIE
        "0816",  # SACHAVACA EN PIE O VIVO
    }
)

# Slugs de la canasta (orden estable).
PRODUCTOS_CANASTA: tuple[str, ...] = tuple(CANASTA_GRUPOS)

# Alias retrocompatibles: el código y los tests viejos usan estos nombres.
MVP_GRUPOS = CANASTA_GRUPOS
PRODUCTOS_MVP = PRODUCTOS_CANASTA


def normalizar_codigo(codigo: object) -> str | None:
    """Lleva un `p601a` crudo a string de 4 dígitos con cero a la izquierda.

    En el `.dta` el código puede venir como entero (``501`` en vez de ``"0501"``)
    o como float (``501.0``). Devuelve None si no es un código numérico válido.

    >>> normalizar_codigo(501)
    '0501'
    >>> normalizar_codigo("3201")
    '3201'
    >>> normalizar_codigo(700.0)
    '0700'
    >>> normalizar_codigo(None) is None
    True
    """
    if codigo is None:
        return None
    if isinstance(codigo, float):
        if math.isnan(codigo):
            return None
        codigo = int(codigo)
    s = str(codigo).strip()
    if s.endswith(".0"):
        s = s[:-2]
    if not s or not s.isdigit():
        return None
    return s.zfill(4)


def es_agregado(codigo_normalizado: str) -> bool:
    """¿Es el código agregado `XX00` del grupo? Ver el docstring del módulo."""
    return codigo_normalizado.endswith("00")


def mapear_producto(codigo: object) -> str | None:
    """Devuelve el slug del producto de la canasta para un `p601a`, o None.

    None cubre: código de otro grupo (no está en la canasta), el **agregado
    `XX00`** (duplicaría el gasto de su propio grupo), un procesado a excluir, o
    un código inválido/ausente.

    >>> mapear_producto(501)      # papa amarilla
    'papa'
    >>> mapear_producto("0500")   # agregado del grupo papa -> duplicaría
    >>> mapear_producto("0507")   # papa seca -> procesado
    >>> mapear_producto(304)      # arroz extra a granel
    'arroz'
    >>> mapear_producto(3301)     # tomate italiano
    'tomate'
    >>> mapear_producto(1804)     # harina (grupo fuera de la canasta)
    """
    norm = normalizar_codigo(codigo)
    if norm is None or norm in EXCLUIDOS or es_agregado(norm):
        return None
    return GRUPO_A_PRODUCTO.get(norm[:2])
