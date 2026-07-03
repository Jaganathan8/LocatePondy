import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Recognized as "unsafe" — if this is still the SECRET_KEY at startup, app.py
# will print a loud warning telling you to set a real one before deploying.
_DEV_SECRET = "locatepondy-dev-secret-change-in-production"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", _DEV_SECRET)

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'locatepondy.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB total request (up to 5 photos x ~4MB)
    MAX_PHOTOS_PER_SHOP = 5
    SHOP_NAME_MAX_LENGTH = 150

    # ---- Google OAuth (fill these in to enable real Google Sign-In) ----
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
    GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")

    # ---- SMS/OTP gateway (fill these in to enable real phone OTP) ----
    SMS_GATEWAY_API_KEY = os.environ.get("SMS_GATEWAY_API_KEY", "")
    OTP_EXPIRY_SECONDS = 300          # 5 minutes
    OTP_MAX_ATTEMPTS = 5

    # ---- Admin account (seeded automatically on first run) ----
    # Change these via environment variables before deploying anywhere real.
    ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "ChangeMe@123")

    # ---- Login security ----
    MAX_FAILED_LOGIN_ATTEMPTS = 5
    ACCOUNT_LOCKOUT_MINUTES = 15

    # ---- Session / cookie security ----
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Set FORCE_HTTPS=1 in production (behind HTTPS) to mark cookies secure-only.
    SESSION_COOKIE_SECURE = os.environ.get("FORCE_HTTPS", "0") == "1"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 4  # 4 hours

    # ---- CSRF ----
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
