# Resumen de Sesión: Conexión Segura con Supabase

## 📌 Datos de la Issue

* **Nombre de la Tarea:** Crear cuenta Supabase + probar conexión Python
* **Ubicación en el Monorepo:** `observatorio/conexion/`
* **Estado:** 🟢 EXITOSO / CERRADO

---

### 📚 Librerías de Python Importadas

* **`supabase`** (`from supabase import create_client, Client`): Cliente oficial de Supabase para Python. Se encarga de gestionar la autenticación por tokens JWT y de interactuar de forma nativa con el backend de PostgREST en la nube.
* **`dotenv`** (`from dotenv import load_dotenv`): Permite cargar configuraciones dinámicas y credenciales desde un archivo físico `.env` en entornos de desarrollo local.

## 🛠️ Hitos y Pasos Técnicos Realizados

### 1. Configuración de la Región e Infraestructura

* **Ubicación Estratégica:** Se seleccionó la región **East US (Ohio) — `us-east-2`** en la consola de Supabase. Esta configuración reduce la latencia en las consultas debido a que los runners virtuales de GitHub Actions operan principalmente en centros de datos de Estados Unidos.

* **Solución de DNS:** Al presentarse un error inicial `[Errno 11001] getaddrinfo failed`, se identificó que la URL apuntaba al subdominio nativo de Postgres (`db.xyz...`). Se corrigió removiendo el prefijo `db.`, enlazando el cliente de Python directamente al endpoint de la API REST pública de Supabase.

* **Centralización del Módulo:** Se estableció que el código de conexión residirá en `observatorio/conexion/`. De esta forma, las futuras capas de transformación (Silver/Gold) y los modelos de Machine Learning reutilizarán el mismo cliente evitando duplicidad de código.

### 2. Validación de Conexión en Frío (Handshake Puro)

* **Principio de Diseño:** Con el fin de validar el canal y mantener la base de datos 100% limpia y vacía en esta fase preliminar, se descartó la inserción de registros de prueba o creación de esquemas relacionales.

* **Simulación de Control:** Se programó una consulta intencional a una tabla inexistente (`supabase.table("tabla_inexistente_test").select("*")`). El motor de Supabase respondió con un código de error controlado **`PGRST205`**.

* **Diagnóstico de Éxito:** Recibir el código `PGRST205` certifica de forma empírica que la clave `SUPABASE_KEY` (token JWT) pasó el muro de seguridad criptográfico de la API. El servidor procesó la solicitud legítimamente y denegó el acceso únicamente porque el objeto no existe en su caché, garantizando una conexión funcional y bidireccional.

### 3. Arquitectura de Credenciales para GitHub Actions

* **Seguridad del Repositorio:** El archivo `.env` se mantiene estrictamente local y registrado en `.gitignore` para salvaguardar las contraseñas del acceso público.

* **Manejo Híbrido en Python:** El cargador de código se estructuró de forma adaptativa para trabajar en dos entornos:
  * **En Local:** La función `load_dotenv()` lee y carga las variables directamente desde el archivo físico `.env`.
  * **En GitHub Actions:** Al no existir un archivo `.env` en la nube, `load_dotenv()` omite el paso amigablemente y Python captura los accesos de la memoria virtual del sistema operativo a través de `os.getenv()`.

* **Configuración en la Nube:** Las credenciales se registran en la interfaz web de GitHub como **Repository Secrets** (`Settings ➡️ Secrets and variables ➡️ Actions`). El flujo de automatización en el archivo `.yml` se encargará de inyectar estas claves directamente al entorno durante la ejecución diaria de la ingesta.
