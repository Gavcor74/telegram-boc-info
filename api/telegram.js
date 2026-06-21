import { buildMeteoMessage, buildNotamsMessage, helpMessage, sendLongMessage, statusMessage, telegram } from './lib.js';

function commandFrom(update) {
  const text = update?.message?.text || '';
  return text.trim().split(/\s+/)[0].replace(/^\//, '').split('@')[0].toLowerCase();
}

export default async function handler(req, res) {
  if (req.method === 'GET') {
    return res.status(200).json({ ok: true, service: 'telegram-boc-info' });
  }
  if (req.method !== 'POST') {
    return res.status(405).json({ ok: false, error: 'method_not_allowed' });
  }

  const update = req.body || {};
  const chatId = update?.message?.chat?.id;
  const command = commandFrom(update);

  if (!chatId) return res.status(200).json({ ok: true, ignored: true });

  try {
    if (command === 'start' || command === 'help') {
      await telegram('sendMessage', { chat_id: chatId, text: helpMessage() });
    } else if (command === 'status') {
      await telegram('sendMessage', { chat_id: chatId, text: statusMessage() });
    } else if (command === 'meteo') {
      await telegram('sendMessage', { chat_id: chatId, text: 'Consultando METEO LEMO...' });
      await sendLongMessage(chatId, await buildMeteoMessage());
    } else if (command === 'notams' || command === 'notam') {
      await telegram('sendMessage', { chat_id: chatId, text: 'Consultando NOTAM LEMO...' });
      await sendLongMessage(chatId, await buildNotamsMessage());
    } else {
      await telegram('sendMessage', { chat_id: chatId, text: helpMessage() });
    }
    return res.status(200).json({ ok: true });
  } catch (error) {
    await telegram('sendMessage', { chat_id: chatId, text: `Error: ${error.message}` }).catch(() => {});
    return res.status(200).json({ ok: false, error: error.message });
  }
}