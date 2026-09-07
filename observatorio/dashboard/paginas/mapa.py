"""Mapa coroplético por departamento (#39)."""

from __future__ import annotations

from datetime import date

import plotly.express as px
import streamlit as st

from observatorio.dashboard import datos
from observatorio.dashboard.logica import (
    peso_por_departamento,
    semaforo_por_departamento,
)

_NOMBRES = {
    "papa": "Papa",
    "pollo": "Pollo",
    "huevo": "Huevos",
    "cebolla": "Cebolla",
    "tomate": "Tomate",
    "limon": "Limón",
}

_VARIACION = "Variación mensual de la canasta"
_PESO = "Peso de un producto en la canasta"


def _coropleta(geojson, valores: dict[str, float], nombres: dict[str, str], *, etiqueta, escala):
    codigos = sorted(valores)
    fig = px.choropleth(
        {
            "cod": codigos,
            "valor": [valores[c] for c in codigos],
            "departamento": [nombres.get(c, c) for c in codigos],
        },
        geojson=geojson,
        locations="cod",
        featureidkey=datos.GEOJSON_CLAVE,
        color="valor",
        color_continuous_scale=escala,
        hover_name="departamento",
        labels={"valor": etiqueta},
    )
    # `fitbounds` encuadra en Perú sin necesidad de un token de mapbox: es el
    # renderer geo nativo de plotly, no un tile server.
    fig.update_geos(fitbounds="locations", visible=False)
    fig.update_layout(height=560, margin={"l": 0, "r": 0, "t": 10, "b": 0})
    return fig


def _tabla(valores: dict[str, float], nombres: dict[str, str], *, etiqueta: str, con_signo: bool):
    """Los mismos datos del mapa, ordenados de mayor a menor."""
    formato = "{:+.1f}%" if con_signo else "{:.1f}%"
    return [
        {"Departamento": nombres.get(cod, cod), etiqueta: formato.format(valor)}
        for cod, valor in sorted(valores.items(), key=lambda kv: -kv[1])
    ]


def render() -> None:
    st.title("🗺️ Mapa por departamento")

    if not datos.hay_conexion():
        st.error("Falta `SUPABASE_DB_URL` en el entorno o en `.env`.")
        return

    nombres = dict(datos.departamentos())
    pesos = datos.pesos_por_departamento()
    if not pesos:
        st.warning("No hay canasta cargada en `gold.canasta_consumo_dept`.")
        return

    with st.sidebar:
        st.header("Filtros")
        modo = st.radio("Qué mapear", options=[_VARIACION, _PESO])
        slug = None
        if modo == _PESO:
            slugs = sorted({s for p in pesos.values() for s in p})
            slug = st.selectbox(
                "Producto",
                options=slugs,
                index=slugs.index("papa") if "papa" in slugs else 0,
                format_func=lambda s: _NOMBRES.get(s, s),
            )
        fuente = st.selectbox("Fuente de precios", options=datos.FUENTES, index=0)

    if modo == _PESO:
        valores = peso_por_departamento(pesos, slug)
        etiqueta = f"% de la canasta que es {_NOMBRES.get(slug, slug)}"
        con_signo, escala = False, "Blues"
        st.caption(
            f"Qué porción del gasto en alimentos frescos representa "
            f"**{_NOMBRES.get(slug, slug)}** en cada departamento. Dato departamental "
            "puro: sale entero de la ENAHO y no depende de ningún precio."
        )
    else:
        # Un solo conjunto de precios para los 25 departamentos: hoy solo Lima
        # tiene precios propios (ver docs/dashboard.md §3).
        deptos_con_precio = datos.departamentos_con_precio_propio(fuente)
        clave = next(iter(deptos_con_precio), None) if deptos_con_precio else "nacional"
        precios = datos.precios_mensuales(fuente, clave or "todas")
        if not precios:
            st.warning(f"No hay precios en `{fuente}`.")
            return

        hoy = date.today()
        semaforos = semaforo_por_departamento(
            precios, pesos, mes_actual=f"{hoy.year}-{hoy.month:02d}"
        )
        valores = {
            cod: sem.variacion for cod, sem in semaforos.items() if sem.variacion is not None
        }
        if not valores:
            alguno = next(iter(semaforos.values()), None)
            st.info(
                "Sin variación mensual comparable: "
                + (alguno.motivo if alguno and alguno.motivo else "faltan meses consecutivos.")
            )
            return

        etiqueta, con_signo, escala = "Variación mensual (%)", True, "RdYlGn_r"
        mes = next(iter(semaforos.values())).mes
        st.warning(
            f"**Este mapa muestra composición de consumo, no diferencias de precio.** "
            f"Solo {nombres.get(next(iter(deptos_con_precio), ''), 'Lima')} tiene precios "
            f"propios en `{fuente}`, así que los 25 departamentos se valorizan con los "
            "mismos precios: lo que cambia de un departamento a otro es **qué** consume. "
            "Cuando SISAP cubra más departamentos, el mapa pasa a ser de precios sin "
            "tocar el código."
        )
        st.caption(f"Variación del costo de la canasta en {mes} contra el mes anterior.")

    geojson = datos.geojson_departamentos()
    if geojson is None:
        st.info(
            "No se pudieron cargar los límites departamentales (la descarga falló). "
            "Abajo van los mismos datos en tabla."
        )
    else:
        st.plotly_chart(
            _coropleta(geojson, valores, nombres, etiqueta=etiqueta, escala=escala),
            width="stretch",
        )
        st.caption(datos.GEOJSON_ATRIBUCION)

    with st.expander("Ver como tabla", expanded=geojson is None):
        st.dataframe(
            _tabla(valores, nombres, etiqueta=etiqueta, con_signo=con_signo),
            hide_index=True,
            width="stretch",
        )
