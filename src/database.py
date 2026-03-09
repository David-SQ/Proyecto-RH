"""
database.py — Conexión y operaciones CRUD con PostgreSQL para ProyectoRH.
"""

import psycopg2
import psycopg2.extras
import json
import os
from datetime import datetime


DOCUMENTOS_REQUERIDOS = [
    "DNI / Carnet de Extranjería vigente",
    "1 foto tamaño carnet con fondo blanco",
    "Certificado de antecedentes penales y policiales",
    "Certificados de retenciones de 5ta. categoría",
    "Constancia de pago de utilidades",
    "Certificado de estudios (Bachiller o Título)",
    "Las tres últimas constancias de trabajo",
    "CV formato Entelgy",
    "Declaración de NO Retenciones",
    "Formato elección régimen pensionario",
    "Declaración Jurada de Domicilio",
    "Ficha del trabajador",
    "Acta de matrimonio",
    "DNI Derechohabientes",
]

CONFIG_LOCAL_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "db_config.json"
)

DEFAULT_DB_CONFIG = {
    "host": "shortline.proxy.rlwy.net",
    "puerto": "20159",
    "nombre": "railway",
    "usuario": "postgres",
    "password": "MQzTrQOvzDJrUBelHjCYOocRSdgPrqnn",
}


def cargar_config_local():
    if os.path.exists(CONFIG_LOCAL_FILE):
        with open(CONFIG_LOCAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return dict(DEFAULT_DB_CONFIG)


def guardar_config_local(config):
    with open(CONFIG_LOCAL_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


SQL_CREAR_TABLAS = """
CREATE TABLE IF NOT EXISTS configuracion (
    clave VARCHAR(100) PRIMARY KEY,
    valor TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS puestos (
    id SERIAL PRIMARY KEY,
    titulo VARCHAR(200) NOT NULL,
    area VARCHAR(200) DEFAULT '',
    descripcion TEXT DEFAULT '',
    requisitos TEXT DEFAULT '',
    tecnologias TEXT DEFAULT '',
    salario_min NUMERIC(12,2) DEFAULT 0,
    salario_max NUMERIC(12,2) DEFAULT 0,
    estado VARCHAR(50) DEFAULT 'Abierto',
    fecha_creacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS candidatos (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    apellidos VARCHAR(200) NOT NULL,
    email VARCHAR(200) DEFAULT '',
    telefono VARCHAR(50) DEFAULT '',
    puesto_id INTEGER REFERENCES puestos(id) ON DELETE SET NULL,
    puesto_texto VARCHAR(200) DEFAULT '',
    estado VARCHAR(50) DEFAULT 'Nuevo',
    notas TEXT DEFAULT '',
    cv_json JSONB,
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS documentos_candidato (
    id SERIAL PRIMARY KEY,
    candidato_id INTEGER REFERENCES candidatos(id) ON DELETE CASCADE,
    nombre_documento VARCHAR(300) NOT NULL,
    recibido BOOLEAN DEFAULT FALSE,
    fecha_recepcion TIMESTAMP,
    ruta_archivo VARCHAR(500) DEFAULT '',
    notas TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS historial_estado (
    id SERIAL PRIMARY KEY,
    candidato_id INTEGER REFERENCES candidatos(id) ON DELETE CASCADE,
    estado_anterior VARCHAR(50) DEFAULT '',
    estado_nuevo VARCHAR(50) NOT NULL,
    fecha_cambio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notas TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS correos_enviados (
    id SERIAL PRIMARY KEY,
    candidato_id INTEGER REFERENCES candidatos(id) ON DELETE CASCADE,
    asunto VARCHAR(500) DEFAULT '',
    fecha_envio TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    exitoso BOOLEAN DEFAULT TRUE,
    error TEXT DEFAULT ''
);
"""

_CAMPOS_CANDIDATO = {
    "nombre", "apellidos", "email", "telefono", "puesto_id",
    "puesto_texto", "notas", "estado", "cv_json", "fecha_actualizacion",
}

_CAMPOS_PUESTO = {
    "titulo", "area", "descripcion", "requisitos", "tecnologias",
    "salario_min", "salario_max", "estado",
}


class Database:
    def __init__(self):
        self._conn = None

    # ── Conexión ──────────────────────────────────────────

    def conectar(self, host="localhost", puerto="5432", nombre="proyecto_rh",
                 usuario="postgres", password=""):
        try:
            if self._conn and not self._conn.closed:
                self._conn.close()
            self._conn = psycopg2.connect(
                host=host, port=int(puerto), dbname=nombre,
                user=usuario, password=password,
            )
            self._conn.autocommit = True
            self._crear_tablas()
            self._insertar_config_default()
            return True, "Conexión exitosa"
        except Exception as e:
            self._conn = None
            return False, str(e)

    def _crear_tablas(self):
        with self._conn.cursor() as cur:
            cur.execute(SQL_CREAR_TABLAS)

    def _insertar_config_default(self):
        defaults = {
            "smtp_servidor": "smtp.gmail.com",
            "smtp_puerto": "587",
            "smtp_email": "",
            "smtp_password": "",
            "smtp_remitente": "Recursos Humanos",
            "gemini_api_key": "",
            "gemini_modelo": "gemini-2.5-flash",
            "ruta_documentos": "",
            "graph_client_id": "",
            "graph_tenant_id": "",
        }
        with self._conn.cursor() as cur:
            for clave, valor in defaults.items():
                cur.execute(
                    "INSERT INTO configuracion (clave, valor) "
                    "VALUES (%s, %s) ON CONFLICT (clave) DO NOTHING",
                    (clave, valor),
                )

    @property
    def conectado(self):
        return self._conn is not None and not self._conn.closed

    def cerrar(self):
        if self._conn and not self._conn.closed:
            self._conn.close()

    # ── Configuración ─────────────────────────────────────

    def obtener_config(self, clave, default=""):
        with self._conn.cursor() as cur:
            cur.execute("SELECT valor FROM configuracion WHERE clave = %s", (clave,))
            row = cur.fetchone()
            return row[0] if row else default

    def guardar_config(self, clave, valor):
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO configuracion (clave, valor) VALUES (%s, %s) "
                "ON CONFLICT (clave) DO UPDATE SET valor = EXCLUDED.valor",
                (clave, valor),
            )

    def obtener_todas_configs(self):
        with self._conn.cursor() as cur:
            cur.execute("SELECT clave, valor FROM configuracion")
            return dict(cur.fetchall())

    # ── Puestos ───────────────────────────────────────────

    def listar_puestos(self, solo_abiertos=False):
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if solo_abiertos:
                cur.execute(
                    "SELECT * FROM puestos WHERE estado = 'Abierto' ORDER BY fecha_creacion DESC"
                )
            else:
                cur.execute("SELECT * FROM puestos ORDER BY fecha_creacion DESC")
            return cur.fetchall()

    def obtener_puesto(self, puesto_id):
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("SELECT * FROM puestos WHERE id = %s", (puesto_id,))
            return cur.fetchone()

    def crear_puesto(self, titulo, area="", descripcion="", requisitos="",
                     tecnologias="", salario_min=0, salario_max=0):
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO puestos (titulo, area, descripcion, requisitos, "
                "tecnologias, salario_min, salario_max) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (titulo, area, descripcion, requisitos, tecnologias,
                 salario_min, salario_max),
            )
            return cur.fetchone()[0]

    def actualizar_puesto(self, puesto_id, **campos):
        campos = {k: v for k, v in campos.items() if k in _CAMPOS_PUESTO}
        if not campos:
            return
        sets = ", ".join(f"{k} = %s" for k in campos)
        vals = list(campos.values()) + [puesto_id]
        with self._conn.cursor() as cur:
            cur.execute(f"UPDATE puestos SET {sets} WHERE id = %s", vals)

    def eliminar_puesto(self, puesto_id):
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM puestos WHERE id = %s", (puesto_id,))

    # ── Candidatos ────────────────────────────────────────

    def listar_candidatos(self, estado_filtro=None):
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            if estado_filtro and estado_filtro != "Todos":
                cur.execute(
                    "SELECT c.*, p.titulo AS puesto_nombre FROM candidatos c "
                    "LEFT JOIN puestos p ON c.puesto_id = p.id "
                    "WHERE c.estado = %s ORDER BY c.fecha_registro DESC",
                    (estado_filtro,),
                )
            else:
                cur.execute(
                    "SELECT c.*, p.titulo AS puesto_nombre FROM candidatos c "
                    "LEFT JOIN puestos p ON c.puesto_id = p.id "
                    "ORDER BY c.fecha_registro DESC",
                )
            return cur.fetchall()

    def obtener_candidato(self, candidato_id):
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT c.*, p.titulo AS puesto_nombre FROM candidatos c "
                "LEFT JOIN puestos p ON c.puesto_id = p.id WHERE c.id = %s",
                (candidato_id,),
            )
            return cur.fetchone()

    def crear_candidato(self, nombre, apellidos, email="", telefono="",
                        puesto_id=None, puesto_texto="", notas=""):
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO candidatos "
                "(nombre, apellidos, email, telefono, puesto_id, puesto_texto, notas) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (nombre, apellidos, email, telefono, puesto_id, puesto_texto, notas),
            )
            cid = cur.fetchone()[0]
            for doc in DOCUMENTOS_REQUERIDOS:
                cur.execute(
                    "INSERT INTO documentos_candidato (candidato_id, nombre_documento) "
                    "VALUES (%s, %s)", (cid, doc),
                )
            cur.execute(
                "INSERT INTO historial_estado "
                "(candidato_id, estado_anterior, estado_nuevo) VALUES (%s, '', 'Nuevo')",
                (cid,),
            )
            return cid

    def actualizar_candidato(self, candidato_id, **campos):
        campos = {k: v for k, v in campos.items() if k in _CAMPOS_CANDIDATO}
        if not campos:
            return
        campos["fecha_actualizacion"] = datetime.now()
        sets = ", ".join(f"{k} = %s" for k in campos)
        vals = list(campos.values()) + [candidato_id]
        with self._conn.cursor() as cur:
            cur.execute(f"UPDATE candidatos SET {sets} WHERE id = %s", vals)

    def cambiar_estado_candidato(self, candidato_id, nuevo_estado, notas=""):
        candidato = self.obtener_candidato(candidato_id)
        if not candidato:
            return
        estado_anterior = candidato["estado"]
        if estado_anterior == nuevo_estado:
            return
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE candidatos SET estado = %s, "
                "fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = %s",
                (nuevo_estado, candidato_id),
            )
            cur.execute(
                "INSERT INTO historial_estado "
                "(candidato_id, estado_anterior, estado_nuevo, notas) "
                "VALUES (%s, %s, %s, %s)",
                (candidato_id, estado_anterior, nuevo_estado, notas),
            )

    def guardar_cv_json(self, candidato_id, cv_json):
        with self._conn.cursor() as cur:
            cur.execute(
                "UPDATE candidatos SET cv_json = %s, "
                "fecha_actualizacion = CURRENT_TIMESTAMP WHERE id = %s",
                (json.dumps(cv_json, ensure_ascii=False), candidato_id),
            )

    def eliminar_candidato(self, candidato_id):
        with self._conn.cursor() as cur:
            cur.execute("DELETE FROM candidatos WHERE id = %s", (candidato_id,))

    # ── Documentos ────────────────────────────────────────

    def listar_documentos(self, candidato_id):
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM documentos_candidato "
                "WHERE candidato_id = %s ORDER BY id", (candidato_id,),
            )
            return cur.fetchall()

    def marcar_documento(self, doc_id, recibido, ruta_archivo=""):
        with self._conn.cursor() as cur:
            if recibido:
                cur.execute(
                    "UPDATE documentos_candidato SET recibido = TRUE, "
                    "fecha_recepcion = CURRENT_TIMESTAMP, ruta_archivo = %s "
                    "WHERE id = %s", (ruta_archivo, doc_id),
                )
            else:
                cur.execute(
                    "UPDATE documentos_candidato SET recibido = FALSE, "
                    "fecha_recepcion = NULL, ruta_archivo = '' WHERE id = %s",
                    (doc_id,),
                )

    # ── Historial ─────────────────────────────────────────

    def obtener_historial(self, candidato_id):
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM historial_estado "
                "WHERE candidato_id = %s ORDER BY fecha_cambio DESC",
                (candidato_id,),
            )
            return cur.fetchall()

    # ── Correos ───────────────────────────────────────────

    def registrar_correo(self, candidato_id, asunto, exitoso=True, error=""):
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO correos_enviados "
                "(candidato_id, asunto, exitoso, error) VALUES (%s, %s, %s, %s)",
                (candidato_id, asunto, exitoso, error),
            )

    def listar_correos(self, candidato_id):
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM correos_enviados "
                "WHERE candidato_id = %s ORDER BY fecha_envio DESC",
                (candidato_id,),
            )
            return cur.fetchall()

    # ── Estadísticas ──────────────────────────────────────

    def contar_por_estado(self):
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT estado, COUNT(*) FROM candidatos GROUP BY estado"
            )
            return dict(cur.fetchall())

    def total_candidatos(self):
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM candidatos")
            return cur.fetchone()[0]

    def total_puestos_abiertos(self):
        with self._conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM puestos WHERE estado = 'Abierto'")
            return cur.fetchone()[0]

    def actividad_reciente(self, limite=10):
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT * FROM (
                    SELECT 'estado' AS tipo, h.fecha_cambio AS fecha,
                           c.nombre || ' ' || c.apellidos AS candidato,
                           h.estado_anterior, h.estado_nuevo,
                           '' AS asunto, h.candidato_id
                    FROM historial_estado h
                    JOIN candidatos c ON h.candidato_id = c.id
                    UNION ALL
                    SELECT 'correo' AS tipo, co.fecha_envio AS fecha,
                           c.nombre || ' ' || c.apellidos AS candidato,
                           '' AS estado_anterior, '' AS estado_nuevo,
                           co.asunto, co.candidato_id
                    FROM correos_enviados co
                    JOIN candidatos c ON co.candidato_id = c.id
                ) AS actividad
                ORDER BY fecha DESC LIMIT %s
            """, (limite,))
            return cur.fetchall()

    def candidatos_por_puesto(self, puesto_id):
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM candidatos "
                "WHERE puesto_id = %s ORDER BY fecha_registro DESC",
                (puesto_id,),
            )
            return cur.fetchall()

    def candidatos_con_cv(self):
        """Retorna candidatos que tienen CV JSON almacenado."""
        with self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT c.*, p.titulo AS puesto_nombre FROM candidatos c "
                "LEFT JOIN puestos p ON c.puesto_id = p.id "
                "WHERE c.cv_json IS NOT NULL "
                "ORDER BY c.fecha_registro DESC",
            )
            return cur.fetchall()
