"""Mapa coroplético por departamento (#39)."""

from __future__ import annotations

from datetime import date

import plotly.express as px
import streamlit as st

from observatorio.dashboard import datos
from observatorio.dashboard.logica import (
    mes_legible,
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
    "arroz": "Arroz",
    "carne_res": "Carne de res",
    "pescado": "Pescado",
    "leche": "Leche",
    "azucar": "Azúcar",
    "aceite": "Aceite",
    "menestras": "Menestras",
}

_PESO = "Qué se consume en cada departamento"
_VARIACION = "Cuánto golpea la suba en cada departamento"


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
    st.title("🗺️ El mapa del consumo")
    st.caption(
        "No todo el país come lo mismo, y por eso una misma suba de precios no "
        "pega igual en todas partes. Este mapa muestra dónde pesa más cada "
        "alimento en el gasto de los hogares."
    )

    if not datos.hay_conexion():
        st.error(
            "No se pudo conectar a la base de precios. Si administrás este "
            "dashboard, falta configurar `SUPABASE_DB_URL`."
        )
        return

    nombres = dict(datos.departamentos())
    pesos = datos.pesos_por_departamento()
    if not pesos:
        st.warning("Todavía no hay datos de consumo por departamento.")
        return

    with st.sidebar:
        st.header("Filtros")
        modo = st.radio("Qué mapear", options=[_PESO, _VARIACION])
        slug, fuente = None, datos.FUENTE_DEFECTO
        if modo == _PESO:
            slugs = sorted({s for p in pesos.values() for s in p})
            slug = st.selectbox(
                "Producto",
                options=slugs,
                index=slugs.index("papa") if "papa" in slugs else 0,
                format_func=lambda s: _NOMBRES.get(s, s),
            )
        else:
            # El selector de precios solo aparece en el modo que los usa: en el de
            # consumo no cambiaría nada y un control inerte confunde.
            fuente = st.selectbox(
                "Precios de",
                options=datos.FUENTES,
                index=0,
                format_func=datos.nombre_fuente,
            )

    if modo == _PESO:
        valores = peso_por_departamento(pesos, slug)
        etiqueta = f"% de la canasta que es {_NOMBRES.get(slug, slug)}"
        con_signo, escala = False, "Blues"
        st.caption(
            f"De cada S/ 100 que un hogar gasta en estos trece alimentos, cuánto "
            f"se va en **{_NOMBRES.get(slug, slug)}**. Sale de la encuesta de "
            "hogares del INEI."
        )
    else:
        # Un solo conjunto de precios para los 25 departamentos: hoy solo Lima
        # tiene precios propios (ver docs/dashboard.md §3).
        deptos_con_precio = datos.departamentos_con_precio_propio(fuente)
        clave = next(iter(deptos_con_precio), None) if deptos_con_precio else "nacional"
        precios = datos.precios_mensuales(fuente, clave or "todas")
        if not precios:
            st.warning(f"No hay precios en {datos.nombre_fuente(fuente)}.")
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
        st.caption(
            f"Cuánto se encareció la canasta local en {mes_legible(mes)} respecto "
            "del mes "
            "anterior, aplicando los mismos precios a la dieta de cada "
            "departamento. Las diferencias del mapa vienen de **qué** se come, "
            "no de dónde está más caro."
        )
        st.info(
            "Todavía no medimos precios propios fuera de Lima, así que este mapa "
            "no dice dónde la comida cuesta más. Dice dónde una misma suba "
            "golpea más fuerte, según lo que se consume en cada zona."
        )

    geojson = datos.geojson_departamentos()
    if geojson is None:
        st.info(
            "No se pudo cargar el mapa en este momento. Abajo están los mismos "
            "datos en tabla."
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
