from app.extensions import login_manager
from app.models.usuario import Usuario

@login_manager.user_loader
def load_user(user_id):
    return Usuario.query.filter(
        Usuario.id_usuario == int(user_id),
        Usuario.deleted_at.is_(None)
    ).first()