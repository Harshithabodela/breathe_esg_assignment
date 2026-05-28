from .base import *
from decouple import config
import dj_database_url
import os

DEBUG = False
SECRET_KEY = config("SECRET_KEY")
ALLOWED_HOSTS = ["*"]
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "None"
CSRF_COOKIE_SAMESITE = "None"
CSRF_TRUSTED_ORIGINS = [
    "https://breathe-esg-production-1d54.up.railway.app",
    "https://breathe-esg-api-production-f142.up.railway.app",
]

DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(DATABASE_URL, conn_max_age=600)
    }
