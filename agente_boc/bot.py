from __future__ import annotations

import asyncio

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from .config import Settings
from .providers import AviationWeatherSource, InsigniaNotamSource, build_notam_message, build_public_aip_message, pick_source, render_plain_spanish


def _common_reply(settings: Settings) -> str:
    return (
        f"Proyecto: AGENTE BOC\n"
        f"ICAO objetivo: {settings.target_icao}\n"
        f"Comandos: /meteo /notams /status"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data['settings']
    ollama_enabled = bool(settings.ollama_base_url and settings.ollama_model)
    await update.message.reply_text(
        'AGENTE BOC listo.\n\n'
        + _common_reply(settings)
        + '\n\nMETEO usa una fuente pública gratis por defecto. NOTAM usa una vista pública AIP configurable. '
        + ('Ollama está preparado para convertirlo a español natural.' if ollama_enabled else 'Ollama aún no está configurado en este equipo.')
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data['settings']
    meteo_ready = True
    notam_ready = bool(settings.notam_source_url or settings.notam_source_text)
    ollama_ready = bool(settings.ollama_base_url and settings.ollama_model)
    await update.message.reply_text(
        'Estado del bot:\n'
        f'- METEO configurado: {"sí" if meteo_ready else "no"}\n'
        f'- NOTAM configurado: {"sí" if notam_ready else "no"}\n'
        f'- Ollama configurado: {"sí" if ollama_ready else "no"}\n'
        f'- ICAO: {settings.target_icao}'
    )


async def meteo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data['settings']
    source = settings.meteo_source_url or settings.meteo_source_text
    if source:
        meteo_source = pick_source(
            settings.meteo_source_url,
            settings.meteo_source_selector,
            settings.meteo_source_text,
            settings.http_user_agent,
        )
        raw = await asyncio.to_thread(meteo_source.fetch)
    else:
        meteo_source = AviationWeatherSource(icao=settings.target_icao, user_agent=settings.http_user_agent)
        raw = await asyncio.to_thread(meteo_source.fetch)

    message = render_plain_spanish(raw, 'METEO', settings)
    await update.message.reply_text(message)


async def notams(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    settings: Settings = context.application.bot_data['settings']
    if settings.notam_source_url or settings.notam_source_text:
        source = pick_source(
            settings.notam_source_url,
            settings.notam_source_selector,
            settings.notam_source_text,
            settings.http_user_agent,
        )
        raw = await asyncio.to_thread(source.fetch)
        message = render_plain_spanish(build_notam_message(raw, settings.target_icao), 'NOTAM', settings)
    else:
        try:
            source = InsigniaNotamSource(settings.target_icao)
            message = await asyncio.to_thread(source.fetch)
        except Exception:
            message = build_public_aip_message(settings.target_icao)
    await update.message.reply_text(message)


def build_application(settings: Settings) -> Application:
    application = Application.builder().token(settings.telegram_bot_token).build()
    application.bot_data['settings'] = settings
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('status', status))
    application.add_handler(CommandHandler('meteo', meteo))
    application.add_handler(CommandHandler('notams', notams))
    return application
