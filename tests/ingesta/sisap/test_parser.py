import os
import requests
from bs4 import BeautifulSoup

# Importamos la lista de IDs desde nuestro archivo de configuración
from config import PRODUCTOS_CANASTA_BASICA


def ejecutar_extraccion_completa():
    url = "http://sistemas.midagri.gob.pe/sisap/portal2/ciudades/resumenes/filtrar"

    # Parámetros base del 25/05/2026
    params = {
        "region": "150000",
        "variables[]": "min_precio_prom",
        "fecha": "25/05/2026",
        "desde": "01/05/2026",
        "hasta": "26/05/2026",
        "anios[]": "2026",
        "meses[]": "05",
        "periodicidad": "dia",
        "__ajax_carga_final": "consulta",
        "ajax": "true",
    }

    # IMPORTANTE: Para enviar múltiples parámetros con la misma llave (productos[]=ID)
    # en una petición GET de la librería 'requests', se pasa una lista de tuplas o un diccionario modificado.
    # Requests se encargará de serializarlo como: productos[]=1001&productos[]=1018...
    payload_productos = [("productos[]", pid) for pid in PRODUCTOS_CANASTA_BASICA]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    print(
        f"🛰️ Enviando petición al SISAP incluyendo {len(PRODUCTOS_CANASTA_BASICA)} IDs de productos..."
    )
    try:
        # Pasamos los parámetros base y extendemos con la lista de tuplas de productos
        response = requests.get(
            url, params=list(params.items()) + payload_productos, headers=headers, timeout=30
        )
        response.raise_for_status()
        html_content = response.text

        # Guardado del HTML real completo en la capa Bronze simulada
        ruta_guardado = os.path.join(os.path.dirname(__file__), "resultado.html")
        with open(ruta_guardado, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"💾 HTML completo respaldado localmente en: {ruta_guardado}")

        # Parseo e impresión limpia en consola (Simulación Capa Silver)
        soup = BeautifulSoup(html_content, "html.parser")
        filas = soup.find_all("tr", class_="contenido")

        print(f"\n✅ ¡Éxito! El servidor devolvió {len(filas)} registros de productos válidos.")
        print("=" * 75)

        for fila in filas:
            columnas = fila.find_all("td")
            if len(columnas) >= 4:
                nombre = columnas[0].text.strip()
                unidad = columnas[1].text.strip() if columnas[1].text.strip() else "Vacío"
                precio_raw = columnas[3].text.strip()

                precio_str = f"S/. {precio_raw}" if precio_raw else "SIN PRECIO (NULL)"
                print(f"📦 {nombre:<40} | 📏 {unidad:<10} | 💰 {precio_str}")

    except requests.exceptions.RequestException as e:
        print(f"🚨 Error durante la ejecución del pipeline local: {e}")


if __name__ == "__main__":
    ejecutar_extraccion_completa()
