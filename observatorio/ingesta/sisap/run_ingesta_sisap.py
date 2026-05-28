# observatorio/ingesta/sisap/run_ingesta_sisap.py

import os
import sys
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# Importación absoluta oficial del monorepo
from observatorio.ingesta.sisap.config import PRODUCTOS_CANASTA_BASICA

URL_SISAP = "http://sistemas.midagri.gob.pe/sisap/portal2/ciudades/resumenes/filtrar"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-ES,es;q=0.8"
}

def configurar_sesion_resiliente():
    """Configura una sesión con reintentos automáticos e incrementos de tiempo."""
    session = requests.Session()
    estrategia_reintentos = Retry(
        total=5,                          # Reintenta hasta 5 veces antes de morir
        backoff_factor=3,                 # Esperas inteligentes: 3s, 6s, 12s, 24s...
        status_forcelist=[500, 502, 503, 504], # Reintenta si el servidor da estos errores
        raise_on_status=False
    )
    adaptador = HTTPAdapter(max_retries=estrategia_reintentos)
    session.mount("http://", adaptador)
    session.mount("https://", adaptador)
    return session

def ejecutar_ingesta_diaria():
    # Sincronización horaria: GitHub corre en UTC-0. Restamos 5 horas para Perú (UTC-5)
    hora_peru = datetime.utcnow() - timedelta(hours=5)
    
    str_fecha = hora_peru.strftime("%d/%m/%Y")
    str_archivo = hora_peru.strftime("%Y-%m-%d")
    
    # 💡 AJUSTE TÉCNICO: 'desde' al inicio de mes, 'hasta' fijado exactamente al día de hoy
    str_desde = hora_peru.replace(day=1).strftime("%d/%m/%Y")
    str_hasta = str_fecha  
    
    print(f"🚀 Iniciando Pipeline Bronze Resiliente - SISAP")
    print(f"📅 Fecha objetivo Perú: {str_fecha}")
    print(f"📊 Parámetros indexados: Desde {str_desde} hasta {str_hasta}")
    
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
    
    ruta_salida = os.path.join(os.path.dirname(__file__), "output_bronze_sisap")
    os.makedirs(ruta_salida, exist_ok=True)
    
    cliente = configurar_sesion_resiliente()
    
    try:
        print(f"📡 Solicitando {len(PRODUCTOS_CANASTA_BASICA)} categorías padre al MIDAGRI...")
        # (Timeout de conexión, Timeout de lectura de datos)
        response = cliente.get(URL_SISAP, params=mix_params, headers=HEADERS, timeout=(15, 45))
        response.raise_for_status()
        
        html_content = response.text
        soup = BeautifulSoup(html_content, 'html.parser')
        filas = soup.find_all('tr', class_='contenido')
        
        if filas:
            nombre_archivo = f"{str_archivo}_sisap_lima.html"
            ruta_completa = os.path.join(ruta_salida, nombre_archivo)
            
            with open(ruta_completa, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            print(f"✅ ¡Descarga completada de forma exitosa!")
            print(f"💾 Archivo Bronze temporal salvado: {nombre_archivo} ({len(filas)} filas)")
            
            print("\n🔍 Muestra de control visual en los logs (Data Quality Checks):")
            for fila in filas[:3]:
                columnas = fila.find_all('td')
                if columnas:
                    print(f"  -> 📦 {columnas[0].text.strip():<35} | 💰 S/. {columnas[3].text.strip()}")
        else:
            print(f"⚠️ El servidor respondió con éxito pero la tabla vino vacía.")
            print(f"ℹ️ Diagnóstico: Parámetros validados. Aún no hay actualización pública en el SISAP a esta hora.")
            
    except requests.exceptions.RequestException as e:
        print(f"🚨 Error crítico insuperable tras agotar la política de reintentos: {e}")
        sys.exit(1)

if __name__ == "__main__":
    ejecutar_ingesta_diaria()