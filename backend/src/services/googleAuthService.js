const { OAuth2Client } = require('google-auth-library');
const prisma = require('../db');

function configuration() {
  const clientId = process.env.GOOGLE_CLIENT_ID;
  const clientSecret = process.env.GOOGLE_CLIENT_SECRET;
  const redirectUri = process.env.GOOGLE_REDIRECT_URI;
  const frontend = process.env.APP_FRONTEND_URL || 'http://localhost:3000';
  if (!clientId || !clientSecret || !redirectUri) throw new Error('Google sign-in is not configured.');
  for (const value of [redirectUri, frontend]) {
    const url = new URL(value);
    if (url.protocol !== 'https:' && !(url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) {
      throw new Error('OAuth endpoints require HTTPS outside localhost.');
    }
  }
  return { clientId, clientSecret, redirectUri, frontend };
}

async function exchange(code, flow, config) {
  const client = new OAuth2Client({ clientId: config.clientId, clientSecret: config.clientSecret,
    redirectUri: config.redirectUri });
  const { tokens } = await client.getToken({ code, codeVerifier: flow.code_verifier,
    redirect_uri: config.redirectUri });
  if (!tokens.id_token) throw new Error('Google did not provide an identity token.');
  // The library checks signature, issuer, audience, and expiry with Google's keys.
  const ticket = await client.verifyIdToken({ idToken: tokens.id_token, audience: config.clientId });
  return ticket.getPayload();
}

async function accountFor(payload, flow, signedInUser) {
  if (!payload || payload.nonce !== flow.nonce || payload.email_verified !== true
    || typeof payload.sub !== 'string' || !payload.sub || payload.sub.length > 255
    || typeof payload.email !== 'string' || payload.email.length > 254) {
    throw new Error('Invalid Google identity.');
  }
  const email = payload.email.trim().toLowerCase();
  if (flow.user_id) {
    // Linking requires both the original local session and the Google identity.
    if (!signedInUser || signedInUser.id !== flow.user_id || signedInUser.email !== email || !signedInUser.active) {
      throw new Error('Sign in to the matching local account before linking Google.');
    }
    const existing = await prisma.user.findUnique({ where: { google_sub: payload.sub } });
    if (existing && existing.id !== signedInUser.id) throw new Error('Google identity is already linked.');
    // Compare-and-set prevents a parallel flow from silently replacing a link.
    const result = await prisma.user.updateMany({ where: { id: signedInUser.id, active: true,
      OR: [{ google_sub: null }, { google_sub: payload.sub }] }, data: { google_sub: payload.sub } });
    if (result.count !== 1) throw new Error('Account already has a different Google identity.');
    return prisma.user.findUnique({ where: { id: signedInUser.id } });
  }
  const linked = await prisma.user.findUnique({ where: { google_sub: payload.sub } });
  if (linked) {
    if (!linked.active || linked.email !== email) throw new Error('Google account is unavailable or its email has changed.');
    return linked;
  }
  // Local email accounts are not automatically merged: their email was not
  // verified at password registration. Require explicit authenticated linking.
  if (await prisma.user.findUnique({ where: { email } })) {
    const error = new Error('Sign in with your existing password, then link Google.');
    error.code = 'GOOGLE_LINK_REQUIRED';
    throw error;
  }
  return prisma.user.create({ data: { email, google_sub: payload.sub,
    name: (String(payload.name || email).trim() || email).slice(0, 100) } });
}
module.exports = { configuration, exchange, accountFor };
