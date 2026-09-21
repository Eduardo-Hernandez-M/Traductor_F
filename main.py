from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from passlib.context import CryptContext
from deep_translator import GoogleTranslator
import jwt
from datetime import datetime, timedelta
import sqlite3
import asyncio
import os

# --- CONFIGURACIÓN DE SEGURIDAD ---
SECRET_KEY = os.getenv("JWT_SECRET", "super-llave-secreta-traductor")
ALGORITHM = "HS256"
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

def init_db():
    conn = sqlite3.connect("usuarios.db")
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (username TEXT UNIQUE, password TEXT)''')
    
    c.execute("SELECT * FROM users WHERE username = 'admin'")
    if not c.fetchone():
        hashed_pw = pwd_context.hash("Traductor.2026")
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", ('admin', hashed_pw))
        
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

class UserAuth(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=6)

class TranslationRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)
    direction: str = Field(..., pattern="^(es-zh|zh-es)$")

def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="La sesión ha expirado.")
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
def register(request: Request, user: UserAuth, current_user: str = Depends(verify_token)):
    # Capa de seguridad adicional: Solo el admin puede usar este endpoint
    if current_user != "admin":
        raise HTTPException(status_code=403, detail="Solo el administrador puede crear usuarios.")
        
    if user.username.lower() == "admin":
        raise HTTPException(status_code=400, detail="Este nombre está reservado.")
        
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
    return {"message": f"Usuario '{user.username}' creado con éxito."}

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
    
    token = jwt.encode({"sub": user.username, "exp": datetime.utcnow() + timedelta(hours=24)}, SECRET_KEY, algorithm=ALGORITHM)
    return {"access_token": token, "username": user.username}

@app.post("/translate")
@limiter.limit("15/minute")
async def translate_text(request: Request, payload: TranslationRequest, current_user: str = Depends(verify_token)):
    safe_text = payload.text.strip()
    
    # Configuración de idiomas para deep-translator
    source_lang = 'es' if payload.direction == "es-zh" else 'zh-CN'
    target_lang = 'zh-CN' if payload.direction == "es-zh" else 'es'
    
    try:
        # Se ejecuta en un hilo separado para no bloquear el servidor asíncrono
        traductor = GoogleTranslator(source=source_lang, target=target_lang)
        resultado = await asyncio.to_thread(traductor.translate, safe_text)
        return {"original": safe_text, "translation": resultado}
    except Exception as e:
        raise HTTPException(status_code=500, detail="Fallo en el motor de traducción interno.")