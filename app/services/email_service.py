import smtplib

from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app


class EmailService:
    @staticmethod
    def send(destinatario: str, asunto: str, html: str):
        mensaje = MIMEMultipart("alternative")

        mensaje["From"] = current_app.config["GMAIL_EMAIL"]
        mensaje["To"] = destinatario
        mensaje["Subject"] = asunto

        mensaje.attach(MIMEText(html, "html", "utf-8"))

        with smtplib.SMTP("smtp.gmail.com", 587) as servidor:
            servidor.starttls()

            servidor.login(
                current_app.config["GMAIL_EMAIL"],
                current_app.config["GMAIL_PASSWORD"],
            )

            servidor.send_message(mensaje)
