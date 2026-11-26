const express = require('express');
const { z } = require('zod');
const prisma = require('../db');
const { requireUser } = require('../middleware/requireUser');
const { hashPassword, verifyPassword, hashToken, startSession, sessionCookie, tokenFrom, publicUser } = require('../services/authService');
const { createGoogleRouter } = require('./googleAuth');
const router = express.Router();
const credentials = z.object({ email: z.string().trim().email().max(254).transform((value) => value.toLowerCase()),
  password: z.string().min(10).max(128) });
const attempts = new Map();
// Bound memory and work before invoking the password KDF. Applies to registration too.
function limit(req, res, next) {
  const now = Date.now();
  for (const [key, item] of attempts) if (item.expires <= now) attempts.delete(key);
  const key = req.ip;
  const item = attempts.get(key) || { count: 0, expires: now + 15 * 60000 };
  if (item.count >= 20 || (!attempts.has(key) && attempts.size >= 10000)) {
    res.setHeader('Retry-After', '900');
    return res.status(429).json({ detail: 'Too many attempts. Try again later.' });
  }
  item.count += 1;
  attempts.set(key, item);
  next();
}
router.use('/google/start', limit);
router.use('/google', createGoogleRouter());
router.post('/register', limit, async (req, res, next) => {
  try {
    const input = credentials.extend({ name: z.string().trim().min(1).max(100) }).parse(req.body);
    const password_hash = await hashPassword(input.password);
    const user = await prisma.user.create({ data: { email: input.email, name: input.name, password_hash } });
    const token = await startSession(user.id);
    res.setHeader('Set-Cookie', sessionCookie(req, token));
    res.status(201).json({ user: publicUser(user) });
  } catch (error) {
    if (error.code === 'P2002') return res.status(409).json({ detail: 'Email is already registered.' });
    next(error);
  }
});
router.post('/login', limit, async (req, res, next) => {
  try {
    const input = credentials.parse(req.body);
    const user = await prisma.user.findUnique({ where: { email: input.email } });
    // Dummy KDF work avoids a fast absent-account path.
    const stored = user?.password_hash || `scrypt$${'0'.repeat(32)}$${'0'.repeat(128)}`;
    const valid = await verifyPassword(input.password, stored);
    if (!user || !user.password_hash || !valid || !user.active) return res.status(401).json({ detail: 'Invalid email or password.' });
    const token = await startSession(user.id);
    res.setHeader('Set-Cookie', sessionCookie(req, token));
    res.json({ message: 'Signed in.' });
  } catch (error) { next(error); }
});
router.get('/me', requireUser, (req, res) => res.json({ user: publicUser(req.user) }));
router.post('/logout', async (req, res, next) => {
  try {
    const token = tokenFrom(req);
    if (token) await prisma.authSession.deleteMany({ where: { token_hash: hashToken(token) } });
    res.setHeader('Set-Cookie', sessionCookie(req, '', 0));
    res.json({ message: 'Signed out.' });
  } catch (error) { next(error); }
});
module.exports = router;
