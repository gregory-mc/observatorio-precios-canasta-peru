import os
from dotenv import load_dotenv
from supabase import create_client, Client

# 1. Cargar las variables del archivo .env localizado en la raíz
ruta_env = os.path.join(os.path.dirname(__file__), "../../.env")
load_dotenv(dotenv_path=ruta_env)

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Error: No se encontraron las credenciales en el archivo .env")
    exit(1)

def verificar_handshake_definitivo():
    print("🔌 Intentando handshake final con Supabase en observatorio/conexion/...")
    try:
        # 2. Inicializar el cliente oficial
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        
        # 3. Consulta REST segura sobre un objeto inexistente
        # PostgREST validará la sesión JWT. Si las llaves están bien, devolverá [] (vacío)
        print("🔑 Validando llaves de API y comunicación en frío...")
        respuesta = supabase.table("tabla_inexistente_test").select("*").limit(1).execute()
        
    except Exception as e:
        error_msg = str(e)
        
        # Si el error contiene código de tabla no encontrada, significa que pasamos el muro de autenticación
        if "PGRST116" in error_msg or "does not exist" in error_msg or "not found" in error_msg.lower():
            print("\n✅ ¡HANDSHAKE EXITOSO!")
            print("🚀 Python se conectó a Supabase correctamente y validó el token JWT.")
            print("💡 La nube respondió de inmediato. Confirmado: la base de datos sigue 100% limpia.")
            return

        print("\n❌ Falló el intento de conexión:")
        if "401" in error_msg or "Invalid API key" in error_msg:
            print("👉 Diagnóstico: La 'SUPABASE_KEY' o el 'SUPABASE_URL' en tu archivo .env son incorrectos.")
        else:
            print(f"👉 Detalle del error: {error_msg}")

if __name__ == "__main__":
    verificar_handshake_definitivo()