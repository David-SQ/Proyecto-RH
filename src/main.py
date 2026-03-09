"""
main.py — Aplicación de Gestión de Contratación con Flet + PostgreSQL.
"""

import flet as ft
import os
import re
import json
import shutil
import threading
import webbrowser
import urllib.parse

from database import (
    Database, cargar_config_local, guardar_config_local,
)
from cv_converter import (
    extraer_texto_pdf, procesar_con_gemini, actualizar_json_con_gemini,
    generar_pdf_entelgy, GEMINI_OK,
)
from email_manager import (
    GraphClient, generar_cuerpo_solicitud, procesar_correos_entrantes,
    codigo_candidato, DOCUMENTO_A_CODIGO,
)

# ════════════════════════════════════════════════════════════
#  Colores y constantes
# ════════════════════════════════════════════════════════════
COLOR_PRIMARIO = "#1565C0"
COLOR_SECUNDARIO = "#0D47A1"
COLOR_FONDO = "#F5F7FA"
COLOR_TARJETA = "#FFFFFF"
COLOR_EXITO = "#2E7D32"
COLOR_ALERTA = "#E65100"
COLOR_ERROR = "#C62828"

ESTADOS_CANDIDATO = [
    "Nuevo",
    "Documentación solicitada",
    "Documentación parcial",
    "Documentación completa",
    "Contratado",
    "Rechazado",
]

ESTADO_COLORES = {
    "Nuevo": "#1565C0",
    "Documentación solicitada": "#F57F17",
    "Documentación parcial": "#E65100",
    "Documentación completa": "#2E7D32",
    "Contratado": "#1B5E20",
    "Rechazado": "#C62828",
}

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
LOGO_PATH = os.path.join(ASSETS_DIR, "logo_entelgy.png")

db = Database()


def _nombre_carpeta(c):
    """Genera el nombre de carpeta para un candidato."""
    ap = re.sub(r"[^\w\s]", "", c.get("apellidos", ""))
    nm = re.sub(r"[^\w\s]", "", c.get("nombre", ""))
    return f"{c['id']:04d}_{ap}_{nm}".replace(" ", "_")


def _carpeta_candidato(c, ruta_base):
    """Retorna la ruta completa de la carpeta del candidato, creándola si no existe."""
    if not ruta_base:
        return None
    path = os.path.join(ruta_base, _nombre_carpeta(c))
    os.makedirs(path, exist_ok=True)
    return path


# ════════════════════════════════════════════════════════════
#  Aplicación principal
# ════════════════════════════════════════════════════════════

def main(page: ft.Page):
    page.title = "ProyectoRH — Gestión de Contratación"
    page.theme_mode = ft.ThemeMode.LIGHT
    page.bgcolor = COLOR_FONDO
    page.padding = 0
    page.window.width = 1280
    page.window.height = 850

    # ── File picker (se monta después de page.add) ────
    file_picker = ft.FilePicker()

    # ── Helpers UI ────────────────────────────────────────
    def snack(msg, color=COLOR_PRIMARIO):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(msg, color="white"), bgcolor=color,
        )
        page.snack_bar.open = True
        page.update()

    contenido = ft.Container(expand=True, padding=24)

    def mostrar_vista(vista):
        contenido.content = vista
        page.update()

    def vista_no_conectado():
        return ft.Column(
            [
                ft.Container(height=80),
                ft.Icon(ft.Icons.CLOUD_OFF, size=64, color="#CCC"),
                ft.Text("Sin conexión a la base de datos",
                         size=20, weight=ft.FontWeight.BOLD, color="#666"),
                ft.Text("Configure la conexión en Configuración.",
                         size=14, color="#999"),
                ft.Container(height=20),
                ft.Button(
                    "Ir a Configuración", icon=ft.Icons.SETTINGS,
                    bgcolor=COLOR_PRIMARIO, color="white",
                    on_click=lambda _: _ir_config(),
                ),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

    def _ir_config():
        rail.selected_index = 6
        mostrar_vista(construir_configuracion())
        page.update()

    # ════════════════════════════════════════════════════════
    #  DASHBOARD
    # ════════════════════════════════════════════════════════

    def construir_dashboard():
        if not db.conectado:
            return vista_no_conectado()

        try:
            conteos = db.contar_por_estado()
            total = db.total_candidatos()
            puestos_ab = db.total_puestos_abiertos()
        except Exception as e:
            return ft.Text(f"Error al cargar datos: {e}", color=COLOR_ERROR)

        en_proc = conteos.get("Documentación solicitada", 0) + \
                  conteos.get("Documentación parcial", 0)
        compl = conteos.get("Documentación completa", 0) + \
                conteos.get("Contratado", 0)

        def kpi(val, lbl, col, ico):
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Container(
                            content=ft.Icon(ico, color="white", size=28),
                            bgcolor=col, width=56, height=56,
                            border_radius=12, alignment=ft.Alignment.CENTER,
                        ),
                        ft.Column([
                            ft.Text(str(val), size=28,
                                    weight=ft.FontWeight.BOLD, color=col),
                            ft.Text(lbl, size=12, color="#777"),
                        ], spacing=0),
                    ],
                    spacing=16,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                bgcolor=COLOR_TARJETA, border_radius=12,
                padding=ft.Padding(20, 18, 20, 18),
                shadow=ft.BoxShadow(blur_radius=6, spread_radius=1,
                                    color="#0000000F"),
                expand=True,
            )

        fila_kpis = ft.Row([
            kpi(total, "Total candidatos", COLOR_PRIMARIO, ft.Icons.PEOPLE),
            kpi(conteos.get("Nuevo", 0), "Nuevos", "#1565C0",
                ft.Icons.PERSON_ADD),
            kpi(en_proc, "En proceso", COLOR_ALERTA,
                ft.Icons.HOURGLASS_BOTTOM),
            kpi(compl, "Completados", COLOR_EXITO, ft.Icons.CHECK_CIRCLE),
            kpi(puestos_ab, "Puestos abiertos", "#7B1FA2", ft.Icons.WORK),
        ], spacing=14)

        # ── Barras de estado ──
        barras = []
        for est in ESTADOS_CANDIDATO:
            cnt = conteos.get(est, 0)
            col = ESTADO_COLORES.get(est, COLOR_PRIMARIO)
            pct = (cnt / total * 100) if total > 0 else 0
            barras.append(ft.Column([
                ft.Row([
                    ft.Container(width=10, height=10, bgcolor=col,
                                 border_radius=5),
                    ft.Text(est, size=13, weight=ft.FontWeight.W_500,
                            expand=True),
                    ft.Text(str(cnt), size=13, weight=ft.FontWeight.BOLD,
                            color=col),
                    ft.Text(f"({pct:.0f}%)", size=11, color="#999"),
                ], spacing=8, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                ft.ProgressBar(value=pct / 100, color=col, bgcolor="#E8EAF6",
                               bar_height=6, border_radius=3),
            ], spacing=4))

        panel_barras = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.BAR_CHART, color=COLOR_SECUNDARIO,
                            size=20),
                    ft.Text("Distribución por estado", size=15,
                            weight=ft.FontWeight.W_600, color="#333"),
                ], spacing=8),
                ft.Divider(height=1, color="#E0E0E0"),
                ft.Column(barras, spacing=12),
            ], spacing=12),
            bgcolor=COLOR_TARJETA, border_radius=12, padding=24,
            shadow=ft.BoxShadow(blur_radius=6, spread_radius=1,
                                color="#0000000F"),
            expand=2,
        )

        # ── Pendientes ──
        try:
            candidatos_all = db.listar_candidatos()
        except Exception:
            candidatos_all = []
        pendientes = [
            c for c in candidatos_all
            if c["estado"] in ("Nuevo", "Documentación solicitada",
                               "Documentación parcial")
        ][:8]
        filas_pend = []
        for c in pendientes:
            col_e = ESTADO_COLORES.get(c["estado"], COLOR_PRIMARIO)
            ini = (c["nombre"][:1] + c["apellidos"][:1]).upper()
            filas_pend.append(ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Text(ini, size=14,
                                        weight=ft.FontWeight.BOLD,
                                        color="white"),
                        bgcolor=col_e, width=36, height=36,
                        border_radius=18, alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column([
                        ft.Text(f"{c['nombre']} {c['apellidos']}", size=13,
                                weight=ft.FontWeight.W_600),
                        ft.Text(c.get("puesto_nombre") or
                                c.get("puesto_texto", ""), size=11,
                                color="#888"),
                    ], spacing=0, expand=True),
                    ft.Container(
                        content=ft.Text(c["estado"], size=10, color="white",
                                        weight=ft.FontWeight.W_600),
                        bgcolor=col_e, border_radius=10,
                        padding=ft.Padding(8, 3, 8, 3),
                    ),
                ], spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(12, 8, 12, 8), border_radius=8,
                bgcolor="#FAFAFA",
                on_click=lambda _, cid=c["id"]: mostrar_vista(
                    construir_detalle(cid)),
            ))
        if not filas_pend:
            filas_pend.append(ft.Text("Sin candidatos pendientes", size=13,
                                      italic=True, color="#999"))

        panel_pend = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.NOTIFICATION_IMPORTANT,
                            color=COLOR_ALERTA, size=20),
                    ft.Text("Requieren atención", size=15,
                            weight=ft.FontWeight.W_600, color="#333"),
                ], spacing=8),
                ft.Divider(height=1, color="#E0E0E0"),
                ft.Column(filas_pend, spacing=6, scroll=ft.ScrollMode.AUTO),
            ], spacing=12),
            bgcolor=COLOR_TARJETA, border_radius=12, padding=24,
            shadow=ft.BoxShadow(blur_radius=6, spread_radius=1,
                                color="#0000000F"),
            expand=3,
        )

        # ── Actividad reciente ──
        try:
            actividad = db.actividad_reciente(10)
        except Exception:
            actividad = []
        filas_act = []
        for a in actividad:
            if a["tipo"] == "estado":
                ico = ft.Icons.SWAP_HORIZ
                col_ic = COLOR_PRIMARIO
                txt = (f"{a['candidato']}: {a['estado_anterior']} "
                       f"→ {a['estado_nuevo']}")
            else:
                ico = ft.Icons.EMAIL
                col_ic = COLOR_ALERTA
                txt = f"{a['candidato']}: {a['asunto']}"
            fecha_s = a["fecha"].strftime("%d/%m %H:%M") if a["fecha"] else ""
            filas_act.append(ft.Container(
                content=ft.Row([
                    ft.Container(
                        content=ft.Icon(ico, color="white", size=16),
                        bgcolor=col_ic, width=32, height=32,
                        border_radius=8, alignment=ft.Alignment.CENTER,
                    ),
                    ft.Text(txt, size=12, expand=True, color="#444"),
                    ft.Text(fecha_s, size=11, color="#AAA"),
                ], spacing=10,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.Padding(10, 6, 10, 6), border_radius=8,
                bgcolor="#FAFAFA",
            ))
        if not filas_act:
            filas_act.append(ft.Text("Sin actividad reciente", size=13,
                                     italic=True, color="#999"))

        panel_act = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.HISTORY, color=COLOR_SECUNDARIO,
                            size=20),
                    ft.Text("Actividad reciente", size=15,
                            weight=ft.FontWeight.W_600, color="#333"),
                ], spacing=8),
                ft.Divider(height=1, color="#E0E0E0"),
                ft.Column(filas_act, spacing=6, scroll=ft.ScrollMode.AUTO),
            ], spacing=12),
            bgcolor=COLOR_TARJETA, border_radius=12, padding=24,
            shadow=ft.BoxShadow(blur_radius=6, spread_radius=1,
                                color="#0000000F"),
            expand=True,
        )

        return ft.Column([
            ft.Row([
                ft.Text("Panel de Control", size=24,
                         weight=ft.FontWeight.BOLD, color=COLOR_SECUNDARIO),
                ft.Container(expand=True),
                ft.Container(
                    content=ft.Text("Marzo 2026", size=12, color="#888"),
                    padding=ft.Padding(12, 6, 12, 6), border_radius=8,
                    bgcolor="#E8EAF6",
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1, color="#E0E0E0"),
            fila_kpis,
            ft.Row([panel_barras, panel_pend], spacing=14, expand=True),
            panel_act,
        ], spacing=16, expand=True, scroll=ft.ScrollMode.AUTO)

    # ════════════════════════════════════════════════════════
    #  LISTA DE CANDIDATOS
    # ════════════════════════════════════════════════════════

    def construir_lista_candidatos(filtro="Todos"):
        if not db.conectado:
            return vista_no_conectado()

        try:
            candidatos = db.listar_candidatos(
                filtro if filtro != "Todos" else None
            )
        except Exception as e:
            return ft.Text(f"Error: {e}", color=COLOR_ERROR)

        def tarjeta(c):
            col_e = ESTADO_COLORES.get(c["estado"], COLOR_PRIMARIO)
            puesto = c.get("puesto_nombre") or c.get("puesto_texto", "")
            return ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(f"{c['nombre']} {c['apellidos']}", size=16,
                                weight=ft.FontWeight.BOLD),
                        ft.Text(f"Puesto: {puesto}", size=13, color="#666"),
                        ft.Text(f"Email: {c['email']}", size=12, color="#888"),
                    ], spacing=2, expand=True),
                    ft.Container(
                        content=ft.Text(c["estado"], size=12, color="white",
                                        weight=ft.FontWeight.W_600),
                        bgcolor=col_e, border_radius=12,
                        padding=ft.Padding(12, 4, 12, 4),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.ARROW_FORWARD_IOS,
                        icon_color=COLOR_PRIMARIO,
                        on_click=lambda _, cid=c["id"]:
                            mostrar_vista(construir_detalle(cid)),
                    ),
                ], alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=COLOR_TARJETA, border_radius=10, padding=15,
                shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
            )

        tarjetas = [tarjeta(c) for c in candidatos]

        dd_filtro = ft.Dropdown(
            label="Filtrar por estado", width=250, value=filtro,
            options=[ft.dropdown.Option("Todos")]
                    + [ft.dropdown.Option(e) for e in ESTADOS_CANDIDATO],
            on_select=lambda e: mostrar_vista(
                construir_lista_candidatos(e.control.value)),
        )

        return ft.Column([
            ft.Row([
                ft.Text("Candidatos", size=22, weight=ft.FontWeight.BOLD,
                         color=COLOR_SECUNDARIO),
                ft.Container(expand=True),
                dd_filtro,
                ft.Button(
                    "Nuevo candidato", icon=ft.Icons.PERSON_ADD,
                    bgcolor=COLOR_PRIMARIO, color="white",
                    on_click=lambda _: mostrar_vista(
                        construir_formulario_candidato()),
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(),
            ft.Column(tarjetas, scroll=ft.ScrollMode.AUTO, expand=True,
                      spacing=8)
            if tarjetas
            else ft.Text("No hay candidatos registrados.", size=14,
                         color="#999", italic=True),
        ], expand=True)

    # ════════════════════════════════════════════════════════
    #  FORMULARIO NUEVO/EDITAR CANDIDATO
    # ════════════════════════════════════════════════════════

    def construir_formulario_candidato(candidato_id=None):
        if not db.conectado:
            return vista_no_conectado()

        editando = candidato_id is not None
        c = db.obtener_candidato(candidato_id) if editando else {}

        tf_nombre = ft.TextField(label="Nombre *", width=280,
                                 value=c.get("nombre", ""))
        tf_apellidos = ft.TextField(label="Apellidos *", width=280,
                                    value=c.get("apellidos", ""))
        tf_email = ft.TextField(label="Email", width=280,
                                value=c.get("email", ""))
        tf_telefono = ft.TextField(label="Teléfono", width=280,
                                   value=c.get("telefono", ""))
        tf_notas = ft.TextField(label="Notas", width=580, multiline=True,
                                min_lines=3, max_lines=5,
                                value=c.get("notas", ""))

        # Puestos dropdown
        try:
            puestos = db.listar_puestos(solo_abiertos=True)
        except Exception:
            puestos = []

        opciones_puesto = [ft.dropdown.Option(key="", text="— Sin asignar —")]
        for p in puestos:
            opciones_puesto.append(
                ft.dropdown.Option(key=str(p["id"]), text=p["titulo"])
            )
        opciones_puesto.append(
            ft.dropdown.Option(key="otro", text="Otro (especificar)")
        )

        current_puesto_key = ""
        if editando and c.get("puesto_id"):
            current_puesto_key = str(c["puesto_id"])
        elif editando and c.get("puesto_texto"):
            current_puesto_key = "otro"

        dd_puesto = ft.Dropdown(
            label="Puesto", width=280, value=current_puesto_key,
            options=opciones_puesto,
        )
        tf_puesto_otro = ft.TextField(
            label="Especificar puesto", width=280,
            visible=(current_puesto_key == "otro"),
            value=c.get("puesto_texto", ""),
        )

        def on_puesto_change(_):
            tf_puesto_otro.visible = (dd_puesto.value == "otro")
            page.update()

        dd_puesto.on_select = on_puesto_change

        def guardar(_):
            nom = tf_nombre.value.strip()
            ape = tf_apellidos.value.strip()
            if not nom or not ape:
                snack("Nombre y Apellidos son obligatorios.", COLOR_ERROR)
                return
            puesto_id = None
            puesto_texto = ""
            if dd_puesto.value and dd_puesto.value not in ("", "otro"):
                puesto_id = int(dd_puesto.value)
            elif dd_puesto.value == "otro":
                puesto_texto = tf_puesto_otro.value.strip()

            try:
                if editando:
                    db.actualizar_candidato(
                        candidato_id, nombre=nom, apellidos=ape,
                        email=tf_email.value.strip(),
                        telefono=tf_telefono.value.strip(),
                        puesto_id=puesto_id, puesto_texto=puesto_texto,
                        notas=tf_notas.value.strip(),
                    )
                    snack("Candidato actualizado.", COLOR_EXITO)
                    mostrar_vista(construir_detalle(candidato_id))
                else:
                    new_id = db.crear_candidato(
                        nom, ape,
                        email=tf_email.value.strip(),
                        telefono=tf_telefono.value.strip(),
                        puesto_id=puesto_id, puesto_texto=puesto_texto,
                        notas=tf_notas.value.strip(),
                    )
                    # Crear carpeta
                    ruta_base = db.obtener_config("ruta_documentos")
                    if ruta_base:
                        cand = db.obtener_candidato(new_id)
                        _carpeta_candidato(cand, ruta_base)
                    snack("Candidato registrado.", COLOR_EXITO)
                    mostrar_vista(construir_detalle(new_id))
            except Exception as e:
                snack(f"Error: {e}", COLOR_ERROR)

        titulo = "Editar Candidato" if editando else "Nuevo Candidato"
        return ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK,
                              icon_color=COLOR_PRIMARIO,
                              on_click=lambda _: mostrar_vista(
                                  construir_lista_candidatos())),
                ft.Text(titulo, size=22, weight=ft.FontWeight.BOLD,
                         color=COLOR_SECUNDARIO),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(),
            ft.Container(
                content=ft.Column([
                    ft.Row([tf_nombre, tf_apellidos], spacing=20),
                    ft.Row([tf_email, tf_telefono], spacing=20),
                    ft.Row([dd_puesto, tf_puesto_otro], spacing=20),
                    tf_notas,
                    ft.Container(height=10),
                    ft.Row([
                        ft.TextButton(
                            "Cancelar",
                            on_click=lambda _: mostrar_vista(
                                construir_lista_candidatos()),
                        ),
                        ft.Button(
                            "Guardar", icon=ft.Icons.SAVE,
                            bgcolor=COLOR_PRIMARIO, color="white",
                            on_click=guardar,
                        ),
                    ], spacing=16),
                ], spacing=16),
                bgcolor=COLOR_TARJETA, border_radius=12, padding=30,
                shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
            ),
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ════════════════════════════════════════════════════════
    #  SOLICITAR DOCUMENTOS POR CORREO
    # ════════════════════════════════════════════════════════

    def _solicitar_docs(candidato_id, c, docs):
        email_dest = c.get("email", "").strip()
        if not email_dest:
            snack("El candidato no tiene email registrado.", COLOR_ERROR)
            return

        # Documentos pendientes
        pendientes = []
        for d in docs:
            if not d["recibido"]:
                cod = DOCUMENTO_A_CODIGO.get(d["nombre_documento"])
                if cod:
                    pendientes.append({
                        "codigo": cod,
                        "nombre": d["nombre_documento"],
                    })
        if not pendientes:
            snack("Todos los documentos ya fueron recibidos.", COLOR_EXITO)
            return

        # Verificar config M365
        cfgs = db.obtener_todas_configs()
        client_id = cfgs.get("graph_client_id", "").strip()
        tenant_id = cfgs.get("graph_tenant_id", "").strip()
        if not client_id or not tenant_id:
            snack("Configure Microsoft 365 en Configuración.", COLOR_ERROR)
            return

        gc = GraphClient(client_id, tenant_id)
        if not gc.autenticado():
            snack("Inicie sesión en Microsoft 365 primero.", COLOR_ERROR)
            return

        cod_rh = codigo_candidato(candidato_id)
        nombre = f"{c['nombre']} {c['apellidos']}"
        asunto = f"[{cod_rh}] Solicitud de documentos"
        cuerpo = generar_cuerpo_solicitud(nombre, cod_rh, pendientes)

        def _enviar():
            ok, err = gc.enviar_correo(email_dest, asunto, cuerpo)
            if ok:
                try:
                    db.registrar_correo(candidato_id, email_dest, asunto,
                                        True, "")
                    db.cambiar_estado_candidato(candidato_id,
                                                "Documentación solicitada")
                except Exception:
                    pass
                snack(f"Correo enviado a {email_dest}", COLOR_EXITO)
                mostrar_vista(construir_detalle(candidato_id))
            else:
                try:
                    db.registrar_correo(candidato_id, email_dest, asunto,
                                        False, err)
                except Exception:
                    pass
                snack(f"Error al enviar: {err}", COLOR_ERROR)

        threading.Thread(target=_enviar, daemon=True).start()
        snack("Enviando correo…", COLOR_ALERTA)

    # ════════════════════════════════════════════════════════
    #  DETALLE DEL CANDIDATO
    # ════════════════════════════════════════════════════════

    def construir_detalle(candidato_id):
        if not db.conectado:
            return vista_no_conectado()

        c = db.obtener_candidato(candidato_id)
        if not c:
            return ft.Text("Candidato no encontrado.", color=COLOR_ERROR)

        col_est = ESTADO_COLORES.get(c["estado"], COLOR_PRIMARIO)
        puesto = c.get("puesto_nombre") or c.get("puesto_texto", "N/A")

        # ── Estado ──
        dd_estado = ft.Dropdown(
            label="Cambiar estado", width=260, value=c["estado"],
            options=[ft.dropdown.Option(e) for e in ESTADOS_CANDIDATO],
        )

        def aplicar_estado(_):
            if dd_estado.value != c["estado"]:
                db.cambiar_estado_candidato(candidato_id, dd_estado.value)
                snack(f"Estado cambiado a '{dd_estado.value}'.", COLOR_EXITO)
                mostrar_vista(construir_detalle(candidato_id))

        def eliminar_candidato(_):
            def confirmar(_):
                db.eliminar_candidato(candidato_id)
                page.pop_dialog()
                snack("Candidato eliminado.", COLOR_ALERTA)
                mostrar_vista(construir_lista_candidatos())

            dlg = ft.AlertDialog(
                title=ft.Text("¿Eliminar candidato?"),
                content=ft.Text(
                    f"Se eliminará a {c['nombre']} {c['apellidos']} "
                    "y toda su información asociada."
                ),
                actions=[
                    ft.TextButton("Cancelar",
                                  on_click=lambda _: _cerrar_dlg(dlg)),
                    ft.Button("Eliminar", bgcolor=COLOR_ERROR,
                                      color="white", on_click=confirmar),
                ],
            )
            page.show_dialog(dlg)

        # ── Documentos ──
        try:
            docs = db.listar_documentos(candidato_id)
        except Exception:
            docs = []

        docs_checks = []
        for d in docs:
            fecha_txt = ""
            if d["recibido"] and d["fecha_recepcion"]:
                fecha_txt = f"  ({d['fecha_recepcion'].strftime('%Y-%m-%d')})"

            def toggle_doc(e, did=d["id"], recv=d["recibido"]):
                db.marcar_documento(did, not recv)
                mostrar_vista(construir_detalle(candidato_id))

            docs_checks.append(ft.Row([
                ft.Checkbox(value=d["recibido"], on_change=toggle_doc),
                ft.Text(
                    d["nombre_documento"], size=13,
                    weight=ft.FontWeight.W_500 if d["recibido"]
                    else ft.FontWeight.NORMAL,
                    color=COLOR_EXITO if d["recibido"] else "#333",
                    expand=True,
                ),
                ft.Text(fecha_txt, size=11, color="#999"),
            ], spacing=4))

        # ── CV Entelgy ──
        tiene_cv = c.get("cv_json") is not None
        cv_status = ft.Text(
            "CV Entelgy generado" if tiene_cv else "Sin CV Entelgy",
            size=13, color=COLOR_EXITO if tiene_cv else "#999",
            italic=not tiene_cv,
        )

        cv_extra = ft.TextField(
            label="Datos extra / Instrucciones para la IA",
            width=500, multiline=True, min_lines=2, max_lines=4,
        )
        cv_progress = ft.ProgressRing(visible=False, width=24, height=24)
        cv_status_text = ft.Text("", size=12)

        async def subir_cv(_):
            archivos = await file_picker.pick_files(
                allowed_extensions=["pdf"],
                dialog_title="Seleccionar CV del candidato",
            )
            if not archivos:
                return
            ruta_pdf = archivos[0].path
            api_key = db.obtener_config("gemini_api_key")
            modelo = db.obtener_config("gemini_modelo", "gemini-2.5-flash")
            ruta_base = db.obtener_config("ruta_documentos")

            if not api_key:
                snack("Configure la API Key de Gemini en Configuración.",
                      COLOR_ERROR)
                return

            cv_progress.visible = True
            cv_status_text.value = "Procesando CV..."
            page.update()

            def _procesar():
                try:
                    # Copiar original a carpeta del candidato
                    if ruta_base:
                        carpeta = _carpeta_candidato(c, ruta_base)
                        if carpeta:
                            shutil.copy2(
                                ruta_pdf,
                                os.path.join(carpeta, "CV_Original.pdf"),
                            )

                    texto = extraer_texto_pdf(ruta_pdf)
                    if not texto:
                        cv_progress.visible = False
                        cv_status_text.value = "Error al leer el PDF."
                        page.update()
                        return

                    datos, err = procesar_con_gemini(
                        texto, api_key, modelo,
                        cv_extra.value.strip(),
                    )
                    if err:
                        cv_progress.visible = False
                        cv_status_text.value = err
                        page.update()
                        return

                    db.guardar_cv_json(candidato_id, datos)

                    # Generar PDF Entelgy
                    if ruta_base:
                        carpeta = _carpeta_candidato(c, ruta_base)
                        if carpeta:
                            pdf_out = os.path.join(
                                carpeta, "CV_Entelgy.pdf"
                            )
                            generar_pdf_entelgy(
                                datos, pdf_out, LOGO_PATH,
                            )

                    cv_progress.visible = False
                    cv_status_text.value = ""
                    snack("CV procesado y guardado exitosamente.",
                          COLOR_EXITO)
                    mostrar_vista(construir_detalle(candidato_id))
                except Exception as ex:
                    cv_progress.visible = False
                    cv_status_text.value = f"Error: {ex}"
                    page.update()

            threading.Thread(target=_procesar, daemon=True).start()

        def actualizar_cv(_):
            if not tiene_cv:
                snack("Primero suba un CV para procesarlo.", COLOR_ALERTA)
                return
            extra = cv_extra.value.strip()
            if not extra:
                snack("Escriba instrucciones de modificación.", COLOR_ALERTA)
                return
            api_key = db.obtener_config("gemini_api_key")
            modelo = db.obtener_config("gemini_modelo", "gemini-2.5-flash")
            if not api_key:
                snack("Configure la API Key de Gemini.", COLOR_ERROR)
                return

            cv_progress.visible = True
            cv_status_text.value = "Actualizando CV..."
            page.update()

            def _actualizar():
                try:
                    nuevo, err = actualizar_json_con_gemini(
                        c["cv_json"], extra, api_key, modelo,
                    )
                    if err:
                        cv_progress.visible = False
                        cv_status_text.value = err
                        page.update()
                        return

                    db.guardar_cv_json(candidato_id, nuevo)
                    ruta_base = db.obtener_config("ruta_documentos")
                    if ruta_base:
                        carpeta = _carpeta_candidato(c, ruta_base)
                        if carpeta:
                            generar_pdf_entelgy(
                                nuevo,
                                os.path.join(carpeta, "CV_Entelgy.pdf"),
                                LOGO_PATH,
                            )
                    cv_progress.visible = False
                    cv_status_text.value = ""
                    snack("CV actualizado.", COLOR_EXITO)
                    mostrar_vista(construir_detalle(candidato_id))
                except Exception as ex:
                    cv_progress.visible = False
                    cv_status_text.value = f"Error: {ex}"
                    page.update()

            threading.Thread(target=_actualizar, daemon=True).start()

        # ── Historial de estados ──
        try:
            historial = db.obtener_historial(candidato_id)
        except Exception:
            historial = []

        filas_hist = []
        for h in historial:
            fecha_h = h["fecha_cambio"].strftime("%d/%m/%Y %H:%M") \
                if h["fecha_cambio"] else ""
            ant = h["estado_anterior"] or "—"
            filas_hist.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.SWAP_HORIZ, color=COLOR_PRIMARIO,
                            size=18),
                    ft.Text(f"{ant} → {h['estado_nuevo']}", size=13,
                            weight=ft.FontWeight.W_500, expand=True),
                    ft.Text(fecha_h, size=11, color="#999"),
                ]),
                bgcolor="#F9F9F9", border_radius=6, padding=8,
            ))

        # ── Correos ──
        try:
            correos = db.listar_correos(candidato_id)
        except Exception:
            correos = []

        filas_correos = []
        for cor in correos:
            icono = ft.Icons.CHECK_CIRCLE if cor["exitoso"] else ft.Icons.ERROR
            col_ic = COLOR_EXITO if cor["exitoso"] else COLOR_ERROR
            fecha_c = cor["fecha_envio"].strftime("%d/%m/%Y %H:%M") \
                if cor["fecha_envio"] else ""
            filas_correos.append(ft.Container(
                content=ft.Row([
                    ft.Icon(icono, color=col_ic, size=18),
                    ft.Text(cor["asunto"], size=13,
                            weight=ft.FontWeight.W_500, expand=True),
                    ft.Text(fecha_c, size=11, color="#999"),
                ]),
                bgcolor="#F9F9F9", border_radius=6, padding=8,
            ))

        # ── Vista completa ──
        return ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK,
                              icon_color=COLOR_PRIMARIO,
                              on_click=lambda _: mostrar_vista(
                                  construir_lista_candidatos())),
                ft.Text(f"{c['nombre']} {c['apellidos']}", size=22,
                         weight=ft.FontWeight.BOLD),
                ft.Container(expand=True),
                ft.IconButton(icon=ft.Icons.EDIT, icon_color=COLOR_PRIMARIO,
                              tooltip="Editar candidato",
                              on_click=lambda _: mostrar_vista(
                                  construir_formulario_candidato(
                                      candidato_id))),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Text(
                f"Puesto: {puesto}  |  Email: {c['email'] or 'N/A'}"
                f"  |  Tel: {c['telefono'] or 'N/A'}",
                size=14, color="#666",
            ),
            ft.Row([
                ft.Text("Estado: ", size=14, color="#555"),
                ft.Container(
                    content=ft.Text(c["estado"], size=12, color="white",
                                    weight=ft.FontWeight.W_600),
                    bgcolor=col_est, border_radius=10,
                    padding=ft.Padding(10, 3, 10, 3),
                ),
            ]),
            ft.Text(f"Notas: {c['notas']}" if c.get("notas") else "",
                     size=13, color="#555", italic=True),
            ft.Divider(),

            # Cambio de estado
            ft.Row([
                dd_estado,
                ft.Button("Aplicar", bgcolor=COLOR_PRIMARIO,
                                  color="white", on_click=aplicar_estado),
                ft.Container(expand=True),
                ft.IconButton(icon=ft.Icons.DELETE_FOREVER,
                              icon_color=COLOR_ERROR,
                              tooltip="Eliminar candidato",
                              on_click=eliminar_candidato),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(),

            # CV Entelgy
            ft.Text("CV Formato Entelgy", size=16,
                     weight=ft.FontWeight.BOLD, color=COLOR_SECUNDARIO),
            cv_status,
            ft.Row([
                ft.Button(
                    "Subir CV (PDF)" if not tiene_cv else "Reprocesar CV",
                    icon=ft.Icons.UPLOAD_FILE,
                    bgcolor=COLOR_PRIMARIO, color="white",
                    on_click=subir_cv,
                ),
                ft.Button(
                    "Actualizar con IA", icon=ft.Icons.AUTO_FIX_HIGH,
                    bgcolor="#7B1FA2", color="white",
                    on_click=actualizar_cv,
                    visible=tiene_cv,
                ),
                cv_progress,
                cv_status_text,
            ], spacing=10, wrap=True),
            cv_extra,
            ft.Divider(),

            # Documentación
            ft.Text("Documentación recibida", size=16,
                     weight=ft.FontWeight.BOLD, color=COLOR_SECUNDARIO),
            ft.Container(
                content=ft.Column(docs_checks, spacing=4),
                padding=ft.Padding(10, 0, 0, 0),
            ),
            ft.Row([
                ft.Button(
                    "Solicitar documentos por correo",
                    icon=ft.Icons.SEND,
                    bgcolor=COLOR_PRIMARIO, color="white",
                    on_click=lambda _: _solicitar_docs(candidato_id, c, docs),
                ),
            ], spacing=10),
            ft.Divider(),

            # Historial de estados
            ft.Text("Historial de estados", size=16,
                     weight=ft.FontWeight.BOLD, color=COLOR_SECUNDARIO),
            ft.Container(
                content=ft.Column(filas_hist, spacing=6) if filas_hist
                else ft.Text("Sin historial.", size=13, italic=True,
                             color="#999"),
                height=160,
                padding=ft.Padding(10, 0, 0, 0),
            ),
            ft.Divider(),

            # Correos
            ft.Text("Historial de correos", size=16,
                     weight=ft.FontWeight.BOLD, color=COLOR_SECUNDARIO),
            ft.Container(
                content=ft.Column(filas_correos, spacing=6) if filas_correos
                else ft.Text("Sin correos enviados.", size=13, italic=True,
                             color="#999"),
                height=160,
                padding=ft.Padding(10, 0, 0, 0),
            ),
        ], scroll=ft.ScrollMode.AUTO, expand=True)

    # ════════════════════════════════════════════════════════
    #  PUESTOS  (Perfilamiento)
    # ════════════════════════════════════════════════════════

    def construir_puestos():
        if not db.conectado:
            return vista_no_conectado()

        try:
            puestos = db.listar_puestos()
        except Exception as e:
            return ft.Text(f"Error: {e}", color=COLOR_ERROR)

        def tarjeta_puesto(p):
            est_col = COLOR_EXITO if p["estado"] == "Abierto" else "#999"
            try:
                n_cands = len(db.candidatos_por_puesto(p["id"]))
            except Exception:
                n_cands = 0

            return ft.Container(
                content=ft.Row([
                    ft.Column([
                        ft.Text(p["titulo"], size=16,
                                weight=ft.FontWeight.BOLD),
                        ft.Text(f"Área: {p['area'] or '—'}  |  "
                                f"Tecnologías: {p['tecnologias'] or '—'}",
                                size=12, color="#666"),
                        ft.Text(f"Candidatos: {n_cands}", size=12,
                                color="#888"),
                    ], spacing=2, expand=True),
                    ft.Container(
                        content=ft.Text(p["estado"], size=12, color="white",
                                        weight=ft.FontWeight.W_600),
                        bgcolor=est_col, border_radius=12,
                        padding=ft.Padding(12, 4, 12, 4),
                    ),
                    ft.IconButton(
                        icon=ft.Icons.EDIT, icon_color=COLOR_PRIMARIO,
                        on_click=lambda _, pid=p["id"]: mostrar_vista(
                            construir_form_puesto(pid)),
                    ),
                ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                bgcolor=COLOR_TARJETA, border_radius=10, padding=15,
                shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
            )

        cards = [tarjeta_puesto(p) for p in puestos]

        return ft.Column([
            ft.Row([
                ft.Text("Puestos / Perfilamiento", size=22,
                         weight=ft.FontWeight.BOLD, color=COLOR_SECUNDARIO),
                ft.Container(expand=True),
                ft.Button(
                    "Nuevo puesto", icon=ft.Icons.ADD_BUSINESS,
                    bgcolor=COLOR_PRIMARIO, color="white",
                    on_click=lambda _: mostrar_vista(construir_form_puesto()),
                ),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(),
            ft.Column(cards, scroll=ft.ScrollMode.AUTO, expand=True,
                      spacing=8)
            if cards
            else ft.Text("No hay puestos registrados.", size=14,
                         color="#999", italic=True),
        ], expand=True)

    def construir_form_puesto(puesto_id=None):
        if not db.conectado:
            return vista_no_conectado()

        editando = puesto_id is not None
        p = db.obtener_puesto(puesto_id) if editando else {}

        tf_titulo = ft.TextField(label="Título del puesto *", width=400,
                                 value=p.get("titulo", ""))
        tf_area = ft.TextField(label="Área / Departamento", width=280,
                               value=p.get("area", ""))
        tf_desc = ft.TextField(label="Descripción", width=580,
                               multiline=True, min_lines=3, max_lines=6,
                               value=p.get("descripcion", ""))
        tf_req = ft.TextField(label="Requisitos", width=580, multiline=True,
                              min_lines=3, max_lines=6,
                              value=p.get("requisitos", ""))
        tf_tec = ft.TextField(label="Tecnologías", width=580,
                              value=p.get("tecnologias", ""))
        tf_sal_min = ft.TextField(
            label="Salario mínimo", width=180,
            keyboard_type=ft.KeyboardType.NUMBER,
            value=str(p.get("salario_min", 0) or ""),
        )
        tf_sal_max = ft.TextField(
            label="Salario máximo", width=180,
            keyboard_type=ft.KeyboardType.NUMBER,
            value=str(p.get("salario_max", 0) or ""),
        )
        dd_estado = ft.Dropdown(
            label="Estado", width=200,
            value=p.get("estado", "Abierto"),
            options=[ft.dropdown.Option("Abierto"),
                     ft.dropdown.Option("Cerrado")],
        )

        def guardar(_):
            titulo = tf_titulo.value.strip()
            if not titulo:
                snack("El título es obligatorio.", COLOR_ERROR)
                return
            try:
                s_min = float(tf_sal_min.value or 0)
                s_max = float(tf_sal_max.value or 0)
            except ValueError:
                s_min, s_max = 0, 0

            try:
                if editando:
                    db.actualizar_puesto(
                        puesto_id, titulo=titulo,
                        area=tf_area.value.strip(),
                        descripcion=tf_desc.value.strip(),
                        requisitos=tf_req.value.strip(),
                        tecnologias=tf_tec.value.strip(),
                        salario_min=s_min, salario_max=s_max,
                        estado=dd_estado.value,
                    )
                    snack("Puesto actualizado.", COLOR_EXITO)
                else:
                    db.crear_puesto(
                        titulo,
                        area=tf_area.value.strip(),
                        descripcion=tf_desc.value.strip(),
                        requisitos=tf_req.value.strip(),
                        tecnologias=tf_tec.value.strip(),
                        salario_min=s_min, salario_max=s_max,
                    )
                    snack("Puesto creado.", COLOR_EXITO)
                mostrar_vista(construir_puestos())
            except Exception as e:
                snack(f"Error: {e}", COLOR_ERROR)

        def eliminar(_):
            if editando:
                db.eliminar_puesto(puesto_id)
                snack("Puesto eliminado.", COLOR_ALERTA)
                mostrar_vista(construir_puestos())

        titulo_vista = "Editar Puesto" if editando else "Nuevo Puesto"
        return ft.Column([
            ft.Row([
                ft.IconButton(icon=ft.Icons.ARROW_BACK,
                              icon_color=COLOR_PRIMARIO,
                              on_click=lambda _: mostrar_vista(
                                  construir_puestos())),
                ft.Text(titulo_vista, size=22, weight=ft.FontWeight.BOLD,
                         color=COLOR_SECUNDARIO),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(),
            ft.Container(
                content=ft.Column([
                    ft.Row([tf_titulo, tf_area], spacing=20),
                    tf_desc,
                    tf_req,
                    tf_tec,
                    ft.Row([tf_sal_min, tf_sal_max, dd_estado], spacing=20),
                    ft.Container(height=10),
                    ft.Row([
                        ft.TextButton("Cancelar",
                                      on_click=lambda _: mostrar_vista(
                                          construir_puestos())),
                        ft.Button(
                            "Guardar", icon=ft.Icons.SAVE,
                            bgcolor=COLOR_PRIMARIO, color="white",
                            on_click=guardar,
                        ),
                    ] + ([
                        ft.Container(expand=True),
                        ft.Button(
                            "Eliminar", icon=ft.Icons.DELETE,
                            bgcolor=COLOR_ERROR, color="white",
                            on_click=eliminar,
                        ),
                    ] if editando else []), spacing=16),
                ], spacing=16),
                bgcolor=COLOR_TARJETA, border_radius=12, padding=30,
                shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
            ),
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ════════════════════════════════════════════════════════
    #  CONVERTIDOR CV  (Independiente)
    # ════════════════════════════════════════════════════════

    def construir_convertidor():
        if not db.conectado:
            return vista_no_conectado()

        estado_json = {"datos": None}
        ruta_pdf_src = {"path": None}

        lbl_archivo = ft.Text("Ningún archivo seleccionado", size=13,
                              color="#888", italic=True)
        progress = ft.ProgressRing(visible=False, width=24, height=24)
        lbl_status = ft.Text("", size=12)
        resultado_json = ft.TextField(
            label="JSON extraído", multiline=True, min_lines=10,
            max_lines=20, read_only=True, width=700, visible=False,
        )

        tf_extra = ft.TextField(
            label="Datos extra / Instrucciones para la IA",
            width=600, multiline=True, min_lines=2, max_lines=4,
        )

        # Dropdown candidatos
        try:
            cands = db.listar_candidatos()
        except Exception:
            cands = []
        opts_cand = [ft.dropdown.Option(key="", text="— Sin vincular —")]
        for cc in cands:
            opts_cand.append(ft.dropdown.Option(
                key=str(cc["id"]),
                text=f"{cc['nombre']} {cc['apellidos']}",
            ))
        dd_cand = ft.Dropdown(
            label="Vincular a candidato (opcional)", width=400,
            value="", options=opts_cand,
        )

        async def seleccionar_pdf(_):
            archivos = await file_picker.pick_files(
                allowed_extensions=["pdf"],
                dialog_title="Seleccionar CV (PDF)",
            )
            if archivos:
                ruta_pdf_src["path"] = archivos[0].path
                lbl_archivo.value = os.path.basename(archivos[0].path)
                lbl_archivo.italic = False
                page.update()

        def procesar_cv(_):
            if not ruta_pdf_src["path"]:
                snack("Seleccione un archivo PDF primero.", COLOR_ALERTA)
                return
            api_key = db.obtener_config("gemini_api_key")
            modelo = db.obtener_config("gemini_modelo", "gemini-2.5-flash")
            if not api_key:
                snack("Configure la API Key de Gemini.", COLOR_ERROR)
                return

            progress.visible = True
            lbl_status.value = "Procesando con IA..."
            page.update()

            def _run():
                try:
                    texto = extraer_texto_pdf(ruta_pdf_src["path"])
                    if not texto:
                        progress.visible = False
                        lbl_status.value = "Error al leer el PDF."
                        page.update()
                        return

                    datos, err = procesar_con_gemini(
                        texto, api_key, modelo, tf_extra.value.strip(),
                    )
                    if err:
                        progress.visible = False
                        lbl_status.value = err
                        page.update()
                        return

                    estado_json["datos"] = datos
                    resultado_json.value = json.dumps(
                        datos, ensure_ascii=False, indent=2
                    )
                    resultado_json.visible = True
                    progress.visible = False
                    lbl_status.value = "Procesamiento completado."
                    lbl_status.color = COLOR_EXITO

                    # Si hay candidato vinculado
                    cid = dd_cand.value
                    if cid:
                        cid = int(cid)
                        db.guardar_cv_json(cid, datos)
                        cand = db.obtener_candidato(cid)
                        ruta_base = db.obtener_config("ruta_documentos")
                        if ruta_base and cand:
                            carpeta = _carpeta_candidato(cand, ruta_base)
                            if carpeta:
                                shutil.copy2(
                                    ruta_pdf_src["path"],
                                    os.path.join(carpeta, "CV_Original.pdf"),
                                )
                                generar_pdf_entelgy(
                                    datos,
                                    os.path.join(carpeta, "CV_Entelgy.pdf"),
                                    LOGO_PATH,
                                )
                        lbl_status.value += f" Vinculado a candidato #{cid}."

                    page.update()
                except Exception as ex:
                    progress.visible = False
                    lbl_status.value = f"Error: {ex}"
                    page.update()

            threading.Thread(target=_run, daemon=True).start()

        async def guardar_pdf(_):
            if not estado_json["datos"]:
                snack("Primero procese un CV.", COLOR_ALERTA)
                return

            carpeta = await file_picker.get_directory_path(
                dialog_title="Seleccionar carpeta de destino",
            )
            if carpeta:
                pdf_out = os.path.join(carpeta, "CV_Entelgy.pdf")
                try:
                    generar_pdf_entelgy(
                        estado_json["datos"], pdf_out, LOGO_PATH,
                    )
                    snack(f"PDF guardado en: {pdf_out}", COLOR_EXITO)
                except Exception as ex:
                    snack(f"Error: {ex}", COLOR_ERROR)

        def actualizar_cv(_):
            if not estado_json["datos"]:
                snack("Primero procese un CV.", COLOR_ALERTA)
                return
            extra = tf_extra.value.strip()
            if not extra:
                snack("Escriba instrucciones de actualización.", COLOR_ALERTA)
                return
            api_key = db.obtener_config("gemini_api_key")
            modelo = db.obtener_config("gemini_modelo", "gemini-2.5-flash")
            if not api_key:
                snack("Configure la API Key de Gemini.", COLOR_ERROR)
                return

            progress.visible = True
            lbl_status.value = "Actualizando..."
            page.update()

            def _run():
                try:
                    nuevo, err = actualizar_json_con_gemini(
                        estado_json["datos"], extra, api_key, modelo,
                    )
                    if err:
                        progress.visible = False
                        lbl_status.value = err
                        page.update()
                        return
                    estado_json["datos"] = nuevo
                    resultado_json.value = json.dumps(
                        nuevo, ensure_ascii=False, indent=2,
                    )
                    progress.visible = False
                    lbl_status.value = "Actualización completada."
                    lbl_status.color = COLOR_EXITO

                    cid = dd_cand.value
                    if cid:
                        cid = int(cid)
                        db.guardar_cv_json(cid, nuevo)
                        cand = db.obtener_candidato(cid)
                        ruta_base = db.obtener_config("ruta_documentos")
                        if ruta_base and cand:
                            carpeta = _carpeta_candidato(cand, ruta_base)
                            if carpeta:
                                generar_pdf_entelgy(
                                    nuevo,
                                    os.path.join(carpeta, "CV_Entelgy.pdf"),
                                    LOGO_PATH,
                                )

                    page.update()
                except Exception as ex:
                    progress.visible = False
                    lbl_status.value = f"Error: {ex}"
                    page.update()

            threading.Thread(target=_run, daemon=True).start()

        return ft.Column([
            ft.Text("Convertidor de CV a Formato Entelgy", size=22,
                     weight=ft.FontWeight.BOLD, color=COLOR_SECUNDARIO),
            ft.Divider(),
            ft.Container(
                content=ft.Column([
                    ft.Text("1. Seleccionar archivo", size=15,
                            weight=ft.FontWeight.W_600, color="#333"),
                    ft.Row([
                        ft.Button(
                            "Seleccionar PDF", icon=ft.Icons.ATTACH_FILE,
                            bgcolor=COLOR_PRIMARIO, color="white",
                            on_click=seleccionar_pdf,
                        ),
                        lbl_archivo,
                    ], spacing=12),
                    ft.Divider(height=1, color="#EEE"),
                    ft.Text("2. Opciones", size=15,
                            weight=ft.FontWeight.W_600, color="#333"),
                    dd_cand,
                    tf_extra,
                    ft.Divider(height=1, color="#EEE"),
                    ft.Text("3. Procesar", size=15,
                            weight=ft.FontWeight.W_600, color="#333"),
                    ft.Row([
                        ft.Button(
                            "Analizar CV", icon=ft.Icons.AUTO_FIX_HIGH,
                            bgcolor=COLOR_PRIMARIO, color="white",
                            on_click=procesar_cv,
                        ),
                        ft.Button(
                            "Actualizar con IA",
                            icon=ft.Icons.REFRESH,
                            bgcolor="#7B1FA2", color="white",
                            on_click=actualizar_cv,
                        ),
                        ft.Button(
                            "Guardar PDF", icon=ft.Icons.SAVE_ALT,
                            bgcolor=COLOR_EXITO, color="white",
                            on_click=guardar_pdf,
                        ),
                        progress,
                        lbl_status,
                    ], spacing=10, wrap=True),
                    resultado_json,
                ], spacing=14),
                bgcolor=COLOR_TARJETA, border_radius=12, padding=30,
                shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
            ),
        ], expand=True, scroll=ft.ScrollMode.AUTO)

    # ════════════════════════════════════════════════════════
    #  CONFIGURACIÓN
    # ════════════════════════════════════════════════════════

    def construir_configuracion():
        # ── Tab: Base de datos ──
        cfg_local = cargar_config_local()
        tf_db_host = ft.TextField(label="Host", width=300,
                                  value=cfg_local.get("host", "localhost"))
        tf_db_port = ft.TextField(label="Puerto", width=140,
                                  value=cfg_local.get("puerto", "5432"),
                                  keyboard_type=ft.KeyboardType.NUMBER)
        tf_db_name = ft.TextField(label="Nombre BD", width=300,
                                  value=cfg_local.get("nombre", "proyecto_rh"))
        tf_db_user = ft.TextField(label="Usuario", width=300,
                                  value=cfg_local.get("usuario", "postgres"))
        tf_db_pass = ft.TextField(label="Contraseña", width=300,
                                  password=True, can_reveal_password=True,
                                  value=cfg_local.get("password", ""))
        lbl_db_status = ft.Text("", size=12)

        def probar_bd(_):
            ok, msg = db.conectar(
                tf_db_host.value, tf_db_port.value,
                tf_db_name.value, tf_db_user.value, tf_db_pass.value,
            )
            if ok:
                lbl_db_status.value = "Conexión exitosa."
                lbl_db_status.color = COLOR_EXITO
            else:
                lbl_db_status.value = f"Error: {msg}"
                lbl_db_status.color = COLOR_ERROR
            page.update()

        def guardar_bd(_):
            cfg = {
                "host": tf_db_host.value.strip(),
                "puerto": tf_db_port.value.strip(),
                "nombre": tf_db_name.value.strip(),
                "usuario": tf_db_user.value.strip(),
                "password": tf_db_pass.value,
            }
            guardar_config_local(cfg)
            ok, msg = db.conectar(**cfg)
            if ok:
                snack("Conexión guardada y establecida.", COLOR_EXITO)
            else:
                snack(f"Guardado, pero conexión falló: {msg}", COLOR_ALERTA)

        tab_bd = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.STORAGE, color=COLOR_SECUNDARIO,
                            size=22),
                    ft.Text("Conexión a PostgreSQL", size=18,
                            weight=ft.FontWeight.W_600,
                            color=COLOR_SECUNDARIO),
                ], spacing=10),
                ft.Container(
                    content=ft.Column([
                        ft.Row([tf_db_host, tf_db_port], spacing=20),
                        tf_db_name,
                        ft.Row([tf_db_user, tf_db_pass], spacing=20),
                        ft.Container(height=6),
                        ft.Row([
                            ft.Button(
                                "Probar conexión",
                                icon=ft.Icons.WIFI_TETHERING,
                                bgcolor="#7B1FA2", color="white",
                                on_click=probar_bd,
                            ),
                            ft.Button(
                                "Guardar y conectar",
                                icon=ft.Icons.SAVE,
                                bgcolor=COLOR_PRIMARIO, color="white",
                                on_click=guardar_bd,
                            ),
                            lbl_db_status,
                        ], spacing=12),
                    ], spacing=16),
                    bgcolor=COLOR_TARJETA, border_radius=12, padding=30,
                    shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE, color="#888", size=16),
                        ft.Text(
                            "Asegúrese de que PostgreSQL esté ejecutándose "
                            "y la base de datos exista.",
                            size=12, color="#888", expand=True,
                        ),
                    ], spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START),
                    padding=ft.Padding(12, 10, 12, 10), border_radius=8,
                    bgcolor="#E8EAF6",
                ),
            ], spacing=18, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(0, 16, 0, 16), expand=True,
        )

        # ── Tab: SMTP ──
        _cfgs = db.obtener_todas_configs() if db.conectado else {}
        tf_smtp_srv = ft.TextField(
            label="Servidor SMTP", width=300,
            value=_cfgs.get("smtp_servidor", "smtp.gmail.com"),
        )
        tf_smtp_port = ft.TextField(
            label="Puerto", width=140,
            value=_cfgs.get("smtp_puerto", "587"),
            keyboard_type=ft.KeyboardType.NUMBER,
        )
        tf_smtp_email = ft.TextField(
            label="Email de envío", width=400,
            value=_cfgs.get("smtp_email", ""),
        )
        tf_smtp_pass = ft.TextField(
            label="Contraseña / App Password", width=400,
            password=True, can_reveal_password=True,
            value=_cfgs.get("smtp_password", ""),
        )
        tf_smtp_sender = ft.TextField(
            label="Nombre del remitente", width=400,
            value=_cfgs.get("smtp_remitente", "Recursos Humanos"),
        )

        def guardar_smtp(_):
            if not db.conectado:
                snack("Conecte la base de datos primero.", COLOR_ERROR)
                return
            db.guardar_config("smtp_servidor", tf_smtp_srv.value.strip())
            db.guardar_config("smtp_puerto", tf_smtp_port.value.strip())
            db.guardar_config("smtp_email", tf_smtp_email.value.strip())
            db.guardar_config("smtp_password", tf_smtp_pass.value)
            db.guardar_config("smtp_remitente", tf_smtp_sender.value.strip())
            snack("Configuración SMTP guardada.", COLOR_EXITO)

        tab_smtp = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.EMAIL, color=COLOR_SECUNDARIO, size=22),
                    ft.Text("Servidor de Correo (SMTP)", size=18,
                            weight=ft.FontWeight.W_600,
                            color=COLOR_SECUNDARIO),
                ], spacing=10),
                ft.Container(
                    content=ft.Column([
                        ft.Row([tf_smtp_srv, tf_smtp_port], spacing=20),
                        tf_smtp_email,
                        tf_smtp_pass,
                        tf_smtp_sender,
                        ft.Container(height=6),
                        ft.Button(
                            "Guardar configuración", icon=ft.Icons.SAVE,
                            bgcolor=COLOR_PRIMARIO, color="white",
                            on_click=guardar_smtp,
                        ),
                    ], spacing=16),
                    bgcolor=COLOR_TARJETA, border_radius=12, padding=30,
                    shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE, color="#888", size=16),
                        ft.Text(
                            "Para Gmail: Seguridad → Verificación en "
                            "2 pasos → Contraseñas de aplicación.",
                            size=12, color="#888", expand=True,
                        ),
                    ], spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START),
                    padding=ft.Padding(12, 10, 12, 10), border_radius=8,
                    bgcolor="#E8EAF6",
                ),
            ], spacing=18, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(0, 16, 0, 16), expand=True,
        )

        # ── Tab: API Gemini ──
        tf_api_key = ft.TextField(
            label="API Key de Gemini", width=500,
            password=True, can_reveal_password=True,
            value=_cfgs.get("gemini_api_key", ""),
        )
        tf_modelo = ft.TextField(
            label="Modelo", width=300,
            value=_cfgs.get("gemini_modelo", "gemini-2.5-flash"),
        )
        lbl_gemini_status = ft.Text("", size=12)

        def guardar_gemini(_):
            if not db.conectado:
                snack("Conecte la base de datos primero.", COLOR_ERROR)
                return
            db.guardar_config("gemini_api_key", tf_api_key.value.strip())
            db.guardar_config("gemini_modelo", tf_modelo.value.strip())
            snack("Configuración de Gemini guardada.", COLOR_EXITO)

        def probar_gemini(_):
            key = tf_api_key.value.strip()
            if not key:
                lbl_gemini_status.value = "Ingrese una API Key."
                lbl_gemini_status.color = COLOR_ERROR
                page.update()
                return
            if not GEMINI_OK:
                lbl_gemini_status.value = (
                    "Paquete google-genai no instalado."
                )
                lbl_gemini_status.color = COLOR_ERROR
                page.update()
                return
            try:
                from google import genai as _g
                cli = _g.Client(api_key=key)
                cli.models.list()
                lbl_gemini_status.value = "Conexión exitosa."
                lbl_gemini_status.color = COLOR_EXITO
            except Exception as e:
                lbl_gemini_status.value = f"Error: {e}"
                lbl_gemini_status.color = COLOR_ERROR
            page.update()

        tab_gemini = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.SMART_TOY, color=COLOR_SECUNDARIO,
                            size=22),
                    ft.Text("API de Google Gemini", size=18,
                            weight=ft.FontWeight.W_600,
                            color=COLOR_SECUNDARIO),
                ], spacing=10),
                ft.Container(
                    content=ft.Column([
                        tf_api_key,
                        tf_modelo,
                        ft.Container(height=6),
                        ft.Row([
                            ft.Button(
                                "Probar conexión",
                                icon=ft.Icons.WIFI_TETHERING,
                                bgcolor="#7B1FA2", color="white",
                                on_click=probar_gemini,
                            ),
                            ft.Button(
                                "Guardar", icon=ft.Icons.SAVE,
                                bgcolor=COLOR_PRIMARIO, color="white",
                                on_click=guardar_gemini,
                            ),
                            lbl_gemini_status,
                        ], spacing=12),
                    ], spacing=16),
                    bgcolor=COLOR_TARJETA, border_radius=12, padding=30,
                    shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE, color="#888", size=16),
                        ft.Text(
                            "Obtenga su API Key en "
                            "aistudio.google.com/apikey",
                            size=12, color="#888", expand=True,
                        ),
                    ], spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START),
                    padding=ft.Padding(12, 10, 12, 10), border_radius=8,
                    bgcolor="#E8EAF6",
                ),
            ], spacing=18, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(0, 16, 0, 16), expand=True,
        )

        # ── Tab: Ruta de documentos ──
        tf_ruta = ft.TextField(
            label="Ruta base para documentos de candidatos",
            width=500,
            value=_cfgs.get("ruta_documentos", ""),
            hint_text=r"Ej: C:\RH\Documentos_Candidatos",
        )

        async def seleccionar_ruta(_):
            carpeta = await file_picker.get_directory_path(
                dialog_title="Seleccionar carpeta base",
            )
            if carpeta:
                tf_ruta.value = carpeta
                page.update()

        def guardar_ruta(_):
            if not db.conectado:
                snack("Conecte la base de datos primero.", COLOR_ERROR)
                return
            ruta = tf_ruta.value.strip()
            if ruta:
                os.makedirs(ruta, exist_ok=True)
            db.guardar_config("ruta_documentos", ruta)
            snack("Ruta de documentos guardada.", COLOR_EXITO)

        tab_docs = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.FOLDER, color=COLOR_SECUNDARIO,
                            size=22),
                    ft.Text("Almacenamiento de Documentos", size=18,
                            weight=ft.FontWeight.W_600,
                            color=COLOR_SECUNDARIO),
                ], spacing=10),
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            tf_ruta,
                            ft.Button(
                                "Examinar", icon=ft.Icons.FOLDER_OPEN,
                                bgcolor=COLOR_SECUNDARIO, color="white",
                                on_click=seleccionar_ruta,
                            ),
                        ], spacing=12),
                        ft.Container(height=6),
                        ft.Button(
                            "Guardar ruta", icon=ft.Icons.SAVE,
                            bgcolor=COLOR_PRIMARIO, color="white",
                            on_click=guardar_ruta,
                        ),
                    ], spacing=16),
                    bgcolor=COLOR_TARJETA, border_radius=12, padding=30,
                    shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE, color="#888", size=16),
                        ft.Text(
                            "Se creará una subcarpeta por cada candidato "
                            "con el formato: 0001_Apellidos_Nombre",
                            size=12, color="#888", expand=True,
                        ),
                    ], spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START),
                    padding=ft.Padding(12, 10, 12, 10), border_radius=8,
                    bgcolor="#E8EAF6",
                ),
            ], spacing=18, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(0, 16, 0, 16), expand=True,
        )

        # ── Tab: Microsoft 365 ──
        tf_client_id = ft.TextField(
            label="Application (Client) ID", width=500,
            value=_cfgs.get("graph_client_id", ""),
            hint_text="UUID de Azure AD App Registration",
        )
        tf_tenant_id = ft.TextField(
            label="Directory (Tenant) ID", width=500,
            value=_cfgs.get("graph_tenant_id", ""),
            hint_text="UUID de su organización / tenant",
        )
        lbl_m365_status = ft.Text("", size=12)
        lbl_device_code = ft.Text("", size=13, selectable=True)

        _graph_ref = {"client": None}

        def _crear_graph():
            cid = tf_client_id.value.strip()
            tid = tf_tenant_id.value.strip()
            if not cid or not tid:
                return None
            return GraphClient(cid, tid)

        def guardar_m365(_):
            if not db.conectado:
                snack("Conecte la base de datos primero.", COLOR_ERROR)
                return
            db.guardar_config("graph_client_id",
                              tf_client_id.value.strip())
            db.guardar_config("graph_tenant_id",
                              tf_tenant_id.value.strip())
            snack("Configuración Microsoft 365 guardada.", COLOR_EXITO)

        def iniciar_login(_):
            gc = _crear_graph()
            if gc is None:
                lbl_m365_status.value = (
                    "Ingrese Client ID y Tenant ID primero."
                )
                lbl_m365_status.color = COLOR_ERROR
                page.update()
                return

            # Primero verificar si ya hay token
            token = gc.obtener_token()
            if token:
                lbl_m365_status.value = "Ya autenticado."
                lbl_m365_status.color = COLOR_EXITO
                lbl_device_code.value = ""
                _graph_ref["client"] = gc
                page.update()
                return

            flow = gc.iniciar_device_flow()
            if not flow:
                lbl_m365_status.value = "Error al iniciar autenticación."
                lbl_m365_status.color = COLOR_ERROR
                page.update()
                return

            lbl_device_code.value = (
                f"Abra https://microsoft.com/devicelogin\n"
                f"e ingrese el código: {flow['user_code']}"
            )
            lbl_m365_status.value = "Esperando autenticación…"
            lbl_m365_status.color = COLOR_ALERTA
            _graph_ref["client"] = gc
            page.update()

            def _esperar():
                ok, msg = gc.completar_device_flow()
                if ok:
                    lbl_m365_status.value = "Autenticación exitosa."
                    lbl_m365_status.color = COLOR_EXITO
                    lbl_device_code.value = ""
                else:
                    lbl_m365_status.value = f"Error: {msg}"
                    lbl_m365_status.color = COLOR_ERROR
                    lbl_device_code.value = ""
                page.update()

            threading.Thread(target=_esperar, daemon=True).start()

        def cerrar_sesion_m365(_):
            gc = _crear_graph()
            if gc:
                gc.cerrar_sesion()
            lbl_m365_status.value = "Sesión cerrada."
            lbl_m365_status.color = "#888"
            lbl_device_code.value = ""
            _graph_ref["client"] = None
            page.update()

        tab_m365 = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.CLOUD, color=COLOR_SECUNDARIO,
                            size=22),
                    ft.Text("Microsoft 365 (Graph API)", size=18,
                            weight=ft.FontWeight.W_600,
                            color=COLOR_SECUNDARIO),
                ], spacing=10),
                ft.Container(
                    content=ft.Column([
                        tf_client_id,
                        tf_tenant_id,
                        ft.Container(height=6),
                        ft.Row([
                            ft.Button(
                                "Guardar", icon=ft.Icons.SAVE,
                                bgcolor=COLOR_PRIMARIO, color="white",
                                on_click=guardar_m365,
                            ),
                            ft.Button(
                                "Iniciar sesión",
                                icon=ft.Icons.LOGIN,
                                bgcolor="#7B1FA2", color="white",
                                on_click=iniciar_login,
                            ),
                            ft.Button(
                                "Cerrar sesión",
                                icon=ft.Icons.LOGOUT,
                                bgcolor=COLOR_ERROR, color="white",
                                on_click=cerrar_sesion_m365,
                            ),
                        ], spacing=12),
                        lbl_m365_status,
                        lbl_device_code,
                    ], spacing=16),
                    bgcolor=COLOR_TARJETA, border_radius=12, padding=30,
                    shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
                ),
                ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.INFO_OUTLINE, color="#888",
                                size=16),
                        ft.Text(
                            "Registre una app en Azure AD → App registrations "
                            "con permisos Mail.ReadWrite y Mail.Send. "
                            "Configure como 'Public client'.",
                            size=12, color="#888", expand=True,
                        ),
                    ], spacing=8,
                        vertical_alignment=ft.CrossAxisAlignment.START),
                    padding=ft.Padding(12, 10, 12, 10), border_radius=8,
                    bgcolor="#E8EAF6",
                ),
            ], spacing=18, scroll=ft.ScrollMode.AUTO),
            padding=ft.Padding(0, 16, 0, 16), expand=True,
        )

        # ── Selector de tabs ──
        tabs_content = ft.Container(expand=True, content=tab_bd)
        tab_idx = {"v": 0}

        def _tab_btn(label, icon, idx):
            activo = (idx == tab_idx["v"])
            return ft.Container(
                content=ft.Row([
                    ft.Icon(icon,
                            color="white" if activo else COLOR_PRIMARIO,
                            size=18),
                    ft.Text(label,
                            color="white" if activo else COLOR_PRIMARIO,
                            weight=ft.FontWeight.W_600, size=13),
                ], spacing=6, alignment=ft.MainAxisAlignment.CENTER),
                bgcolor=COLOR_PRIMARIO if activo else "#E8EAF6",
                border_radius=8,
                padding=ft.Padding(16, 10, 16, 10),
                on_click=lambda _, i=idx: _sel_tab(i),
            )

        def _sel_tab(idx):
            tab_idx["v"] = idx
            vistas = [tab_bd, tab_smtp, tab_gemini, tab_docs, tab_m365]
            tabs_content.content = vistas[idx]
            # Reconstruir botones
            fila_tabs.controls = [
                _tab_btn("Base de Datos", ft.Icons.STORAGE, 0),
                _tab_btn("Correo SMTP", ft.Icons.EMAIL, 1),
                _tab_btn("API Gemini", ft.Icons.SMART_TOY, 2),
                _tab_btn("Documentos", ft.Icons.FOLDER, 3),
                _tab_btn("Microsoft 365", ft.Icons.CLOUD, 4),
            ]
            page.update()

        fila_tabs = ft.Row([
            _tab_btn("Base de Datos", ft.Icons.STORAGE, 0),
            _tab_btn("Correo SMTP", ft.Icons.EMAIL, 1),
            _tab_btn("API Gemini", ft.Icons.SMART_TOY, 2),
            _tab_btn("Documentos", ft.Icons.FOLDER, 3),
            _tab_btn("Microsoft 365", ft.Icons.CLOUD, 4),
        ], spacing=10)

        return ft.Column([
            ft.Text("Configuración", size=22, weight=ft.FontWeight.BOLD,
                     color=COLOR_SECUNDARIO),
            ft.Divider(height=1, color="#E0E0E0"),
            fila_tabs,
            tabs_content,
        ], spacing=14, expand=True)

    # ════════════════════════════════════════════════════════
    #  DIÁLOGO DE CONEXIÓN (cerrar)
    # ════════════════════════════════════════════════════════

    def _cerrar_dlg(dlg):
        page.pop_dialog()

    # ════════════════════════════════════════════════════════
    #  HUNTING — Búsqueda de candidatos
    # ════════════════════════════════════════════════════════

    PORTALES_BUSQUEDA = [
        {
            "nombre": "LinkedIn",
            "icono": ft.Icons.BUSINESS_CENTER,
            "color": "#0077B5",
            "url": lambda kw, loc: (
                "https://www.linkedin.com/search/results/people/?"
                + urllib.parse.urlencode({"keywords": kw, "origin": "GLOBAL_SEARCH_HEADER"})
            ),
        },
        {
            "nombre": "Indeed",
            "icono": ft.Icons.TRAVEL_EXPLORE,
            "color": "#2164F3",
            "url": lambda kw, loc: (
                "https://www.indeed.com/q-"
                + urllib.parse.quote(kw) + "-jobs.html"
            ),
        },
        {
            "nombre": "CompuTrabajo",
            "icono": ft.Icons.COMPUTER,
            "color": "#FF6D00",
            "url": lambda kw, loc: (
                "https://www.computrabajo.com.pe/trabajo-de-"
                + urllib.parse.quote(kw.lower().replace(' ', '-'))
            ),
        },
        {
            "nombre": "Bumeran",
            "icono": ft.Icons.ROCKET_LAUNCH,
            "color": "#6A1B9A",
            "url": lambda kw, loc: (
                "https://www.bumeran.com.pe/empleos-busqueda-"
                + urllib.parse.quote(kw.lower().replace(' ', '-')) + ".html"
            ),
        },
    ]

    def construir_hunting():
        if not db.conectado:
            return vista_no_conectado()

        # ── Datos para los dropdowns ──
        try:
            puestos = db.listar_puestos()
        except Exception:
            puestos = []

        opciones_puesto = [ft.dropdown.Option(key="", text="— Seleccionar puesto —")]
        for p in puestos:
            opciones_puesto.append(
                ft.dropdown.Option(key=str(p["id"]), text=p["titulo"])
            )

        dd_puesto = ft.Dropdown(
            label="Buscar por puesto", width=400, value="",
            options=opciones_puesto,
        )
        tf_keywords = ft.TextField(
            label="Palabras clave (tecnologías, habilidades, cargo)",
            width=500,
            hint_text="Ej: Python, React, DevOps, Analista de datos",
        )
        tf_ubicacion = ft.TextField(
            label="Ubicación (opcional)", width=250,
            hint_text="Ej: Lima, Perú",
        )

        col_resultados_ext = ft.Column([], spacing=10)
        col_resultados_int = ft.Column([], spacing=8)
        lbl_int_status = ft.Text("", size=12)
        progress_int = ft.ProgressRing(visible=False, width=24, height=24)

        def _obtener_keywords():
            """Construye las palabras clave desde el puesto o el campo libre."""
            kw = tf_keywords.value.strip()
            pid = dd_puesto.value
            if pid:
                p = db.obtener_puesto(int(pid))
                if p:
                    partes = [p["titulo"]]
                    if p.get("tecnologias"):
                        partes.append(p["tecnologias"])
                    if kw:
                        partes.append(kw)
                    return " ".join(partes), p
            return kw, None

        def _auto_fill_puesto(_):
            """Al seleccionar un puesto, auto-rellena keywords."""
            pid = dd_puesto.value
            if pid:
                p = db.obtener_puesto(int(pid))
                if p:
                    partes = []
                    if p.get("tecnologias"):
                        partes.append(p["tecnologias"])
                    if p.get("requisitos"):
                        # Extraer primera línea o primeros 60 chars
                        req = p["requisitos"].split("\n")[0][:60]
                        partes.append(req)
                    tf_keywords.value = ", ".join(partes)
                    page.update()

        dd_puesto.on_select = _auto_fill_puesto

        # ── Búsqueda Externa ──
        def buscar_externo(_):
            kw, _ = _obtener_keywords()
            if not kw:
                snack("Ingrese palabras clave o seleccione un puesto.", COLOR_ALERTA)
                return
            loc = tf_ubicacion.value.strip()

            botones = []
            for portal in PORTALES_BUSQUEDA:
                url = portal["url"](kw, loc)
                botones.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Container(
                                content=ft.Icon(portal["icono"],
                                                color="white", size=24),
                                bgcolor=portal["color"], width=44, height=44,
                                border_radius=10,
                                alignment=ft.Alignment.CENTER,
                            ),
                            ft.Column([
                                ft.Text(portal["nombre"], size=15,
                                        weight=ft.FontWeight.BOLD),
                                ft.Text(f"Buscar: {kw[:50]}{'…' if len(kw)>50 else ''}",
                                        size=11, color="#888"),
                            ], spacing=2, expand=True),
                            ft.IconButton(
                                icon=ft.Icons.OPEN_IN_NEW,
                                icon_color=portal["color"],
                                tooltip=f"Abrir en {portal['nombre']}",
                                url=url,
                            ),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor=COLOR_TARJETA, border_radius=10, padding=14,
                        shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
                    )
                )

            col_resultados_ext.controls = [
                ft.Text("Haga clic en un portal para buscar candidatos externos:",
                         size=13, color="#666", italic=True),
            ] + botones
            page.update()

        # ── Búsqueda Interna (con Gemini) ──
        def buscar_interno(_):
            kw, puesto = _obtener_keywords()
            if not kw:
                snack("Ingrese palabras clave o seleccione un puesto.", COLOR_ALERTA)
                return

            api_key = db.obtener_config("gemini_api_key")
            if not api_key:
                snack("Configure la API Key de Gemini para matching interno.", COLOR_ERROR)
                return

            try:
                candidatos_cv = db.candidatos_con_cv()
            except Exception:
                candidatos_cv = []

            if not candidatos_cv:
                col_resultados_int.controls = [
                    ft.Text("No hay candidatos con CV procesado en la base de datos.",
                             size=13, color="#999", italic=True),
                ]
                page.update()
                return

            progress_int.visible = True
            lbl_int_status.value = f"Analizando {len(candidatos_cv)} candidato(s) con IA…"
            lbl_int_status.color = COLOR_ALERTA
            page.update()

            def _analizar():
                try:
                    from google import genai
                    modelo = db.obtener_config("gemini_modelo", "gemini-2.5-flash")
                    client = genai.Client(api_key=api_key)

                    # Construir perfil de búsqueda
                    perfil = f"Palabras clave: {kw}"
                    if puesto:
                        perfil += f"\nPuesto: {puesto['titulo']}"
                        if puesto.get('descripcion'):
                            perfil += f"\nDescripción: {puesto['descripcion'][:300]}"
                        if puesto.get('requisitos'):
                            perfil += f"\nRequisitos: {puesto['requisitos'][:300]}"
                        if puesto.get('tecnologias'):
                            perfil += f"\nTecnologías: {puesto['tecnologias']}"

                    # Construir resúmenes de candidatos
                    resúmenes = []
                    for c in candidatos_cv:
                        cv = c["cv_json"]
                        if isinstance(cv, str):
                            try:
                                cv = json.loads(cv)
                            except Exception:
                                continue
                        resumen = {
                            "id": c["id"],
                            "nombre": f"{c['nombre']} {c['apellidos']}",
                            "presentacion": cv.get("presentacion", "")[:200],
                            "experiencia": [
                                {"cargo": exp.get("cargo", ""),
                                 "empresa": exp.get("empresa", ""),
                                 "tecnologia": exp.get("tecnologia", "")}
                                for exp in (cv.get("experiencia", []) or [])[:4]
                            ],
                            "estudios": cv.get("estudios_superiores", [])[:2],
                            "idiomas": cv.get("idiomas", []),
                        }
                        resúmenes.append(resumen)

                    prompt = (
                        "Eres un reclutador experto. Analiza los siguientes candidatos "
                        "y evalúa qué tan compatibles son con el perfil buscado.\n\n"
                        f"PERFIL BUSCADO:\n{perfil}\n\n"
                        f"CANDIDATOS:\n{json.dumps(resúmenes, ensure_ascii=False)}\n\n"
                        "Responde SOLO con un JSON array, sin markdown. Cada elemento:\n"
                        '[{"id": <int>, "score": <0-100>, "razon": "<1-2 oraciones>"}]\n'
                        "Ordena de mayor a menor score. Si ningún candidato coincide, "
                        "devuelve el array con scores bajos."
                    )

                    resp = client.models.generate_content(
                        model=modelo, contents=prompt,
                    )
                    texto = resp.text.strip()
                    # Limpiar markdown si viene envuelto
                    if texto.startswith("```"):
                        texto = re.sub(r"^```\w*\n?", "", texto)
                        texto = re.sub(r"\n?```$", "", texto)

                    ranking = json.loads(texto)

                    # Mapear candidatos por ID
                    cand_map = {c["id"]: c for c in candidatos_cv}

                    filas = []
                    for r in ranking:
                        cid = r.get("id")
                        score = r.get("score", 0)
                        razon = r.get("razon", "")
                        c = cand_map.get(cid)
                        if not c:
                            continue

                        # Color del score
                        if score >= 70:
                            score_col = COLOR_EXITO
                        elif score >= 40:
                            score_col = COLOR_ALERTA
                        else:
                            score_col = COLOR_ERROR

                        puesto_txt = c.get("puesto_nombre") or c.get("puesto_texto", "")

                        filas.append(ft.Container(
                            content=ft.Row([
                                ft.Container(
                                    content=ft.Text(
                                        f"{score}%", size=16,
                                        weight=ft.FontWeight.BOLD,
                                        color="white",
                                        text_align=ft.TextAlign.CENTER,
                                    ),
                                    bgcolor=score_col, width=56, height=56,
                                    border_radius=12,
                                    alignment=ft.Alignment.CENTER,
                                ),
                                ft.Column([
                                    ft.Text(
                                        f"{c['nombre']} {c['apellidos']}",
                                        size=15, weight=ft.FontWeight.BOLD,
                                    ),
                                    ft.Text(puesto_txt, size=12, color="#888")
                                    if puesto_txt else ft.Container(),
                                    ft.Text(razon, size=12, color="#555",
                                            italic=True),
                                ], spacing=2, expand=True),
                                ft.Container(
                                    content=ft.Text(
                                        c["estado"], size=10, color="white",
                                        weight=ft.FontWeight.W_600,
                                    ),
                                    bgcolor=ESTADO_COLORES.get(
                                        c["estado"], COLOR_PRIMARIO),
                                    border_radius=10,
                                    padding=ft.Padding(8, 3, 8, 3),
                                ),
                                ft.IconButton(
                                    icon=ft.Icons.ARROW_FORWARD_IOS,
                                    icon_color=COLOR_PRIMARIO,
                                    tooltip="Ver detalle",
                                    on_click=lambda _, cid=cid: mostrar_vista(
                                        construir_detalle(cid)),
                                ),
                            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                            bgcolor=COLOR_TARJETA, border_radius=10, padding=14,
                            shadow=ft.BoxShadow(blur_radius=4, color="#0000001A"),
                        ))

                    if not filas:
                        filas = [ft.Text("Sin coincidencias.", size=13,
                                         color="#999", italic=True)]

                    col_resultados_int.controls = filas
                    progress_int.visible = False
                    lbl_int_status.value = f"{len(ranking)} candidato(s) evaluado(s)."
                    lbl_int_status.color = COLOR_EXITO
                    page.update()

                except Exception as ex:
                    progress_int.visible = False
                    lbl_int_status.value = f"Error: {ex}"
                    lbl_int_status.color = COLOR_ERROR
                    page.update()

            threading.Thread(target=_analizar, daemon=True).start()

        # ── Vista completa de Hunting ──
        return ft.Column([
            ft.Row([
                ft.Text("Hunting — Búsqueda de Talento", size=22,
                         weight=ft.FontWeight.BOLD, color=COLOR_SECUNDARIO),
            ]),
            ft.Divider(height=1, color="#E0E0E0"),

            # Panel de búsqueda
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.MANAGE_SEARCH,
                                color=COLOR_SECUNDARIO, size=22),
                        ft.Text("Criterios de búsqueda", size=16,
                                weight=ft.FontWeight.W_600,
                                color=COLOR_SECUNDARIO),
                    ], spacing=10),
                    dd_puesto,
                    tf_keywords,
                    tf_ubicacion,
                    ft.Container(height=4),
                    ft.Row([
                        ft.Button(
                            "Buscar en portales externos",
                            icon=ft.Icons.TRAVEL_EXPLORE,
                            bgcolor=COLOR_PRIMARIO, color="white",
                            on_click=buscar_externo,
                        ),
                        ft.Button(
                            "Buscar en candidatos internos (IA)",
                            icon=ft.Icons.SMART_TOY,
                            bgcolor="#7B1FA2", color="white",
                            on_click=buscar_interno,
                        ),
                        progress_int,
                        lbl_int_status,
                    ], spacing=12, wrap=True),
                ], spacing=14),
                bgcolor=COLOR_TARJETA, border_radius=12, padding=24,
                shadow=ft.BoxShadow(blur_radius=6, spread_radius=1,
                                    color="#0000000F"),
            ),

            # Resultados externos
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.PUBLIC, color=COLOR_PRIMARIO,
                                size=20),
                        ft.Text("Portales Externos", size=15,
                                weight=ft.FontWeight.W_600, color="#333"),
                    ], spacing=8),
                    col_resultados_ext,
                ], spacing=10),
                visible=True,
            ),

            # Resultados internos
            ft.Container(
                content=ft.Column([
                    ft.Row([
                        ft.Icon(ft.Icons.PEOPLE_ALT, color="#7B1FA2",
                                size=20),
                        ft.Text("Candidatos Internos — Ranking IA", size=15,
                                weight=ft.FontWeight.W_600, color="#333"),
                    ], spacing=8),
                    col_resultados_int,
                ], spacing=10),
                visible=True,
            ),
        ], spacing=16, expand=True, scroll=ft.ScrollMode.AUTO)

    # ════════════════════════════════════════════════════════
    #  BANDEJA DE CORREOS
    # ════════════════════════════════════════════════════════

    def construir_bandeja():
        if not db.conectado:
            return vista_no_conectado()

        cfgs = db.obtener_todas_configs()
        client_id = cfgs.get("graph_client_id", "").strip()
        tenant_id = cfgs.get("graph_tenant_id", "").strip()

        if not client_id or not tenant_id:
            return ft.Column([
                ft.Text("Bandeja de Correos", size=22,
                         weight=ft.FontWeight.BOLD,
                         color=COLOR_SECUNDARIO),
                ft.Divider(),
                ft.Text("Configure Microsoft 365 en Configuración.",
                         color=COLOR_ERROR, size=14),
                ft.Button("Ir a Configuración",
                          icon=ft.Icons.SETTINGS,
                          bgcolor=COLOR_PRIMARIO, color="white",
                          on_click=lambda _: (
                              setattr(rail, "selected_index", 6),
                              mostrar_vista(construir_configuracion()),
                          )),
            ], spacing=14, expand=True)

        gc = GraphClient(client_id, tenant_id)
        if not gc.autenticado():
            return ft.Column([
                ft.Text("Bandeja de Correos", size=22,
                         weight=ft.FontWeight.BOLD,
                         color=COLOR_SECUNDARIO),
                ft.Divider(),
                ft.Text("Inicie sesión en Microsoft 365 primero.",
                         color=COLOR_ERROR, size=14),
                ft.Button("Ir a Configuración",
                          icon=ft.Icons.SETTINGS,
                          bgcolor=COLOR_PRIMARIO, color="white",
                          on_click=lambda _: (
                              setattr(rail, "selected_index", 6),
                              mostrar_vista(construir_configuracion()),
                          )),
            ], spacing=14, expand=True)

        lbl_status = ft.Text("", size=12)
        col_correos = ft.Column([], spacing=8, scroll=ft.ScrollMode.AUTO,
                                expand=True)
        lbl_resultado = ft.Text("", size=12)

        def _cargar_correos(_=None):
            lbl_status.value = "Buscando correos…"
            lbl_status.color = COLOR_ALERTA
            page.update()

            def _buscar():
                correos = gc.buscar_correos_rh(solo_no_leidos=False)
                filas = []
                for co in correos:
                    icono = ft.Icons.MARK_EMAIL_UNREAD if not co["leido"] \
                        else ft.Icons.MARK_EMAIL_READ
                    color_icono = COLOR_PRIMARIO if not co["leido"] \
                        else "#999"
                    adj_txt = "📎" if co["tiene_adjuntos"] else ""

                    filas.append(ft.Container(
                        content=ft.Row([
                            ft.Icon(icono, color=color_icono, size=20),
                            ft.Column([
                                ft.Text(co["asunto"], size=13,
                                        weight=ft.FontWeight.W_600
                                        if not co["leido"]
                                        else ft.FontWeight.NORMAL),
                                ft.Text(f"{co['remitente_nombre']} "
                                        f"<{co['remitente']}>  •  "
                                        f"{co['fecha'][:16]}",
                                        size=11, color="#777"),
                            ], spacing=2, expand=True),
                            ft.Text(adj_txt, size=16),
                            ft.Text(f"RH-{co['candidato_id']:04d}",
                                    size=12, color=COLOR_PRIMARIO,
                                    weight=ft.FontWeight.W_600),
                        ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        bgcolor=COLOR_TARJETA if co["leido"]
                        else "#E3F2FD",
                        border_radius=8, padding=12,
                        shadow=ft.BoxShadow(blur_radius=2,
                                            color="#0000000D"),
                    ))

                col_correos.controls = filas if filas else [
                    ft.Text("No se encontraron correos con [RH-XXXX].",
                             size=13, color="#999", italic=True),
                ]
                lbl_status.value = f"{len(correos)} correo(s) encontrado(s)."
                lbl_status.color = COLOR_EXITO if correos else "#999"
                page.update()

            threading.Thread(target=_buscar, daemon=True).start()

        def _procesar_todos(_):
            ruta_base = cfgs.get("ruta_documentos", "").strip()
            if not ruta_base:
                snack("Configure la ruta de documentos primero.",
                      COLOR_ERROR)
                return
            lbl_resultado.value = "Procesando correos entrantes…"
            lbl_resultado.color = COLOR_ALERTA
            page.update()

            def _proc():
                resultados = procesar_correos_entrantes(
                    gc, ruta_base, db
                )
                procesados = sum(
                    1 for r in resultados if r.get("status") == "procesado"
                )
                ignorados = sum(
                    1 for r in resultados if r.get("status") == "ignorado"
                )
                adjuntos_total = sum(
                    len(r.get("adjuntos", []))
                    for r in resultados
                    if r.get("status") == "procesado"
                )

                lbl_resultado.value = (
                    f"Listo: {procesados} procesados, "
                    f"{ignorados} ignorados, "
                    f"{adjuntos_total} adjuntos descargados."
                )
                lbl_resultado.color = COLOR_EXITO
                page.update()
                _cargar_correos()

            threading.Thread(target=_proc, daemon=True).start()

        _cargar_correos()

        return ft.Column([
            ft.Row([
                ft.Text("Bandeja de Correos", size=22,
                         weight=ft.FontWeight.BOLD,
                         color=COLOR_SECUNDARIO),
                ft.Container(expand=True),
                ft.Button("Actualizar",
                          icon=ft.Icons.REFRESH,
                          bgcolor=COLOR_PRIMARIO, color="white",
                          on_click=_cargar_correos),
                ft.Button("Procesar no leídos",
                          icon=ft.Icons.DOWNLOAD,
                          bgcolor="#7B1FA2", color="white",
                          on_click=_procesar_todos),
            ], vertical_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Divider(height=1, color="#E0E0E0"),
            ft.Row([lbl_status, ft.Container(expand=True),
                    lbl_resultado], spacing=10),
            col_correos,
        ], spacing=10, expand=True)

    # ════════════════════════════════════════════════════════
    #  NAVIGATION RAIL + LAYOUT
    # ════════════════════════════════════════════════════════

    def cambiar_vista(e):
        idx = e.control.selected_index
        builders = {
            0: construir_dashboard,
            1: construir_lista_candidatos,
            2: construir_puestos,
            3: construir_convertidor,
            4: construir_hunting,
            5: construir_bandeja,
            6: construir_configuracion,
        }
        builder = builders.get(idx, construir_dashboard)
        contenido.content = builder()
        page.update()

    rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=100,
        min_extended_width=200,
        group_alignment=-0.9,
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.DASHBOARD,
                                         label="Panel"),
            ft.NavigationRailDestination(icon=ft.Icons.PEOPLE,
                                         label="Candidatos"),
            ft.NavigationRailDestination(icon=ft.Icons.WORK,
                                         label="Puestos"),
            ft.NavigationRailDestination(icon=ft.Icons.DESCRIPTION,
                                         label="Convertidor CV"),
            ft.NavigationRailDestination(icon=ft.Icons.MANAGE_SEARCH,
                                         label="Hunting"),
            ft.NavigationRailDestination(icon=ft.Icons.INBOX,
                                         label="Bandeja"),
            ft.NavigationRailDestination(icon=ft.Icons.SETTINGS,
                                         label="Configuración"),
        ],
        on_change=cambiar_vista,
        bgcolor=COLOR_TARJETA,
    )

    # ── Conexión inicial ──
    cfg = cargar_config_local()
    ok, _ = db.conectar(
        cfg.get("host", "localhost"),
        cfg.get("puerto", "5432"),
        cfg.get("nombre", "proyecto_rh"),
        cfg.get("usuario", "postgres"),
        cfg.get("password", ""),
    )

    contenido.content = construir_dashboard()

    if not ok:
        contenido.content = construir_configuracion()
        rail.selected_index = 6

    # Montar el FilePicker como servicio antes de page.add()
    page.services.append(file_picker)

    page.add(
        ft.Row([rail, ft.VerticalDivider(width=1), contenido], expand=True)
    )


ft.run(main)
