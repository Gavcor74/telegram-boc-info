# AGENTE BOC

Bot de Telegram para consultar información aeronáutica de la Base Aérea de Morón (`LEMO`).

## Qué hace

- Responde por Telegram.
- Consulta METEO para `LEMO`.
- Consulta NOTAM / avisos públicos para `LEMO`.
- Puede leer una URL, usar texto pegado o extraer contenido HTML con un selector CSS opcional.
- Si Ollama está disponible, reescribe la salida en español más natural.

## Fuentes gratis

- METEO: [AviationWeather Data API](https://aviationweather.gov/data/api/)
- NOTAM / avisos: [AIP España](https://aip.enaire.es/aip/NOTAM-es.html)

## Ollama

Si configuras estas variables:

- `OLLAMA_BASE_URL` (por defecto `http://localhost:11434`)
- `OLLAMA_MODEL` (por defecto `llama3.1`)

el bot intentará convertir la salida técnica a un español más claro y natural.

Si Ollama no está instalado o no responde, el bot seguirá funcionando con el texto bruto.

## Importante

La información aeronáutica es sensible. Este bot debe tratarse como una ayuda operativa y no como fuente única de decisión.

## Estado actual

Este repositorio deja la base técnica preparada, pero las fuentes automáticas reales aún dependen de la accesibilidad del sitio origen:

- `AviationWeather` suele funcionar sin pagar y cubre METAR/TAF mundial.
- `ENAIRE / AIP` expone información pública y avisos, pero la parte de NOTAM en tiempo real puede no estar disponible como una API pública estable.

Por eso el bot soporta:

- `METEO` por defecto contra AviationWeather
- `URL` configurable
- `selector CSS` opcional
- `texto pegado` por variable de entorno

## Instalación

1. Crea un entorno virtual.
2. Instala dependencias.
3. Copia `.env.example` a `.env`.
4. Rellena el token de Telegram.
5. Ejecuta `python -m agente_boc`.

## Variables de entorno

- `TELEGRAM_BOT_TOKEN`: token del bot de Telegram.
- `TARGET_ICAO`: por defecto `LEMO`.
- `HTTP_USER_AGENT`: identificador enviado al hacer solicitudes HTTP.
- `OLLAMA_BASE_URL`: URL de Ollama.
- `OLLAMA_MODEL`: modelo a usar en Ollama.
- `METEO_SOURCE_URL`: URL alternativa de la fuente meteorológica.
- `METEO_SOURCE_SELECTOR`: selector CSS opcional para extraer solo el bloque útil.
- `METEO_SOURCE_TEXT`: texto fijo si quieres probar sin scraping.
- `NOTAM_SOURCE_URL`: URL alternativa para avisos/NOTAM.
- `NOTAM_SOURCE_SELECTOR`: selector CSS opcional para extraer solo el bloque útil.
- `NOTAM_SOURCE_TEXT`: texto fijo si quieres probar sin scraping.

## Comandos del bot

- `/start`
- `/meteo`
- `/notams`
- `/status`

## Despliegue en VPS

### EasyPanel / Docker

Este bot funciona como un servicio de fondo, así que en EasyPanel debes crear un contenedor tipo worker o servicio sin puerto público.

Pasos recomendados:

1. Crea un servicio nuevo desde el repositorio o subiendo este proyecto.
2. Usa el `Dockerfile` del proyecto.
3. No expongas ningún puerto, porque el bot solo hace polling a Telegram.
4. Añade estas variables de entorno en EasyPanel:

```env
TELEGRAM_BOT_TOKEN=tu_token
TARGET_ICAO=LEMO
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_MODEL=qwen2.5:0.5b
HTTP_USER_AGENT=AGENTE-BOC/1.0
```

5. Si tu servicio de Ollama en EasyPanel se llama distinto, cambia `OLLAMA_BASE_URL` para apuntar al nombre interno correcto del servicio dentro de la misma red.
6. Despliega y revisa los logs.

Notas útiles:

- Si Ollama vive en el mismo proyecto de EasyPanel, la URL interna suele ser `http://ollama:11434`.
- No hace falta publicar Ollama al exterior para que este bot lo use.
- Si solo quieres probar el bot sin Ollama, puedes dejar `OLLAMA_BASE_URL` y `OLLAMA_MODEL` vacíos.

### systemd

- Puedes ejecutar este bot como servicio `systemd`.
- También puedes meterlo en Docker más adelante.
