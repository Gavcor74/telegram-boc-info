const TELEGRAM_BOT_TOKEN = clean(process.env.TELEGRAM_BOT_TOKEN);
const TARGET_ICAO = clean(process.env.TARGET_ICAO || 'LEMO').toUpperCase();
const HTTP_USER_AGENT = clean(process.env.HTTP_USER_AGENT || 'AGENTE-BOC/1.0');
const ANTHROPIC_API_KEY = clean(process.env.ANTHROPIC_API_KEY);
const ANTHROPIC_BASE_URL = clean(process.env.ANTHROPIC_BASE_URL || 'https://api.anthropic.com').replace(/\/$/, '');
const ANTHROPIC_MODEL = clean(process.env.ANTHROPIC_MODEL || 'claude-sonnet-4-5');
const MAX_TOKENS = Number(process.env.MAX_TOKENS || 900);
const NOTAM_SOURCE_TEXT = clean(process.env.NOTAM_SOURCE_TEXT || '');
const METEO_SOURCE_TEXT = clean(process.env.METEO_SOURCE_TEXT || '');

const EMOJI = {
  plane: String.fromCodePoint(0x2708, 0xfe0f),
  antenna: String.fromCodePoint(0x1f4e1),
  landing: String.fromCodePoint(0x1f6ec),
  warning: String.fromCodePoint(0x26a0, 0xfe0f),
  point: String.fromCodePoint(0x1f449),
  stop: String.fromCodePoint(0x1f6d1),
  construction: String.fromCodePoint(0x1f6a7),
  info: String.fromCodePoint(0x2139, 0xfe0f),
  clock: String.fromCodePoint(0x1f552),
  cloud: String.fromCodePoint(0x2601, 0xfe0f),
  wind: String.fromCodePoint(0x1f32c, 0xfe0f),
  temp: String.fromCodePoint(0x1f321, 0xfe0f),
};

function clean(value) {
  return String(value || '').trim().replace(/^["']|["']$/g, '');
}

function normalizeHeader(text) {
  return String(text || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}

function chunkTelegram(text, max = 3900) {
  const chunks = [];
  let remaining = String(text || '').trim();
  while (remaining.length > max) {
    let cut = remaining.lastIndexOf('\n\n', max);
    if (cut < 500) cut = remaining.lastIndexOf('\n', max);
    if (cut < 500) cut = max;
    chunks.push(remaining.slice(0, cut).trim());
    remaining = remaining.slice(cut).trim();
  }
  if (remaining) chunks.push(remaining);
  return chunks;
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    ...options,
    headers: {
      'user-agent': HTTP_USER_AGENT,
      accept: 'application/json,text/plain,*/*',
      ...(options.headers || {}),
    },
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${text.slice(0, 180)}`);
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`Respuesta no JSON: ${text.slice(0, 180)}`);
  }
}

function firstItem(data) {
  if (Array.isArray(data)) return data[0] || {};
  if (data && Array.isArray(data.data)) return data.data[0] || {};
  return data || {};
}

function rawFrom(item, keys) {
  for (const key of keys) {
    if (typeof item?.[key] === 'string' && item[key].trim()) return item[key].trim();
  }
  return '';
}

export async function getMeteoRaw(icao = TARGET_ICAO) {
  if (METEO_SOURCE_TEXT) return METEO_SOURCE_TEXT;
  const params = new URLSearchParams({ ids: icao, format: 'json' });
  const [metarData, tafData] = await Promise.all([
    fetchJson(`https://aviationweather.gov/api/data/metar?${params}`),
    fetchJson(`https://aviationweather.gov/api/data/taf?${params}`),
  ]);
  const metarItem = firstItem(metarData);
  const tafItem = firstItem(tafData);
  const metar = rawFrom(metarItem, ['rawOb', 'raw_text', 'raw', 'text', 'metar']);
  const taf = rawFrom(tafItem, ['rawTAF', 'rawOb', 'raw_text', 'raw', 'text', 'taf']);
  const lines = [`METEO ${icao}`];
  if (metar) lines.push(`METAR: ${metar}`);
  if (taf) lines.push(`TAF: ${taf}`);
  if (!metar && !taf) lines.push('Sin datos meteorologicos disponibles.');
  return lines.join('\n');
}

function parseDate(value) {
  if (!value) return null;
  const text = String(value).trim();
  let m = text.match(/^(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (m) return new Date(Date.UTC(Number(m[3]), Number(m[2]) - 1, Number(m[1]), Number(m[4]), Number(m[5]), Number(m[6] || 0)));
  m = text.match(/^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})$/);
  if (m) return new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]), Number(m[4]), Number(m[5])));
  return null;
}

function formatDate(value) {
  const dt = parseDate(value);
  if (!dt) return value || 'sin fecha';
  const pad = (n) => String(n).padStart(2, '0');
  return `${pad(dt.getUTCDate())}/${pad(dt.getUTCMonth() + 1)}/${dt.getUTCFullYear()} ${pad(dt.getUTCHours())}:${pad(dt.getUTCMinutes())} UTC`;
}

function friendlyNotam(desc) {
  const text = String(desc || '').replace(/\s+/g, ' ').trim();
  const upper = text.toUpperCase();
  if (upper.includes('VOR/DME') || upper.includes('TACAN') || upper.includes('RADIOAID')) {
    const title = upper.includes('VOR/DME') ? 'VOR/DME MRN 115.500 / CH102X' : upper.includes('TACAN') ? 'TACAN MRN CH100X' : text;
    const notes = [];
    if (upper.includes('UNMONITORED')) notes.push('Funciona, pero sin supervision tecnica.', 'No confiar al 100% para procedimientos criticos.');
    if (upper.includes('U/S') && !upper.includes('UNMONITORED')) notes.push('Puede estar fuera de servicio o degradado.');
    if (!notes.length) notes.push('Estado operativo a revisar con precaucion.');
    return { section: 'radio', title, notes };
  }
  if (upper.includes('GCA') || upper.includes('APPROACH') || upper.includes('APPROX')) {
    return { section: 'approach', title: upper.includes('GCA') ? 'GCA (Ground Controlled Approach)' : text, notes: ['Fuera de servicio.', 'No disponible para aproximaciones guiadas por radar.'] };
  }
  if (upper.includes('ARRESTING')) return { section: 'arresting', title: text.replace(/\s+U\/S\b/i, ''), notes: ['Fuera de servicio.', 'Sin sistema de frenado operativo en esa ventana.'] };
  if (upper.includes('RWY') || upper.includes('TWY') || upper.includes('AD LTD') || upper.includes('WIP')) {
    const notes = [];
    if (upper.includes('ONLY ALLOWED FOR VFR HELICOPTERS')) notes.push('Solo permitido para helicopteros VFR.');
    if (upper.includes('SR/SS')) notes.push('Ventana operativa entre salida y puesta de sol.');
    if (upper.includes('PPR')) notes.push('PPR obligatorio con antelacion.');
    notes.push('Operacion restringida: revisar antes de planificar.');
    return { section: 'restriction', title: text, notes };
  }
  if (upper.includes('PPR')) return { section: 'coordination', title: text, notes: ['PPR obligatorio con antelacion.'] };
  return { section: 'other', title: text, notes: ['Revisar texto completo antes de usar operacionalmente.'] };
}

function sectionLabel(section) {
  const labels = {
    radio: `${EMOJI.antenna} Radioayudas`,
    approach: `${EMOJI.landing} Sistemas de aproximacion`,
    arresting: `${EMOJI.stop} Sistemas de frenado`,
    restriction: `${EMOJI.construction} Restricciones de aerodromo`,
    coordination: 'Coordinacion previa',
    other: `${EMOJI.info} Otros avisos`,
  };
  return labels[section] || labels.other;
}

export async function getNotamsRaw(icao = TARGET_ICAO) {
  if (NOTAM_SOURCE_TEXT) return NOTAM_SOURCE_TEXT;
  const url = 'https://servais.enaire.es/insignias/rest/services/NOTAM/NOTAM_APP_V3/MapServer/0/query';
  const outFields = 'notamId,notamSerie,notamNumber,notamYear,itemA,itemBstr,itemCstr,itemD,itemE,affectedElement,DESCRIPTION,icaoFormatText,sourceInformationNotam';
  const makeUrl = (where) => `${url}?${new URLSearchParams({
    f: 'json',
    where,
    outFields,
    returnGeometry: 'false',
    orderByFields: 'notamYear DESC, notamNumber DESC',
    resultRecordCount: '20',
  })}`;
  let payload = await fetchJson(makeUrl(`itemA = '${icao}'`));
  let features = Array.isArray(payload.features) ? payload.features : [];
  if (!features.length) {
    payload = await fetchJson(makeUrl(`icaoFormatText LIKE '%A)${icao}%'`));
    features = Array.isArray(payload.features) ? payload.features : [];
  }
  return JSON.stringify({ icao, features }, null, 2);
}

export function formatNotams(raw, icao = TARGET_ICAO) {
  let features = [];
  try {
    const parsed = JSON.parse(raw);
    features = Array.isArray(parsed.features) ? parsed.features : [];
  } catch {
    return `NOTAM ${icao}\n\n${raw}`;
  }
  if (!features.length) return `NOTAM ${icao}\n\nNo se encontraron NOTAM publicos para este aerodromo en Insignia/ENAIRE.`;

  const now = new Date();
  const groups = { vigente: [], proximo: [] };
  for (const feature of features) {
    const attrs = feature?.attributes || {};
    const id = attrs.notamId || attrs.sourceInformationNotam || 'NOTAM';
    const start = attrs.itemBstr || '';
    const end = attrs.itemCstr || '';
    const desc = attrs.itemE || attrs.DESCRIPTION || attrs.icaoFormatText || '';
    const startDate = parseDate(start);
    const endDate = parseDate(end);
    if (endDate && now > endDate) continue;
    const status = startDate && now < startDate ? 'proximo' : 'vigente';
    const friendly = friendlyNotam(desc);
    groups[status].push({ id, start, end, ...friendly });
  }

  const lines = [
    `NOTAM ${icao}`,
    '',
    'Resumen operativo de NOTAM desde Insignia/ENAIRE. Es una traduccion util y sencilla, no el texto legal completo.',
  ];
  const renderGroup = (key, heading) => {
    const items = groups[key];
    if (!items.length) return;
    lines.push('', heading);
    let lastSection = '';
    for (const item of items) {
      if (item.section !== lastSection) {
        lastSection = item.section;
        lines.push(sectionLabel(item.section));
      }
      lines.push(`- ${item.id} ${formatDate(item.start)} -> ${formatDate(item.end)}`);
      lines.push(`  ${item.title}`);
      for (const note of item.notes) lines.push(`  ${EMOJI.point} ${note}`);
    }
  };
  renderGroup('vigente', `${EMOJI.plane} Estado actual (en vigor ahora)`);
  renderGroup('proximo', `${EMOJI.warning} Proximos eventos (planificacion)`);
  return lines.join('\n');
}

function describeMetar(report) {
  const tokens = String(report || '').split(/\s+/).filter(Boolean);
  const details = [];
  for (const token of tokens) {
    let m = token.match(/^(\d{3}|VRB)(\d{2})(?:G(\d{2}))?KT$/);
    if (m) details.push(`${EMOJI.wind} Viento ${m[1] === 'VRB' ? 'variable' : 'del ' + m[1]} a ${m[2]} kt${m[3] ? ', rachas ' + m[3] + ' kt' : ''}`);
    else if (token === 'CAVOK') details.push(`${EMOJI.cloud} CAVOK: visibilidad buena, sin nubosidad significativa`);
    else if (token === 'NOSIG') details.push('NOSIG: sin cambios significativos a corto plazo');
    else if (/^Q\d{4}$/.test(token)) details.push(`QNH ${token.slice(1)} hPa`);
    else if (/^(M?\d{2})\/(M?\d{2})$/.test(token)) details.push(`${EMOJI.temp} Temperatura/punto de rocio ${token.replaceAll('M', '-')}`);
  }
  return details.length ? details.join('\n') : 'Sin interpretacion automatica disponible.';
}

export function formatMeteo(raw, icao = TARGET_ICAO) {
  const lines = String(raw || '').split('\n').map((line) => line.trim()).filter(Boolean);
  const metar = (lines.find((line) => line.startsWith('METAR:')) || '').split(':').slice(1).join(':').trim();
  const taf = (lines.find((line) => line.startsWith('TAF:')) || '').split(':').slice(1).join(':').trim();
  const out = [`METEO ${icao}`];
  if (metar) out.push('', 'METAR bruto:', metar, '', 'Lectura rapida:', describeMetar(metar));
  if (taf) out.push('', 'TAF bruto:', taf);
  if (!metar && !taf) out.push('', 'Sin datos meteorologicos disponibles.');
  return out.join('\n');
}

async function refineWithAnthropic(kind, text) {
  if (!ANTHROPIC_API_KEY) return text;
  const prompt = kind === 'NOTAM'
    ? `Revisa este resumen operativo de NOTAM para ${TARGET_ICAO}. Manten el formato, no inventes datos, no cambies codigos/fechas/unidades. Mejora solo la claridad en espanol y conserva la frase de que no es texto legal completo.\n\n${text}`
    : `Interpreta esta METEO aeronautica para ${TARGET_ICAO} en espanol claro. Mantiene METAR/TAF brutos, no inventes datos, no cambies numeros/unidades. Anade solo lectura operativa prudente.\n\n${text}`;
  const response = await fetch(`${ANTHROPIC_BASE_URL}/v1/messages`, {
    method: 'POST',
    headers: {
      'x-api-key': ANTHROPIC_API_KEY,
      'anthropic-version': '2023-06-01',
      'content-type': 'application/json',
    },
    body: JSON.stringify({
      model: ANTHROPIC_MODEL,
      max_tokens: MAX_TOKENS,
      temperature: 0,
      system: 'Eres un asistente de operaciones aeronauticas. No inventas datos. Eres claro, prudente y conciso.',
      messages: [{ role: 'user', content: prompt }],
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) return text;
  const output = (data.content || []).filter((block) => block.type === 'text').map((block) => block.text).join('').trim();
  return output || text;
}

export async function buildMeteoMessage() {
  const raw = await getMeteoRaw(TARGET_ICAO);
  return refineWithAnthropic('METEO', formatMeteo(raw, TARGET_ICAO));
}

export async function buildNotamsMessage() {
  const raw = await getNotamsRaw(TARGET_ICAO);
  return refineWithAnthropic('NOTAM', formatNotams(raw, TARGET_ICAO));
}

export async function telegram(method, payload) {
  if (!TELEGRAM_BOT_TOKEN) throw new Error('Falta TELEGRAM_BOT_TOKEN.');
  const response = await fetch(`https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/${method}`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.description || `Telegram error ${response.status}`);
  return data;
}

export async function sendLongMessage(chatId, text) {
  for (const chunk of chunkTelegram(text)) {
    await telegram('sendMessage', { chat_id: chatId, text: chunk });
  }
}

export function statusMessage() {
  return [
    'AGENTE BOC activo en Vercel.',
    `ICAO objetivo: ${TARGET_ICAO}`,
    `Anthropic: ${ANTHROPIC_API_KEY ? 'configurado' : 'sin configurar'}`,
    'Comandos: /meteo /notams /status',
  ].join('\n');
}

export function helpMessage() {
  return [
    'BOC_Notas listo.',
    '',
    '/meteo - METAR/TAF de LEMO con lectura rapida',
    '/notams - resumen operativo de NOTAM LEMO',
    '/status - estado del servicio',
    '',
    'Aviso: ayuda operativa. No sustituye fuentes oficiales ni criterio profesional.',
  ].join('\n');
}