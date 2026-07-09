from flask import Blueprint, render_template
from flask_login import login_required
from app.auth.decorators import role_required

dashboard_bp = Blueprint("dashboard", __name__)

@dashboard_bp.get("/")
@login_required
@role_required("admin")
def dashboard():
    return render_template("admin/dashboard.html")