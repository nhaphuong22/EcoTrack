const express = require('express');
const { randomBytes, createHash } = require('crypto');
const prisma = require('../db');
const google = require('../services/googleAuthService');
const { hashToken, resolveSession, startSession, sessionCookie } = require('../services/authService');

function flowCookie(value, maxAge = 600) {
  return `ecotrack_oauth=${value}; HttpOnly; SameSite=Lax; Path=/api/v1/auth/google; Max-Age=${maxAge}`
    + (process.env.NODE_ENV === 'production' ? '; Secure' : '');
}
function createGoogleRouter({ exchange = google.exchange } = {}) {
  const router = express.Router();
  router.get('/start', async (req, res) => {
    try {
      const config = google.configuration();
      const user = await resolveSession(req);
      const state = randomBytes(32).toString('hex');
      const browser = randomBytes(32).toString('hex');
      const nonce = randomBytes(32).toString('hex');
      const verifier = randomBytes(48).toString('base64url');
      await prisma.oAuthFlow.deleteMany({ where: { expires_at: { lte: new Date() } } });
      await prisma.oAuthFlow.create({ data: { state_hash: hashToken(state), browser_hash: hashToken(browser),
        nonce, code_verifier: verifier, user_id: user?.id || null, expires_at: new Date(Date.now() + 600000) } });
      const url = new URL('https://accounts.google.com/o/oauth2/v2/auth');
      url.search = new URLSearchParams({ client_id: config.clientId, redirect_uri: config.redirectUri,
        response_type: 'code', scope: 'openid email profile', state, nonce,
        code_challenge: createHash('sha256').update(verifier).digest('base64url'), code_challenge_method: 'S256',
        prompt: 'select_account' }).toString();
      res.setHeader('Set-Cookie', flowCookie(browser));
      res.redirect(url.toString());
    } catch {
      res.status(503).json({ detail: 'Google sign-in is temporarily unavailable.' });
    }
  });
  router.get('/callback', async (req, res) => {
    let config;
    try { config = google.configuration(); } catch {
      return res.status(503).json({ detail: 'Google sign-in is not configured.' });
    }
    const destination = new URL(config.frontend);
    res.setHeader('Set-Cookie', flowCookie('', 0));
    try {
      const state = req.query.state;
      const browser = (req.headers.cookie || '').split(';').map((part) => part.trim())
        .find((part) => part.startsWith('ecotrack_oauth='))?.slice('ecotrack_oauth='.length);
      if (typeof state !== 'string' || !/^[a-f0-9]{64}$/.test(state)
        || !browser || !/^[a-f0-9]{64}$/.test(browser)) throw new Error('Invalid OAuth state.');
      const flow = await prisma.oAuthFlow.findUnique({ where: { state_hash: hashToken(state) } });
      if (!flow || flow.expires_at <= new Date() || flow.browser_hash !== hashToken(browser)) throw new Error('Invalid OAuth flow.');
      const consumed = await prisma.oAuthFlow.deleteMany({ where: { state_hash: flow.state_hash,
        browser_hash: flow.browser_hash, expires_at: { gt: new Date() } } });
      if (consumed.count !== 1) throw new Error('OAuth flow was already used.');
      if (req.query.error || typeof req.query.code !== 'string' || req.query.code.length > 4096) throw new Error('Google authorization failed.');
      const payload = await exchange(req.query.code, flow, config);
      const user = await google.accountFor(payload, flow, flow.user_id ? await resolveSession(req) : null);
      const token = await startSession(user.id);
      res.setHeader('Set-Cookie', [flowCookie('', 0), sessionCookie(req, token)]);
      res.redirect(destination.toString());
    } catch (error) {
      // Do not log OAuth codes, tokens, client secrets, or raw provider errors.
      destination.searchParams.set('auth_error', error.code === 'GOOGLE_LINK_REQUIRED' ? 'google_link_required' : 'google_failed');
      res.redirect(destination.toString());
    }
  });
  return router;
}
module.exports = { createGoogleRouter };
