from flask import Blueprint, redirect, url_for
from flask_login import current_user, login_required

main_bp = Blueprint("main", __name__)

@main_bp.route("/")
def index():
    if current_user.is_authenticated:
        if current_user.role == "admin":
            return redirect(url_for("admin.dashboard"))
        else:
            return redirect(url_for("ventas.dashboard"))
    return redirect(url_for("auth.login"))


@main_bp.get("/calcular-conversion/<float:precio>/<from_currency>")
@login_required
def calcular_conversion_MXN(precio, from_currency):
    from app.services.CurrencyService import CurrencyService

    try:
        equivalencia = CurrencyService.calcular_conversion_MXN(precio, from_currency)
        return {"equivalencia": equivalencia[0]}, 200
    except Exception as e:
        return {"error": str(e)}, 500