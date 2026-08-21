import os
import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("sai")

FONNTE_TOKEN = os.getenv("FONNTE_TOKEN", "")
FONNTE_FROM = os.getenv("FONNTE_FROM_NUMBER", "6289876543210")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "")
JWT_EXPIRATION = int(os.getenv("JWT_EXPIRATION", "86400") or "86400")
API_TOKEN = os.getenv("API_TOKEN", "")
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")

RATE_WINDOW = int(os.getenv("RATE_WINDOW", "60"))
RATE_MAX = int(os.getenv("RATE_MAX", "60"))

FRONTEND_FILE = os.getenv(
    "FRONTEND_FILE",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "index.html"),
)

# Supabase (opsional, kompatibilitas env lama; store utama SQLite)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()] or \
               ["http://localhost:8000", "http://127.0.0.1:8000"]

AUTH_ENABLED = bool(JWT_SECRET_KEY or API_TOKEN)

# Escape hatch eksplisit untuk lokal dev tanpa auth. Jangan pernah di-set di production.
ALLOW_DEV_MODE = os.getenv("SAI_ALLOW_DEV_MODE", "").strip().lower() in ("1", "true", "yes")

APP_VERSION = "0.6.0"


def validate_security_config() -> None:
    """Secure by default: tolak boot jika auth tidak dikonfigurasi.

    Production wajib menyetel JWT_SECRET_KEY (atau API_TOKEN).
    Untuk eksperimen lokal, set SAI_ALLOW_DEV_MODE=1 secara sadar.
    """
    if AUTH_ENABLED:
        if JWT_SECRET_KEY and len(JWT_SECRET_KEY) < 16:
            raise RuntimeError(
                "JWT_SECRET_KEY terlalu pendek (min 16 karakter). "
                "Generate dengan: python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return
    if ALLOW_DEV_MODE:
        log.warning(
            "[SECURITY] Berjalan TANPA auth (SAI_ALLOW_DEV_MODE=1). "
            "Semua request dianggap admin dev. JANGAN gunakan di production."
        )
        return
    raise RuntimeError(
        "Auth belum dikonfigurasi. Set JWT_SECRET_KEY (wajib) sebelum menjalankan server. "
        "Untuk development lokal tanpa auth, set SAI_ALLOW_DEV_MODE=1 secara eksplisit."
    )
