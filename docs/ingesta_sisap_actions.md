# Documentación de Ingesta: SISAP (MIDAGRI) y Automatización con GitHub Actions

## 📝 Descripción del Componente

Este componente automatiza la recolección diaria de datos macro de precios de la canasta básica familiar en mercados minoristas de Lima, correspondientes al **Sistema de Información de Abastecimiento y Precios (SISAP)** del Ministerio de Desarrollo Agrario y Riego (MIDAGRI). Los archivos recolectados se integran como el punto de partida crudo para la arquitectura **Medallion (Capa Bronze)** del observatorio.

---

### 📚 Librerías de Python Importadas

* **`requests`** (`import requests`): Cliente HTTP estándar para Python, encargado de gestionar la comunicación directa con el portal web. Transmite los encabezados (*Headers*) de simulación y el listado de parámetros en formato de tuplas. Incluye una sesión resiliente con política de reintentos automáticos ante errores 5xx del servidor estatal.

* **`beautifulsoup4`** (`from bs4 import BeautifulSoup`): Motor de raspado (*scraping*) que procesa la respuesta HTML del SISAP. Se utiliza para aislar las filas de la tabla minorista bajo la clase `.contenido` y extraer los precios correspondientes.

## 🏗️ Decisiones de Arquitectura e Infraestructura

### 1. Request Único con los 51 Productos

* **Comportamiento del SISAP:** El backend AJAX del MIDAGRI acepta sin problemas los 51 identificadores de producto en una sola petición HTTP. No existe limitación de payload por parte del servidor.

* **Solución implementada:** Un único `GET` con todos los productos inyectados como tuplas `("productos[]", pid)` en el payload. El timeout está configurado de forma independiente para conexión (15s) y lectura (45s), absorbiendo las intermitencias habituales de la infraestructura estatal.

### 2. Simulación de Navegador y Regla de Rango Indexado Estricto

* **Anatomía de la URL:** El backend AJAX parcial del MIDAGRI requiere que el parámetro `desde` apunte al **primer día del mes actual consultado**.

* **Control de Borde Superior:** Consultar fechas futuras provoca que el backend del SISAP devuelva un HTML limpio pero sin filas de datos (tabla vacía). El orquestador ajusta estrictamente los parámetros `fecha` y `hasta` apuntando en sincronía al día de hoy.

### 3. Geo-bloqueo del MIDAGRI y Solución con Self-Hosted Runner

* **Problema identificado:** El servidor `sistemas.midagri.gob.pe` bloquea a nivel de firewall las IPs de Microsoft Azure, que son las que usan los runners estándar de GitHub Actions (`ubuntu-latest`). Esto provocaba `ConnectTimeoutError` en el 100% de los requests, incluso con un solo producto en el payload.

* **Diagnóstico:** El servidor es accesible desde IPs peruanas (verificado con `Test-NetConnection` desde la PC local) pero inaccesible desde IPs de centros de datos extranjeros.

* **Solución implementada:** Se configuró un **self-hosted runner** en la PC de desarrollo local (con IP peruana). GitHub Actions delega la ejecución del workflow a esta máquina en lugar de los servidores de Azure, resolviendo el bloqueo sin costo adicional. El runner corre como servicio de Windows (`GitHubRunnerSISAP`) en segundo plano, arrancando automáticamente con el sistema operativo.

### 4. Modularización y Simetría del Monorepo

* La lógica de producción del sector público se aisló en `observatorio/ingesta/sisap/`, manteniendo simetría con el módulo de supermercados (`observatorio/ingesta/marketplace/`).

---

## ⚙️ Configuración de Scripts de Producción

### 1. Catálogo Maestro Dinámico (`observatorio/ingesta/sisap/config.py`)

Filtra exclusivamente los identificadores de categorías macro (`len(cid) == 4`), reduciendo el tamaño de la consulta HTTP y automatizando el mapeo inverso de datos.

### 2. Orquestador de Descarga (`observatorio/ingesta/sisap/run_ingesta_sisap.py`)

* **Sincronización Horaria:** Resta 5 horas al reloj UTC del runner para obtener la hora oficial de Perú (UTC-5).

* **Request Único:** Envía los 51 productos del catálogo en una sola petición con timeout `(15s conexión, 45s lectura)` y sesión resiliente con 3 reintentos y backoff de 2s ante errores 5xx.

* **Control de Calidad:** Valida que la respuesta contenga filas reales bajo `.contenido`. Si la tabla viene vacía, informa el diagnóstico sin abortar el workflow. Si hay error de red insuperable, finaliza con `sys.exit(1)`.

---

## 🤖 Automatización: Canal de GitHub Actions

El archivo `.github/workflows/ingesta_sisap.yml` ejecuta el pipeline en un **self-hosted runner** con IP peruana, resolviendo el geo-bloqueo del servidor del MIDAGRI.

### Especificaciones del Workflow

* **Runner:** `self-hosted` — PC de desarrollo local registrada como runner en GitHub. Corre como servicio de Windows (`GitHubRunnerSISAP`) en segundo plano, arrancando automáticamente al iniciar el sistema operativo sin necesidad de sesión abierta ni ventana visible.

* **Frecuencia (Cron):** `15:30 UTC` (10:30 AM hora de Perú) todos los días, ajustado al horario de encendido habitual de la máquina.

* **Workflow Dispatch:** Permite ejecuciones manuales bajo demanda desde la pestaña *Actions* de GitHub para auditorías rápidas.

* **Compatibilidad Windows:** El step de ejecución declara `shell: powershell` y usa `$env:PYTHONPATH` en lugar de `export`. La variable `PYTHONUTF8: "1"` fuerza codificación UTF-8 para soportar los emojis en los logs de consola.

* **Persistencia (Artefactos):** El HTML crudo generado en `output_bronze_sisap/` se empaqueta y sube a GitHub como artefacto descargable (`snapshot-sisap-html`) con retención de 3 días.

---

## 🏃‍♂️ Guía de Ejecución en Desarrollo Local

Activa tu entorno virtual `.venv`, sitúate en la raíz del proyecto y ejecuta:

```bash
python -m observatorio.ingesta.sisap.run_ingesta_sisap
```

El orquestador creará el directorio `output_bronze_sisap/` al mismo nivel del script con el HTML del día.

## 📁 Estructura Completa de Archivos

```text
observatorio-precios-canasta-peru/
├── .github/
│   └── workflows/
│       ├── ingesta-marketplace.yml  # Pipeline para sector supermercados
│       └── ingesta_sisap.yml        # Workflow cron con self-hosted runner
├── observatorio/
│   ├── __init__.py
│   ├── conexion/
│   │   ├── __init__.py
│   │   └── test_supabase.py         # Validación de conectividad Supabase
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
        └── sisap/                   # Scripts aislados de experimentación y backfill
```
