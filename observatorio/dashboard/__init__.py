"""Dashboard público del Observatorio de Precios (M5, issues #36–#42).

Estructura:

- ``logica.py``  — núcleo puro: índice de canasta, variación y semáforo. Sin
  streamlit ni base de datos, así que se testea directo.
- ``datos.py``   — única capa de acceso a datos. Hoy lee Supabase directo; cuando
  la API esté desplegada (#47) se reemplaza este módulo y nada más.
- ``paginas/``   — una función ``render()`` por página.
- ``app.py``     — entrypoint: ``streamlit run observatorio/dashboard/app.py``.
"""
