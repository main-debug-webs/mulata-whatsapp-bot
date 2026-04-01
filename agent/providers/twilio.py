import os
import logging
import base64
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")


class ProveedorTwilio(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando Twilio."""

    def __init__(self):
        self.account_sid = os.getenv("TWILIO_ACCOUNT_SID")
        self.auth_token = os.getenv("TWILIO_AUTH_TOKEN")
        self.phone_number = os.getenv("TWILIO_PHONE_NUMBER")

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload form-encoded de Twilio."""
        content_type = request.headers.get("content-type", "")
        logger.info(f"Twilio webhook - Content-Type: {content_type}")

        # Intentar parsear como form data
        try:
            form = await request.form()
            logger.info(f"Twilio webhook - Form keys: {list(form.keys())}")
        except Exception as e:
            # Si no es form data, intentar como JSON
            logger.warning(f"Error parseando form data: {e}")
            try:
                body = await request.json()
                logger.info(f"Twilio webhook - JSON body: {body}")
            except Exception:
                body_raw = await request.body()
                logger.info(f"Twilio webhook - Raw body: {body_raw[:500]}")
            return []

        texto = form.get("Body", "")
        telefono = form.get("From", "").replace("whatsapp:", "")
        mensaje_id = form.get("MessageSid", "")
        logger.info(f"Twilio webhook - From: {form.get('From', '')}, Body: {texto}, SID: {mensaje_id}")

        if not texto:
            return []

        return [MensajeEntrante(
            telefono=telefono,
            texto=texto,
            mensaje_id=mensaje_id,
            es_propio=False,
        )]

    async def enviar_mensaje(self, telefono: str, mensaje: str, imagen_url: str = None) -> bool:
        """Envía mensaje via Twilio API. Opcionalmente incluye una imagen."""
        if not all([self.account_sid, self.auth_token, self.phone_number]):
            logger.warning("Variables de Twilio no configuradas")
            return False

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        auth = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode()).decode()
        headers = {"Authorization": f"Basic {auth}"}
        data = {
            "From": f"whatsapp:{self.phone_number}",
            "To": f"whatsapp:{telefono}",
            "Body": mensaje,
        }

        if imagen_url:
            data["MediaUrl"] = imagen_url

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(url, data=data, headers=headers)
                if r.status_code != 201:
                    logger.error(f"Error Twilio: {r.status_code} — {r.text}")
                    return False
                return True
        except Exception as e:
            logger.error(f"Error enviando mensaje Twilio: {e}")
            return False
