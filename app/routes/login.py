from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user
from app.services.user_service import UserService

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = UserService.get_user_by_username(username)

        if user and user.check_password(password):
            login_user(user)

            if user.role == "admin":
                return redirect(url_for("admin.dashboard"))
            else:
                return redirect(url_for("ventas.dashboard"))

        flash("Usuario o contraseña incorrectos", "danger")

    return render_template("login/login.html")


@auth_bp.route("/logout")
def logout():
    logout_user()
    flash("Sesión cerrada", "info")
    return redirect(url_for("auth.login"))