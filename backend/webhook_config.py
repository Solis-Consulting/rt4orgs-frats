"""
Webhook configuration module.
Provides in-memory config state for controlling Twilio webhook behavior.
"""
from pydantic import BaseModel


class WebhookConfig(BaseModel):
    enabled: bool = True
    mode: str = "prod"  # prod | dry_run | paused
    log_payloads: bool = True


# Global singleton config instance
WEBHOOK_CONFIG = WebhookConfig()

