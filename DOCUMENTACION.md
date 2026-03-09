# Proyecto RH — Documentación Técnica Completa

> **Versión:** 0.1.0  
> **Última actualización:** 8 de marzo de 2026  
> **Stack:** Python 3.10+ · Flet 0.82 · PostgreSQL · Google Gemini API · Microsoft Graph API

---

## Índice

1. [Descripción General](#1-descripción-general)
2. [Arquitectura del Sistema](#2-arquitectura-del-sistema)
3. [Estructura del Proyecto](#3-estructura-del-proyecto)
4. [Dependencias](#4-dependencias)
5. [Instalación y Ejecución](#5-instalación-y-ejecución)
6. [Módulo: database.py — Capa de Datos](#6-módulo-databasepy--capa-de-datos)
7. [Módulo: cv_converter.py — Procesamiento de CV](#7-módulo-cv_converterpy--procesamiento-de-cv)
8. [Módulo: email_manager.py — Integración Microsoft 365](#8-módulo-email_managerpy--integración-microsoft-365)
9. [Módulo: main.py — Interfaz de Usuario](#9-módulo-mainpy--interfaz-de-usuario)
10. [Flujos de Datos Principales](#10-flujos-de-datos-principales)
11. [Configuración de Servicios Externos](#11-configuración-de-servicios-externos)
12. [Consideraciones de Seguridad](#12-consideraciones-de-seguridad)
13. [Notas sobre Flet 0.82](#13-notas-sobre-flet-082)

---

## 1. Descripción General

**Proyecto RH** es un sistema integral de gestión de contratación y recursos humanos diseñado como aplicación de escritorio multiplataforma. Administra el ciclo completo del proceso de contratación:

- **Gestión de puestos** — Crear y administrar perfiles de puesto con requisitos, tecnologías y rangos salariales.
- **Gestión de candidatos** — Registro, seguimiento de estado y trazabilidad completa del proceso.
- **Recolección de documentos** — Lista de 14 documentos requeridos con seguimiento individual, solicitud automatizada por correo y recepción automática de adjuntos.
- **Conversión de CV** — Extracción de texto de PDF, procesamiento con IA (Gemini) y generación de CV en formato Entelgy.
- **Comunicación por correo** — Envío de solicitudes y monitoreo del buzón vía Microsoft Graph API.
- **Dashboard** — KPIs en tiempo real, distribución por estado, actividad reciente y candidatos pendientes.

---

## 2. Arquitectura del Sistema

```
┌─────────────────────────────────────────────────────────────┐
│                    INTERFAZ DE USUARIO                      │
│                  main.py (Flet 0.82)                        │
│  ┌──────┬───────────┬────────┬───────────┬────────┬──────┐  │
│  │Panel │Candidatos │Puestos │Convertidor│Bandeja │Config│  │
│  │(0)   │(1)        │(2)     │CV (3)     │(4)     │(5)   │  │
│  └──┬───┴─────┬─────┴───┬────┴─────┬─────┴───┬────┴──┬───┘  │
└─────┼─────────┼─────────┼──────────┼─────────┼───────┼──────┘
      │         │         │          │         │       │
┌─────▼─────────▼─────────▼──────────┼─────────┼───────┼──────┐
│           database.py              │         │       │      │
│        PostgreSQL (Railway)        │         │       │      │
│  ┌────────────┬──────────────┐     │         │       │      │
│  │configuracion│ candidatos  │     │         │       │      │
│  │puestos      │ documentos  │     │         │       │      │
│  │historial    │ correos     │     │         │       │      │
│  └────────────┴──────────────┘     │         │       │      │
└────────────────────────────────────┘         │       │      │
                                               │       │      │
┌──────────────────────────────────────────────▼───────┘      │
│            email_manager.py                                  │
│         Microsoft Graph API + MSAL                           │
│  ┌───────────────────────────────────────────┐              │
│  │ Device Code Flow · Envío/recepción correos│              │
│  │ Descarga de adjuntos · Auto-clasificación │              │
│  └───────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────┘
                                                       │
┌──────────────────────────────────────────────────────▼──────┐
│              cv_converter.py                                 │
│         Google Gemini API + fpdf2                            │
│  ┌───────────────────────────────────────────┐              │
│  │ Extracción PDF · Procesamiento IA ·       │              │
│  │ Generación PDF formato Entelgy            │              │
│  └───────────────────────────────────────────┘              │
└──────────────────────────────────────────────────────────────┘
```

| Capa | Tecnología | Responsabilidad |
|------|-----------|-----------------|
| **UI** | Flet 0.82 (Python) | GUI de escritorio multiplataforma, 6 secciones de navegación |
| **Lógica de negocio** | Python | Operaciones CRUD, generación de correos, procesamiento de CV |
| **Base de datos** | PostgreSQL (Railway) | Persistencia de candidatos, documentos, logs de auditoría, configuración |
| **Procesamiento CV** | Google Gemini API + fpdf2 | Texto no estructurado → JSON estructurado → PDF formateado |
| **Correo** | Microsoft Graph API + MSAL | Leer buzón de Outlook → descargar adjuntos → auto-marcar documentos |
| **Almacenamiento** | Sistema de archivos | Documentos de candidatos organizados en carpetas `XXXX_Apellidos_Nombre/` |

---

## 3. Estructura del Proyecto

```
Proyecto RH/
├── pyproject.toml              # Dependencias y configuración del proyecto
├── README.md                   # Guía básica de ejecución
├── DOCUMENTACION.md            # Este archivo
├── db_config.json              # Configuración local de conexión a BD (generado)
├── msal_token_cache.json       # Caché de tokens Microsoft (generado, NO versionar)
├── venv/                       # Entorno virtual de Python
└── src/
    ├── main.py                 # Aplicación principal Flet (2314 líneas)
    ├── database.py             # Capa de datos PostgreSQL (612 líneas)
    ├── cv_converter.py         # Procesamiento de CV con Gemini + fpdf2 (457 líneas)
    ├── email_manager.py        # Integración Microsoft 365 Graph API (541 líneas)
    └── assets/
        └── logo_entelgy.png    # Logo para encabezado de CV (opcional)
```

---

## 4. Dependencias

| Paquete | Versión | Propósito |
|---------|---------|-----------|
| `flet` | ≥0.82.0 | Framework de UI multiplataforma |
| `psycopg2-binary` | ≥2.9 | Driver de PostgreSQL |
| `pdfplumber` | ≥0.11 | Extracción de texto de archivos PDF |
| `google-genai` | ≥1.0 | Cliente de Google Gemini API |
| `fpdf2` | ≥2.8 | Generación de archivos PDF |
| `msal` | ≥1.28 | Autenticación Microsoft (MSAL / OAuth2) |
| `requests` | ≥2.31 | Cliente HTTP para Graph API |

**Dependencias de desarrollo:**

| Paquete | Propósito |
|---------|-----------|
| `flet-cli` | Herramienta CLI de Flet |
| `flet-desktop` | Runtime de escritorio |
| `flet-web` | Runtime web (opcional) |

---

## 5. Instalación y Ejecución

### Requisitos previos

- Python 3.10 o superior
- PostgreSQL accesible (local o remoto)
- Cuenta de Microsoft 365 (para funcionalidad de correo)
- API Key de Google Gemini (para conversión de CV)

### Instalación

```bash
# Clonar o descargar el proyecto
cd "Proyecto RH"

# Crear y activar entorno virtual
python -m venv venv
.\venv\Scripts\activate        # Windows
# source venv/bin/activate     # Linux/Mac

# Instalar dependencias
pip install flet psycopg2-binary pdfplumber google-genai fpdf2 msal requests
# O con uv:
uv sync
```

### Ejecución

```bash
# Como aplicación de escritorio
flet run src/main.py

# O directamente con Python
python src/main.py

# Como aplicación web (opcional)
flet run --web src/main.py
```

### Primera ejecución

1. La aplicación se abrirá directamente en la pestaña **Configuración** si no hay conexión a BD.
2. Configurar la conexión a PostgreSQL y hacer clic en **"Guardar y conectar"**.
3. La base de datos creará automáticamente las 6 tablas necesarias.
4. Configurar las credenciales de Gemini API (pestaña "API Gemini").
5. Configurar la ruta de almacenamiento de documentos (pestaña "Documentos").
6. (Opcional) Configurar Microsoft 365 (pestaña "Microsoft 365").

---

## 6. Módulo: database.py — Capa de Datos

### 6.1 Esquema de la Base de Datos

#### Tabla `configuracion`
Almacén clave-valor para configuraciones de la aplicación.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `clave` | VARCHAR(100) PK | Identificador de la configuración |
| `valor` | TEXT | Valor de la configuración |

**Claves predeterminadas insertadas automáticamente:**

| Clave | Valor por defecto | Uso |
|-------|------------------|-----|
| `smtp_servidor` | `smtp.gmail.com` | Servidor de correo SMTP |
| `smtp_puerto` | `587` | Puerto SMTP |
| `smtp_email` | *(vacío)* | Email de envío |
| `smtp_password` | *(vacío)* | Contraseña/App Password |
| `smtp_remitente` | `Recursos Humanos` | Nombre del remitente |
| `gemini_api_key` | *(vacío)* | API Key de Google Gemini |
| `gemini_modelo` | `gemini-2.5-flash` | Modelo de IA a utilizar |
| `ruta_documentos` | *(vacío)* | Carpeta base de documentos |
| `graph_client_id` | *(vacío)* | App ID de Azure AD |
| `graph_tenant_id` | *(vacío)* | Tenant ID de Microsoft 365 |

#### Tabla `puestos`
Perfiles de puesto disponibles en la organización.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | SERIAL PK | Identificador único |
| `titulo` | VARCHAR(200) | Nombre del puesto |
| `area` | VARCHAR(100) | Área o departamento |
| `descripcion` | TEXT | Descripción del puesto |
| `requisitos` | TEXT | Requisitos del puesto |
| `tecnologias` | TEXT | Tecnologías requeridas |
| `salario_min` | NUMERIC(12,2) | Salario mínimo |
| `salario_max` | NUMERIC(12,2) | Salario máximo |
| `estado` | VARCHAR(30) | `Abierto` / `Cerrado` |
| `fecha_creacion` | TIMESTAMP | Fecha de creación |

#### Tabla `candidatos`
Información personal y de proceso de cada candidato.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | SERIAL PK | Identificador único (genera código RH-XXXX) |
| `nombre` | VARCHAR(100) | Nombre del candidato |
| `apellidos` | VARCHAR(150) | Apellidos del candidato |
| `email` | VARCHAR(200) | Correo electrónico |
| `telefono` | VARCHAR(30) | Teléfono de contacto |
| `puesto_id` | INT FK→puestos | Puesto asignado (nullable) |
| `puesto_texto` | VARCHAR(200) | Puesto en texto libre |
| `estado` | VARCHAR(50) | Estado actual del proceso |
| `notas` | TEXT | Notas adicionales |
| `cv_json` | TEXT | CV estructurado en formato JSON |
| `fecha_registro` | TIMESTAMP | Fecha de registro |
| `fecha_actualizacion` | TIMESTAMP | Última actualización |

**Estados posibles del candidato:**

| Estado | Color | Significado |
|--------|-------|-------------|
| `Nuevo` | #1565C0 (azul) | Recién registrado |
| `Documentación solicitada` | #E65100 (naranja) | Se envió correo solicitando documentos |
| `Documentación parcial` | #F9A825 (amarillo) | Algunos documentos recibidos |
| `Documentación completa` | #2E7D32 (verde) | Todos los documentos recibidos |
| `Contratado` | #6A1B9A (morado) | Proceso completado |
| `Rechazado` | #C62828 (rojo) | Candidato descartado |

#### Tabla `documentos_candidato`
Checklist de 14 documentos requeridos por candidato.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | SERIAL PK | Identificador único |
| `candidato_id` | INT FK→candidatos | Candidato asociado |
| `nombre_documento` | VARCHAR(200) | Nombre del documento |
| `recibido` | BOOLEAN | ¿Documento recibido? |
| `fecha_recepcion` | TIMESTAMP | Fecha en que se recibió |
| `ruta_archivo` | TEXT | Ruta del archivo en disco |
| `notas` | TEXT | Notas sobre el documento |

**Documentos requeridos (14):**

| Código | Documento |
|--------|-----------|
| DOC-01 | DNI / Carnet de Extranjería vigente |
| DOC-02 | 1 foto tamaño carnet con fondo blanco |
| DOC-03 | Certificado de antecedentes penales y policiales |
| DOC-04 | Certificados de retenciones de 5ta. categoría |
| DOC-05 | Constancia de pago de utilidades |
| DOC-06 | Certificado de estudios (Bachiller o Título) |
| DOC-07 | Las tres últimas constancias de trabajo |
| DOC-08 | CV formato Entelgy |
| DOC-09 | Declaración de NO Retenciones |
| DOC-10 | Formato elección régimen pensionario |
| DOC-11 | Declaración Jurada de Domicilio |
| DOC-12 | Ficha del trabajador |
| DOC-13 | Acta de matrimonio |
| DOC-14 | DNI Derechohabientes |

#### Tabla `historial_estado`
Registro de auditoría de cambios de estado.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | SERIAL PK | Identificador único |
| `candidato_id` | INT FK→candidatos | Candidato asociado |
| `estado_anterior` | VARCHAR(50) | Estado previo |
| `estado_nuevo` | VARCHAR(50) | Nuevo estado |
| `fecha_cambio` | TIMESTAMP | Momento del cambio |
| `notas` | TEXT | Notas del cambio |

#### Tabla `correos_enviados`
Log de correos electrónicos enviados.

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | SERIAL PK | Identificador único |
| `candidato_id` | INT FK→candidatos | Candidato asociado |
| `destinatario` | VARCHAR(200) | Email del destinatario |
| `asunto` | VARCHAR(500) | Asunto del correo |
| `fecha_envio` | TIMESTAMP | Fecha y hora de envío |
| `exitoso` | BOOLEAN | ¿Se envió correctamente? |
| `error` | TEXT | Mensaje de error (si falló) |

### 6.2 Clase `Database` — API Completa

#### Conexión

| Método | Parámetros | Retorno | Descripción |
|--------|-----------|---------|-------------|
| `conectar()` | `host, puerto, nombre, usuario, password` | `(bool, str)` | Establece conexión, crea tablas e inserta config por defecto |
| `cerrar()` | — | — | Cierra la conexión |
| `conectado` | *(property)* | `bool` | Verifica si la conexión está activa |

#### Configuración

| Método | Parámetros | Retorno | Descripción |
|--------|-----------|---------|-------------|
| `obtener_config()` | `clave, default=""` | `str` | Obtiene un valor de configuración |
| `guardar_config()` | `clave, valor` | — | Guarda/actualiza un valor (UPSERT) |
| `obtener_todas_configs()` | — | `dict` | Retorna todas las configuraciones como diccionario |

#### Puestos (CRUD)

| Método | Parámetros | Retorno | Descripción |
|--------|-----------|---------|-------------|
| `listar_puestos()` | `solo_abiertos=False` | `list[dict]` | Lista puestos con conteo de candidatos |
| `obtener_puesto()` | `puesto_id` | `dict\|None` | Obtiene un puesto por ID |
| `crear_puesto()` | `titulo, area, descripcion, requisitos, tecnologias, salario_min, salario_max` | `int` | Crea puesto, retorna ID |
| `actualizar_puesto()` | `puesto_id, **campos` | — | Actualiza campos (validados con whitelist) |
| `eliminar_puesto()` | `puesto_id` | — | Elimina puesto (candidatos quedan con puesto_id=NULL) |

#### Candidatos (CRUD)

| Método | Parámetros | Retorno | Descripción |
|--------|-----------|---------|-------------|
| `listar_candidatos()` | `estado_filtro=None` | `list[dict]` | Lista con JOIN a puestos, filtro opcional |
| `obtener_candidato()` | `candidato_id` | `dict\|None` | Detalle completo del candidato |
| `crear_candidato()` | `nombre, apellidos, email, telefono, puesto_id, puesto_texto, notas` | `int` | Crea candidato + 14 documentos + historial inicial |
| `actualizar_candidato()` | `candidato_id, **campos` | — | Actualiza campos (validados con whitelist) |
| `cambiar_estado_candidato()` | `candidato_id, nuevo_estado, notas=""` | — | Cambia estado + registra en historial |
| `guardar_cv_json()` | `candidato_id, cv_json` | — | Guarda JSON del CV procesado |
| `eliminar_candidato()` | `candidato_id` | — | Elimina con CASCADE (documentos, historial, correos) |

#### Documentos

| Método | Parámetros | Retorno | Descripción |
|--------|-----------|---------|-------------|
| `listar_documentos()` | `candidato_id` | `list[dict]` | Lista los 14 documentos con estado |
| `marcar_documento()` | `doc_id, recibido, ruta_archivo=""` | — | Marca como recibido/pendiente + fecha |

#### Historial y Correos

| Método | Parámetros | Retorno | Descripción |
|--------|-----------|---------|-------------|
| `obtener_historial()` | `candidato_id` | `list[dict]` | Historial de cambios de estado |
| `registrar_correo()` | `candidato_id, destinatario, asunto, exitoso, error=""` | — | Registra envío de correo |
| `listar_correos()` | `candidato_id` | `list[dict]` | Historial de correos enviados |

#### Estadísticas (Dashboard)

| Método | Parámetros | Retorno | Descripción |
|--------|-----------|---------|-------------|
| `contar_por_estado()` | — | `dict{estado: count}` | Distribución de candidatos por estado |
| `total_candidatos()` | — | `int` | Total de candidatos registrados |
| `total_puestos_abiertos()` | — | `int` | Puestos con estado='Abierto' |
| `actividad_reciente()` | `limite=10` | `list[dict]` | UNION de cambios de estado + correos (más recientes primero) |
| `candidatos_por_puesto()` | `puesto_id` | `list[dict]` | Candidatos asignados a un puesto |

### 6.3 Funciones auxiliares

| Función | Descripción |
|---------|-------------|
| `cargar_config_local()` | Carga configuración de BD desde `db_config.json` (fallback a `DEFAULT_DB_CONFIG`) |
| `guardar_config_local(config)` | Guarda configuración de BD en disco |

### 6.4 Patrones de diseño

- **Validación por whitelist**: Los métodos `actualizar_candidato()` y `actualizar_puesto()` solo aceptan campos de un conjunto predefinido (`_CAMPOS_CANDIDATO`, `_CAMPOS_PUESTO`) para prevenir inyección SQL.
- **RealDictCursor**: Todas las consultas retornan diccionarios en lugar de tuplas.
- **UPSERT**: `ON CONFLICT DO UPDATE` para escritura idempotente de configuración.
- **CASCADE**: Las foreign keys borran automáticamente los registros dependientes.

---

## 7. Módulo: cv_converter.py — Procesamiento de CV

### 7.1 Flujo de procesamiento

```
PDF del candidato
    │
    ▼
extraer_texto_pdf(ruta_pdf)         ← pdfplumber extrae texto con layout
    │
    ▼
procesar_con_gemini(texto, key)     ← Gemini estructura el texto en JSON
    │
    ▼
{JSON estructurado}
    │
    ▼
generar_pdf_entelgy(datos, ruta)    ← fpdf2 genera PDF en formato Entelgy
    │
    ▼
CV_Entelgy.pdf
```

### 7.2 Funciones principales

#### `extraer_texto_pdf(ruta_pdf) → str`
Usa `pdfplumber` para extraer texto de cada página del PDF, concatenando con doble salto de línea. Limpia espacios múltiples.

#### `procesar_con_gemini(texto_cv, api_key, modelo, datos_extra="") → dict`
Envía el texto del CV a Google Gemini con un prompt detallado que indica:
- Extraer iniciales del nombre completo
- Generar presentación profesional (máximo 4 líneas)
- Separar experiencia laboral real de proyectos académicos
- Validar datos específicos de Entelgy (sector, proyecto, tecnología)
- Idioma español nativo por defecto
- Retornar JSON válido sin markdown

**Estructura JSON de salida:**

```json
{
  "iniciales": "D. J. S. Q.",
  "presentacion": "Profesional con experiencia en...",
  "experiencia": [
    {
      "empresa": "Nombre de la Empresa",
      "fechas": "Ene 2023 - Actualidad",
      "cargo": "Desarrollador Senior",
      "sector": "Tecnología",
      "proyecto": "Sistema de gestión interna",
      "tecnologia": "Python, PostgreSQL, React",
      "funciones": ["Función 1", "Función 2"]
    }
  ],
  "estudios_superiores": ["Universidad X, Facultad Y, Grado Z, 2020"],
  "certificaciones": ["AWS: Solutions Architect - 2024"],
  "estudios_complementarios": ["Proyecto Académico: App Móvil - Flutter"],
  "idiomas": ["Español: Nativo", "Inglés: Avanzado. Institución: ICPNA"],
  "consideraciones": "Nota sobre datos faltantes..."
}
```

#### `actualizar_json_con_gemini(json_actual, datos_extra, api_key, modelo) → dict`
Toma un JSON existente y aplica modificaciones indicadas por el usuario mediante IA. Útil para corregir datos, agregar información o ajustar el formato.

#### `generar_pdf_entelgy(datos_cv, ruta_salida, logo_path=None) → str`
Genera un PDF profesional con el formato corporativo de Entelgy:

1. **Encabezado**: Logo de Entelgy (o texto "ENTELGY" si no hay logo)
2. **Iniciales**: Nombre en formato grande
3. **Presentación**: Resumen profesional
4. **Experiencia Profesional**: Detalle por empresa con cargo, sector, proyecto, tecnología y funciones
5. **Estudios Superiores**
6. **Certificaciones**
7. **Estudios Complementarios**
8. **Idiomas**
9. **Consideraciones** (si existen)

### 7.3 Clase `_PDFEntelgy(FPDF)`

Subclase de FPDF con métodos de renderizado personalizados:

| Método | Propósito |
|--------|-----------|
| `header()` | Pie de página con número de página y texto "CV - Formato Entelgy" |
| `seccion(titulo)` | Encabezado de sección con línea azul debajo |
| `parrafo(texto)` | Párrafo con word-wrap automático |
| `viñeta(texto, indent)` | Viñeta con guión (—) y sangría |
| `etiqueta(label, valor)` | Etiqueta en negrita + valor en texto regular |

### 7.4 Codificación segura

La función `_safe(text)` convierte caracteres Unicode problemáticos a equivalentes Windows-1252:
- Viñetas (•, ▪, ►) → guiones
- Comillas tipográficas → comillas rectas
- Guiones largos → guiones simples
- Caracteres de acento y especiales

---

## 8. Módulo: email_manager.py — Integración Microsoft 365

### 8.1 Protocolo de comunicación

El sistema usa **códigos estandarizados** para la comunicación con candidatos:

**Código de candidato:** `[RH-XXXX]` donde XXXX es el ID con ceros a la izquierda.

**Códigos de documento:** `DOC-01` a `DOC-14` en los nombres de archivo.

**Flujo de correo:**
```
ENVÍO:
  Asunto: "[RH-0001] Solicitud de documentos"
  Cuerpo: Tabla HTML con DOC-XX y nombre de cada documento pendiente

RESPUESTA DEL CANDIDATO:
  Asunto: "RE: [RH-0001] Solicitud de documentos"
  Adjuntos: DOC-01_DNI_JuanPerez.pdf, DOC-06_Titulo_JuanPerez.pdf
```

### 8.2 Mapeo de códigos

```python
CODIGO_DOCUMENTO = {
    "DOC-01": "DNI / Carnet de Extranjería vigente",
    "DOC-02": "1 foto tamaño carnet con fondo blanco",
    "DOC-03": "Certificado de antecedentes penales y policiales",
    ...
    "DOC-14": "DNI Derechohabientes",
}
```

### 8.3 Clase `GraphClient` — Autenticación y operaciones

#### Autenticación (Device Code Flow)

El flujo de autenticación no requiere abrir un navegador embebido:

```
1. iniciar_device_flow()
   → Retorna: { user_code: "ABC123", verification_uri: "https://microsoft.com/devicelogin" }

2. El usuario abre la URL manualmente e ingresa el código

3. completar_device_flow()
   → Espera a que el usuario complete la autenticación
   → Almacena el token en msal_token_cache.json

4. obtener_token()
   → En llamadas futuras, renueva silenciosamente desde el caché
```

#### Métodos de autenticación

| Método | Retorno | Descripción |
|--------|---------|-------------|
| `obtener_token()` | `str\|None` | Token del caché (renovación silenciosa) |
| `iniciar_device_flow()` | `dict\|None` | Inicia flujo, retorna código + URL |
| `completar_device_flow()` | `(bool, str)` | Espera autenticación del usuario |
| `autenticado()` | `bool` | Verifica si hay token válido |
| `cerrar_sesion()` | — | Elimina caché de tokens |

#### Operaciones de correo

| Método | Retorno | Endpoint Graph API | Descripción |
|--------|---------|-------------------|-------------|
| `enviar_correo(dest, asunto, html)` | `(bool, str)` | `POST /me/sendMail` | Envía correo HTML |
| `buscar_correos_rh(solo_no_leidos)` | `list[dict]` | `GET /me/messages` | Busca correos con `[RH-` en asunto |
| `obtener_adjuntos(message_id)` | `list[dict]` | `GET /me/messages/{id}/attachments` | Descarga adjuntos (base64 → bytes) |
| `marcar_como_leido(message_id)` | `bool` | `PATCH /me/messages/{id}` | Marca mensaje como leído |

### 8.4 Funciones auxiliares

| Función | Descripción |
|---------|-------------|
| `codigo_candidato(id)` | `42` → `"RH-0042"` |
| `extraer_id_candidato(asunto)` | `"[RH-0042] Solicitud"` → `42` |
| `extraer_codigo_doc(nombre)` | `"DOC-01_DNI.pdf"` → `"DOC-01"` |
| `nombre_documento_por_codigo(codigo)` | `"DOC-01"` → `"DNI / Carnet de Extranjería vigente"` |
| `generar_cuerpo_solicitud(nombre, cod, docs)` | Genera HTML del correo de solicitud |
| `guardar_adjunto(carpeta, nombre, datos)` | Guarda archivo, maneja duplicados, sanitiza nombre |
| `_construir_carpeta_candidato(candidato, ruta)` | Crea carpeta `0001_Apellidos_Nombre` |

### 8.5 Procesamiento automático

La función `procesar_correos_entrantes(graph, ruta_base, db)` ejecuta el flujo completo:

```
1. graph.buscar_correos_rh(solo_no_leidos=True)
   └─ Filtra correos con [RH-XXXX] en asunto

2. Para cada correo:
   ├─ Extraer candidato_id del asunto
   ├─ Verificar que el candidato existe en BD
   ├─ Si tiene adjuntos:
   │   ├─ graph.obtener_adjuntos(message_id)
   │   ├─ Para cada adjunto:
   │   │   ├─ Guardar en /ruta_base/XXXX_Apellidos_Nombre/
   │   │   ├─ Extraer código DOC-XX del nombre
   │   │   └─ si el código coincide → db.marcar_documento(recibido=True)
   │   └─ Registrar resultado
   └─ graph.marcar_como_leido(message_id)

3. Retornar lista de resultados (procesado/ignorado por correo)
```

---

## 9. Módulo: main.py — Interfaz de Usuario

### 9.1 Constantes de diseño

```python
COLOR_PRIMARIO   = "#1565C0"    # Azul principal
COLOR_SECUNDARIO = "#0D47A1"    # Azul oscuro (títulos)
COLOR_FONDO      = "#F5F7FA"    # Fondo gris claro
COLOR_TARJETA    = "#FFFFFF"    # Tarjetas blancas
COLOR_EXITO      = "#2E7D32"    # Verde (éxito)
COLOR_ALERTA     = "#E65100"    # Naranja (advertencia)
COLOR_ERROR      = "#C62828"    # Rojo (error)
```

### 9.2 Navegación principal

```
NavigationRail (lateral izquierdo)
├─ [0] Panel       → construir_dashboard()
├─ [1] Candidatos  → construir_lista_candidatos()
├─ [2] Puestos     → construir_puestos()
├─ [3] Convertidor → construir_convertidor()
├─ [4] Bandeja     → construir_bandeja()
└─ [5] Configuración → construir_configuracion()
```

### 9.3 Sección 0: Dashboard (`construir_dashboard`)

Muestra un resumen ejecutivo del sistema:

- **KPIs en tarjetas**: Total candidatos, nuevos, en proceso, completos, puestos abiertos
- **Gráfico de distribución**: Barra horizontal con porcentaje por estado
- **Candidatos pendientes**: Top 8 en estados {Nuevo, Solicitada, Parcial}, clickeables
- **Actividad reciente**: Últimos 10 eventos (cambios de estado + correos enviados)

### 9.4 Sección 1: Candidatos

#### Vista de lista (`construir_lista_candidatos`)
- Filtro por dropdown de estado (predeterminado: "Todos")
- Tarjeta por candidato: nombre, puesto, email, badge de estado coloreado
- Botón "Nuevo candidato" → formulario de creación

#### Formulario (`construir_formulario_candidato`)
- Campos: nombre*, apellidos*, email, teléfono, puesto (dropdown con puestos abiertos), notas
- Opción "Otro (especificar)" para puesto personalizado
- Al crear: genera los 14 documentos en BD + historial estado "Nuevo"

#### Detalle (`construir_detalle`)

Vista completa del candidato con:

1. **Encabezado**: Datos personales del candidato
2. **Gestión de estado**: Dropdown + botón "Aplicar" para cambiar estado
3. **CV Entelgy**:
   - Indicador de estado (generado/pendiente)
   - "Subir CV (PDF)" → extrae → procesa con Gemini → guarda JSON → genera PDF
   - "Actualizar con IA" → modifica JSON existente con instrucciones del usuario
   - Campo de instrucciones extra
4. **Checklist de documentos**: 14 checkboxes con estado y fecha
5. **Solicitar documentos por correo**: Botón que envía email vía Graph API con tabla de pendientes
6. **Historial de estados**: Timeline con estado anterior → nuevo + fecha
7. **Historial de correos**: Lista de correos enviados con estado (éxito/error)
8. **Eliminar candidato**: Con diálogo de confirmación

### 9.5 Sección 2: Puestos (`construir_puestos`)

- Lista de puestos con título, área, tecnologías, conteo de candidatos, badge de estado
- Formulario CRUD: título*, área, descripción, requisitos, tecnologías, salario min/max, estado
- Botón eliminar con confirmación (solo en modo edición)

### 9.6 Sección 3: Convertidor CV (`construir_convertidor`)

Herramienta independiente (puede usarse sin vincular a un candidato):

1. Seleccionar PDF de CV
2. (Opcional) Vincular a candidato existente
3. (Opcional) Agregar instrucciones extra para la IA
4. "Analizar CV" → extrae texto → Gemini → muestra JSON
5. "Actualizar con IA" → aplica modificaciones al JSON existente
6. "Guardar PDF" → genera PDF en formato Entelgy

Si se vincula a un candidato, también:
- Guarda el JSON en la BD
- Copia el CV original a la carpeta del candidato
- Genera el CV Entelgy en la carpeta del candidato

### 9.7 Sección 4: Bandeja de Correos (`construir_bandeja`)

- **Requisito**: Microsoft 365 configurado y sesión iniciada
- **Actualizar**: Busca correos con `[RH-XXXX]` en asunto
- **Vista**: Lista de correos con ícono leído/no leído, asunto, remitente, fecha, indicador de adjuntos, código RH
- **Procesar no leídos**: Ejecuta `procesar_correos_entrantes()` → descarga adjuntos, marca documentos en BD, marca correos como leídos
- **Resultado**: Muestra conteo de procesados, ignorados y adjuntos descargados

### 9.8 Sección 5: Configuración (`construir_configuracion`)

5 pestañas con diseño de tarjetas:

| Pestaña | Contenido | Almacenamiento |
|---------|-----------|----------------|
| **Base de Datos** | Host, puerto, nombre BD, usuario, contraseña + Probar/Guardar | `db_config.json` (local) |
| **Correo SMTP** | Servidor, puerto, email, password, nombre remitente | BD (`configuracion`) |
| **API Gemini** | API Key (oculta), modelo + Probar/Guardar | BD (`configuracion`) |
| **Documentos** | Ruta base + selector de carpeta | BD (`configuracion`) |
| **Microsoft 365** | Client ID, Tenant ID + Iniciar/Cerrar sesión | BD (`configuracion`) + `msal_token_cache.json` |

### 9.9 Modelo de hilos (threading)

Las operaciones pesadas se ejecutan en hilos daemon para no bloquear la UI:

| Operación | Hilo | Callback UI |
|-----------|------|-------------|
| Procesamiento de CV (Gemini) | `threading.Thread` | `page.update()` |
| Actualización de CV | `threading.Thread` | `page.update()` |
| Autenticación M365 (espera) | `threading.Thread` | `page.update()` |
| Carga de correos | `threading.Thread` | `page.update()` |
| Procesamiento de correos | `threading.Thread` | `page.update()` |
| Envío de correo | `threading.Thread` | `snack()` + `page.update()` |

### 9.10 FilePicker (Flet 0.82)

En Flet 0.82, `FilePicker` es un **Service** (no un control visual):

```python
file_picker = ft.FilePicker()
page.services.append(file_picker)  # ANTES de page.add()

# Uso (async):
result = await file_picker.pick_files(...)
result = await file_picker.get_directory_path(...)
```

---

## 10. Flujos de Datos Principales

### 10.1 Registro y seguimiento de candidato

```
Crear candidato (formulario)
    │
    ├─ INSERT candidatos
    ├─ INSERT 14 documentos_candidato (recibido=False)
    ├─ INSERT historial_estado (→ "Nuevo")
    └─ Crear carpeta en disco (si ruta configurada)
         │
         ▼
Solicitar documentos por correo
    │
    ├─ Generar HTML con tabla de documentos pendientes
    ├─ GraphClient.enviar_correo()
    ├─ INSERT correos_enviados
    └─ UPDATE estado → "Documentación solicitada"
         │
         ▼
Candidato responde con adjuntos
    │
    ▼
Procesar correos entrantes (Bandeja)
    │
    ├─ Buscar correos con [RH-XXXX]
    ├─ Descargar adjuntos → guardar en carpeta
    ├─ Extraer DOC-XX del nombre de archivo
    ├─ UPDATE documentos_candidato (recibido=True)
    └─ Marcar correo como leído en Outlook
```

### 10.2 Conversión de CV

```
Seleccionar PDF
    │
    ▼
extraer_texto_pdf()        ← pdfplumber
    │
    ▼
procesar_con_gemini()      ← Gemini 2.5 Flash
    │
    ▼
{JSON estructurado}        ← Se muestra en pantalla
    │                         Se guarda en candidatos.cv_json (si vinculado)
    ▼
generar_pdf_entelgy()      ← fpdf2
    │
    ▼
CV_Entelgy_XXXX.pdf        ← Se guarda en carpeta del candidato o ruta elegida
```

### 10.3 Ciclo de autenticación Microsoft 365

```
Configurar Client ID + Tenant ID → Guardar en BD
    │
    ▼
"Iniciar sesión" → iniciar_device_flow()
    │
    ├─ Mostrar código + URL al usuario
    │
    ▼
Usuario abre https://microsoft.com/devicelogin
    │
    ├─ Ingresa código → autoriza la app
    │
    ▼
completar_device_flow() → Token almacenado en msal_token_cache.json
    │
    ▼
Operaciones de correo usan obtener_token() → renovación silenciosa automática
```

---

## 11. Configuración de Servicios Externos

### 11.1 PostgreSQL (Railway)

La base de datos predeterminada está en Railway. Para usar otra instancia:

1. Ir a **Configuración → Base de Datos**
2. Ingresar las credenciales de su servidor PostgreSQL
3. Hacer clic en **"Probar conexión"** y después **"Guardar y conectar"**

Las tablas se crean automáticamente en la primera conexión.

### 11.2 Google Gemini API

1. Obtener una API Key en [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Ir a **Configuración → API Gemini**
3. Ingresar la API Key y opcionalmente cambiar el modelo (predeterminado: `gemini-2.5-flash`)
4. **"Probar conexión"** para verificar

### 11.3 Microsoft 365 (Graph API)

#### Prerrequisitos

Se necesita una **App Registration** en Azure Active Directory:

1. Ir a [portal.azure.com](https://portal.azure.com) → Azure Active Directory → App registrations
2. Crear nueva aplicación:
   - **Nombre**: "Proyecto RH" (o el que prefiera)
   - **Supported account types**: "Accounts in this organizational directory only" (Single tenant)
   - **Redirect URI**: Dejar vacío (no se necesita para Device Code Flow)
3. En la aplicación creada:
   - Copiar **Application (client) ID**
   - Copiar **Directory (tenant) ID**
4. Ir a **Authentication**:
   - En "Advanced settings", activar **"Allow public client flows"** = Yes
5. Ir a **API permissions**:
   - Agregar permiso → Microsoft Graph → Delegated permissions:
     - `Mail.ReadWrite`
     - `Mail.Send`
   - (Opcional) Solicitar consentimiento del administrador

#### Configuración en la app

1. Ir a **Configuración → Microsoft 365**
2. Ingresar el **Client ID** y **Tenant ID**
3. Hacer clic en **"Guardar"**
4. Hacer clic en **"Iniciar sesión"**
5. Se mostrará un código. Abrir `https://microsoft.com/devicelogin` e ingresar el código
6. Autorizar la aplicación con su cuenta de Microsoft 365

---

## 12. Consideraciones de Seguridad

| Aspecto | Implementación |
|---------|----------------|
| **Inyección SQL** | Consultas parametrizadas (`%s`) + validación de campos por whitelist |
| **Almacenamiento de credenciales** | API keys en BD, DB password en archivo local, tokens en caché cifrado de MSAL |
| **Nombres de archivo** | Sanitización con regex (`[<>:"/\\|?*]` → `_`) |
| **Autenticación OAuth2** | Device Code Flow (sin almacenar contraseñas de correo) |
| **Validación de entrada** | Campos requeridos verificados antes de guardar |
| **Cascade deletes** | Foreign keys con ON DELETE CASCADE mantienen integridad referencial |

**Archivos sensibles (NO versionar):**
- `db_config.json` — Credenciales de PostgreSQL
- `msal_token_cache.json` — Tokens de Microsoft 365
- `.env` (si se usa) — Variables de entorno

---

## 13. Notas sobre Flet 0.82

La versión 0.82 de Flet introduce cambios importantes respecto a versiones anteriores:

| Cambio | Antes | Flet 0.82 |
|--------|-------|-----------|
| Botones | `ft.ElevatedButton(...)` | `ft.Button(...)` |
| Dropdown evento | `on_change` | `on_select` |
| FilePicker montaje | `page.services.append(fp)` | `page.services.append(fp)` (antes de `page.add()`) |
| FilePicker operaciones | Síncronas | Asíncronas (`await fp.pick_files()`) |
| Diálogos | `page.dialog = dlg; dlg.open = True` | `page.show_dialog(dlg)` / `page.pop_dialog()` |

---

*Documento generado automáticamente — Proyecto RH v0.1.0*
