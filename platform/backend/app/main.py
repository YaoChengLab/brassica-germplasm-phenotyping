
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError as PydanticValidationError
from contextlib import asynccontextmanager
import logging
import time
import uvicorn
from sqlalchemy import text
import redis

from .config.settings import settings
from .api.v1.api import api_router
from .models.base import Base
from .config.database import engine
from .core.exceptions import DatabaseError, ValidationError
from .core.middleware import IPWhitelistMiddleware

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Lifespan event handler (replaces on_event)
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup events
    logger.info(f"Starting {settings.project_name} v{settings.version}")
    
    # Create database tables
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables created/verified successfully")
    except Exception as e:
        logger.error(f"Failed to create database tables: {e}")
        raise
    
    # Application ready
    yield
    
    # Shutdown events
    logger.info("Shutting down Plant Phenotyping Platform API")

# Create FastAPI app with lifespan
app = FastAPI(
    title=settings.project_name,
    version=settings.version,
    description="API for plant phenotyping database queries and analysis",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url=f"{settings.api_v1_prefix}/docs",
    redoc_url=f"{settings.api_v1_prefix}/redoc",
    lifespan=lifespan
)

# Custom CORS middleware to allow IP range
from fastapi.middleware.cors import CORSMiddleware
import re

# CORS middleware with custom origin validation
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1):(3000|8000)$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# Server-side IP whitelist (must be added after CORS so CORS preflight is also gated)
app.add_middleware(
    IPWhitelistMiddleware,
    allowed_ip_cidrs=settings.allowed_ip_cidrs,
    exempt_paths=settings.ip_whitelist_exempt_paths,
)

# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    logger.warning(f"Validation error: {exc}")
    
    # Convert validation errors to JSON-serializable format
    error_details = []
    for error in exc.errors():
        # Extract field name from location tuple
        field = " -> ".join(str(loc) for loc in error["loc"] if loc != "body")
        message = error["msg"]
        
        # Handle ValueError context properly
        if "ctx" in error and "error" in error["ctx"]:
            if isinstance(error["ctx"]["error"], ValueError):
                message = str(error["ctx"]["error"])
        
        error_details.append({
            "field": field,
            "message": message,
            "type": error["type"]
        })
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "details": error_details,
            "timestamp": time.time()
        }
    )

@app.exception_handler(DatabaseError)
async def database_exception_handler(request: Request, exc: DatabaseError):
    logger.error(f"Database error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Database Error",
            "message": str(exc),
            "timestamp": time.time()
        }
    )

@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError):
    logger.warning(f"Custom validation error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Validation Error",
            "message": str(exc),
            "timestamp": time.time()
        }
    )

@app.exception_handler(PydanticValidationError)
async def pydantic_validation_exception_handler(request: Request, exc: PydanticValidationError):
    logger.warning(f"Pydantic validation error: {exc}")
    errors = []
    for error in exc.errors():
        field = error.get('loc', ['unknown'])[-1]
        msg = error.get('msg', 'Validation failed')
        errors.append(f"{field}: {msg}")

    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Validation Error",
            "message": "; ".join(errors),
            "timestamp": time.time()
        }
    )

# Include routers
app.include_router(api_router, prefix=settings.api_v1_prefix)

# Root endpoint
@app.get("/")
async def root():
    return {
        "message": "Plant Phenotyping Platform API",
        "version": settings.version,
        "docs": f"{settings.api_v1_prefix}/docs",
        "status": "running"
    }

@app.get("/health")
async def health_check():
    # Basic health check
    health_status = {
        "status": "healthy",
        "timestamp": time.time(),
        "version": settings.version,
        "services": {}
    }
    
    # Check database connectivity
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        health_status["services"]["database"] = "healthy"
    except Exception as e:
        health_status["services"]["database"] = f"unhealthy: {str(e)}"
        health_status["status"] = "degraded"
    
    # Check Redis connectivity (if Redis is configured)
    try:
        redis_client = redis.Redis.from_url(settings.redis_url)
        redis_client.ping()
        health_status["services"]["redis"] = "healthy"
    except Exception as e:
        health_status["services"]["redis"] = f"unhealthy: {str(e)}"
        if health_status["status"] == "healthy":
            health_status["status"] = "degraded"
    
    return health_status

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )