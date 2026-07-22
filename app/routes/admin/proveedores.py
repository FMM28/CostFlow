from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.auth.decorators import role_required
from app.services.proveedores.SiclikService import SiclikService
from app.services.proveedor_credenciales_service import ProveedorCredencialesService
from app.services.proveedor_service import ProveedorService
from app.services.proveedores import (
    ImportacionDigitalService,
    ArrobaComputerService,
    PYPRService,
)
from werkzeug.utils import secure_filename
import tempfile
import os

proveedores_bp = Blueprint("proveedores", __name__)

# Configuración de proveedores
PROVEEDORES_CONFIG = {
    "exel": {
        "nombre": "EXEL",
        "campos": [
            {"name": "usuario", "label": "Usuario", "type": "text", "oculto": False},
            {
                "name": "password",
                "label": "Password",
                "type": "password",
                "oculto": True,
            },
        ],
    },
    "gloma": {
        "nombre": "GLOMA",
        "campos": [
            {
                "name": "usuario",
                "label": "Usuario (email)",
                "type": "text",
                "oculto": False,
            },
            {
                "name": "password",
                "label": "Password",
                "type": "password",
                "oculto": True,
            },
        ],
    },
    "techsmart": {
        "nombre": "TECHSMART",
        "campos": [
            {"name": "rfc", "label": "RFC", "type": "text", "oculto": False},
            {"name": "usuario", "label": "Usuario", "type": "text", "oculto": False},
            {
                "name": "password",
                "label": "Password",
                "type": "password",
                "oculto": True,
            },
        ],
    },
    "syscom": {
        "nombre": "SYSCOM",
        "campos": [
            {
                "name": "client_id",
                "label": "Client ID",
                "type": "text",
                "oculto": False,
            },
            {
                "name": "client_secret",
                "label": "Client Secret",
                "type": "password",
                "oculto": True,
            },
        ],
    },
    "ingram": {
        "nombre": "INGRAM",
        "campos": [
            {
                "name": "host",
                "label": "Host (url)",
                "type": "text",
                "oculto": False,
            },
            {
                "name": "port",
                "label": "Port",
                "type": "text",
                "oculto": False,
            },
            {
                "name": "username",
                "label": "Username",
                "type": "text",
                "oculto": False,
            },
            {
                "name": "password",
                "label": "Password",
                "type": "password",
                "oculto": True,
            },
        ],
    },
    "cva": {
        "nombre": "CVA",
        "campos": [
            {"name": "cliente", "label": "Cliente", "type": "text", "oculto": False},
        ],
    },
}


@proveedores_bp.get("/")
@login_required
@role_required("admin")
def index():
    return render_template(
        "admin/config_proveedores.html", siclik_activo=SiclikService.sesion_activa()
    )


@proveedores_bp.get("/siclik")
@login_required
@role_required("admin")
def siclik():
    credenciales = ProveedorCredencialesService.obtener("SICLIK") or {}
    return render_template(
        "admin/siclik.html",
        autenticado=SiclikService.sesion_activa(),
        email=credenciales.get("email", ""),
        customer_id=credenciales.get("customer_id", ""),
    )


@proveedores_bp.post("/siclik")
@login_required
@role_required("admin")
def siclik_update():
    email = request.form.get("email", "").strip()
    customer_id = request.form.get("customer_id", "").strip()
    password = request.form.get("password", "").strip()

    if not email or not customer_id or not password:
        flash("Todos los campos son requeridos", "error")
        return redirect(url_for("admin.proveedores.siclik"))

    proveedor = ProveedorService.search_by_nombre("SICLIK")
    if proveedor is None:
        flash("El proveedor SICLIK no existe", "error")
        return redirect(url_for("admin.proveedores.siclik"))

    credenciales = {
        "email": email,
        "customer_id": customer_id,
        "password": password,
    }

    success = ProveedorCredencialesService.guardar(
        id_proveedor=proveedor.id_proveedor,
        credenciales=credenciales,
        updated_by=current_user.id_usuario,
    )

    if not success:
        flash("No se pudieron actualizar las credenciales.", "error")
        return redirect(url_for("admin.proveedores.siclik"))

    flash("Se actualizaron correctamente las credenciales de SICLIK.", "success")
    return redirect(url_for("admin.proveedores.siclik"))


@proveedores_bp.post("/siclik/iniciar")
@login_required
@role_required("admin")
def siclik_iniciar():
    try:
        SiclikService.iniciar_autenticacion()
        return jsonify({"success": True, "message": "Código enviado por WhatsApp"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@proveedores_bp.post("/siclik/confirmar")
@login_required
@role_required("admin")
def siclik_confirmar():
    try:
        codigo = request.json.get("codigo")
        if not codigo:
            return jsonify({"success": False, "message": "Código requerido"}), 400

        SiclikService.confirmar_autenticacion(codigo)
        return jsonify({"success": True, "message": "Siclik autenticado"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@proveedores_bp.get("/<proveedor>")
@login_required
@role_required("admin")
def ver_proveedor(proveedor):
    """Vista genérica para proveedores con credenciales."""
    proveedor = proveedor.lower()

    if proveedor == "siclik":
        return redirect(url_for("admin.proveedores.siclik"))

    if proveedor in ["importacion-digital", "arroba-computer", "pypr"]:
        flash("Este proveedor usa carga de Excel", "error")
        return redirect(url_for("admin.proveedores.index"))

    if proveedor not in PROVEEDORES_CONFIG:
        flash("Proveedor no encontrado", "error")
        return redirect(url_for("admin.proveedores.index"))

    config = PROVEEDORES_CONFIG[proveedor]
    credenciales = ProveedorCredencialesService.obtener(config["nombre"]) or {}

    campos = []
    for campo in config["campos"]:
        campos.append(
            {
                "name": campo["name"],
                "label": campo["label"],
                "type": campo["type"],
                "value": ""
                if campo.get("oculto", False)
                else credenciales.get(campo["name"], ""),
            }
        )

    return render_template(
        "admin/credenciales.html",
        nombre=config["nombre"],
        url_post=url_for(
            "admin.proveedores.actualizar_credenciales", proveedor=proveedor
        ),
        campos=campos,
    )


@proveedores_bp.post("/<proveedor>/credenciales")
@login_required
@role_required("admin")
def actualizar_credenciales(proveedor):
    """Endpoint genérico para actualizar credenciales."""
    proveedor = proveedor.lower()

    if proveedor == "siclik":
        return redirect(url_for("admin.proveedores.siclik"))

    if proveedor in ["importacion-digital", "arroba-computer", "pypr"]:
        flash("Este proveedor no utiliza credenciales", "error")
        return redirect(url_for("admin.proveedores.index"))

    if proveedor not in PROVEEDORES_CONFIG:
        flash("Proveedor no válido", "error")
        return redirect(url_for("admin.proveedores.index"))

    config = PROVEEDORES_CONFIG[proveedor]

    # Recolectar y validar todos los campos
    credenciales = {}
    for campo in config["campos"]:
        valor = request.form.get(campo["name"], "").strip()
        if not valor:
            flash(f"El campo {campo['label']} es requerido", "error")
            return redirect(
                url_for("admin.proveedores.ver_proveedor", proveedor=proveedor)
            )
        credenciales[campo["name"]] = valor

    # Obtener proveedor de la base de datos
    proveedor_db = ProveedorService.search_by_nombre(config["nombre"])
    if proveedor_db is None:
        proveedor_bd, error = ProveedorService.create({"nombre": config["nombre"]})

    # Guardar credenciales
    success = ProveedorCredencialesService.guardar(
        id_proveedor=proveedor_db.id_proveedor,
        credenciales=credenciales,
        updated_by=current_user.id_usuario,
    )

    if not success:
        flash("No se pudieron actualizar las credenciales.", "error")
        return redirect(url_for("admin.proveedores.ver_proveedor", proveedor=proveedor))

    flash(
        f"Se actualizaron correctamente las credenciales de {config['nombre']}.",
        "success",
    )
    return redirect(url_for("admin.proveedores.ver_proveedor", proveedor=proveedor))


@proveedores_bp.get("/importacion-digital")
@login_required
@role_required("admin")
def importacion_digital():
    return render_template(
        "admin/carga_excel.html",
        proveedor="Importación Digital",
        direccion_subida=url_for("admin.proveedores.importacion_digital_excel"),
        mensaje="",
    )


@proveedores_bp.post("/importacion-digital/subir")
@login_required
@role_required("admin")
def importacion_digital_excel():
    redireccion = url_for("admin.proveedores.importacion_digital")
    archivo = request.files.get("excel")

    if not archivo or archivo.filename == "":
        flash("Selecciona un archivo.", "error")
        return redirect(redireccion)

    if not archivo.filename.lower().endswith((".xlsx", ".xls")):
        flash("Archivo no válido.", "error")
        return redirect(redireccion)

    ruta_temporal = None
    try:
        extension = os.path.splitext(secure_filename(archivo.filename))[1]
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temp:
            archivo.save(temp.name)
            ruta_temporal = temp.name

        cantidad = ImportacionDigitalService.subir_excel(ruta_temporal)
        flash(f"{cantidad} productos importados.", "success")
    except Exception as e:
        flash(str(e), "error")
    finally:
        if ruta_temporal and os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)

    return redirect(redireccion)


@proveedores_bp.get("/arroba-computer")
@login_required
@role_required("admin")
def arroba_computer():
    return render_template(
        "admin/carga_excel.html",
        proveedor="Arroba Computer",
        direccion_subida=url_for("admin.proveedores.arroba_computer_excel"),
        mensaje="Antes de importar el catálogo, verifica y actualiza el valor del tipo de cambio en el archivo Excel.",
    )


@proveedores_bp.post("/arroba-computer/subir")
@login_required
@role_required("admin")
def arroba_computer_excel():
    redireccion = url_for("admin.proveedores.arroba_computer")
    archivo = request.files.get("excel")

    if not archivo or archivo.filename == "":
        flash("Selecciona un archivo.", "error")
        return redirect(redireccion)

    if not archivo.filename.lower().endswith((".xlsx", ".xls")):
        flash("Archivo no válido.", "error")
        return redirect(redireccion)

    ruta_temporal = None
    try:
        extension = os.path.splitext(secure_filename(archivo.filename))[1]
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temp:
            archivo.save(temp.name)
            ruta_temporal = temp.name

        cantidad = ArrobaComputerService.subir_excel(ruta_temporal)
        flash(f"{cantidad} productos importados.", "success")
    except Exception as e:
        flash(str(e), "error")
    finally:
        if ruta_temporal and os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)

    return redirect(redireccion)


@proveedores_bp.get("/pypr")
@login_required
@role_required("admin")
def pypr():
    return render_template(
        "admin/carga_excel.html",
        proveedor="Procesadores y Partes en retail PYPR",
        direccion_subida=url_for("admin.proveedores.pypr_excel"),
        mensaje="",
    )


@proveedores_bp.post("/pypr/subir")
@login_required
@role_required("admin")
def pypr_excel():
    redireccion = url_for("admin.proveedores.pypr")
    archivo = request.files.get("excel")

    if not archivo or archivo.filename == "":
        flash("Selecciona un archivo.", "error")
        return redirect(redireccion)

    if not archivo.filename.lower().endswith((".xlsx", ".xls")):
        flash("Archivo no válido.", "error")
        return redirect(redireccion)

    ruta_temporal = None
    try:
        extension = os.path.splitext(secure_filename(archivo.filename))[1]
        with tempfile.NamedTemporaryFile(suffix=extension, delete=False) as temp:
            archivo.save(temp.name)
            ruta_temporal = temp.name

        cantidad = PYPRService.subir_excel(ruta_temporal)
        flash(f"{cantidad} productos importados.", "success")
    except Exception as e:
        flash(str(e), "error")
    finally:
        if ruta_temporal and os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)

    return redirect(redireccion)
