"""Página principal: selector de departamento + semáforo de la canasta (#37)."""

from __future__ import annotations

from datetime import date

import streamlit as st

from observatorio.dashboard import datos
from observatorio.dashboard.logica import (
    AMBAR,
    ROJO,
    SIN_DATO,
    UMBRAL_ALERTA,
    UMBRAL_ESTABLE,
    VERDE,
    evaluar_semaforo,
    indice_canasta,
    mes_legible,
    resolver_ambito,
)
from observatorio.validacion.canasta_vs_ipc import rango_plausible

_COLORES = {
    VERDE: ("#1a7f37", "🟢"),
    AMBAR: ("#9a6700", "🟡"),
    ROJO: ("#b42318", "🔴"),
    SIN_DATO: ("#57606a", "⚪"),
}

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


def _tarjeta_semaforo(sem) -> None:
    color, emoji = _COLORES[sem.nivel]
    variacion = "—" if sem.variacion is None else f"{sem.variacion:+.1f}%"
    periodo = (
        f"{mes_legible(sem.mes)} frente a {mes_legible(sem.mes_previo)}"
        if sem.mes and sem.mes_previo
        else "sin un mes con qué comparar"
    )
    st.markdown(
        f"""
        <div style="border-left:6px solid {color};background:rgba(127,127,127,.08);
                    padding:1rem 1.25rem;border-radius:.5rem">
          <div style="font-size:2.5rem;line-height:1">{emoji} {variacion}</div>
          <div style="font-size:1.1rem;font-weight:600;color:{color}">{sem.etiqueta}</div>
          <div style="opacity:.75;font-size:.9rem">{periodo}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if sem.motivo:
        st.info(sem.motivo.capitalize())


def render() -> None:
    st.title("🥔 ¿Se encareció la comida este mes?")
    st.caption(
        "Seguimos el precio de trece alimentos básicos y los combinamos según lo "
        "que realmente se consume en cada departamento, para responder una sola "
        "pregunta: comprar lo mismo que el mes pasado, ¿cuesta más o menos?"
    )

    if not datos.hay_conexion():
        st.error(
            "No se pudo conectar a la base de precios. Si administrás este "
            "dashboard, falta configurar `SUPABASE_DB_URL`."
        )
        return

    deptos = datos.departamentos()
    nombres = {cod: nombre for cod, nombre in deptos}

    with st.sidebar:
        st.header("Filtros")
        cod_dep = st.selectbox(
            "Departamento",
            options=[cod for cod, _ in deptos],
            format_func=lambda c: nombres[c],
            index=[cod for cod, _ in deptos].index("15") if "15" in nombres else 0,
        )
        fuente = st.selectbox(
            "Precios de",
            options=datos.FUENTES,
            index=0,
            format_func=datos.nombre_fuente,
        )

    ambito = resolver_ambito(
        cod_dep,
        deptos_con_precio=datos.departamentos_con_precio_propio(fuente),
        tiene_nacional=datos.tiene_precios_nacionales(fuente),
        nombres=nombres,
    )

    precios = datos.precios_mensuales(fuente, ambito.clave)
    pesos, anio_enaho = datos.pesos_canasta(cod_dep)

    if not precios or not pesos:
        st.warning(f"Todavía no hay datos de {nombres[cod_dep]} en {datos.nombre_fuente(fuente)}.")
        return

    indice = indice_canasta(precios, pesos)
    hoy = date.today()
    sem = evaluar_semaforo(indice, mes_actual=f"{hoy.year}-{hoy.month:02d}")

    izq, der = st.columns([2, 3])
    with izq:
        _tarjeta_semaforo(sem)
        st.caption(
            "🟢 se mantuvo o bajó · 🟡 subió · 🔴 subió fuerte"
        )
        with st.expander("Cómo se mide"):
            st.markdown(
                f"""
Se compara el costo del **último mes cerrado** contra el mes anterior. El mes en
curso no se usa: con pocos días cargados, su promedio todavía no dice nada.

Los cortes son 🟡 a partir de **{UMBRAL_ESTABLE:g}%** y 🔴 a partir de
**{UMBRAL_ALERTA:g}%**. No son números redondos elegidos a gusto: salen de medir
cuánto se mueve normalmente esta canasta mes a mes. La mitad de los meses se
mueve menos de {UMBRAL_ESTABLE:g}%, y solo uno de cada cinco supera
{UMBRAL_ALERTA:g}% — por eso ese es el umbral de alarma. Los alimentos frescos
son volátiles por naturaleza: un semáforo más sensible estaría casi siempre en
rojo y no serviría de nada.
"""
            )

    with der:
        if ambito.nota:
            st.warning(f"**{nombres[cod_dep]}.** {ambito.nota}")
        st.markdown(f"**Qué se come en {nombres[cod_dep]}**")
        st.caption(
            "De cada S/ 100 gastados en estos trece alimentos, cuánto va a cada "
            f"uno. Sale de la encuesta de hogares del INEI ({anio_enaho})."
        )
        st.dataframe(
            [
                {"Producto": _NOMBRES.get(slug, slug), "Del gasto": f"{peso:.1%}"}
                for slug, peso in sorted(pesos.items(), key=lambda kv: -kv[1])
            ],
            hide_index=True,
            width="stretch",
        )

    st.divider()
    st.subheader("Últimos precios")
    recientes = datos.precios_recientes(fuente, ambito.clave)
    if not recientes:
        st.info("Todavía no hay precios recientes para esta selección.")
        return

    filas = []
    for slug, precio, fecha in recientes:
        piso, techo = rango_plausible(slug)
        dentro = piso <= precio <= techo
        filas.append(
            {
                "Producto": _NOMBRES.get(slug, slug),
                "Soles por kilo": f"{precio:.2f}",
                "Rango normal": f"{piso:g} – {techo:g}",
                "": "" if dentro else "⚠️",
                "Medido el": fecha,
            }
        )
    st.dataframe(filas, hide_index=True, width="stretch")
    if any(fila[""] for fila in filas):
        st.caption("⚠️ marca un precio fuera del rango normal — ver la nota de abajo.")

    with st.expander("De dónde salen estos seis productos y estos rangos"):
        st.markdown(
            """
**Por qué estos trece.** Son los alimentos que cumplen dos condiciones a la vez: la
encuesta de hogares del INEI permite saber cuánto pesa cada uno en el gasto de
**cada departamento**, y la fuente oficial de precios los publica **todos los
días**. Sin lo primero no se puede ponderar por departamento; sin lo segundo no
hay seguimiento diario.

Es un punto de partida, no un límite: ya está medido que sumar arroz, aceite,
azúcar y leche acercaría bastante más el resultado a la inflación de alimentos
que publica el INEI.

**El rango normal** es el recorrido de precios habitual de cada producto, con
margen para picos de escasez genuinos — el limón, por ejemplo, llega a S/ 18–20
por kilo cuando falta. Un valor por fuera no significa que el precio sea falso:
es un aviso de que conviene mirarlo, porque muchas veces es un error de unidad
en la fuente. En el mercado mayorista, el limón y el tomate se cotizan por
millar o por jaba, así que caen fuera del rango por cómo publica la fuente y no
por un problema del dato.
"""
        )
