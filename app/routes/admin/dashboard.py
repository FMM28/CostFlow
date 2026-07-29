from flask import Blueprint, render_template
from flask_login import current_user, login_required

from app.auth.decorators import role_required
from app.services.orden_service import OrdenService
from app.services.proveedor_service import ProveedorService
from app.services.proveedores import SiclikService

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.get("/")
@login_required
@role_required("admin")
def dashboard():
    ultimas_ordenes = OrdenService.get_latests_by_user(
        current_user.id_usuario, limite=10
    )

    actualizaciones_catalogo = ProveedorService.get_latests_updates()

    sesion_siclik_activa = SiclikService.sesion_activa()

    return render_template(
        "admin/dashboard.html",
        ultimas_ordenes=ultimas_ordenes,
        actualizaciones_catalogo=actualizaciones_catalogo,
        sesion_siclik_activa=sesion_siclik_activa,
    )
