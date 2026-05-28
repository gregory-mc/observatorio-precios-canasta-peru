# observatorio/ingesta/sisap/run_ingesta_sisap.py

import os
import sys
import time
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# Importación absoluta del monorepo
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
        total=3,                          
        backoff_factor=2,                 
        status_forcelist=[500, 502, 503, 504], 
        raise_on_status=False
    )
    adaptador = HTTPAdapter(max_retries=estrategia_reintentos)
    session.mount("http://", adaptador)
    session.mount("https://", adaptador)
    return session

def segmentar_lista(lista, tamaño_lote):
    """Divide la lista de productos en bloques más pequeños."""
    for i in range(0, len(lista), tamaño_lote):
        yield lista[i:i + tamaño_lote]

def ejecutar_ingesta_diaria():
    # Sincronización horaria con Perú (UTC-5)
    hora_peru = datetime.utcnow() - timedelta(hours=5)
    
    str_fecha = hora_peru.strftime("%d/%m/%Y")
    str_archivo = hora_peru.strftime("%Y-%m-%d")
    
    str_desde = hora_peru.replace(day=1).strftime("%d/%m/%Y")
    str_hasta = str_fecha  
    
    print(f"🚀 Iniciando Pipeline Bronze Segmentado - SISAP")
    print(f"📅 Fecha objetivo Perú: {str_fecha}")
    print(f"📊 Parámetros indexados: Desde {str_desde} hasta {str_hasta}")
    
    ruta_salida = os.path.join(os.path.dirname(__file__), "output_bronze_sisap")
    os.makedirs(ruta_salida, exist_ok=True)
    
    # 🧱 Segmentamos los 51 productos en lotes de 5 para no saturar los filtros de la URL
    lotes_productos = list(segmentar_lista(PRODUCTOS_CANASTA_BASICA, tamaño_lote=5))
    print(f"📦 Se dividió el catálogo maestro en {len(lotes_productos)} lotes de consulta secuencial.")
    
    cliente = configurar_sesion_resiliente()
    html_consolidado = ""
    total_filas_capturadas = 0
    
    # Iniciamos el bucle por lotes
    for indice, lote in enumerate(lotes_productos, start=1):
        print(f"   ⏳ Solicitando Lote {indice}/{len(lotes_productos)}: {lote}...")
        
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
        
        payload_productos = [("productos[]", pid) for pid in lote]
        mix_params = list(params.items()) + payload_productos
        
        try:
            response = cliente.get(URL_SISAP, params=mix_params, headers=HEADERS, timeout=(10, 30))
            response.raise_for_status()
            
            # Validamos si este lote trajo filas reales
            soup = BeautifulSoup(response.text, 'html.parser')
            filas = soup.find_all('tr', class_='contenido')
            
            if filas:
                html_consolidado += response.text + "\n"
                total_filas_capturadas += len(filas)
                print(f"      ✅ Éxito: Se recuperaron {len(filas)} productos.")
            else:
                print(f"      ⚠️ Lote vacío: El servidor no reportó datos para este grupo hoy.")
                
        except requests.exceptions.RequestException as e:
            print(f"      🚨 Fallo de conexión en lote {indice}: {e}. Saltando al siguiente bloque...")
        
        # ⏱️ Pausa obligatoria de cortesía de 2.5 segundos para camuflar la ráfaga de red
        time.sleep(2.5)
        
    # Guardamos el HTML unificado final si logramos capturar información
    if total_filas_capturadas > 0:
        nombre_archivo = f"{str_archivo}_sisap_lima.html"
        ruta_completa = os.path.join(ruta_salida, nombre_archivo)
        
        with open(ruta_completa, "w", encoding="utf-8") as f:
            f.write(html_consolidado)
            
        print(f"\n🏁 Pipeline finalizado con éxito.")
        print(f"💾 Artefacto unificado guardado: {nombre_archivo} ({total_filas_capturadas} productos totales en Bronze)")
    else:
        print(f"\n⚠️ Alerta: El proceso terminó pero no se recolectaron filas en ningún lote hoy.")
        print("ℹ️ Diagnóstico: El MIDAGRI aún no cuelga el reporte minorista oficial en su plataforma web.")

if __name__ == "__main__":
    ejecutar_ingesta_diaria()