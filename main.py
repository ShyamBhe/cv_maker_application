import io, json, os, secrets, time, collections, datetime as dt
import bcrypt, jwt
from fastapi import FastAPI, Depends, HTTPException, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import Annotated, Literal
from pydantic import BaseModel, EmailStr, Field, StringConstraints
from sqlalchemy import create_engine, String, Integer, Text, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Mapped, mapped_column, Session
from pdf import render_pdf
from parser import parse_pdf

SECRET = os.getenv("JWT_SECRET") or secrets.token_hex(32)  # set JWT_SECRET in production
DB = os.getenv("DATABASE_URL", "sqlite:///cv.db").replace("postgres://", "postgresql://", 1)
if DB.startswith("postgresql://"): DB = DB.replace("postgresql://", "postgresql+psycopg2://", 1)
engine = create_engine(DB, connect_args={"check_same_thread": False} if DB.startswith("sqlite") else {})
Session_ = sessionmaker(engine, expire_on_commit=False)

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String)
    password: Mapped[str] = mapped_column(String)
    role: Mapped[str] = mapped_column(String, default="user")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
class CV(Base):
    __tablename__ = "cvs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    data: Mapped[str] = mapped_column(Text, default="{}")
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
Base.metadata.create_all(engine)

def hash_pw(p: str) -> str: return bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
def db():
    with Session_() as s: yield s

# Seed an admin from env vars
if os.getenv("ADMIN_EMAIL") and os.getenv("ADMIN_PASSWORD"):
    with Session_() as s:
        if not s.query(User).filter_by(email=os.environ["ADMIN_EMAIL"].lower()).first():
            s.add(User(email=os.environ["ADMIN_EMAIL"].lower(), full_name="Admin",
                       password=hash_pw(os.environ["ADMIN_PASSWORD"]), role="admin")); s.commit()

STATIC = os.path.join(os.path.dirname(__file__), "static")
PROD = os.path.isdir(STATIC)  # production container: hide API docs
app = FastAPI(title="CV Maker", docs_url=None if PROD else "/docs", redoc_url=None, openapi_url=None if PROD else "/openapi.json")

@app.middleware("http")
async def security_headers(req, call_next):
    r = await call_next(req)
    r.headers.update({"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                      "Strict-Transport-Security": "max-age=31536000",
                      "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"} if PROD else {})
    return r

def client_ip(req: Request) -> str:  # behind one trusted proxy (Caddy/Render) the last hop is the real client
    return req.headers.get("x-forwarded-for", "").split(",")[-1].strip() or (req.client.host if req.client else "")
HITS: dict[str, list[float]] = collections.defaultdict(list)
def rate(key: str, limit: int, window: int):
    now = time.time(); h = [t for t in HITS[key] if now - t < window]
    if len(h) >= limit: raise HTTPException(429, "Too many requests. Please wait a moment.")
    HITS[key] = h + [now]
FAILS: dict[str, list[float]] = collections.defaultdict(list)
def throttle(key: str, record: bool = False):  # max 5 failed logins per 15 minutes per email+IP
    now = time.time(); FAILS[key] = [t for t in FAILS[key] if now - t < 900]
    if record: FAILS[key].append(now)
    elif len(FAILS[key]) >= 5: raise HTTPException(429, "Too many attempts. Try again in 15 minutes.")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173").split(","), allow_methods=["*"], allow_headers=["*"])
bearer = HTTPBearer()

def current_user(c: HTTPAuthorizationCredentials = Depends(bearer), s: Session = Depends(db)) -> User:
    try: uid = int(jwt.decode(c.credentials, SECRET, algorithms=["HS256"])["sub"])
    except Exception: raise HTTPException(401, "Invalid or expired token")
    u = s.get(User, uid)
    if not u: raise HTTPException(401, "User not found")
    return u
def admin_only(u: User = Depends(current_user)) -> User:
    if u.role != "admin": raise HTTPException(403, "Admins only")
    return u

class RegisterIn(BaseModel):
    email: EmailStr; full_name: str = Field(min_length=1); password: str = Field(min_length=10)
class LoginIn(BaseModel):
    email: EmailStr; password: str
Str = Annotated[str, StringConstraints(max_length=4000)]
class Item(BaseModel):
    title: Str = ""; subtitle: Str = ""; period: Str = ""; bullets: list[Str] = Field(default=[], max_length=40); level: int = Field(3, ge=0, le=5)
class Section(BaseModel):
    title: Str = ""; kind: Literal["text", "entries", "skills", "list"] = "text"; text: Str = ""; items: list[Item] = Field(default=[], max_length=60)
class CVData(BaseModel):
    name: Str = ""; title: Str = ""; email: Str = ""; phone: Str = ""; website: Str = ""; linkedin: Str = ""
    template: Literal["sidebar", "classic", "modern"] = "sidebar"; font: Literal["sans", "serif"] = "sans"
    color: str = Field("#5b9ac6", pattern=r"^#[0-9a-fA-F]{6}$")
    sections: list[Section] = Field(default=[], max_length=30)

def token_for(u: User): 
    t = jwt.encode({"sub": str(u.id), "exp": dt.datetime.utcnow() + dt.timedelta(hours=24)}, SECRET, algorithm="HS256")
    return {"token": t, "user": {"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role}}

@app.post("/api/auth/register")
def register(b: RegisterIn, req: Request, s: Session = Depends(db)):
    rate("reg|" + client_ip(req), 10, 3600)
    if s.query(User).filter_by(email=b.email.lower()).first(): raise HTTPException(409, "Email already registered")
    u = User(email=b.email.lower(), full_name=b.full_name, password=hash_pw(b.password)); s.add(u); s.commit()
    return token_for(u)

@app.post("/api/auth/login")
def login(b: LoginIn, req: Request, s: Session = Depends(db)):
    key = b.email.lower() + "|" + client_ip(req)
    throttle(key)
    u = s.query(User).filter_by(email=b.email.lower()).first()
    if not u or not bcrypt.checkpw(b.password.encode(), u.password.encode()):
        throttle(key, record=True); raise HTTPException(401, "Wrong email or password")
    FAILS.pop(key, None); return token_for(u)

def load_cv(s: Session, uid: int) -> CVData:
    cv = s.query(CV).filter_by(user_id=uid).first()
    try: return CVData(**json.loads(cv.data)) if cv else CVData()
    except Exception: return CVData()

@app.get("/api/cv")
def get_cv(u: User = Depends(current_user), s: Session = Depends(db)): return load_cv(s, u.id)

@app.put("/api/cv")
def save_cv(b: CVData, u: User = Depends(current_user), s: Session = Depends(db)):
    cv = s.query(CV).filter_by(user_id=u.id).first() or CV(user_id=u.id)
    cv.data = b.model_dump_json(); cv.updated_at = dt.datetime.utcnow(); s.add(cv); s.commit()
    return b

def pdf_response(d: CVData):
    return StreamingResponse(render_pdf(d), media_type="application/pdf",
                             headers={"Content-Disposition": 'attachment; filename="cv.pdf"'})

@app.post("/api/preview")  # public, watermarked, rate-limited: lets people design before registering
def preview(b: CVData, req: Request):
    rate("pv|" + client_ip(req), 30, 60)
    return StreamingResponse(render_pdf(b, watermark=True), media_type="application/pdf", headers={"Content-Disposition": 'inline; filename="preview.pdf"'})

@app.post("/api/parse")  # upload an existing PDF CV -> structured data (file is processed in memory, never stored)
def parse_cv(req: Request, file: UploadFile = File(...)):
    rate("parse|" + client_ip(req), 6, 60)
    data = file.file.read(5_000_001)
    if len(data) > 5_000_000: raise HTTPException(413, "File too large (max 5 MB)")
    if not data.startswith(b"%PDF"): raise HTTPException(400, "Please upload a PDF file")
    try: cv = parse_pdf(io.BytesIO(data))
    except Exception: raise HTTPException(422, "Could not read this PDF. Scanned or image-only PDFs are not supported.")
    if not cv["name"] and not cv["sections"]: raise HTTPException(422, "No readable text found in this PDF.")
    return CVData(**cv)

@app.get("/api/cv/pdf")  # registration/login required
def my_pdf(u: User = Depends(current_user), s: Session = Depends(db)): return pdf_response(load_cv(s, u.id))

@app.get("/api/admin/users")
def users(_: User = Depends(admin_only), s: Session = Depends(db)):
    out = []
    for u in s.query(User).order_by(User.created_at.desc()):
        cv = s.query(CV).filter_by(user_id=u.id).first()
        out.append({"id": u.id, "email": u.email, "full_name": u.full_name, "role": u.role,
                    "created_at": u.created_at.isoformat(), "has_cv": bool(cv),
                    "cv_updated_at": cv.updated_at.isoformat() if cv else None})
    return out

@app.get("/api/admin/users/{uid}/cv")
def admin_cv(uid: int, _: User = Depends(admin_only), s: Session = Depends(db)): return load_cv(s, uid)

@app.get("/api/admin/users/{uid}/cv/pdf")
def admin_pdf(uid: int, _: User = Depends(admin_only), s: Session = Depends(db)): return pdf_response(load_cv(s, uid))

# Serve the built React app (production: one container serves API + UI)
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
if PROD:
    app.mount("/assets", StaticFiles(directory=os.path.join(STATIC, "assets")), name="assets")
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"): raise HTTPException(404)
        f = os.path.realpath(os.path.join(STATIC, path))
        return FileResponse(f if f.startswith(os.path.realpath(STATIC)) and os.path.isfile(f) else os.path.join(STATIC, "index.html"))
