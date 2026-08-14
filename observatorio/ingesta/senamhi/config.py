"""Constantes del scraper de clima diario de SENAMHI (issue #14).

La fuente es el visor de estaciones de SENAMHI. El spike de factibilidad (ver
docs/sources.md §SENAMHI) confirmó que **no hay Cloudflare Turnstile ni login en
las rutas de datos** (el challenge está solo en el mapa interactivo), así que la
ingesta es `requests` puro — no navega con headless browser como OSINERGMIN.

Dos piezas:
  1. **Catálogo** de estaciones: embebido como `var PruebaTest = [...]` en el HTML
     de ``URL_MAPA``. Trae cod, nombre, lat/lon, categoría, estado y tipo (ico).
  2. **Serie por estación**: ``URL_SERIE`` (``map_red_graf.php``) devuelve HTML con
     las series Highcharts (precipitación, temp máx/mín) — se parsea aparte.

El portal comparte con INEI la **cadena TLS incompleta**, así que las descargas
usan ``verify=False`` (solo datos públicos). Y geo-bloquea IPs de datacenter igual
que MIDAGRI/INEI ⇒ corre en el **self-hosted runner** con IP peruana.
"""

from __future__ import annotations

# HTML del mapa de estaciones: contiene el catálogo completo (`var PruebaTest`).
URL_MAPA = "https://www.senamhi.gob.pe/mapas/mapa-estaciones-2/"

# Serie diaria por estación (HTML con Highcharts). Parámetros descubiertos en el JS
# del mapa: cod, estado, tipo_esta (ico), cate, cod_old.
URL_SERIE = "https://www.senamhi.gob.pe/mapas/mapa-estaciones-2/map_red_graf.php"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Timeout (connect, read) en segundos. La infra estatal es intermitente.
TIMEOUT = (15, 45)

# --------------------------------------------------------------------------- #
# Filtros del subset curado (issue #14).
# --------------------------------------------------------------------------- #
# El observatorio correlaciona clima con precios de la canasta, así que solo
# interesan estaciones **meteorológicas** (no hidrológicas) con **dato fresco**.
#
# `estado` en el catálogo: AUTOMATICA / REAL entregan dato reciente; DIFERIDO es
# histórico rezagado (a veces años). Nos quedamos con las dos primeras.
ESTADOS_FRESCOS = frozenset({"AUTOMATICA", "REAL"})

# `ico` en el catálogo: "M" = meteorológica (precip/temp), "H" = hidrológica (ríos).
TIPO_METEOROLOGICA = "M"

# Regiones productoras de la canasta MVP (papa, limón, pollo, cebolla, huevo,
# tomate) + Lima como polo de consumo (donde SISAP mide precios). Cada una es un
# bounding-box (lat_min, lat_max, lon_min, lon_max) en grados decimales; el
# catálogo no trae departamento, solo lat/lon, así que se filtra por caja.
# Coordenadas de Perú: lat ∈ [-18.4, 0], lon ∈ [-81.4, -68.7]. Cajas generosas y
# fáciles de afinar; una estación cuenta si cae en CUALQUIERA.
REGIONES_PRODUCTORAS: dict[str, tuple[float, float, float, float]] = {
    # Lima Metropolitana + valles de Lima (consumo; cruza con precios SISAP Lima).
    "lima": (-13.1, -10.3, -77.9, -76.0),
    # Ica (cebolla, tomate, hortalizas de costa sur-centro).
    "ica": (-15.5, -13.0, -76.4, -74.8),
    # Arequipa: valles de Camaná/Majes (cebolla, ajo, hortalizas).
    "arequipa": (-17.4, -14.5, -74.5, -71.0),
    # La Libertad: valles de Trujillo/Virú (hortalizas, avicultura).
    "la_libertad": (-8.7, -7.0, -79.6, -77.5),
    # Piura-Lambayeque: limón y cítricos del norte.
    "piura_lambayeque": (-7.2, -4.0, -81.4, -79.2),
    # Sierra central productora de papa (Junín, Huánuco, Pasco, Huancavelica).
    "sierra_central": (-13.2, -9.3, -76.5, -74.2),
    # Altiplano productor de papa (Puno, Cusco).
    "altiplano": (-17.3, -12.9, -71.6, -68.9),
}
