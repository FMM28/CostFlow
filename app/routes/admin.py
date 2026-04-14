from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.services.user_service import UserService
from app.auth.decorators import role_required


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.get("/")
@login_required
@role_required("admin")
def dashboard():
    return render_template("admin/dashboard.html")


@admin_bp.get("/users")
@login_required
@role_required("admin")
def users():
    usuarios = UserService.get_all_users()
    return render_template("admin/users.html", usuarios=usuarios)


@admin_bp.get("/users/create")
@login_required
@role_required("admin")
def create_user():
    return render_template("admin/form_user.html", usuario=None)


@admin_bp.post("/users/create")
@login_required
@role_required("admin")
def create_user_post():
    user, error = UserService.create_user(
        username=request.form.get("username"),
        email=request.form.get("email"),
        role=request.form.get("role"),
        nombre=request.form.get("nombre"),
        ap_paterno=request.form.get("ap_paterno"),
        ap_materno=request.form.get("ap_materno"),
        password=request.form.get("password"),
    )

    if error:
        flash(error, "danger")
        return render_template("admin/form_user.html", usuario=None)

    flash("Usuario creado correctamente", "success")
    return redirect(url_for("admin.users"))


@admin_bp.get("/users/<int:user_id>/edit")
@login_required
@role_required("admin")
def edit_user(user_id):
    usuario = UserService.get_user_by_id(user_id)

    if not usuario:
        flash("Usuario no encontrado", "danger")
        return redirect(url_for("admin.users"))

    return render_template("admin/form_user.html", usuario=usuario)


@admin_bp.post("/users/<int:user_id>/edit")
@login_required
@role_required("admin")
def edit_user_post(user_id):
    user, error = UserService.update_user(
        user_id=user_id,
        username=request.form.get("username"),
        email=request.form.get("email"),
        role=request.form.get("role"),
        nombre=request.form.get("nombre"),
        ap_paterno=request.form.get("ap_paterno"),
        ap_materno=request.form.get("ap_materno"),
        password=request.form.get("password"),
    )

    if error:
        flash(error, "danger")
        usuario = UserService.get_user_by_id(user_id)
        return render_template("admin/form_user.html", usuario=usuario)

    flash("Usuario actualizado correctamente", "success")
    return redirect(url_for("admin.users"))


@admin_bp.post("/users/<int:user_id>/delete")
@login_required
@role_required("admin")
def delete_user(user_id):
    success, error = UserService.delete_user(user_id)

    if error:
        flash(error, "danger")
    else:
        flash("Usuario eliminado correctamente", "success")

    return redirect(url_for("admin.users"))