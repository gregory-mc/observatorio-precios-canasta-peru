"""Entrypoint que Streamlit Community Cloud busca por defecto (#49).

Community Cloud propone `streamlit_app.py` en la raíz como "Main file path". El
dashboard vive en `observatorio/dashboard/app.py` para quedar dentro del paquete,
así que este archivo es solo un puente: existe para que el valor por defecto del
formulario de deploy funcione, en vez de fallar con "This file does not exist".

Las dos rutas son equivalentes:

    streamlit run streamlit_app.py                    # el default de Cloud
    streamlit run observatorio/dashboard/app.py       # directo al paquete
"""

from observatorio.dashboard.app import main

main()
