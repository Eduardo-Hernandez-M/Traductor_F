from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from passlib.context import CryptContext
import jwt
from datetime import datetime, timedelta
import sqlite3
import httpx
import html
import os

# --- CONFIGURACIÓN DE SEGURIDAD Y BASE DE DATOS ---
SECRET_KEY = os.getenv("JWT_SECRET", "super-llave-secreta-traductor")
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def init_db():
    """Inicializa la base de datos SQLite local dentro de la app"""
    conn = sqlite3.connect("usuarios.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT UNIQUE, password TEXT)''')
    conn.commit()
    conn.close()

init_db()

# --- CONFIGURACIÓN DE FASTAPI ---
limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="Traductor Profesional Seguro")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODELOS DE DATOS ---
class UserAuth(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)

class TranslationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    direction: str = Field(..., pattern="^(es-zh|zh-es)$")

# --- VALIDACIÓN DE TOKEN ---
def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="La sesión ha expirado. Inicia sesión de nuevo.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token inválido.")

# --- ENDPOINTS ---
@app.get("/", response_class=HTMLResponse)
async def serve_webpage():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>Error: Archivo index.html no encontrado</h1>"

@app.post("/register")
@limiter.limit("5/minute")
def register(request: Request, user: UserAuth):
    conn = sqlite3.connect("usuarios.db")
    c = conn.cursor()
    hashed_pw = pwd_context.hash(user.password)
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (user.username, hashed_pw))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="El usuario ya existe.")
    conn.close()
    return {"message": "Usuario creado exitosamente. Ya puedes iniciar sesión."}

@app.post("/login")
@limiter.limit("10/minute")
def login(request: Request, user: UserAuth):
    conn = sqlite3.connect("usuarios.db")
    c = conn.cursor()
    c.execute("SELECT password FROM users WHERE username = ?", (user.username,))
    row = c.fetchone()
    conn.close()
    
    if not row or not pwd_context.verify(user.password, row[0]):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    
    # Crea un token válido por 24 horas
    token = jwt.encode({"sub": user.username, "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "username": user.username}

@app.post("/translate")
@limiter.limit("15/minute")
async def translate_text(request: Request, payload: TranslationRequest, current_user: str = Depends(verify_token)):
    safe_text = html.escape(payload.text.strip())
    # Corrección de códigos de idioma para evitar errores de servidor
    langpair = "es|zh-CN" if payload.direction == "es-zh" else "zh-CN|es"
    url = "https://api.mymemory.translated.net/get"
    params = {"q": safe_text, "langpair": langpair}
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, params=params, timeout=15.0)
            if response.status_code != 200:
                raise HTTPException(status_code=502, detail="El motor de traducción está saturado. Intenta más tarde.")
                
            data = response.json()
            if data.get("responseStatus") == 200:
                return {"original": safe_text, "translation": data["responseData"]["translatedText"]}
            else:
                raise HTTPException(status_code=500, detail=f"Error del traductor: {data.get('responseDetails')}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Tiempo de espera agotado. El texto es muy largo o la red está lenta.")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Fallo de conexión interno.")