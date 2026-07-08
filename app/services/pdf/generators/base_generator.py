from io import BytesIO
from pathlib import Path

from flask import current_app, render_template
from weasyprint import CSS, HTML


class BaseGenerator:
    template = "pdf/base.html"

    def generar(self, cotizacion):

        context = self.get_context(cotizacion)

        css_path = Path(current_app.static_folder) / "css" / "pdf.css"

        html = render_template(
            self.template,
            **context,
        )

        pdf = HTML(
            string=html,
            base_url=current_app.root_path,
        ).write_pdf(stylesheets=[CSS(filename=str(css_path))])

        return BytesIO(pdf)

    def get_context(self, cotizacion):

        vendedor = cotizacion.vendedor

        logo = Path(current_app.static_folder) / "img" / "logo.png"
        font_path = Path(current_app.static_folder) / "fonts" / "Sansation_Bold.ttf"

        return {
            "cotizacion": cotizacion,
            "logo_path": logo.as_uri(),
            "font_path": font_path.as_uri(),
            "vendedor": vendedor,
            **self.extra_context(cotizacion),
        }

    def extra_context(self, cotizacion):
        return {}