# AGENTE BOC

Bot de Telegram para consultar informacion aeronautica publica de la Base Aerea de Moron (`LEMO`).

## Comandos

- `/meteo`: METAR/TAF de LEMO con lectura rapida.
- `/notams`: resumen operativo de NOTAM LEMO desde Insignia/ENAIRE.
- `/status`: estado del servicio.
- `/start` o `/help`: ayuda.

## Despliegue en Vercel

Variables necesarias:

```env
TELEGRAM_BOT_TOKEN=
TARGET_ICAO=LEMO
HTTP_USER_AGENT=AGENTE-BOC/1.0
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=claude-sonnet-4-5
MAX_TOKENS=900
```

Tras desplegar, registrar webhook visitando:

```text
https://TU-PROYECTO.vercel.app/api/setup-webhook
```

Luego probar en Telegram con `/status`, `/meteo` y `/notams`.

## Probar modelos gratis/baratos

El bot soporta proveedores OpenAI-compatible. Para OpenRouter/Qwen/DeepSeek:

```env
AI_PROVIDER=openai-compatible
OPENAI_COMPAT_API_KEY=tu_key
OPENAI_COMPAT_BASE_URL=https://openrouter.ai/api/v1
OPENAI_COMPAT_MODEL=qwen/qwen3-235b-a22b:free
```

Tambien puedes usar DeepSeek directo:

```env
AI_PROVIDER=openai-compatible
OPENAI_COMPAT_API_KEY=tu_deepseek_key
OPENAI_COMPAT_BASE_URL=https://api.deepseek.com
OPENAI_COMPAT_MODEL=deepseek-chat
```

Si el proveedor falla o no hay key, el bot vuelve al texto operativo generado con reglas locales.

## Fuentes

- METEO: AviationWeather Data API.
- NOTAM: capa publica Insignia/ENAIRE.

## Aviso

La informacion aeronautica es sensible. Este bot es una ayuda operativa y no sustituye fuentes oficiales ni criterio profesional.