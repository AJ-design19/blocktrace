from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "BlockTrace"
    environment: str = "development"           # development | production
    secret_key: str = "change-me-in-production-please-use-32+chars"
    access_token_minutes: int = 60
    database_url: str = "sqlite:///./blocktrace.db"
    cors_origins: str = "http://localhost:5173"
    rate_limit_per_minute: int = 240
    login_rate_limit_per_minute: int = 10
    anchor_batch_size: int = 50
    risk_alert_threshold: float = 0.40          # create an alert at/above this score
    risk_high_threshold: float = 0.70           # auto-flag the token at/above this score
    # optional on-chain anchoring (leave empty to run fully off-chain)
    chain_rpc_url: str = ""
    chain_contract_address: str = ""
    chain_private_key: str = ""

    def validate_for_production(self) -> None:
        if self.environment == "production" and self.secret_key.startswith("change-me"):
            raise RuntimeError("SECRET_KEY must be set to a strong random value in production")


@lru_cache
def get_settings() -> Settings:
    return Settings()
