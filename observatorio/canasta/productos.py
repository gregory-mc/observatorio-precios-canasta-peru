"""Mapeo de los códigos `p601a` de la ENAHO a los productos del MVP — issue #19.

Destila las decisiones ya cerradas en docs/enaho.md y docs/canasta_consumo_dept.md:

  * El código `p601a` tiene 4 dígitos; los **2 primeros = grupo** del producto.
    Cada producto del MVP cae en un único grupo (mapear por grupo evita los falsos
    positivos de buscar por nombre: SALSA DE TOMATE, PAN DE HUEVO, HOJA DE LIMÓN…).
  * Dentro del grupo se **suman todas las presentaciones frescas** (`XX00` agregado
    y `XX0n` específicas), **excluyendo los códigos procesados**.

La mayoría de los procesados listados en docs/enaho.md viven en OTROS grupos
(harina de papa = 18, salsa de tomate = 30, fideos al huevo = 19, etc.) y por eso
quedan fuera automáticamente al filtrar por grupo. El único procesado que comparte
grupo con su producto fresco es la **papa seca** (`0507`, grupo `05`), así que es
el único que hace falta excluir explícitamente.
"""

from __future__ import annotations

import math

# producto MVP (slug) → grupo de 2 dígitos de p601a.
MVP_GRUPOS: dict[str, str] = {
    "papa": "05",
    "huevo": "07",
    "pollo": "09",
    "cebolla": "32",
    "tomate": "33",
    "limon": "38",
}

# Inverso: grupo → producto. (Los grupos son únicos por producto.)
GRUPO_A_PRODUCTO: dict[str, str] = {grupo: prod for prod, grupo in MVP_GRUPOS.items()}

# Códigos `p601a` que caen en un grupo MVP pero son procesados → se excluyen.
# Ver docstring: solo la papa seca comparte grupo con su producto fresco.
EXCLUIDOS: frozenset[str] = frozenset({"0507"})

# Slugs de los productos del MVP (orden estable).
PRODUCTOS_MVP: tuple[str, ...] = tuple(MVP_GRUPOS)


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


def mapear_producto(codigo: object) -> str | None:
    """Devuelve el slug del producto MVP para un `p601a`, o None si no aplica.

    None cubre: código de otro grupo (no MVP), código procesado a excluir, o
    código inválido/ausente.

    >>> mapear_producto(501)      # papa amarilla
    'papa'
    >>> mapear_producto("0507")   # papa seca → procesado
    >>> mapear_producto(3301)     # tomate italiano
    'tomate'
    >>> mapear_producto(1804)     # harina (otro grupo)
    """
    norm = normalizar_codigo(codigo)
    if norm is None or norm in EXCLUIDOS:
        return None
    return GRUPO_A_PRODUCTO.get(norm[:2])
