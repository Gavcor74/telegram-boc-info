from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Protocol

import requests
from bs4 import BeautifulSoup

from .config import Settings


class DataSource(Protocol):
    def fetch(self) -> str:
        raise NotImplementedError


@dataclass
class StaticTextSource:
    text: str

    def fetch(self) -> str:
        return self.text.strip()


@dataclass
class URLSource:
    url: str
    user_agent: str = 'AGENTE-BOC/1.0'
    selector: str | None = None
    timeout: int = 20

    def fetch(self) -> str:
        headers = {'User-Agent': self.user_agent}
        response = requests.get(self.url, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        content_type = response.headers.get('content-type', '')
        if 'text/html' in content_type or 'application/xhtml+xml' in content_type:
            soup = BeautifulSoup(response.text, 'lxml')
            if self.selector:
                nodes = soup.select(self.selector)
                extracted = '\n'.join(node.get_text(' ', strip=True) for node in nodes)
                if extracted.strip():
                    return extracted.strip()
            return soup.get_text('\n', strip=True)
        return response.text.strip()


@dataclass
class AviationWeatherSource:
    icao: str
    user_agent: str = 'AGENTE-BOC/1.0'
    timeout: int = 20

    def _fetch_json(self, endpoint: str) -> object:
        url = f'https://aviationweather.gov/api/data/{endpoint}'
        params = {'ids': self.icao, 'format': 'json'}
        headers = {'User-Agent': self.user_agent}
        response = requests.get(url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def fetch(self) -> str:
        metar_data = self._fetch_json('metar')
        taf_data = self._fetch_json('taf')
        return format_aviation_weather(metar_data, taf_data, self.icao)


@dataclass
class InsigniaNotamSource:
    icao: str
    user_agent: str = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'
    timeout: int = 30

    def _query(self, where: str) -> list[dict[str, object]]:
        url = 'https://servais.enaire.es/insignias/rest/services/NOTAM/NOTAM_APP_V3/MapServer/0/query'
        params = {
            'f': 'json',
            'where': where,
            'outFields': 'notamId,notamSerie,notamNumber,notamYear,icaroCreationTime,itemA,itemBstr,itemCstr,itemD,itemE,affectedElement,DESCRIPTION,icaoFormatText,sourceInformationNotam',
            'returnGeometry': 'false',
            'orderByFields': 'notamYear DESC, notamNumber DESC',
            'resultRecordCount': '20',
        }
        headers = {'User-Agent': self.user_agent, 'Accept': 'application/json,text/plain,*/*'}
        response = requests.get(url, params=params, headers=headers, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        return payload.get('features', []) if isinstance(payload, dict) else []

    def fetch(self) -> str:
        where = f"itemA = '{self.icao.upper()}'"
        features = self._query(where)
        if not features:
            where = f"icaoFormatText LIKE '%A){self.icao.upper()}%'"
            features = self._query(where)
        return format_notam_features(features, self.icao)


def pick_source(url: str | None, selector: str | None, text: str | None, user_agent: str) -> DataSource:
    if text:
        return StaticTextSource(text=text)
    if url:
        return URLSource(url=url, selector=selector, user_agent=user_agent)
    return StaticTextSource(text='No source configured.')


def normalize_output(raw_text: str, header: str) -> str:
    lines = [line.rstrip() for line in raw_text.splitlines()]
    lines = [line for line in lines if line.strip()]
    if not lines:
        return f'{header}\n\nSin datos disponibles.'
    return f'{header}\n\n' + '\n'.join(lines)


def filter_relevant_lines(raw_text: str, keywords: list[str]) -> str:
    lines = [line.strip() for line in raw_text.splitlines()]
    lines = [line for line in lines if line]
    if not lines:
        return ''

    pattern = re.compile('|'.join(re.escape(k) for k in keywords), re.IGNORECASE)
    relevant = [line for line in lines if pattern.search(line)]
    if relevant:
        return '\n'.join(relevant)
    return '\n'.join(lines[:80])


def _first_item(data: object) -> dict | None:
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict):
            return first
    if isinstance(data, dict):
        if 'data' in data and isinstance(data['data'], list) and data['data']:
            first = data['data'][0]
            if isinstance(first, dict):
                return first
        return data
    return None


def _extract_raw_report(item: dict, keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def format_aviation_weather(metar_data: object, taf_data: object, icao: str) -> str:
    metar_item = _first_item(metar_data) or {}
    taf_item = _first_item(taf_data) or {}

    metar_raw = _extract_raw_report(metar_item, ['rawOb', 'raw_text', 'raw', 'text', 'metar'])
    taf_raw = _extract_raw_report(taf_item, ['rawTAF', 'rawOb', 'raw_text', 'raw', 'text', 'taf'])

    lines: list[str] = [f'ESTACIÓN: {icao}']

    if metar_raw:
        lines.append(f'METAR: {metar_raw}')
    else:
        lat = metar_item.get('lat')
        lon = metar_item.get('lon')
        temp = metar_item.get('temp') or metar_item.get('temperature')
        if lat is not None and lon is not None:
            lines.append(f'METAR: datos recibidos para {icao} ({lat}, {lon})')
        if temp is not None:
            lines.append(f'Temperatura: {temp}')

    if taf_raw:
        lines.append(f'TAF: {taf_raw}')

    if not metar_raw and not taf_raw and len(lines) == 1:
        lines.append('Sin datos meteorológicos disponibles.')

    return normalize_output('\n'.join(lines), f'METEO {icao}')


def build_notam_message(raw_text: str, icao: str) -> str:
    body = filter_relevant_lines(raw_text, [icao, 'NOTAM', 'RWY', 'TWY', 'APRON', 'closed', 'closure', 'service', 'disabled'])
    if not body:
        body = raw_text.strip() or 'Sin NOTAM públicos disponibles.'
    return normalize_output(body, f'NOTAM / AIP {icao}')


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in ('%d/%m/%Y %H:%M:%S', '%Y-%m-%d %H:%M:%S', '%Y%m%d%H%M'):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _format_dt(value: str | None) -> str:
    dt = _parse_datetime(value)
    if not dt:
        return value or 'sin fecha'
    return dt.strftime('%d/%m/%Y %H:%M UTC')


def _friendly_notam_entry(desc: str) -> tuple[str, str, list[str]]:
    text = re.sub(r'\s+', ' ', desc.strip())
    upper = text.upper()

    if 'VOR/DME' in upper or 'TACAN' in upper or 'RADIOAYUDA' in upper:
        if 'VOR/DME' in upper:
            section = 'Radioayudas'
            title = 'VOR/DME MRN 115.500 / CH102X'
        elif 'TACAN' in upper:
            section = 'Radioayudas'
            title = 'TACAN MRN CH100X'
        else:
            section = 'Radioayudas'
            title = text
        notes: list[str] = []
        if 'UNMONITORED' in upper:
            notes.append('Funciona, pero sin supervisión técnica.')
            notes.append('No confiar al 100% para procedimientos críticos.')
        if 'U/S' in upper and 'UNMONITORED' not in upper:
            notes.append('Puede estar fuera de servicio o degradado.')
        if not notes:
            notes.append('Estado operativo a revisar con precaución.')
        return section, title, notes

    if 'GCA' in upper or 'APPROACH' in upper or 'APPROX' in upper:
        section = 'Aproximación'
        if 'GCA' in upper:
            title = 'GCA (Ground Controlled Approach)'
            notes = ['Fuera de servicio.', 'No disponible para aproximaciones guiadas por radar.']
        else:
            title = text
            notes = ['Afecta a procedimientos de aproximación.']
        return section, title, notes

    if 'ARRESTING SYSTEM' in upper or 'ARRESTING' in upper:
        section = 'Sistemas de frenado'
        title = text.replace(' U/S', '').strip()
        notes = ['Fuera de servicio.', 'Sin sistema de frenado operativo en esa ventana.']
        return section, title, notes

    if 'RWY02/20' in upper or 'RWY 02/20' in upper or 'TWY' in upper or 'AD LTD' in upper or 'WIP' in upper:
        section = 'Restricción fuerte del aeródromo'
        title = 'Aeródromo muy limitado por obras en pista y calles de rodaje'
        notes: list[str] = []
        if 'ONLY ALLOWED FOR VFR HELICOPTERS' in upper:
            notes.append('Solo permitido para helicópteros VFR.')
        if 'SR/SS' in upper:
            notes.append('Ventana operativa entre salida y puesta de sol.')
        if 'PPR' in upper:
            notes.append('PPR obligatorio con 24 horas de antelación.')
        notes.append('Para aviación convencional, la operación queda muy restringida o prácticamente descartada.')
        return section, title, notes

    if 'PPR' in upper:
        return 'Coordinación previa', text, ['PPR obligatorio con antelación.']

    return 'Otros avisos', text, []




def format_notam_features(features: list[dict[str, object]], icao: str) -> str:
    if not features:
        return normalize_output('No se encontraron NOTAM públicos para este aeródromo en la capa de Insignia.', f'NOTAM {icao}')

    now = datetime.now(timezone.utc)
    grouped: dict[str, list[dict[str, object]]] = {'vigente': [], 'próximo': [], 'caducado': []}

    for feature in features:
        attrs = feature.get('attributes', {}) if isinstance(feature, dict) else {}
        if not isinstance(attrs, dict):
            continue
        notam_id = str(attrs.get('notamId') or attrs.get('sourceInformationNotam') or 'NOTAM')
        start_time = str(attrs.get('itemBstr') or '')
        end_time = str(attrs.get('itemCstr') or '')
        desc = str(attrs.get('itemE') or attrs.get('DESCRIPTION') or '').strip()
        if not desc:
            desc = str(attrs.get('icaoFormatText') or '').strip()

        status = 'vigente'
        start_dt = _parse_datetime(start_time)
        end_dt = _parse_datetime(end_time)
        if start_dt and now < start_dt:
            status = 'próximo'
        elif end_dt and now > end_dt:
            status = 'caducado'

        section, title, notes = _friendly_notam_entry(desc)
        grouped[status].append({
            'id': notam_id,
            'start': _format_dt(start_time),
            'end': _format_dt(end_time),
            'section': section,
            'title': title,
            'notes': notes,
        })

    lines = [
        'Resumen operativo de NOTAM desde Insignia/ENAIRE. Es una traducción útil y sencilla, no el texto legal completo.',
    ]
    for status in ('vigente', 'próximo', 'caducado'):
        items = grouped.get(status, [])
        if not items:
            continue
        lines.append('')
        if status == 'vigente':
            lines.append('✈️ Estado actual (en vigor ahora)')
        elif status == 'próximo':
            lines.append('⚠️ Próximos eventos (planificación)')
        else:
            lines.append('🕓 Avisos caducados')

        current_section = None
        for item in items:
            section = str(item['section'])
            if section != current_section:
                current_section = section
                if section == 'Radioayudas':
                    lines.append('📡 Radioayudas')
                elif section == 'Aproximación':
                    lines.append('🛬 Sistemas de aproximación')
                elif section == 'Sistemas de frenado':
                    lines.append('🛑 Sistemas de frenado')
                elif section == 'Restricción fuerte del aeródromo':
                    lines.append('🚧 Restricción fuerte del aeródromo')
                elif section == 'Coordinación previa':
                    lines.append('📝 Coordinación previa')
                else:
                    lines.append('ℹ️ Otros avisos')
            lines.append(f"- {item['id']} {item['start']} -> {item['end']}")
            lines.append(f"  {item['title']}")
            for note in item['notes']:
                lines.append(f"  👉 {note}")
    return normalize_output('\n'.join(lines), f'NOTAM {icao}')


def _find_public_aip_docs(icao: str, limit: int = 12) -> list[dict[str, str]]:
    index_url = 'https://aip.enaire.es/AIP/indice.zip'
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
    }
    response = requests.get(index_url, headers=headers, timeout=60)
    response.raise_for_status()

    raw = response.content
    prefix = b'data:application/zip;base64,'
    if raw.startswith(prefix):
        import base64
        import io
        import zipfile

        blob = base64.b64decode(raw[len(prefix):])
        archive = zipfile.ZipFile(io.BytesIO(blob))
        name = archive.namelist()[0]
        index_data = archive.read(name).decode('utf-8', errors='ignore')
    else:
        index_data = raw.decode('utf-8', errors='ignore')

    import json

    data = json.loads(index_data)
    docs = data.get('documentStore', {}).get('docs', {}) if isinstance(data, dict) else {}
    icao_upper = icao.upper()
    matches: list[dict[str, str]] = []

    for doc in docs.values():
        if not isinstance(doc, dict):
            continue
        doc_id = str(doc.get('id', ''))
        enlace = str(doc.get('enlace', ''))
        seccion = str(doc.get('seccion', ''))
        desc_es = str(doc.get('desc_es', '')).strip()
        desc_en = str(doc.get('desc_en', '')).strip()

        hay_match = (
            icao_upper in doc_id.upper()
            or icao_upper in enlace.upper()
            or icao_upper in seccion.upper()
            or icao_upper in desc_es.upper()
            or icao_upper in desc_en.upper()
        )
        if not hay_match:
            continue

        matches.append({
            'id': doc_id,
            'seccion': seccion,
            'desc_es': desc_es or desc_en or 'Sin descripción',
            'enlace': enlace,
        })
        if len(matches) >= limit:
            break

    return matches


def build_public_aip_message(icao: str) -> str:
    try:
        docs = _find_public_aip_docs(icao)
    except Exception:
        return normalize_output('No se pudo leer el índice público del AIP de ENAIRE.', f'NOTAM / AIP {icao}')

    if not docs:
        return normalize_output(
            'No se encontraron avisos públicos relacionados con este aeródromo en el índice del AIP.',
            f'NOTAM / AIP {icao}',
        )

    lines = [
        'Avisos públicos del AIP de ENAIRE. Esto no sustituye a un NOTAM en vivo, pero sirve como fallback gratuito.',
    ]
    for doc in docs:
        lines.append(f"- {doc['id']}: {doc['desc_es']}")
    return normalize_output('\n'.join(lines), f'NOTAM / AIP {icao}')


def _format_signed_number(value: str) -> str:
    if value.startswith('M'):
        return f'-{value[1:]}'
    return value


def _describe_metar_report(report: str) -> str:
    tokens = [token.strip() for token in report.split() if token.strip()]
    if not tokens:
        return 'Sin detalles de METAR disponibles.'

    while tokens and tokens[0] in {'METAR', 'SPECI', 'TAF'}:
        tokens = tokens[1:]
    if len(tokens) >= 2 and re.fullmatch(r'[A-Z]{4}', tokens[0]) and re.fullmatch(r'\d{6}Z', tokens[1]):
        tokens = tokens[2:]
    elif tokens and re.fullmatch(r'\d{6}Z', tokens[0]):
        tokens = tokens[1:]

    details: list[str] = []
    remaining: list[str] = []

    for token in tokens:
        wind_match = re.fullmatch(r'(?P<dir>\d{3}|VRB)(?P<speed>\d{2})(?:G(?P<gust>\d{2}))?KT', token)
        temp_match = re.fullmatch(r'(?P<temp>M?\d{2})/(?P<dew>M?\d{2})', token)
        qnh_match = re.fullmatch(r'Q(?P<qnh>\d{4})', token)
        vis_match = re.fullmatch(r'\d{4}', token)

        if token == 'CAVOK':
            details.append('visibilidad excelente y sin nubosidad significativa')
        elif token == 'NOSIG':
            details.append('sin cambios significativos a corto plazo')
        elif wind_match:
            direction = wind_match.group('dir')
            speed = wind_match.group('speed')
            gust = wind_match.group('gust')
            if direction == 'VRB':
                wind_text = f'viento variable de {speed} nudos'
            else:
                wind_text = f'viento del {direction} a {speed} nudos'
            if gust:
                wind_text += f', con rachas de {gust} nudos'
            details.append(wind_text)
        elif temp_match:
            temp = _format_signed_number(temp_match.group('temp'))
            dew = _format_signed_number(temp_match.group('dew'))
            details.append(f'temperatura {temp} C y punto de rocío {dew} C')
        elif qnh_match:
            details.append(f'QNH {qnh_match.group("qnh")} hPa')
        elif vis_match:
            details.append(f'visibilidad de {int(token)} metros')
        elif token not in {'RMK'}:
            remaining.append(token)

    sentences = []
    if details:
        sentences.append('Resumen: ' + '; '.join(details) + '.')
    if remaining:
        sentences.append('Datos técnicos: ' + ' '.join(remaining))
    if not sentences:
        sentences.append('Sin interpretación adicional disponible.')
    return '\n'.join(sentences)


def _describe_taf_report(report: str) -> str:
    tokens = [token.strip() for token in report.split() if token.strip()]
    if not tokens:
        return 'Sin detalles de TAF disponibles.'

    while tokens and tokens[0] == 'TAF':
        tokens = tokens[1:]
    if len(tokens) >= 2 and re.fullmatch(r'[A-Z]{4}', tokens[0]) and re.fullmatch(r'\d{6}Z', tokens[1]):
        tokens = tokens[2:]

    parts: list[str] = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if re.fullmatch(r'\d{4}/\d{4}', token):
            start_day = token[:2]
            start_hour = token[2:4]
            end_day = token[5:7]
            end_hour = token[7:9]
            parts.append(f'Validez prevista del día {start_day} a las {start_hour} UTC hasta el día {end_day} a las {end_hour} UTC')
        elif token.startswith('FM') and re.fullmatch(r'FM\d{6}', token):
            parts.append(f'A partir del día {token[2:4]} a las {token[4:6]} UTC')
        elif token == 'TEMPO':
            parts.append('con cambios temporales:')
        elif token == 'BECMG':
            parts.append('con evolución gradual hacia:')
        elif token in {'PROB30', 'PROB40'}:
            parts.append(f'con probabilidad del {token[4:]}%:')
        elif token == 'CAVOK':
            parts.append('visibilidad excelente y sin nubosidad significativa')
        elif token == 'NOSIG':
            parts.append('sin cambios significativos')
        elif re.fullmatch(r'TX\d{2}/\d{4}Z', token):
            temp = token[2:4]
            day = token[5:7]
            hour = token[7:9]
            parts.append(f'temperatura máxima {temp} C alrededor del día {day} a las {hour} UTC')
        elif re.fullmatch(r'TN\d{2}/\d{4}Z', token):
            temp = token[2:4]
            day = token[5:7]
            hour = token[7:9]
            parts.append(f'temperatura mínima {temp} C alrededor del día {day} a las {hour} UTC')
        else:
            wind_match = re.fullmatch(r'(?P<dir>\d{3}|VRB)(?P<speed>\d{2})(?:G(?P<gust>\d{2}))?KT', token)
            temp_match = re.fullmatch(r'(?P<temp>M?\d{2})/(?P<dew>M?\d{2})', token)
            qnh_match = re.fullmatch(r'Q(?P<qnh>\d{4})', token)
            vis_match = re.fullmatch(r'\d{4}', token)
            if wind_match:
                direction = wind_match.group('dir')
                speed = wind_match.group('speed')
                gust = wind_match.group('gust')
                if direction == 'VRB':
                    wind_text = f'viento variable de {speed} nudos'
                else:
                    wind_text = f'viento del {direction} a {speed} nudos'
                if gust:
                    wind_text += f', con rachas de {gust} nudos'
                parts.append(wind_text)
            elif temp_match:
                temp = _format_signed_number(temp_match.group('temp'))
                dew = _format_signed_number(temp_match.group('dew'))
                parts.append(f'temperatura {temp} C y punto de rocío {dew} C')
            elif qnh_match:
                parts.append(f'QNH {qnh_match.group("qnh")} hPa')
            elif vis_match:
                parts.append(f'visibilidad de {int(token)} metros')
            else:
                parts.append(token)
        i += 1

    cleaned: list[str] = []
    last = None
    for part in parts:
        if part == last:
            continue
        cleaned.append(part)
        last = part
    return ' '.join(cleaned).strip()



def _plain_spanish_fallback(raw_text: str, title: str) -> str:
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    title_upper = title.upper()

    if title_upper.startswith('METEO'):
        metar_line = next((line for line in lines if line.startswith('METAR:')), '')
        taf_line = next((line for line in lines if line.startswith('TAF:')), '')
        station_line = next((line for line in lines if line.startswith('ESTACIÓN:')), '')

        metar_report = metar_line.split(':', 1)[1].strip() if ':' in metar_line else ''
        taf_report = taf_line.split(':', 1)[1].strip() if ':' in taf_line else ''
        station = station_line.split(':', 1)[1].strip() if ':' in station_line else ''

        output_lines = []
        if station:
            output_lines.append(f'Estación: {station}')
        if metar_report:
            output_lines.append(_describe_metar_report(metar_report))
        if taf_report:
            output_lines.append('Pronóstico TAF: ' + _describe_taf_report(taf_report))
        if not output_lines:
            output_lines.append('Sin datos meteorológicos disponibles.')
        return normalize_output('\n'.join(output_lines), title)

    if title_upper.startswith('NOTAM'):
        return normalize_output(raw_text, title)

    return raw_text.strip()


def _ollama_output_is_reasonable(output: str, fallback: str) -> bool:
    cleaned = output.strip()
    if not cleaned:
        return False
    if len(cleaned) < max(40, len(fallback) // 3):
        return False
    forbidden = ['méxico', 'mexico', 'lomé', 'lome']
    lowered = cleaned.lower()
    if any(term in lowered for term in forbidden):
        return False
    if 'ventos ' in lowered:
        return False
    return True


def render_plain_spanish(raw_text: str, title: str, settings: Settings) -> str:
    fallback = _plain_spanish_fallback(raw_text, title)
    if title.upper().startswith('METEO'):
        return fallback
    if not settings.ollama_base_url or not settings.ollama_model:
        return fallback

    base_url = settings.ollama_base_url.rstrip('/')
    prompt = (
        'Eres un asistente de operaciones aeronáuticas.\n'
        'Reescribe el texto siguiente en español natural y claro.\n'
        'Reglas:\n'
        '- No inventes datos ni cambies números, códigos o unidades.\n'
        '- Mantén el significado exacto.\n'
        '- No menciones el título interno ni hagas referencias raras.\n'
        '- Si ya está claro, solo mejóralo un poco.\n\n'
        f'Texto a reescribir:\n{fallback}'
    )

    try:
        response = requests.post(
            f'{base_url}/api/generate',
            json={
                'model': settings.ollama_model,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': 0,
                    'top_p': 0.2,
                    'repeat_penalty': 1.1,
                    'num_predict': 220,
                },
            },
            timeout=90,
        )
        response.raise_for_status()
        data = response.json()
        message = data.get('response', '').strip()
        if _ollama_output_is_reasonable(message, fallback):
            return message
        return fallback
    except Exception:
        return fallback
