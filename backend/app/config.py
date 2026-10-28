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

    cors_origins: str = (
        "http://localhost:5173,http://localhost:8080,"
        "http://127.0.0.1:5173,http://127.0.0.1:8080"
    )
    smtp_host: str = "localhost"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_tls: bool = False
    mail_from: str = "federation@orencode.test"
    notifications_worker: bool = True
    telegram_bot_token: str = ""
    telegram_bot_username: str = ""
    public_site_url: str = "http://localhost:8080"
    # Lets webhooks reach localhost and private networks (local demo receivers).
    webhook_allow_private: bool = False
    pdf_font: str = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    # Letterhead of official documents. Requisites are fictitious demo values:
    # set the real ones through the environment.
    fsp_name: str = (
        "Региональное отделение Общероссийской общественной организации "
        "«Федерация спортивного программирования» в Оренбургской области"
    )
    fsp_short_name: str = "ФСП Оренбургской области"
    fsp_requisites: str = (
        "460000, г. Оренбург, ул. Демонстрационная, д. 1 · ИНН 5600000000 · "
        "ОГРН 1005600000000 · federation@orencode.test"
    )
    fsp_city: str = "г. Оренбург"
    fsp_head_position: str = "Председатель"
    fsp_head_name: str = ""


settings = Settings()
if len(settings.jwt_secret) < 32:
    raise RuntimeError("JWT_SECRET must contain at least 32 characters")
