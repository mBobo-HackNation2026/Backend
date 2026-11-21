from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "eBobo"
    environment: str = "local"
    debug: bool = True

    api_v1_prefix: str = "/api/v1"

    cors_origins: str = "http://localhost:3000,http://localhost:5173"

    database_url: str = "sqlite:///./app.db"

    max_upload_size_mb: int = 20
    upload_dir: str = "./uploads"

    zus_mock_base_url: str = "https://mock.zus.local"
    mobywatel_mock_base_url: str = "https://mock.mobywatel.local"

    # Panel administracyjny (MVP: jeden użytkownik, dane z env) - do rozbudowy o
    # pełny model użytkowników/ról, gdy panel wyjdzie poza zakres hackathonu.
    admin_username: str = "admin"
    admin_password: str = "changeme"
    secret_key: str = "dev-secret-key-change-me-in-production"
    access_token_expire_minutes: int = 60

    # Sesja użytkownika końcowego (anonimowa przy pierwszym otwarciu appki,
    # uwierzytelniona po symulowanym logowaniu mObywatel) - długa ważność,
    # bo reprezentuje instalację aplikacji, nie jednorazową sesję admina.
    user_access_token_expire_minutes: int = 60 * 24 * 30

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
