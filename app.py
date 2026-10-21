import json
import http.client
import ssl
import re
import urllib.request
import os
import hashlib
import time
from bs4 import BeautifulSoup
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from typing import List, Optional, Any, Dict
import uvicorn

app = FastAPI(title="Luxa.Ai V6.5 Multi-User")

API_KEY = "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"

FREE_MODELS = [
    "minimax/minimax-m3.1-flash:free",
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "nvidia/nemotron-3.5-lightning:free",
    "poolside/laguna-s-2.1:free",
]

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "database.json")
HTML_PATH = os.path.join(BASE_DIR, "index.html")

DEFAULT_SETTINGS = {
    "theme": "theme-pink-purple",
    "font": "font-jakarta",
    "persona": "friendly",
    "custom_instructions": "",
    "temperature": 0.7
}

# Supabase Cloud Database Konfigürasyonu
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://ltuitberpsitftyehxft.supabase.co").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "sb_publishable_9k_Z1Lc728OWBLehpJt-AQ_jvvOKPKk")

# Yerel Veritabanı başlatıcı
if not os.path.exists(DB_FILE):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump({"users": {}}, f)

def get_db():
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"users": {}}

def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, indent=2)

def get_user_from_db(email_clean: str):
    """Önce Supabase'e bakar, yoksa veya ayarlanmamışsa yerel database.json'dan okur"""
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/users?email=eq.{urllib.parse.quote(email_clean)}&select=*",
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json"
                }
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                rows = json.loads(resp.read().decode('utf-8'))
                if rows and len(rows) > 0:
                    return rows[0]
                return None
        except Exception as e:
            print(f"[Supabase Okuma Hata]: {e}")
    
    db = get_db()
    return db["users"].get(email_clean)

def save_user_to_db(user_data: dict):
    """Kullanıcıyı hem Supabase buluta hem de yerel database.json'a yazar"""
    if SUPABASE_URL and SUPABASE_KEY:
        try:
            req = urllib.request.Request(
                f"{SUPABASE_URL}/rest/v1/users",
                data=json.dumps(user_data).encode("utf-8"),
                headers={
                    "apikey": SUPABASE_KEY,
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                pass
        except Exception as e:
            print(f"[Supabase Kayit Hata]: {e}")
    
    db = get_db()
    db["users"][user_data["email"]] = user_data
    save_db(db)

def hash_pw(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def extract_url_content(text: str) -> str:
    urls = re.findall(r'https?://[^\s<>"]+|www\.[^\s<>"]+', text)
    if not urls:
        return ""
    url = urls[0]
    if not url.startswith('http'):
        url = 'https://' + url
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        with urllib.request.urlopen(req, timeout=6) as response:
            html = response.read().decode('utf-8', errors='ignore')
            soup = BeautifulSoup(html, 'html.parser')
            for tag in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript']):
                tag.decompose()
            clean_text = ' '.join(soup.stripped_strings)[:3000]
            return f"\n\n[Sistem Notu: Kullanicinin verdigi {url} web sitesi icerigi:\n{clean_text}\nLutfen bunu inceleyerek kullaniciya ozetle.]"
    except Exception as e:
        return f"\n\n[Sistem Notu: {url} adresi acilamadi: {str(e)}]"


# ══════════════ KULLANICIYA ÖZEL AUTH VE VERİ YÖNETİMİ ══════════════
class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class GoogleAuthRequest(BaseModel):
    email: str
    name: str
    picture: Optional[str] = None

class SyncUserDataRequest(BaseModel):
    email: str
    chats: List[Dict[str, Any]]
    settings: Dict[str, Any]

@app.post("/api/auth/register")
def register(req: RegisterRequest):
    email_clean = req.email.strip().lower()
    if get_user_from_db(email_clean):
        raise HTTPException(status_code=400, detail="Bu e-posta adresi ile zaten bir hesap var!")
    
    new_user = {
        "name": req.name.strip(),
        "email": email_clean,
        "password": hash_pw(req.password),
        "picture": None,
        "auth_type": "email",
        "created_at": time.time(),
        "settings": DEFAULT_SETTINGS.copy(),
        "chats": []
    }
    save_user_to_db(new_user)
    
    return {
        "status": "ok",
        "user": {
            "name": new_user["name"],
            "email": email_clean,
            "picture": new_user["picture"],
            "settings": new_user["settings"],
            "chats": new_user["chats"]
        }
    }

@app.post("/api/auth/login")
def login(req: LoginRequest):
    email_clean = req.email.strip().lower()
    user = get_user_from_db(email_clean)
    if not user:
        raise HTTPException(status_code=400, detail="Bu e-posta adresiyle kayıtlı hesap bulunamadı!")
    
    if user.get("password") != hash_pw(req.password):
        raise HTTPException(status_code=400, detail="Hatalı şifre girdiniz!")
    
    return {
        "status": "ok",
        "user": {
            "name": user["name"],
            "email": email_clean,
            "picture": user.get("picture"),
            "settings": user.get("settings", DEFAULT_SETTINGS.copy()),
            "chats": user.get("chats", [])
        }
    }

@app.post("/api/auth/google")
def google_auth(req: GoogleAuthRequest):
    email_clean = req.email.strip().lower()
    user = get_user_from_db(email_clean)
    
    if not user:
        user = {
            "name": req.name.strip(),
            "email": email_clean,
            "password": "GOOGLE_AUTH_ACCOUNT",
            "picture": req.picture or "https://api.iconify.design/logos:google-icon.svg",
            "auth_type": "google",
            "created_at": time.time(),
            "settings": DEFAULT_SETTINGS.copy(),
            "chats": []
        }
    else:
        user["name"] = req.name.strip()
        if req.picture:
            user["picture"] = req.picture
            
    save_user_to_db(user)
    return {
        "status": "ok",
        "user": {
            "name": user["name"],
            "email": email_clean,
            "picture": user.get("picture"),
            "settings": user.get("settings", DEFAULT_SETTINGS.copy()),
            "chats": user.get("chats", [])
        }
    }

@app.post("/api/user/sync")
def sync_user_data(req: SyncUserDataRequest):
    """Her hesabın sohbetlerini ve ayarlarını o hesaba özel olarak kaydeder"""
    email_clean = req.email.strip().lower()
    user = get_user_from_db(email_clean)
    if user:
        user["chats"] = req.chats
        user["settings"] = req.settings
        save_user_to_db(user)
        return {"status": "ok"}
    return {"status": "not_found"}


# ══════════════ SOHBET STREAMING ══════════════
class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    persona: str = "friendly"
    custom_instructions: str = ""
    temperature: float = 0.7

@app.get("/")
async def index():
    with open(HTML_PATH, "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())

@app.post("/api/chat")
def chat(req: ChatRequest):
    def generate():
        last_user_msg = ""
        for m in reversed(req.messages):
            if m.role == "user":
                last_user_msg = m.content
                break
                
        web_context = extract_url_content(last_user_msg)
        
        sys_prompt = (
            "Sen Luxa.Ai adinda gelismis, zeki, faydali ve profesyonel bir Turkce yapay zeka asistanisin. "
            "Kullaniciya daima net, akici, zengin ve estetik cevap ver. "
            "Cevaplarinda onemli yerleri, kilit kavramlari ve can alici noktalarini mutlaka kalin (**ornek**) olarak vurgula ve basliklar (### Baslik) kullan. "
            "Adin sorulursa veya kendinden bahsederken **Luxa.Ai** adini kullan."
        )
        
        if req.persona == "professional":
            sys_prompt += " Ciddi, kurumsal, analitik ve akademik bir ton kullan."
        elif req.persona == "witty":
            sys_prompt += " Sivri dilli, esprili ve zeki bir mizahi yaklasim sergile."
        elif req.persona == "creative":
            sys_prompt += " Cok yaratici, edebi, renkli ve metaforik bir dil kullan."
        else:
            sys_prompt += " Samimi, sicak ve icten bir arkadas gibi konus."
            
        if req.custom_instructions and req.custom_instructions.strip():
            sys_prompt += f"\n[Kullanicinin Ozel Talimati: {req.custom_instructions.strip()}]"

        msgs = [{"role": "system", "content": sys_prompt}]
        for i, m in enumerate(req.messages):
            content = m.content
            if i == len(req.messages) - 1 and m.role == "user" and web_context:
                content += web_context
            msgs.append({"role": m.role, "content": content})

        for model in FREE_MODELS:
            try:
                ctx = ssl.create_default_context()
                conn = http.client.HTTPSConnection("openrouter.ai", context=ctx, timeout=40)

                body = json.dumps({
                    "model": model,
                    "messages": msgs,
                    "max_tokens": 2048,
                    "temperature": req.temperature,
                    "stream": True,
                })

                headers = {
                    "Authorization": f"Bearer {API_KEY}",
                    "Content-Type": "application/json",
                }

                conn.request("POST", "/api/v1/chat/completions", body=body, headers=headers)
                resp = conn.getresponse()

                if resp.status in (429, 403, 404, 400):
                    conn.close()
                    continue

                if resp.status != 200:
                    conn.close()
                    continue

                got = False
                while True:
                    line = resp.readline()
                    if not line:
                        break
                    text = line.decode("utf-8").strip()
                    if not text or not text.startswith("data: "):
                        continue
                    payload = text[6:].strip()
                    if payload == "[DONE]":
                        yield "data: [DONE]\n\n"
                        conn.close()
                        return
                    try:
                        chunk = json.loads(payload)
                        delta = chunk["choices"][0].get("delta", {})
                        content = delta.get("content", "")
                        
                        if content:
                            got = True
                            yield f"data: {json.dumps({'c': content})}\n\n"
                    except:
                        pass

                conn.close()
                if got:
                    yield "data: [DONE]\n\n"
                    return

            except Exception:
                continue

        yield f'data: {json.dumps({"c": "Sunucular su an cok yogun, lutfen birkaç saniye sonra tekrar dene!"})}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    print("=" * 50)
    print(f"  Luxa.Ai V6.5 Baslatiliyor (Port: {port})...")
    print(f"  http://0.0.0.0:{port}")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=port)
