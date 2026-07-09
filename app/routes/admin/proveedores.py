from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from app.auth.decorators import role_required
from app.services.proveedores.SiclikService import SiclikService
from app.services.proveedores import (
    ImportacionDigitalService,
    ArrobaComputerService,
    PYPRService,
)
from werkzeug.utils import secure_filename
import tempfile
import os

proveedores_bp = Blueprint("proveedores", __name__)


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
    return render_template(
        "admin/siclik.html", autenticado=SiclikService.sesion_activa()
    )


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
