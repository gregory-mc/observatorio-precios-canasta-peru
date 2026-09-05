"""Entrypoint del dashboard (#36).

    streamlit run observatorio/dashboard/app.py

Requiere `SUPABASE_DB_URL` (en el entorno o en `.env`) y el extra `dashboard`:

    pip install -e ".[dashboard]"
"""

from __future__ import annotations

import streamlit as st

from observatorio.dashboard.paginas import evolucion, inicio, mapa


def main() -> None:
    st.set_page_config(
        page_title="Observatorio de Precios — Perú",
        page_icon="🥔",
        layout="wide",
    )
    # `url_path` explícito en cada página: Streamlit lo infiere del nombre del
    # callable, y las tres se llaman `render()` — sin esto colisionan y la app
    # no arranca ("Multiple Pages specified with URL pathname render").
    st.navigation(
        [
            st.Page(
                inicio.render, title="Canasta básica", icon="🥔", url_path="canasta", default=True
            ),
            st.Page(evolucion.render, title="Evolución", icon="📈", url_path="evolucion"),
            st.Page(mapa.render, title="Mapa", icon="🗺️", url_path="mapa"),
        ]
    ).run()


if __name__ == "__main__":
    main()
