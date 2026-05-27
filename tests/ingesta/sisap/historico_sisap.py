import os
import time
import requests
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from config import PRODUCTOS_CANASTA_BASICA

def descargar_historico_corregido():
    url = "http://sistemas.midagri.gob.pe/sisap/portal2/ciudades/resumenes/filtrar"
    
    # Rango de prueba de 30 días sugerido por tus logs
    fecha_final = datetime.now()
    fecha_inicial = fecha_final - timedelta(days=10)
    
    ruta_destino = os.path.join(os.path.dirname(__file__), "datos_historicos")
    os.makedirs(ruta_destino, exist_ok=True)
    
    payload_productos = [("productos[]", pid) for pid in PRODUCTOS_CANASTA_BASICA]
    
    # Headers completos para parecer un navegador real en un 100%
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-ES,es;q=0.8"
    }
    
    fecha_actual = fecha_inicial
    print(f"📅 Iniciando descarga histórica indexada desde {fecha_inicial.strftime('%d/%m/%Y')} hasta {fecha_final.strftime('%d/%m/%Y')}...")
    
    while fecha_actual <= fecha_final:
        str_fecha = fecha_actual.strftime("%d/%m/%Y")
        str_archivo = fecha_actual.strftime("%Y-%m-%d")
        
        # 💡 SOLUCIÓN AL RANGO: 
        # 'desde' DEBE ser el primer día del mes actual consultado
        str_desde = fecha_actual.replace(day=1).strftime("%d/%m/%Y")
        # 'hasta' DEBE ser al menos el mismo día consultado o el día siguiente
        str_hasta = (fecha_actual + timedelta(days=1)).strftime("%d/%m/%Y")
        
        params = {
            "region": "150000",
            "variables[]": "min_precio_prom",
            "fecha": str_fecha,    # El día clave que queremos capturar
            "desde": str_desde,    # Primer día del mes (Fijo según el navegador)
            "hasta": str_hasta,    # Control de borde superior
            "anios[]": fecha_actual.strftime("%Y"),
            "meses[]": fecha_actual.strftime("%m"),
            "periodicidad": "dia",
            "__ajax_carga_final": "consulta",
            "ajax": "true"
        }
        
        print(f"⏳ Consultando fecha: {str_fecha} (Rango simulado: {str_desde} al {str_hasta})...")
        
        try:
            mix_params = list(params.items()) + payload_productos
            
            # Aumentamos el timeout a 40 segundos porque el servidor es lento procesando los rangos
            response = requests.get(url, params=mix_params, headers=headers, timeout=40)
            response.raise_for_status()
            
            html_content = response.text
            
            soup = BeautifulSoup(html_content, 'html.parser')
            filas = soup.find_all('tr', class_='contenido')
            
            if filas:
                nombre_archivo = f"{str_archivo}_sisap_lima.html"
                ruta_completa = os.path.join(ruta_destino, nombre_archivo)
                
                with open(ruta_completa, "w", encoding="utf-8") as f:
                    f.write(html_content)
                print(f"   ✅ ¡Éxito! Guardado con {len(filas)} productos.")
            else:
                # Si sigue saliendo vacío, imprimimos un trozo para auditar qué nos dice el MIDAGRI
                print(f"   ⚠️ Contenido vacío. El servidor rechazó los parámetros para esta fecha.")
                
        except requests.exceptions.Timeout:
            print(f"   🚨 Timeout en {str_fecha}. El servidor del MIDAGRI está saturado. Saltando...")
        except requests.exceptions.RequestException as e:
            print(f"   🚨 Error de red en {str_fecha}: {e}")
        
        # 🟢 Aumentamos el delay a 3 segundos para evitar que la IP termine bloqueada
        # o que tire errores de conexión intermitentes
        time.sleep(3.0)
        
        fecha_actual += timedelta(days=1)

    print("\n🏁 Proceso de prueba histórica finalizado.")

if __name__ == "__main__":
    descargar_historico_corregido()