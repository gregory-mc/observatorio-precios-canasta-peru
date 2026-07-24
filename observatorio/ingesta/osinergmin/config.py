# observatorio/ingesta/osinergmin/config.py
"""Constantes del scraper de precios de combustible de Facilito (OSINERGMIN).

La fuente es el buscador de Estaciones de Servicio (EESS) de Facilito:
    https://www.facilito.gob.pe/facilito/pages/facilito/buscadorEESS.jsp

El sitio está protegido con reCAPTCHA v3 (token minado por JS en cada carga de
página), así que la navegación se hace con navegador headless (Playwright) en
``client.py`` — no con ``requests``. Aquí viven solo las constantes estables.

Los códigos de departamento y producto se leyeron del ``<select>`` del propio
formulario (junio 2026). Las **provincias** NO se hardcodean: se descubren en
vivo leyendo el select tras elegir el departamento (varían y cambian de tamaño).
"""

from __future__ import annotations

URL_BUSCADOR = "https://www.facilito.gob.pe/facilito/pages/facilito/buscadorEESS.jsp"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Código Facilito → nombre del departamento (25 + Callao). El código es el value
# del <option> en el <select name="Departamento">.
DEPARTAMENTOS: dict[str, str] = {
    "10000": "AMAZONAS",
    "20000": "ANCASH",
    "30000": "APURIMAC",
    "40000": "AREQUIPA",
    "50000": "AYACUCHO",
    "60000": "CAJAMARCA",
    "70000": "PROV. CONST. DEL CALLAO",
    "80000": "CUSCO",
    "90000": "HUANCAVELICA",
    "100000": "HUANUCO",
    "110000": "ICA",
    "120000": "JUNIN",
    "130000": "LA LIBERTAD",
    "140000": "LAMBAYEQUE",
    "150000": "LIMA",
    "160000": "LORETO",
    "170000": "MADRE DE DIOS",
    "180000": "MOQUEGUA",
    "190000": "PASCO",
    "200000": "PIURA",
    "210000": "PUNO",
    "220000": "SAN MARTIN",
    "230000": "TACNA",
    "240000": "TUMBES",
    "250000": "UCAYALI",
}

# Código Facilito → nombre del producto (combustible automotor líquido).
# GNV y GLP automotor se consultan en buscadores aparte (posible follow-up).
PRODUCTOS: dict[str, str] = {
    "126": "Gasohol Regular",
    "127": "Gasohol Premium",
    "40": "DB5 S-50 UV",
}

# Valores "placeholder" de los <select> que no son una selección real.
VALORES_VACIOS = {"", "#", "9999999"}
