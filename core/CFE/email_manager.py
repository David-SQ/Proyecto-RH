"""
email_manager.py — Envío/recepción de correos vía Microsoft Graph API.

Usa MSAL (Device Code Flow) para autenticación con Microsoft 365.
Lee correos entrantes, descarga adjuntos y envía solicitudes de documentos.
"""

import base64
import json
import os
import re
from datetime import datetime

import msal
import requests


# ════════════════════════════════════════════════════════════
#  Mapeo de códigos ↔ documentos requeridos
# ════════════════════════════════════════════════════════════

CODIGO_DOCUMENTO = {
    "DOC-01": "DNI / Carnet de Extranjería vigente",
    "DOC-02": "1 foto tamaño carnet con fondo blanco",
    "DOC-03": "Certificado de antecedentes penales y policiales",
    "DOC-04": "Certificados de retenciones de 5ta. categoría",
    "DOC-05": "Constancia de pago de utilidades",
    "DOC-06": "Certificado de estudios (Bachiller o Título)",
    "DOC-07": "Las tres últimas constancias de trabajo",
    "DOC-08": "CV formato Entelgy",
    "DOC-09": "Declaración de NO Retenciones",
    "DOC-10": "Formato elección régimen pensionario",
    "DOC-11": "Declaración Jurada de Domicilio",
    "DOC-12": "Ficha del trabajador",
    "DOC-13": "Acta de matrimonio",
    "DOC-14": "DNI Derechohabientes",
}

DOCUMENTO_A_CODIGO = {v: k for k, v in CODIGO_DOCUMENTO.items()}

_RE_CODIGO_CANDIDATO = re.compile(r"\[RH-(\d{4,})\]")
_RE_CODIGO_DOC = re.compile(r"(DOC-\d{2})", re.IGNORECASE)

GRAPH_SCOPES = ["Mail.ReadWrite", "Mail.Send"]
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

_TOKEN_CACHE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "..", "msal_token_cache.json"
)


# ════════════════════════════════════════════════════════════
#  Funciones de código de candidato / documento
# ════════════════════════════════════════════════════════════

def codigo_candidato(candidato_id: int) -> str:
    return f"RH-{candidato_id:04d}"


def extraer_id_candidato(asunto: str) -> int | None:
    m = _RE_CODIGO_CANDIDATO.search(asunto or "")
    return int(m.group(1)) if m else None


def extraer_codigo_doc(nombre_archivo: str) -> str | None:
    m = _RE_CODIGO_DOC.search(nombre_archivo or "")
    return m.group(1).upper() if m else None


def nombre_documento_por_codigo(codigo: str) -> str | None:
    return CODIGO_DOCUMENTO.get(codigo.upper())


# ════════════════════════════════════════════════════════════
#  Plantilla del correo de solicitud
# ════════════════════════════════════════════════════════════

def generar_cuerpo_solicitud(nombre_candidato: str, codigo_rh: str,
                             docs_pendientes: list[dict]) -> str:
    filas = ""
    for d in docs_pendientes:
        filas += (
            f"<tr>"
            f"<td style='padding:6px 12px;border:1px solid #ddd;"
            f"font-weight:bold;color:#1565C0'>{d['codigo']}</td>"
            f"<td style='padding:6px 12px;border:1px solid #ddd'>"
            f"{d['nombre']}</td>"
            f"</tr>\n"
        )

    return f"""\
<html><body style="font-family:Calibri,Arial,sans-serif;color:#333">
<p>Estimado/a <b>{nombre_candidato}</b>,</p>

<p>Como parte del proceso de contratación, le solicitamos nos envíe los
siguientes documentos <b>respondiendo a este mismo correo</b>:</p>

<table style="border-collapse:collapse;margin:16px 0">
<tr style="background:#1565C0;color:white">
  <th style="padding:8px 12px;border:1px solid #1565C0">Código</th>
  <th style="padding:8px 12px;border:1px solid #1565C0">Documento</th>
</tr>
{filas}
</table>

<p><b>Instrucciones importantes:</b></p>
<ol>
  <li>Nombre cada archivo con su código correspondiente al inicio.<br>
      Ejemplo: <code>DOC-01_DNI_JuanPerez.pdf</code></li>
  <li>Incluya el código <b>[{codigo_rh}]</b> en el asunto del correo
      (ya incluido si responde a este mensaje).</li>
  <li>Puede enviar varios documentos en un mismo correo.</li>
  <li>Formatos aceptados: PDF, JPG, PNG, DOCX.</li>
</ol>

<p>Quedamos atentos a su respuesta.</p>
<p>Saludos cordiales,<br><b>Recursos Humanos</b></p>
</body></html>
"""


# ════════════════════════════════════════════════════════════
#  MSAL — Autenticación Microsoft 365 (Device Code Flow)
# ════════════════════════════════════════════════════════════

class GraphClient:
    """
    Cliente de Microsoft Graph API usando Device Code Flow.

    Flujo:
        1. obtener_token() — si hay token cacheado, lo renueva en silencio.
        2. Si no hay token, iniciar_device_flow() devuelve un código + URL.
        3. El usuario abre la URL e ingresa el código.
        4. completar_device_flow() obtiene el token.
        5. El token se cachea en disco.
    """

    def __init__(self, client_id: str, tenant_id: str):
        self._client_id = client_id
        self._tenant_id = tenant_id
        self._app = None
        self._token_cache = msal.SerializableTokenCache()
        self._cargar_cache()
        self._flow = None

    def _crear_app(self):
        if self._app is None:
            authority = f"https://login.microsoftonline.com/{self._tenant_id}"
            self._app = msal.PublicClientApplication(
                self._client_id,
                authority=authority,
                token_cache=self._token_cache,
            )

    def _cargar_cache(self):
        if os.path.exists(_TOKEN_CACHE_FILE):
            with open(_TOKEN_CACHE_FILE, "r") as f:
                self._token_cache.deserialize(f.read())

    def _guardar_cache(self):
        if self._token_cache.has_state_changed:
            with open(_TOKEN_CACHE_FILE, "w") as f:
                f.write(self._token_cache.serialize())

    def obtener_token(self) -> str | None:
        """
        Intenta obtener un token válido del cache (silenciosamente).
        Returns: access_token o None si necesita login.
        """
        self._crear_app()
        cuentas = self._app.get_accounts()
        if cuentas:
            result = self._app.acquire_token_silent(
                GRAPH_SCOPES, account=cuentas[0]
            )
            if result and "access_token" in result:
                self._guardar_cache()
                return result["access_token"]
        return None

    def iniciar_device_flow(self) -> dict | None:
        """
        Inicia el flujo de Device Code.
        Returns: dict con 'user_code', 'verification_uri', 'message'.
        """
        self._crear_app()
        self._flow = self._app.initiate_device_flow(scopes=GRAPH_SCOPES)
        if "user_code" not in self._flow:
            return None
        return {
            "user_code": self._flow["user_code"],
            "verification_uri": self._flow["verification_uri"],
            "message": self._flow["message"],
        }

    def completar_device_flow(self) -> tuple[bool, str]:
        """
        Espera a que el usuario complete la autenticación.
        Returns: (éxito, mensaje)
        """
        if not self._flow:
            return False, "No hay flujo de autenticación iniciado."
        self._crear_app()
        result = self._app.acquire_token_by_device_flow(self._flow)
        self._flow = None
        if "access_token" in result:
            self._guardar_cache()
            return True, "Autenticación exitosa."
        error = result.get("error_description",
                           result.get("error", "Error desconocido"))
        return False, error

    def autenticado(self) -> bool:
        """True si hay un token válido disponible."""
        return self.obtener_token() is not None

    def cerrar_sesion(self):
        """Elimina el cache de tokens."""
        if os.path.exists(_TOKEN_CACHE_FILE):
            os.remove(_TOKEN_CACHE_FILE)
        self._token_cache = msal.SerializableTokenCache()
        self._app = None

    def _headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    # ── Enviar correo ──────────────────────────────────────

    def enviar_correo(self, destinatario: str, asunto: str,
                      cuerpo_html: str) -> tuple[bool, str]:
        token = self.obtener_token()
        if not token:
            return False, "No autenticado. Inicie sesión primero."

        payload = {
            "message": {
                "subject": asunto,
                "body": {
                    "contentType": "HTML",
                    "content": cuerpo_html,
                },
                "toRecipients": [
                    {"emailAddress": {"address": destinatario}}
                ],
            },
            "saveToSentItems": True,
        }

        resp = requests.post(
            f"{GRAPH_BASE}/me/sendMail",
            headers=self._headers(token),
            json=payload,
            timeout=30,
        )

        if resp.status_code == 202:
            return True, ""
        return False, f"HTTP {resp.status_code}: {resp.text[:300]}"

    # ── Leer correos ───────────────────────────────────────

    def buscar_correos_rh(self, solo_no_leidos: bool = True) -> list[dict]:
        """Busca correos cuyo asunto contiene [RH-XXXX]."""
        token = self.obtener_token()
        if not token:
            return []

        filtro = "contains(subject, 'RH-')"
        if solo_no_leidos:
            filtro += " and isRead eq false"

        params = {
            "$filter": filtro,
            "$select": "id,subject,from,receivedDateTime,hasAttachments,isRead",
            "$orderby": "receivedDateTime desc",
            "$top": 50,
        }

        resp = requests.get(
            f"{GRAPH_BASE}/me/messages",
            headers=self._headers(token),
            params=params,
            timeout=30,
        )

        if resp.status_code != 200:
            return []

        mensajes = resp.json().get("value", [])
        resultados = []

        for msg in mensajes:
            asunto = msg.get("subject", "")
            cid = extraer_id_candidato(asunto)
            if cid is None:
                continue

            remitente_info = msg.get("from", {}).get("emailAddress", {})
            resultados.append({
                "id": msg["id"],
                "asunto": asunto,
                "remitente": remitente_info.get("address", ""),
                "remitente_nombre": remitente_info.get("name", ""),
                "fecha": msg.get("receivedDateTime", ""),
                "candidato_id": cid,
                "tiene_adjuntos": msg.get("hasAttachments", False),
                "leido": msg.get("isRead", False),
            })

        return resultados

    def obtener_adjuntos(self, message_id: str) -> list[dict]:
        """Descarga los adjuntos de un mensaje específico."""
        token = self.obtener_token()
        if not token:
            return []

        resp = requests.get(
            f"{GRAPH_BASE}/me/messages/{message_id}/attachments",
            headers=self._headers(token),
            params={"$select": "name,contentBytes,contentType,size"},
            timeout=60,
        )

        if resp.status_code != 200:
            return []

        adjuntos_raw = resp.json().get("value", [])
        adjuntos = []

        for att in adjuntos_raw:
            if att.get("@odata.type") != "#microsoft.graph.fileAttachment":
                continue
            nombre = att.get("name", "sin_nombre")
            datos_b64 = att.get("contentBytes", "")
            datos = base64.b64decode(datos_b64) if datos_b64 else b""
            codigo = extraer_codigo_doc(nombre)

            adjuntos.append({
                "nombre": nombre,
                "datos": datos,
                "codigo_doc": codigo,
            })

        return adjuntos

    def marcar_como_leido(self, message_id: str) -> bool:
        """Marca un mensaje como leído."""
        token = self.obtener_token()
        if not token:
            return False

        resp = requests.patch(
            f"{GRAPH_BASE}/me/messages/{message_id}",
            headers=self._headers(token),
            json={"isRead": True},
            timeout=15,
        )
        return resp.status_code == 200


# ════════════════════════════════════════════════════════════
#  Guardar adjuntos en carpeta del candidato
# ════════════════════════════════════════════════════════════

def guardar_adjunto(ruta_carpeta: str, nombre_archivo: str,
                    datos: bytes) -> str:
    os.makedirs(ruta_carpeta, exist_ok=True)
    nombre_limpio = re.sub(r'[<>:"/\\|?*]', "_", nombre_archivo)
    ruta = os.path.join(ruta_carpeta, nombre_limpio)

    base, ext = os.path.splitext(ruta)
    contador = 1
    while os.path.exists(ruta):
        ruta = f"{base}_{contador}{ext}"
        contador += 1

    with open(ruta, "wb") as f:
        f.write(datos)

    return ruta


# ════════════════════════════════════════════════════════════
#  Procesamiento completo: leer → descargar → registrar
# ════════════════════════════════════════════════════════════

def procesar_correos_entrantes(graph: GraphClient,
                               ruta_base_documentos: str,
                               db) -> list[dict]:
    """
    Flujo completo:
    1. Busca correos no leídos con [RH-XXXX]
    2. Descarga adjuntos a la carpeta del candidato
    3. Marca documentos como recibidos en la BD
    4. Marca el correo como leído en Outlook
    """
    correos = graph.buscar_correos_rh(solo_no_leidos=True)

    if not correos:
        return []

    resultados = []

    for correo in correos:
        cid = correo["candidato_id"]
        candidato = db.obtener_candidato(cid)

        if not candidato:
            resultados.append({
                "candidato_id": cid,
                "status": "ignorado",
                "detalle": f"Candidato RH-{cid:04d} no existe en BD.",
            })
            graph.marcar_como_leido(correo["id"])
            continue

        carpeta_cand = _construir_carpeta_candidato(
            candidato, ruta_base_documentos
        )

        docs_guardados = []
        if correo["tiene_adjuntos"]:
            adjuntos = graph.obtener_adjuntos(correo["id"])
            for adj in adjuntos:
                ruta_archivo = guardar_adjunto(
                    carpeta_cand, adj["nombre"], adj["datos"]
                )

                doc_marcado = False
                if adj["codigo_doc"]:
                    nombre_doc = nombre_documento_por_codigo(adj["codigo_doc"])
                    if nombre_doc:
                        docs_bd = db.listar_documentos(cid)
                        for doc_bd in docs_bd:
                            if (doc_bd["nombre_documento"] == nombre_doc
                                    and not doc_bd["recibido"]):
                                db.marcar_documento(
                                    doc_bd["id"], True, ruta_archivo
                                )
                                doc_marcado = True
                                break

                docs_guardados.append({
                    "archivo": adj["nombre"],
                    "codigo": adj["codigo_doc"],
                    "marcado_en_bd": doc_marcado,
                    "ruta": ruta_archivo,
                })

        graph.marcar_como_leido(correo["id"])

        resultados.append({
            "candidato_id": cid,
            "candidato": f"{candidato['nombre']} {candidato['apellidos']}",
            "status": "procesado",
            "adjuntos": docs_guardados,
            "remitente": correo["remitente"],
            "fecha": correo["fecha"],
        })

    return resultados


# ════════════════════════════════════════════════════════════
#  Utilidades internas
# ════════════════════════════════════════════════════════════

def _construir_carpeta_candidato(candidato: dict,
                                 ruta_base: str) -> str:
    cid = candidato["id"]
    nombre = re.sub(r"[^\w\s]", "", candidato.get("nombre", "")).strip()
    apellidos = re.sub(r"[^\w\s]", "", candidato.get("apellidos", "")).strip()
    nombre_carpeta = (
        f"{cid:04d}_{apellidos.replace(' ', '_')}_{nombre.replace(' ', '_')}"
    )
    carpeta = os.path.join(ruta_base, nombre_carpeta)
    os.makedirs(carpeta, exist_ok=True)
    return carpeta
