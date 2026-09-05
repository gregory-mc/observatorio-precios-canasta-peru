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
}


def _figura(serie, preds, anoms, *, nombre: str) -> go.Figure:
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
                name="Banda de pronóstico",
            )
        )
        fig.add_trace(
            go.Scatter(
                x=fechas,
                y=[v for _, v, _, _ in preds],
                mode="lines",
                line={"dash": "dash", "width": 2, "color": "#1f77b4"},
                name="Pronóstico",
                hovertemplate="%{x|%d/%m/%Y}<br>S/ %{y:.2f} previsto<extra></extra>",
            )
        )

    fig.add_trace(
        go.Scatter(
            x=[f for f, _ in serie],
            y=[v for _, v in serie],
            mode="lines",
            line={"width": 2, "color": "#111"},
            name="Precio observado",
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
                name="Anomalía",
                customdata=[(e, z) for _, _, e, z in anoms],
                hovertemplate=(
                    "%{x|%d/%m/%Y}<br>S/ %{y:.2f} observado"
                    "<br>S/ %{customdata[0]:.2f} esperado"
                    "<br>z = %{customdata[1]:.1f}<extra></extra>"
                ),
            )
        )

    fig.update_layout(
        title=f"{nombre} — S/ por kg",
        hovermode="x unified",
        height=460,
        margin={"l": 10, "r": 10, "t": 50, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    fig.update_yaxes(title=None, rangemode="tozero")
    fig.update_xaxes(title=None)
    return fig


def render() -> None:
    st.title("📈 Evolución temporal")
    st.caption(
        "Precio diario por producto, con la banda de pronóstico y las anomalías "
        "detectadas por el pipeline de ML."
    )

    if not datos.hay_conexion():
        st.error("Falta `SUPABASE_DB_URL` en el entorno o en `.env`.")
        return

    with st.sidebar:
        st.header("Filtros")
        fuente = st.selectbox("Fuente de precios", options=_FUENTES_CON_PRED, index=0)
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
        st.warning(f"No hay serie de {_NOMBRES.get(slug, slug)} en `{fuente}` para ese período.")
        return

    serie = insertar_huecos(crudos)
    preds, modelo, corrida = datos.predicciones(fuente, slug)
    anoms = datos.anomalias(fuente, slug, inicio.isoformat() if inicio else None)

    st.plotly_chart(
        _figura(serie, preds, anoms, nombre=_NOMBRES.get(slug, slug)),
        width="stretch",
    )

    izq, centro, der = st.columns(3)
    ultimo_dia, ultimo_precio = crudos[-1]
    izq.metric("Último precio", f"S/ {ultimo_precio:.2f}", help=f"Del {ultimo_dia:%d/%m/%Y}")

    prox = proxima_prediccion([(f, v, i, s) for f, v, i, s in preds], hoy=hoy)
    if prox:
        centro.metric(
            f"Previsto {prox.fecha:%d/%m}",
            f"S/ {prox.valor:.2f}",
            delta=f"{(prox.valor / ultimo_precio - 1) * 100:+.1f}%",
            help=f"Banda: S/ {prox.inferior:.2f} – {prox.superior:.2f}",
        )
    else:
        centro.metric("Previsto", "—", help="La última corrida ya venció su horizonte")

    der.metric("Anomalías en el período", len(anoms))

    if modelo:
        st.caption(
            f"Pronóstico del modelo **`{modelo}`**, corrida del {corrida} "
            "(horizonte de 14 días, el pipeline corre los lunes). "
            "Prophet quedó apagado el 2026-07-24: perdía contra este baseline "
            "(MAPE 9.44 vs 6.33). Las bandas son empíricas, no intervalos "
            "bayesianos."
        )
    if not preds:
        st.info(f"Sin pronóstico para {_NOMBRES.get(slug, slug)} en `{fuente}`.")

    st.caption(
        "La línea se **corta** donde faltan datos en vez de cruzarlos con un "
        "segmento recto: SISAP no tiene 2026-01 a 2026-05 y unir esos extremos "
        "aparentaría un dato que no existe."
    )
