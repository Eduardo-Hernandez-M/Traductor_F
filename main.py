from fastapi import FastAPI, Depends, HTTPException, Security, Request
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from transformers import pipeline
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import html
import os

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Traductor Seguro ES-ZH")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGIN", "*")],
    allow_credentials=True,
    allow_methods=["POST"],
    allow_headers=["*"],
)

API_KEY = os.getenv("SECRET_API_KEY", "llave-desarrollo-local")
api_key_header = APIKeyHeader(name="X-API-KEY", auto_error=False)

def verify_api_key(api_key_header: str = Security(api_key_header)):
    if api_key_header != API_KEY:
        raise HTTPException(status_code=403, detail="Acceso denegado. Credenciales inválidas.")
    return api_key_header

# Carga de modelos locales (Helsinki-NLP)
translator_es_zh = pipeline("translation", model="Helsinki-NLP/opus-mt-es-zh")
translator_zh_es = pipeline("translation", model="Helsinki-NLP/opus-mt-zh-es")

class TranslationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    direction: str = Field(..., pattern="^(es-zh|zh-es)$")

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response

@app.post("/translate")
@limiter.limit("10/minute")
async def translate_text(request: Request, payload: TranslationRequest, api_key: str = Depends(verify_api_key)):
    safe_text = html.escape(payload.text.strip())
    
    try:
        if payload.direction == "es-zh":
            result = translator_es_zh(safe_text)[0]['translation_text']
        else:
            result = translator_zh_es(safe_text)[0]['translation_text']
            
        return {"original": safe_text, "translation": result}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail="Error interno en el motor de traducción.")