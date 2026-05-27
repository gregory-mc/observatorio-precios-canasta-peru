# Documentación de Ingesta: SISAP (MIDAGRI) y Automatización con GitHub Actions

## 📝 Descripción del Componente

Este componente automatiza la recolección diaria de datos macro de precios de la canasta básica familiar en mercados minoristas de Lima, correspondientes al **Sistema de Información de Abastecimiento y Precios (SISAP)** del Ministerio de Desarrollo Agrario y Riego (MIDAGRI). Los archivos recolectados se integran como el punto de partida crudo para la arquitectura **Medallion (Capa Bronze)** del observatorio.

---

### 📚 Librerías de Python Importadas

* **`requests`** (`import requests`): Cliente HTTP estándar para Python, encargado de gestionar la comunicación directa con el portal web. En este módulo, transmite los encabezados (*Headers*) de simulación y el listado de parámetros en formato de tuplas para forzar la descarga de los fragmentos de datos crudos del MIDAGRI. Además, permite establecer un control estricto de tiempos de espera (`timeout=40`) para evitar que el proceso se quede congelado ante caídas o saturaciones de la infraestructura estatal.

* **`beautifulsoup4`** (`from bs4 import BeautifulSoup`): Biblioteca especializada en la extracción, exploración y navegación de estructuras de datos dentro de archivos HTML y XML. Actúa como el motor de raspado (*scraping*) encargado de procesar el bloque de código de respuesta devuelto por la petición AJAX del SISAP. Se utiliza específicamente para aislar las filas de la tabla minorista bajo la clase de estilos `.contenido` y extraer los precios correspondientes.

## 🏗️ Decisiones de Arquitectura e Infraestructura

### 1. Ingesta Iterativa en Bloques Diarios (Backfill Seguro)

* **Desafío técnico:** El backend del SISAP procesa los rangos mensuales expandiendo el HTML de forma matricial (una columna por día), elevando la complejidad del parseo. Además, la infraestructura estatal sufre intermitencias e imprevistos (*Read Timeouts*) ante ráfagas continuas de peticiones.

* **Solución implementada:** Se diseñó una extracción iterativa secuencial día por día. Esto garantiza archivos `.html` independientes por fecha, facilita de forma nativa auditorías puntuales y asegura la tolerancia a fallos en cargas históricas masivas.

### 2. Simulación de Navegador y Regla de Rango Indexado

* **Anatomía de la URL:** Se descubrió que el backend AJAX parcial del MIDAGRI requiere obligatoriamente que el parámetro `desde` apunte al **primer día del mes actual consultado** y `hasta` mapee al menos el día posterior, de lo contrario devuelve esquemas de tablas vacíos. El orquestador de producción (`run_ingesta_sisap.py`) calcula dinámicamente estas variables adaptándose a la zona horaria de ejecución.

### 3. Modularización y Simetría del Monorepo

* La lógica de producción del sector público se aisló por completo en la ruta dedicada `observatorio/ingesta/sisap/`, manteniendo una simetría arquitectónica exacta con el módulo hermano enfocado en supermercados (`observatorio/ingesta/marketplace/`).

---

## ⚙️ Configuración de Scripts de Producción

### 1. Catálogo Maestro Dinámico (`observatorio/ingesta/sisap/config.py`)

Utiliza un filtro optimizado por comprensión de listas (`len(cid) == 4`) para inyectar exclusivamente los identificadores de categorías macro (Padres). Esto reduce sustancialmente el tamaño de la cadena de consulta HTTP y automatiza el mapeo inverso de datos.

### 2. Orquestador de Descarga (`observatorio/ingesta/sisap/run_ingesta_sisap.py`)

* **Sincronización Horaria:** Sincroniza la zona horaria restando automáticamente 5 horas al reloj del servidor de GitHub (`UTC-0` a `UTC-5` Perú).
* **Inyección de Parámetros:** Estructura los parámetros mutables y los inyecta en formato de tuplas para simular de forma idéntica las solicitudes del navegador mediante la librería `requests`.
* **Calidad de Datos:** Controla la calidad de datos (*Data Quality*) imprimiendo un preview visual en consola y forzando una salida de error (`sys.exit(1)`) si el servidor devuelve respuestas anómalas o vacías, notificando el fallo de inmediato a GitHub Actions.

---

## 🤖 Automatización: Canal de GitHub Actions

El archivo `.github/workflows/ingesta-sisap.yml` levanta un entorno virtual aislado bajo **pip tradicional**, permitiendo que el proyecto se ejecute de manera automatizada y con cero costos de servidor.

### Especificaciones del Workflow

* **Frecuencia (Cron):** Configurado para ejecutarse de forma autónoma a las **07:30 AM UTC** (02:30 AM hora de Perú) todos los días, ventana horaria ideal para capturar las actualizaciones matutinas de los mercados regionales.
* **Workflow Dispatch:** Permite ejecuciones manuales bajo demanda desde la pestaña *Actions* de la interfaz web de GitHub para auditorías rápidas en frío.
* **Persistencia Temporal (Artefactos):** Los archivos crudos HTML recolectados por el runner se empaquetan y almacenan en la nube de GitHub como artefactos descargables (`snapshot-sisap-html`) con una política de retención segura de 3 días antes de su limpieza automática.

---

## 🏃‍♂️ Guía de Ejecución en Desarrollo Local

Para validar la consistencia del módulo SISAP en tu máquina local respetando el estándar del monorepo, activa tu entorno virtual `.venv`, sitúate en la **raíz del proyecto** y ejecuta el flag correspondiente:

```bash
# Probar la extracción y generación de archivos Bronze del SISAP desde la raíz del repo
python -m observatorio.ingesta.sisap.run_ingesta_sisap
```

El orquestador creará un directorio temporal local llamado output_bronze_sisap/ al mismo nivel de su ejecución, confirmando que la lógica responde correctamente antes de interactuar con GitHub Actions.

## 📁 Estructura Completa de Archivos

```text
observatorio-precios-canasta-peru/
├── .github/
│   └── workflows/
│       ├── ingesta-marketplace.yml  # Pipeline para sector supermercados
│       └── ingesta-sisap.yml        # Workflow de orquestación cron para el SISAP
├── observatorio/
│   ├── __init__.py
│   ├── conexion/
│   │   ├── __init__.py
│   │   └── test_supabase.py         # Script de validación de conectividad en frío (Handshake)
│   └── ingesta/
│       ├── __init__.py
│       ├── canasta_productos.json
│       ├── marketplace/             # Módulo de scraping para marketplace privado
│       └── sisap/
│           ├── __init__.py
│           ├── config.py            # Catálogo maestro dinámico con IDs de 4 dígitos
│           └── run_ingesta_sisap.py # Orquestador de producción para ingesta diaria
└── tests/
    └── ingesta/
        └── sisap/                   # Scripts aislados de experimentación local y backfill

