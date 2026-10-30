import os
import sys
from pathlib import Path

# Disable Gradio SSR proxy which binds to 7860 before Python starts
os.environ["GRADIO_SSR_MODE"] = "false"

# Add backend directory to Python path
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Default database URL
os.environ.setdefault("DATABASE_URL", "sqlite:///./agenticwhats.db")

# Initialize database schema first so tables exist
from app.db.session import engine, SessionLocal
from app.models.entities import Base, User

Base.metadata.create_all(bind=engine)

# Seed demo data if database is empty
try:
    with SessionLocal() as db:
        has_users = db.query(User).first() is not None
    if not has_users:
        print("🌱 Seeding demo data for AgenticWhats...")
        import subprocess
        subprocess.run([sys.executable, str(BACKEND_DIR / "scripts" / "seed_demo.py")], check=False)
except Exception as e:
    print(f"Seed note: {e}")

import gradio as gr
import uvicorn
from app.main import app as fastapi_app

# Build Gradio UI for health check and status dashboard
with gr.Blocks(title="AgenticWhats API") as demo:
    gr.Markdown("# 🚀 AgenticWhats API & WhatsApp Webhook Server")
    gr.Markdown("""
    ### ✅ Backend Status: Online & Healthy!
    
    This server is actively hosting the **AgenticWhats** backend APIs and WhatsApp webhooks.
    
    | Endpoint | Purpose |
    |---|---|
    | [`/health`](/health) | System health & status check |
    | `/api/whatsapp/webhook` | Meta WhatsApp Cloud API Webhook |
    | `/api/auth/login` | SaaS Authentication |
    | `/api/menu` | Restaurant menu & categories |
    | `/api/orders` | Customer order management |
    
    **WhatsApp Verify Token:** `agenticwhats-verify`
    """)

# Mount Gradio onto the FastAPI application
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
