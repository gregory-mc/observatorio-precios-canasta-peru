"""Mapa coroplético por departamento — pendiente (#39)."""

from __future__ import annotations

import streamlit as st


def render() -> None:
    st.title("🗺️ Mapa por departamento")
    st.info(
        "Pendiente: issue #39. Coroplético de los 25 departamentos.\n\n"
        "Nota para quien lo implemente: hoy solo Lima tiene precios propios "
        "(SISAP se scrapea únicamente para Lima), así que un mapa de *precios* "
        "pintaría 24 departamentos con el mismo valor. Lo que sí varía por "
        "departamento es la composición de la canasta (pesos ENAHO)."
    )
