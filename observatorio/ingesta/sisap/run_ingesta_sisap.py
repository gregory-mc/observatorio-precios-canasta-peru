# observatorio/ingesta/sisap/run_ingesta_sisap.py

import os
import sys
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

# 🎯 IMPORTACIÓN ABSOLUTA: Garantiza que GitHub Actions encuentre el archivo desde la raíz
from observatorio.ingesta.sisap.config import PRODUCTOS_CANASTA_BASICA

URL_SISAP = "http://sistemas.midagri.gob.pe/sisap/portal2/ciudades/resumenes/filtrar"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
}

def ejecutar_ingesta_diaria():
    # 💡 GitHub Actions corre en UTC-0. Restamos 5 horas para tener la hora oficial de Perú (UTC-5)
    hora_peru = datetime.utcnow() - timedelta(hours=5)
    
    str_fecha = hora_peru.strftime("%d/%m/%Y")
    str_archivo = hora_peru.strftime("%Y-%m-%d")
    
    # Aplicamos tu regla de oro: 'desde' al inicio de mes para que el SISAP responda con datos
    str_desde = hora_peru.replace(day=1).strftime("%d/%m/%Y")
    str_hasta = (hora_peru + timedelta(days=1)).strftime("%d/%m/%Y")
    
    print(f"🚀 Iniciando Pipeline Bronze - SISAP")
    print(f"📅 Fecha objetivo Perú: {str_fecha}")
    print(f"📊 Rango indexado: Desde {str_desde} hasta {str_hasta}")
    
    params = {
        "region": "150000",
        "variables[]": "min_precio_prom",
        "fecha": str_fecha,
        "desde": str_desde,
        "hasta": str_hasta,
        "anios[]": hora_peru.strftime("%Y"),
        "meses[]": hora_peru.strftime("%m"),
        "periodicidad": "dia",
        "__ajax_carga_final": "consulta",
        "ajax": "true"
    }
    
    payload_productos = [("productos[]", pid) for pid in PRODUCTOS_CANASTA_BASICA]
    mix_params = list(params.items()) + payload_productos
    
    # Creamos la carpeta de salida dentro de la misma estructura para empaquetarla como artefacto
    ruta_salida = os.path.join(os.path.dirname(__file__), "output_bronze_sisap")
    os.makedirs(ruta_salida, exist_ok=True)
    
    try:
        print(f"📡 Solicitando {len(PRODUCTOS_CANASTA_BASICA)} categorías padre al MIDAGRI...")
        response = requests.get(URL_SISAP, params=mix_params, headers=HEADERS, timeout=40)
        response.raise_for_status()
        
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        filas = soup.find_all('tr', class_='contenido')
        
        if filas:
            nombre_archivo = f"{str_archivo}_sisap_lima.html"
            ruta_completa = os.path.join(ruta_salida, nombre_archivo)
            
            with open(ruta_completa, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            print(f"✅ ¡Descarga Bronze exitosa!")
            print(f"💾 Archivo guardado en el runner: {nombre_archivo} ({len(filas)} filas)")
            
            # Control de calidad visual en los logs de GitHub
            print("\n🔍 Muestra de control rápido (Data Quality):")
            for fila in filas[:3]:
                columnas = fila.find_all('td')
                if columnas:
                    print(f"  -> 📦 {columnas[0].text.strip():<35} | 💰 S/. {columnas[3].text.strip()}")
        else:
            print(f"⚠️ El servidor respondió pero la tabla vino vacía. Es posible que el MIDAGRI aún no actualice hoy.")
            
    except requests.exceptions.RequestException as e:
        print(f"🚨 Error crítico en la descarga: {e}")
        sys.exit(1) # Provoca que la GitHub Action se ponga en rojo si falla

if __name__ == "__main__":
    ejecutar_ingesta_diaria()