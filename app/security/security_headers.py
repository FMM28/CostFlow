from flask import Flask


def configure_security_headers(app: Flask):

    @app.after_request
    def add_security_headers(response):
        # Evita que la página pueda cargarse dentro de un iframe
        response.headers["X-Frame-Options"] = "DENY"

        # Evita MIME Sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Limita la información enviada en el Referer
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Deshabilita APIs del navegador que no utilizas
        response.headers[
            "Permissions-Policy"
        ] = (
            "camera=(), "
            "microphone=(), "
            "geolocation=(), "
            "payment=(), "
            "usb=(), "
            "fullscreen=(self)"
        )

        # Fuerza HTTPS (solo cuando realmente estés usando HTTPS)
        if not app.debug:
            response.headers[
                "Strict-Transport-Security"
            ] = (
                "max-age=31536000;"
                " includeSubDomains;"
                " preload"
            )

        return response