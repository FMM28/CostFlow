from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required
from app.auth.decorators import role_required
from app.services.departamento_unam_service import DepartamentoUNAMService

unam_bp = Blueprint("unam", __name__)


@unam_bp.get("/departamentos")
@login_required
@role_required("admin")
def departamentos():
    departamentos = DepartamentoUNAMService.get_all()
    return render_template(
        "admin/departamentos.html",
        departamentos=departamentos,
    )


@unam_bp.get("/departamentos/create")
@login_required
@role_required("admin")
def departamento_create():
    return render_template(
        "admin/departamentos_form.html",
        departamento=None,
    )


@unam_bp.post("/departamentos/create")
@login_required
@role_required("admin")
def departamento_create_post():
    nombre = request.form.get("nombre", "").strip()
    prefijo = request.form.get("prefijo", "").strip()
    puntos_entrega = [
        punto.strip()
        for punto in request.form.getlist("puntos_entrega")
        if punto.strip()
    ]

    DepartamentoUNAMService.create(
        nombre=nombre,
        prefijo=prefijo,
        puntos_entrega=puntos_entrega,
    )

    flash("Departamento creado correctamente.", "success")
    return redirect(url_for("admin.unam.departamentos"))


@unam_bp.get("/departamentos/<int:id_departamento>/edit")
@login_required
@role_required("admin")
def departamento_edit(id_departamento):
    departamento = DepartamentoUNAMService.get_by_id(id_departamento)

    if departamento is None:
        flash("Departamento no encontrado.", "danger")
        return redirect(url_for("admin.unam.departamentos"))

    return render_template(
        "admin/departamentos_form.html",
        departamento=departamento,
    )


@unam_bp.post("/departamentos/<int:id_departamento>/update")
@login_required
@role_required("admin")
def departamento_update(id_departamento):
    nombre = request.form.get("nombre", "").strip()
    prefijo = request.form.get("prefijo", "").strip()
    puntos_entrega = [
        punto.strip()
        for punto in request.form.getlist("puntos_entrega")
        if punto.strip()
    ]

    departamento = DepartamentoUNAMService.update(
        id_departamento=id_departamento,
        nombre=nombre,
        prefijo=prefijo,
        puntos_entrega=puntos_entrega,
    )

    if departamento is None:
        flash("Departamento no encontrado.", "danger")
    else:
        flash("Departamento actualizado correctamente.", "success")

    return redirect(url_for("admin.unam.departamentos"))


@unam_bp.post("/departamentos/<int:id_departamento>/delete")
@login_required
@role_required("admin")
def departamento_delete(id_departamento):
    if DepartamentoUNAMService.delete(id_departamento):
        flash("Departamento eliminado correctamente.", "success")
    else:
        flash("Departamento no encontrado.", "danger")

    return redirect(url_for("admin.unam.departamentos"))
