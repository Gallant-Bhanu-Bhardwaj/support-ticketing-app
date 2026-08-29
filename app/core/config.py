from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./app.db"
    # No default: a well-known fallback secret being silently accepted in a
    # misconfigured deployment is worse than the app refusing to start.
    # Must come from the environment (or .env locally).
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24
    # "development" (default, for local HTTP) or "production" (deployed
    # over HTTPS) -- see Settings.is_production, used to decide the auth
    # cookie's secure flag.
    environment: str = "development"

    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @field_validator("database_url")
    @classmethod
    def _normalize_postgres_scheme(cls, value: str) -> str:
        """Some hosts hand out "postgres://" connection strings; SQLAlchemy
        1.4+ only registers the "postgresql://" scheme for the same driver
        and raises NoSuchModuleError otherwise. Normalizing here means a
        production DATABASE_URL works regardless of which form the host
        gives us, with no code change needed either way."""
        if value.startswith("postgres://"):
            return "postgresql://" + value[len("postgres://") :]
        return value


settings = Settings()
