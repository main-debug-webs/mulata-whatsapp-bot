import os
import logging
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import PlainTextResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# Cargar .env SOLO si existe (desarrollo local)
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agentkit")

# Log de diagnóstico: mostrar variables clave al importar
logger.info(f"WHATSAPP_PROVIDER: {os.environ.get('WHATSAPP_PROVIDER', 'NO DEFINIDO')}")
logger.info(f"PORT: {os.environ.get('PORT', 'NO DEFINIDO')}")

from agent.providers import obtener_proveedor
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.brain import generar_respuesta

proveedor = obtener_proveedor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la BD al arrancar."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Proveedor activo: {proveedor.__class__.__name__}")
    yield


app = FastAPI(
    title="Camila - Mulata Joyería",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Endpoint raíz — requerido por Railway para health checks."""
    return {"status": "ok", "service": "agentkit"}


@app.get("/health")
async def health_check():
    """Endpoint de salud alternativo."""
    return {"status": "healthy"}


@app.get("/webhook")
async def webhook_get(request: Request):
    """Validación GET del webhook (requerido por Meta Cloud API)."""
    respuesta = await proveedor.validar_webhook(request)
    if respuesta is not None:
        # Meta espera el challenge como texto plano, NO JSON
        return PlainTextResponse(str(respuesta))
    return PlainTextResponse("Verification failed", status_code=403)


@app.post("/webhook")
async def webhook_post(request: Request):
    """Recibe mensajes de WhatsApp y genera respuestas."""
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            logger.info(f"Mensaje de {msg.telefono}: {msg.texto}")

            historial = await obtener_historial(msg.telefono)
            respuesta = await generar_respuesta(msg.texto, historial)

            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)

            exito = await proveedor.enviar_mensaje(msg.telefono, respuesta)
            if not exito:
                logger.error(f"Error al enviar respuesta a {msg.telefono}")

        # Twilio espera TwiML (XML) como respuesta, no JSON
        return Response(content="<Response></Response>", media_type="text/xml")
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}", exc_info=True)
        return Response(content="<Response></Response>", media_type="text/xml")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
