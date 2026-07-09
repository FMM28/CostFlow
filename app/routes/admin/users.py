from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
)
from flask_login import login_required
from app.auth.decorators import role_required
from app.services.user_service import UserService
from werkzeug.utils import secure_filename
import os

users_bp = Blueprint("users", __name__)


@users_bp.get("/")
@login_required
@role_required("admin")
def index():
    usuarios = UserService.get_all()
    return render_template("admin/users.html", usuarios=usuarios)


@users_bp.get("/create")
@login_required
@role_required("admin")
def create():
    return render_template(
        "admin/form_user.html",
        usuario=None,
        url_action=url_for("admin.users.create_post"),
        url_cancel=url_for("admin.users.index"),
    )


@users_bp.post("/create")
@login_required
@role_required("admin")
def create_post():
    # Obtener el archivo de firma
    firma_file = request.files.get("firma_file")
    url_firma = None
    filepath = None

    # Procesar la firma si existe
    if firma_file and firma_file.filename != "":
        allowed_extensions = {"png", "jpg", "jpeg", "gif", "pdf"}
        if (
            "." in firma_file.filename
            and firma_file.filename.rsplit(".", 1)[1].lower() in allowed_extensions
        ):
            # Generar nombre seguro para el archivo
            filename = secure_filename(
                f"{request.form.get('username')}_{firma_file.filename}"
            )

            # Crear directorio si no existe
            upload_folder = current_app.config.get("UPLOAD_FOLDER")
            os.makedirs(upload_folder, exist_ok=True)

            # Guardar archivo
            filepath = os.path.join(upload_folder, filename)
            firma_file.save(filepath)

            # Generar URL para el archivo
            url_firma = url_for(
                "static", filename=f"uploads/firmas/{filename}", _external=True
            )
        else:
            flash(
                "El formato de archivo no es válido. Formatos permitidos: PNG, JPG, JPEG, GIF, PDF",
                "danger",
            )
            return render_template("admin/form_user.html", usuario=None)

    user, error = UserService.create(
        username=request.form.get("username"),
        email=request.form.get("email"),
        numero=request.form.get("numero"),
        puesto=request.form.get("puesto"),
        role=request.form.get("role"),
        nombre=request.form.get("nombre"),
        ap_paterno=request.form.get("ap_paterno"),
        ap_materno=request.form.get("ap_materno"),
        password=request.form.get("password"),
        url_firma=url_firma,
    )

    if error:
        if url_firma and filepath and os.path.exists(filepath):
            os.remove(filepath)
        flash(error, "danger")
        return render_template("admin/form_user.html", usuario=None)

    flash("Usuario creado correctamente", "success")
    return redirect(url_for("admin.users.index"))


@users_bp.get("/<int:user_id>/edit")
@login_required
@role_required("admin")
def edit(user_id):
    usuario = UserService.get_by_id(user_id)

    if not usuario:
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("admin.users.index"))

    return render_template(
        "admin/form_user.html",
        usuario=usuario,
        url_action=url_for("admin.users.edit_post", user_id=usuario.id),
        url_cancel=url_for("admin.users.index"),
    )


@users_bp.post("/<int:user_id>/edit")
@login_required
@role_required("admin")
def edit_post(user_id):
    user = UserService.get_by_id(user_id)
    if not user:
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("admin.users.index"))

    firma_file = request.files.get("firma_file")
    url_firma = user.url_firma
    old_filepath = None
    filepath = None

    # Procesar la nueva firma si se subió un archivo
    if firma_file and firma_file.filename != "":
        allowed_extensions = {"png", "jpg", "jpeg", "gif", "pdf"}
        if (
            "." in firma_file.filename
            and firma_file.filename.rsplit(".", 1)[1].lower() in allowed_extensions
        ):
            # Generar nombre seguro para el archivo
            filename = secure_filename(f"{user.username}_{firma_file.filename}")

            # Crear directorio si no existe
            upload_folder = current_app.config.get("UPLOAD_FOLDER")
            os.makedirs(upload_folder, exist_ok=True)

            # Guardar archivo
            filepath = os.path.join(upload_folder, filename)
            firma_file.save(filepath)

            # Generar URL para el archivo
            url_firma = url_for(
                "static", filename=f"uploads/firmas/{filename}", _external=True
            )

            # Guardar la ruta del archivo anterior para eliminarlo después
            if user.url_firma:
                old_filename = user.url_firma.split("/")[-1]
                old_filepath = os.path.join(upload_folder, old_filename)
        else:
            flash(
                "El formato de archivo no es válido. Formatos permitidos: PNG, JPG, JPEG, GIF, PDF",
                "danger",
            )
            return render_template("admin/form_user.html", usuario=user)

    user, error = UserService.update(
        id_usuario=user_id,
        username=request.form.get("username"),
        email=request.form.get("email"),
        role=request.form.get("role"),
        nombre=request.form.get("nombre"),
        ap_paterno=request.form.get("ap_paterno"),
        ap_materno=request.form.get("ap_materno"),
        password=request.form.get("password"),
        numero=request.form.get("numero"),
        puesto=request.form.get("puesto"),
        url_firma=url_firma,
    )

    if error:
        if (
            firma_file
            and firma_file.filename != ""
            and filepath
            and os.path.exists(filepath)
        ):
            os.remove(filepath)
        flash(error, "danger")
        usuario = UserService.get_by_id(user_id)
        return render_template("admin/form_user.html", usuario=usuario)

    if old_filepath and os.path.exists(old_filepath):
        try:
            os.remove(old_filepath)
        except Exception as e:
            print(f"Error al eliminar archivo antiguo: {e}")

    flash("Usuario actualizado correctamente", "success")
    return redirect(url_for("admin.users.index"))


@users_bp.post("/<int:user_id>/delete")
@login_required
@role_required("admin")
def delete(user_id):
    success, error = UserService.soft_delete(user_id)

    if error:
        flash(error, "danger")
    else:
        flash("Usuario eliminado correctamente", "success")

    return redirect(url_for("admin.users.index"))
