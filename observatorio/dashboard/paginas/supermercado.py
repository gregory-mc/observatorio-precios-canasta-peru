"""Precios de supermercado: buscador, inflación por categoría y ofertas (#152)."""

from __future__ import annotations

import plotly.graph_objects as go
import streamlit as st

from observatorio.dashboard import datos
from observatorio.dashboard.logica import (
    DIAS_VENTANA,
    VENTANAS_SUPER,
    cambios_por_categoria,
    descuento_pct,
    fecha_menos,
    insertar_huecos,
)

_BUSCAR, _CATEGORIAS, _OFERTAS = "Buscar un producto", "Cuánto subió cada categoría", "Ofertas"


def _figura_sku(serie) -> go.Figure:
    """Precio pagado y precio de lista de un producto, día por día."""
    fig = go.Figure()
    con_lista = [(f, lst) for f, _, lst in serie if lst is not None]
    if con_lista:
        fig.add_trace(
            go.Scatter(
                x=[f for f, _ in con_lista],
                y=[v for _, v in con_lista],
                mode="lines",
                line={"width": 1.5, "color": "#9aa0a6", "dash": "dot"},
                name="Precio de lista",
                hovertemplate="%{x|%d/%m/%Y}<br>S/ %{y:.2f} de lista<extra></extra>",
            )
        )
    pagado = insertar_huecos([(f, p) for f, p, _ in serie])
    fig.add_trace(
        go.Scatter(
            x=[f for f, _ in pagado],
            y=[v for _, v in pagado],
            mode="lines",
            line={"width": 2.5, "color": "#111"},
            name="Precio que pagás",
            connectgaps=False,
            hovertemplate="%{x|%d/%m/%Y}<br>S/ %{y:.2f}<extra></extra>",
        )
    )
    fig.update_layout(
        hovermode="x unified",
        height=340,
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "x": 0},
    )
    fig.update_yaxes(title="Soles", rangemode="tozero")
    return fig


def _bloque_buscador(hasta: str) -> None:
    st.subheader("Buscar un producto")
    texto = st.text_input(
        "Nombre del producto",
        placeholder="aceite, leche evaporada, arroz…",
        label_visibility="collapsed",
    )
    if not texto or len(texto.strip()) < 3:
        st.caption(
            "Escribí al menos 3 letras. Se busca en el catálogo de hoy, así que "
            "un producto que la tienda dejó de listar no aparece."
        )
        return

    resultados = datos.buscar_super(texto.strip(), hasta)
    if not resultados:
        st.info(f"No encontramos productos con «{texto.strip()}».")
        return

    st.caption(f"{len(resultados)} presentaciones encontradas. Elegí una para ver su historia.")
    etiquetas = {
        f"{r['nombre']} — S/ {r['precio']:.2f}" + ("" if r["disponible"] else "  (agotado)"): r
        for r in resultados
    }
    elegida = st.selectbox("Presentación", options=list(etiquetas), label_visibility="collapsed")
    producto = etiquetas[elegida]

    izq, centro, der = st.columns(3)
    izq.metric("Precio", f"S/ {producto['precio']:.2f}")
    dto = descuento_pct(producto["precio"], producto["precio_lista"] or 0)
    if dto:
        centro.metric(
            "En oferta",
            f"−{dto:.0f}%",
            help=f"Precio de lista: S/ {producto['precio_lista']:.2f}",
        )
    else:
        centro.metric("En oferta", "no")
    der.metric("Disponible", "sí" if producto["disponible"] else "agotado")

    serie = datos.serie_sku(producto["sku_id"])
    if len(serie) > 1:
        st.plotly_chart(_figura_sku(serie), width="stretch")
    else:
        st.caption("Todavía no hay suficientes días de este producto para dibujar su historia.")

    detalle = " · ".join(x for x in (producto["marca"], producto["categoria"]) if x)
    if detalle:
        st.caption(detalle)
    if producto["url"]:
        st.caption(f"[Ver en la tienda]({producto['url']})")


def _bloque_categorias(hasta: str) -> None:
    st.subheader("Cuánto subió cada categoría")
    etiqueta = st.radio(
        "Comparar", options=list(VENTANAS_SUPER), horizontal=True, label_visibility="collapsed"
    )
    dias_atras = VENTANAS_SUPER[etiqueta]

    ahora = datos.precios_por_categoria(hasta, DIAS_VENTANA)
    antes = datos.precios_por_categoria(fecha_menos(hasta, dias_atras), DIAS_VENTANA)
    tipicos = datos.precio_tipico_por_categoria(hasta)

    cambios = cambios_por_categoria(antes, ahora, tipicos)
    if not cambios:
        st.info("Todavía no hay suficiente historia para comparar.")
        return

    st.dataframe(
        [
            {
                "Categoría": c.categoria,
                "Subieron": f"{c.pct_subieron:.0f}%",
                "Bajaron": f"{c.pct_bajaron:.0f}%",
                "Sin cambio": f"{100 - c.pct_subieron - c.pct_bajaron:.0f}%",
                "Efecto neto": f"{c.variacion_media:+.1f}%",
                "Precio típico": f"S/ {c.precio_tipico:.2f}",
                "Productos": c.n_productos,
            }
            for c in cambios
        ],
        hide_index=True,
        width="stretch",
    )

    with st.expander("Cómo leer esta tabla"):
        st.markdown(
            f"""
**La mayoría de los precios no se mueve.** En el supermercado, cerca de 7 de
cada 10 productos mantienen el mismo precio de un mes al otro. Por eso la tabla
muestra *cuántos* subieron y bajaron en vez de un único porcentaje: un "0 %"
promedio esconde que un 13 % subió y un 17 % bajó.

El **efecto neto** es el promedio de todas las variaciones: es lo más parecido a
"cuánto se encareció esta categoría".

Se compara **cada producto contra sí mismo**: su precio promedio de la última
semana contra el de la semana equivalente de hace {dias_atras} días, y solo entran
los que están en las dos ventanas. Comparar el precio promedio del catálogo
mezclaría inflación con cambio de surtido: si entran productos caros o salen
baratos, el promedio se mueve sin que ningún precio haya cambiado.

Se cuenta como cambio un movimiento mayor al 0.5 %, porque los precios se
promedian sobre una semana y un solo día de oferta deja una diferencia mínima
que no es un cambio real. Las categorías con menos de 20 productos en común no
se muestran.
"""
        )


def _bloque_ofertas(categorias: list[str], hasta: str) -> None:
    st.subheader("Ofertas de hoy")
    izq, der = st.columns([3, 2])
    categoria = izq.selectbox("Categoría", options=["Todas", *categorias])
    solo_disp = der.checkbox("Solo lo que está en stock", value=True)

    filas = datos.ofertas_super(
        None if categoria == "Todas" else categoria, solo_disp, hasta
    )
    if not filas:
        st.info("No hay ofertas para esa selección.")
        return

    st.dataframe(
        [
            {
                "Producto": f["nombre"],
                "Antes": f"S/ {f['precio_lista']:.2f}",
                "Ahora": f"S/ {f['precio']:.2f}",
                "Descuento": f"−{descuento_pct(f['precio'], f['precio_lista']):.0f}%",
                "Categoría": f["categoria_raiz"],
                "Ver": f["url"],
            }
            for f in filas
        ],
        hide_index=True,
        width="stretch",
        column_config={"Ver": st.column_config.LinkColumn("Ver", display_text="tienda")},
    )
    st.caption(
        "El descuento se calcula contra el precio de lista que publica la propia "
        "tienda, así que refleja lo que ella misma dice que era el precio anterior."
    )


def render() -> None:
    st.title("🛒 Precios de supermercado")

    if not datos.hay_conexion():
        st.error(
            "No se pudo conectar a la base de precios. Si administrás este "
            "dashboard, falta configurar `SUPABASE_DB_URL`."
        )
        return

    desde, hasta = datos.rango_fechas_super()
    if not hasta:
        st.warning("Todavía no hay datos de supermercado.")
        return

    st.caption(
        f"Seguimos día por día los alimentos de una cadena de supermercados, "
        f"desde el {desde}. A diferencia de la canasta, acá no hay seis "
        "productos: son miles."
    )

    with st.sidebar:
        st.header("Qué ver")
        vista = st.radio("Sección", options=[_BUSCAR, _CATEGORIAS, _OFERTAS])

    if vista == _BUSCAR:
        _bloque_buscador(hasta)
    elif vista == _CATEGORIAS:
        _bloque_categorias(hasta)
    else:
        _bloque_ofertas(datos.categorias_super(hasta), hasta)
