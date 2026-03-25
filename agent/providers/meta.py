# agent/providers/meta.py — Adaptador para Meta WhatsApp Cloud API
# Generado por AgentKit

import os
import logging
import httpx
from fastapi import Request
from agent.providers.base import ProveedorWhatsApp, MensajeEntrante

logger = logging.getLogger("agentkit")


class ProveedorMeta(ProveedorWhatsApp):
    """Proveedor de WhatsApp usando la API oficial de Meta (Cloud API)."""

    def __init__(self):
        self.access_token = os.environ.get("META_ACCESS_TOKEN", "")
        self.phone_number_id = os.environ.get("META_PHONE_NUMBER_ID", "")
        self.verify_token = os.environ.get("META_VERIFY_TOKEN", "")
        self.api_version = "v21.0"

        # Log de diagnóstico al inicializar
        logger.info(f"META_ACCESS_TOKEN configurado: {bool(self.access_token)} (len={len(self.access_token)})")
        logger.info(f"META_PHONE_NUMBER_ID: {self.phone_number_id or 'NO CONFIGURADO'}")
        logger.info(f"META_VERIFY_TOKEN: {self.verify_token or 'NO CONFIGURADO'}")

        # Listar todas las variables META_ disponibles
        meta_vars = {k: v[:20] + "..." for k, v in os.environ.items() if k.startswith("META_")}
        logger.info(f"Variables META_ en entorno: {meta_vars}")

    async def validar_webhook(self, request: Request) -> dict | int | None:
        """Meta requiere verificación GET con hub.verify_token."""
        params = request.query_params
        mode = params.get("hub.mode")
        token = params.get("hub.verify_token")
        challenge = params.get("hub.challenge")

        logger.info(f"Webhook GET - mode={mode}, challenge={challenge}")
        logger.info(f"Webhook GET - token recibido: {token}")
        logger.info(f"Webhook GET - token esperado: {self.verify_token}")

        if not self.verify_token:
            logger.error("META_VERIFY_TOKEN no está configurado en el entorno")
            return None

        if mode == "subscribe" and token == self.verify_token:
            logger.info(f"Webhook verificado correctamente, challenge={challenge}")
            return int(challenge)

        logger.warning(f"Verificación fallida - tokens no coinciden")
        return None

    async def parsear_webhook(self, request: Request) -> list[MensajeEntrante]:
        """Parsea el payload anidado de Meta Cloud API."""
        body = await request.json()
        mensajes = []

        for entry in body.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                for msg in value.get("messages", []):
                    if msg.get("type") == "text":
                        mensajes.append(MensajeEntrante(
                            telefono=msg.get("from", ""),
                            texto=msg.get("text", {}).get("body", ""),
                            mensaje_id=msg.get("id", ""),
                            es_propio=False,
                        ))

        return mensajes

    async def enviar_mensaje(self, telefono: str, mensaje: str) -> bool:
        """Envía mensaje via Meta WhatsApp Cloud API."""
        logger.info(f"Intentando enviar mensaje a {telefono}")
        logger.info(f"ACCESS_TOKEN presente: {bool(self.access_token)} (len={len(self.access_token)})")
        logger.info(f"PHONE_NUMBER_ID: {self.phone_number_id}")

        if not self.access_token or not self.phone_number_id:
            logger.error("META_ACCESS_TOKEN o META_PHONE_NUMBER_ID no configurados - no se puede enviar")
            return False

        url = f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": telefono,
            "type": "text",
            "text": {"body": mensaje},
        }

        logger.info(f"Enviando a URL: {url}")
        logger.info(f"Payload: to={telefono}, mensaje={mensaje[:50]}...")

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(url, json=payload, headers=headers)
                logger.info(f"Respuesta Meta API: status={r.status_code}")
                logger.info(f"Respuesta Meta API body: {r.text}")
                if r.status_code != 200:
                    logger.error(f"Error Meta API: {r.status_code} — {r.text}")
                return r.status_code == 200
        except Exception as e:
            logger.error(f"Excepción al enviar mensaje: {e}", exc_info=True)
            return False
