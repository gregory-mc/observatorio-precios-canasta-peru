"""Evolución temporal del precio con banda de pronóstico y anomalías (#38)."""

from __future__ import annotations

from datetime import date

import plotly.graph_objects as go
import streamlit as st

from observatorio.dashboard import datos
from observatorio.dashboard.logica import (
    VENTANAS,
    desde_ventana,
    insertar_huecos,
    proxima_prediccion,
    resolver_ambito,
)

# Solo SISAP tiene pronóstico: el batch de ML corre sobre esas dos fuentes.
_FUENTES_CON_PRED = ("sisap_minorista", "sisap_mayorista")

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


def _figura(serie, preds, anoms) -> go.Figure:
    fig = go.Figure()

    if preds:
        fechas = [f for f, _, _, _ in preds]
        # La banda va primero para que quede detrás de la línea observada.
        fig.add_trace(
            go.Scatter(
                x=fechas + fechas[::-1],
                y=[s for _, _, _, s in preds] + [i for _, _, i, _ in preds][::-1],
                fill="toself",
                fillcolor="rgba(31,119,180,.15)",
                line={"width": 0},
                hoverinfo="skip",
                name="Rango probable",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=fechas,
                y=[v for _, v, _, _ in preds],
                mode="lines",
                line={"dash": "dash", "width": 2, "color": "#1f77b4"},
                name="Proyección",
                hovertemplate="%{x|%d/%m/%Y}<br>S/ %{y:.2f} proyectado<extra></extra>",
            )
        )

    fig.add_trace(
        go.Scatter(
            x=[f for f, _ in serie],
            y=[v for _, v in serie],
            mode="lines",
            line={"width": 2, "color": "#111"},
            name="Precio",
            connectgaps=False,  # los nulos de `insertar_huecos` cortan la línea
            hovertemplate="%{x|%d/%m/%Y}<br>S/ %{y:.2f}<extra></extra>",
        )
    )

    if anoms:
        fig.add_trace(
            go.Scatter(
                x=[f for f, _, _, _ in anoms],
                y=[p for _, p, _, _ in anoms],
                mode="markers",
                marker={
                    "size": 9,
                    "color": "#b42318",
                    "symbol": "circle-open",
                    "line": {"width": 2},
                },
                name="Precio fuera de lo habitual",
                customdata=[(e, z) for _, _, e, z in anoms],
                hovertemplate=(
                    "%{x|%d/%m/%Y}<br>S/ %{y:.2f} ese día"
                    "<br>S/ %{customdata[0]:.2f} era lo esperable"
                    "<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        hovermode="x unified",
        height=460,
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    fig.update_yaxes(title="Soles por kilo", rangemode="tozero")
    fig.update_xaxes(title=None)
    return fig


def render() -> None:
    st.title("📈 Cómo viene cambiando cada precio")
    st.caption(
        "Elegí un producto y mirá su precio día por día. La línea negra es lo que "
        "costó; la punteada, hacia dónde va en las próximas dos semanas. Los "
        "círculos rojos marcan días en que el precio se salió de lo habitual."
    )

    if not datos.hay_conexion():
        st.error(
            "No se pudo conectar a la base de precios. Si administrás este "
            "dashboard, falta configurar `SUPABASE_DB_URL`."
        )
        return

    with st.sidebar:
        st.header("Filtros")
        fuente = st.selectbox(
            "Precios de",
            options=_FUENTES_CON_PRED,
            index=0,
            format_func=datos.nombre_fuente,
        )
        disponibles = datos.productos_con_prediccion(fuente) or list(_NOMBRES)
        slug = st.selectbox(
            "Producto",
            options=disponibles,
            # Papa por defecto: es el producto con más cobertura (7 variedades en
            # SISAP) y el de mayor peso después del pollo en la canasta.
            index=disponibles.index("papa") if "papa" in disponibles else 0,
            format_func=lambda s: _NOMBRES.get(s, s),
        )
        ventana = st.selectbox("Período", options=list(VENTANAS), index=1)

    hoy = date.today()
    inicio = desde_ventana(ventana, hoy)
    ambito = resolver_ambito(
        "15",
        deptos_con_precio=datos.departamentos_con_precio_propio(fuente),
        tiene_nacional=datos.tiene_precios_nacionales(fuente),
    )

    crudos = datos.serie_precio(fuente, ambito.clave, slug, inicio.isoformat() if inicio else None)
    if not crudos:
        st.warning(
            f"No hay precios de {_NOMBRES.get(slug, slug)} para ese período."
        )
        return

    serie = insertar_huecos(crudos)
    preds, _modelo, corrida = datos.predicciones(fuente, slug)
    anoms = datos.anomalias(fuente, slug, inicio.isoformat() if inicio else None)

    st.plotly_chart(
        _figura(serie, preds, anoms),
        width="stretch",
    )

    izq, centro, der = st.columns(3)
    ultimo_dia, ultimo_precio = crudos[-1]
    izq.metric(
        "Precio de hoy",
        f"S/ {ultimo_precio:.2f}",
        help=f"Último dato: {ultimo_dia:%d/%m/%Y}",
    )

    prox = proxima_prediccion([(f, v, i, s) for f, v, i, s in preds], hoy=hoy)
    if prox:
        centro.metric(
            f"Proyectado al {prox.fecha:%d/%m}",
            f"S/ {prox.valor:.2f}",
            delta=f"{(prox.valor / ultimo_precio - 1) * 100:+.1f}%",
            help=f"Podría ubicarse entre S/ {prox.inferior:.2f} y S/ {prox.superior:.2f}",
        )
    else:
        centro.metric("Proyectado", "—", help="Todavía no hay una proyección vigente")

    der.metric("Días fuera de lo habitual", len(anoms))

    if not preds:
        st.info(f"Todavía no hay una proyección para {_NOMBRES.get(slug, slug)}.")

    st.caption(
        "Donde la línea se corta es porque la fuente no publicó precios esos días."
    )

    with st.expander("Cómo se calcula la proyección"):
        vigencia = f" (la vigente es del {corrida})." if corrida else "."
        st.markdown(
            f"""
La proyección estima las próximas dos semanas a partir del comportamiento
reciente del precio, y se recalcula cada lunes{vigencia}

**Sirve para ver la tendencia, no como un valor exacto.** El *rango probable*
—la franja celeste— dice más que la línea: cuanto más ancho, menos previsible
es ese producto.

Un día se marca como *fuera de lo habitual* cuando el precio se aparta bastante
de lo que venía siendo normal para ese producto. Suele coincidir con
desabastecimientos, feriados o un error de la fuente.
"""
        )
