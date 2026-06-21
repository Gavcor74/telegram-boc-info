import { telegram } from './lib.js';

export default async function handler(req, res) {
  if (req.method !== 'GET' && req.method !== 'POST') {
    return res.status(405).json({ ok: false, error: 'method_not_allowed' });
  }
  const host = req.headers['x-forwarded-host'] || req.headers.host;
  const proto = req.headers['x-forwarded-proto'] || 'https';
  const url = `${proto}://${host}/api/telegram`;
  try {
    const result = await telegram('setWebhook', { url, allowed_updates: ['message'] });
    return res.status(200).json({ ok: true, webhook: url, telegram: result });
  } catch (error) {
    return res.status(500).json({ ok: false, error: error.message });
  }
}