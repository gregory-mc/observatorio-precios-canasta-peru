"""Evolución temporal con bandas de predicción — pendiente (#38)."""

from __future__ import annotations

import streamlit as st


def render() -> None:
    st.title("📈 Evolución temporal")
    st.info(
        "Pendiente: issue #38. Serie de precios por producto con las bandas de "
        "`gold.fct_predicciones` y las anomalías de `gold.fct_anomalias`.\n\n"
        "Nota para quien la implemente: las predicciones que hay en prod son del "
        "modelo `naive` con bandas empíricas — Prophet está apagado desde el "
        "2026-07-24 porque perdía contra el baseline (MAPE 9.44 vs 6.33)."
    )
