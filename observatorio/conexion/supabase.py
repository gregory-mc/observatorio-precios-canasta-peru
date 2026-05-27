import os
from dotenv import load_dotenv
from supabase import create_client, Client

# 1. Intentar cargar el archivo .env si existe localmente.
# Si el archivo no existe (como en GitHub Actions), load_dotenv simplemente lo ignora.
load_dotenv()

# 2. os.getenv busca primero en las variables del sistema (inyectadas por GitHub)
# y si no están ahí, revisa lo que cargó el archivo .env local.
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Error Crítico: No se detectaron las credenciales de Supabase en el sistema.")
    exit(1)

def conectar_supabase():
    # Inicialización limpia usando las variables recuperadas
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase