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
}


def _tarjeta_semaforo(sem) -> None:
    color, emoji = _COLORES[sem.nivel]
    variacion = "—" if sem.variacion is None else f"{sem.variacion:+.1f}%"
    periodo = (
        f"{sem.mes} vs {sem.mes_previo}" if sem.mes and sem.mes_previo else "sin período comparable"
    )
    st.markdown(
        f"""
        <div style="border-left:6px solid {color};background:rgba(127,127,127,.08);
                    padding:1rem 1.25rem;border-radius:.5rem">
          <div style="font-size:2.5rem;line-height:1">{emoji} {variacion}</div>
          <div style="font-size:1.1rem;font-weight:600;color:{color}">{sem.etiqueta}</div>
          <div style="opacity:.75;font-size:.9rem">Costo de la canasta · {periodo}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if sem.motivo:
        st.info(sem.motivo.capitalize())


def render() -> None:
    st.title("🥔 Canasta básica de alimentos")
    st.caption(
        "Costo de una canasta de 6 alimentos frescos ponderada por el consumo real "
        "de cada departamento (ENAHO), valorizada con precios diarios."
    )

    if not datos.hay_conexion():
        st.error(
            "Falta `SUPABASE_DB_URL` en el entorno o en `.env`. "
            "El dashboard lee la capa gold de Supabase."
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
        fuente = st.selectbox("Fuente de precios", options=datos.FUENTES, index=0)

    ambito = resolver_ambito(
        cod_dep,
        deptos_con_precio=datos.departamentos_con_precio_propio(fuente),
        tiene_nacional=datos.tiene_precios_nacionales(fuente),
        nombres=nombres,
    )

    precios = datos.precios_mensuales(fuente, ambito.clave)
    pesos, anio_enaho = datos.pesos_canasta(cod_dep)

    if not precios or not pesos:
        st.warning(f"No hay datos suficientes para {nombres[cod_dep]} en `{fuente}`.")
        return

    indice = indice_canasta(precios, pesos)
    hoy = date.today()
    sem = evaluar_semaforo(indice, mes_actual=f"{hoy.year}-{hoy.month:02d}")

    izq, der = st.columns([2, 3])
    with izq:
        _tarjeta_semaforo(sem)
        st.caption(
            f"Verde < {UMBRAL_ESTABLE:g}% · Ámbar {UMBRAL_ESTABLE:g}–{UMBRAL_ALERTA:g}% · "
            f"Rojo ≥ {UMBRAL_ALERTA:g}%. Umbrales calibrados sobre la volatilidad "
            "histórica real de esta canasta, no elegidos a mano."
        )

    with der:
        if ambito.nota:
            st.warning(f"**{nombres[cod_dep]} en `{fuente}`.** {ambito.nota}")
        st.markdown("**Composición de la canasta**")
        st.caption(f"Pesos de consumo ENAHO {anio_enaho} · {nombres[cod_dep]}")
        st.dataframe(
            [
                {"Producto": _NOMBRES.get(slug, slug), "Peso en la canasta": f"{peso:.1%}"}
                for slug, peso in sorted(pesos.items(), key=lambda kv: -kv[1])
            ],
            hide_index=True,
            width="stretch",
        )

    st.divider()
    st.subheader("Precios más recientes")
    recientes = datos.precios_recientes(fuente, ambito.clave)
    if not recientes:
        st.info("Sin precios recientes para esta fuente.")
        return

    filas = []
    for slug, precio, fecha in recientes:
        piso, techo = rango_plausible(slug)
        dentro = piso <= precio <= techo
        filas.append(
            {
                "Producto": _NOMBRES.get(slug, slug),
                "Precio (S//kg)": f"{precio:.2f}",
                "Rango esperado": f"{piso:g} – {techo:g}",
                "": "✓" if dentro else "⚠️ fuera de rango",
                "Fecha": fecha,
            }
        )
    st.dataframe(filas, hide_index=True, width="stretch")
    st.caption(
        "El rango esperado es el mismo que usa la validación de la canasta (#102): "
        "percentiles 1–99 de SISAP minorista con margen para picos de escasez. "
        "Un precio fuera de rango señala un posible error de unidad o de parseo. "
        "En `sisap_mayorista`, limón y tomate cotizan por millar/jaba y caen fuera "
        "por diseño de la fuente."
    )
