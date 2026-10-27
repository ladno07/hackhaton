from urllib.parse import urlsplit
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://orencode:orencode@localhost:5432/orencode"
    jwt_secret: str
    jwt_minutes: int = 120
    public_base_url: str = "http://localhost:8080"

    @field_validator("public_base_url")
    @classmethod
    def validate_public_url(cls, value):
        parts = urlsplit(value)
        if (
            parts.scheme not in {"http", "https"}
            or not parts.hostname
            or parts.username
            or parts.password
            or parts.query
            or parts.fragment
            or parts.path not in {"", "/"}
        ):
            raise ValueError(
                "PUBLIC_BASE_URL must be an http(s) origin without credentials, path or query"
            )
        return value.rstrip("/")

    cors_origins: str = "http://localhost:5173,http://localhost:8080"
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_tls: bool = False
    mail_from: str = "federation@orencode.test"
    notifications_worker: bool = True
    pdf_font: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


settings = Settings()
if len(settings.jwt_secret) < 32:
    raise RuntimeError("JWT_SECRET must contain at least 32 characters")
