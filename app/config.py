import os
from dataclasses import dataclass


@dataclass
class Settings:
    app_name: str = "M-Pesa Payment Gateway"
    database_path: str = os.getenv("DATABASE_PATH", "payments.db")
    mpesa_environment: str = os.getenv("MPESA_ENVIRONMENT", "sandbox")
    mpesa_consumer_key: str = os.getenv("MPESA_CONSUMER_KEY", "")
    mpesa_consumer_secret: str = os.getenv("MPESA_CONSUMER_SECRET", "")
    mpesa_shortcode: str = os.getenv("MPESA_SHORTCODE", "174379")
    mpesa_passkey: str = os.getenv("MPESA_PASSKEY", "")
    mpesa_callback_url: str = os.getenv(
        "MPESA_CALLBACK_URL", "https://example.com/api/payments/callback"
    )
    callback_token: str = os.getenv("CALLBACK_TOKEN", "demo-callback-token")
    simulation_mode: bool = os.getenv("SIMULATION_MODE", "true").lower() == "true"


settings = Settings()
