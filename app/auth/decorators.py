from functools import wraps
from flask import redirect, url_for, abort
from flask_login import current_user

def role_required(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for("auth.login"))

            if current_user.role != role:
                abort(403)

            return f(*args, **kwargs)
        return wrapper
    return decorator
