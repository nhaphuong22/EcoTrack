const { resolveSession } = require('../services/authService');
async function requireUser(req, res, next) {
  try {
    req.user = await resolveSession(req);
    if (!req.user) return res.status(401).json({ detail: 'Please sign in.' });
    next();
  } catch (error) { next(error); }
}
function requirePlatformAdmin(req, res, next) {
  if (!req.user?.is_platform_admin) return res.status(403).json({ detail: 'Use the household portal for scoped access.' });
  next();
}
module.exports = { requireUser, requirePlatformAdmin };
