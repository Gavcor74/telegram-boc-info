from dataclasses import dataclass
import os


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    target_icao: str
    http_user_agent: str
    ollama_base_url: str | None
    ollama_model: str | None
    meteo_source_url: str | None
    meteo_source_selector: str | None
    meteo_source_text: str | None
    notam_source_url: str | None
    notam_source_selector: str | None
    notam_source_text: str | None


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def load_settings() -> Settings:
    return Settings(
        telegram_bot_token=_clean(os.getenv('TELEGRAM_BOT_TOKEN')) or '',
        target_icao=(_clean(os.getenv('TARGET_ICAO')) or 'LEMO').upper(),
        http_user_agent=_clean(os.getenv('HTTP_USER_AGENT')) or 'AGENTE-BOC/1.0',
        ollama_base_url=_clean(os.getenv('OLLAMA_BASE_URL')),
        ollama_model=_clean(os.getenv('OLLAMA_MODEL')),
        meteo_source_url=_clean(os.getenv('METEO_SOURCE_URL')),
        meteo_source_selector=_clean(os.getenv('METEO_SOURCE_SELECTOR')),
        meteo_source_text=_clean(os.getenv('METEO_SOURCE_TEXT')),
        notam_source_url=_clean(os.getenv('NOTAM_SOURCE_URL')),
        notam_source_selector=_clean(os.getenv('NOTAM_SOURCE_SELECTOR')),
        notam_source_text=_clean(os.getenv('NOTAM_SOURCE_TEXT')),
    )


def ensure_token(settings: Settings) -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError(
            'Missing TELEGRAM_BOT_TOKEN. Copy .env.example to .env and set the token.'
        )
