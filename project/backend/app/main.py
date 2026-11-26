
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import db
from app.api.routes.audit import router as audit_router
from app.api.routes.verify import router as verify_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = db.connect()
    db.init_db(conn)
    conn.close()
    yield

app = FastAPI(
    title="AEGIS AI API",
    description="Multi-Agent AI Verification and Security Framework",
    version="1.0.0",
    lifespan=lifespan,
)

# Allow the Next.js frontend to communicate with FastAPI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root():
    return {
        "message": "Welcome to AEGIS AI API",
        "status": "running"
    }

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "project": "AEGIS AI"
    }


app.router.include_router(verify_router)

app.include_router(audit_router)
