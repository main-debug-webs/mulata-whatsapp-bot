import logging
import asyncio
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from agent.providers import obtener_proveedor
from agent.memory import inicializar_db, guardar_mensaje, obtener_historial
from agent.brain import generar_respuesta
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agentkit")

proveedor = obtener_proveedor()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Inicializa la BD al arrancar."""
    await inicializar_db()
    logger.info("Base de datos inicializada")
    logger.info(f"Proveedor: {proveedor.__class__.__name__}")
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
    """Validación GET del webhook (solo Meta la requiere)."""
    respuesta = await proveedor.validar_webhook(request)
    if respuesta is not None:
        return PlainTextResponse(str(respuesta))
    return {"status": "ok"}


@app.post("/webhook")
async def webhook_post(request: Request):
    """Recibe mensajes de WhatsApp y genera respuestas."""
    try:
        mensajes = await proveedor.parsear_webhook(request)

        for msg in mensajes:
            if msg.es_propio or not msg.texto:
                continue

            logger.info(f"Mensaje de {msg.telefono}: {msg.texto}")

            # Obtener historial
            historial = await obtener_historial(msg.telefono)

            # Generar respuesta
            respuesta = await generar_respuesta(msg.texto, historial)

            # Guardar en BD
            await guardar_mensaje(msg.telefono, "user", msg.texto)
            await guardar_mensaje(msg.telefono, "assistant", respuesta)

            # Enviar respuesta
            exito = await proveedor.enviar_mensaje(msg.telefono, respuesta)
            if not exito:
                logger.error(f"Error al enviar respuesta a {msg.telefono}")

        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
