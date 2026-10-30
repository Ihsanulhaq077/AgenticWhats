import os
import sys
from pathlib import Path

# Satisfy Hugging Face ZeroGPU check if Space was created with ZeroGPU hardware
try:
    import spaces

    @spaces.GPU
    def _zerogpu_init():
        return True

    _zerogpu_init()
except Exception as e:
    pass

# Add backend to Python path
ROOT_DIR = Path(__file__).resolve().parent
BACKEND_DIR = ROOT_DIR / "backend"
sys.path.insert(0, str(BACKEND_DIR))

# Ensure database URL is set (SQLite default for simple standalone demo)
os.environ.setdefault("DATABASE_URL", "sqlite:///./agenticwhats.db")

import gradio as gr
import uvicorn
from app.main import app as fastapi_app

# Run seed script on startup to initialize demo data if DB is new
try:
    from app.db.session import SessionLocal
    from app.models.entities import User
    with SessionLocal() as db:
        has_users = db.query(User).first() is not None
    if not has_users:
        print("Initializing seed data for AgenticWhats...")
        import subprocess
        subprocess.run([sys.executable, str(BACKEND_DIR / "scripts" / "seed_demo.py")], check=False)
except Exception as e:
    print(f"Seed initialization note: {e}")

# Build a clean Gradio interface for status and testing
with gr.Blocks(title="AgenticWhats Backend API") as demo:
    gr.Markdown("# 🚀 AgenticWhats API & WhatsApp Webhook Server")
    gr.Markdown("""
    ### ✅ Backend Status: Online
    This Hugging Face Space hosts the FastAPI backend for **AgenticWhats**.
    
    - **Health Check:** [`/health`](/health)
    - **API Prefix:** `/api`
    - **WhatsApp Webhook:** `/api/whatsapp/webhook`
    - **Verify Token:** `agenticwhats-verify`
    
    ### Next Step:
    Use this Space URL as the **`BACKEND_URL`** in your Vercel frontend or Meta WhatsApp dashboard.
    """)

# Mount FastAPI app so all API routes and webhooks are preserved seamlessly
app = gr.mount_gradio_app(fastapi_app, demo, path="/")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)

