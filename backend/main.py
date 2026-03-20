import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from controller.event_controller import router as event_router
from controller.transcribe_controller import router as transcribe_router
from controller.assistant_controller import router as assistant_router
from controller.user_controller import router as auth_router
from controller.google_auth_controller import router as google_auth_router
from database import init_db
from exceptions.validation_exception_handler import validation_exception_handler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Calendar AI API", version="1.0.0")

logger.info("Starting Calendar AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("CORS middleware configured")

app.add_exception_handler(RequestValidationError, validation_exception_handler)


app.include_router(auth_router)
logger.info("Authentication routes included")


app.include_router(event_router)
logger.info("Event routes included")


try:
    init_db()
    logger.info("Database initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize database: {e}", exc_info=True)
    raise

app.include_router(transcribe_router)
app.include_router(assistant_router)
app.include_router(google_auth_router)


@app.get("/")
async def root():
    logger.info("Root endpoint accessed")
    return {"message": "Calendar AI API is running!"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
