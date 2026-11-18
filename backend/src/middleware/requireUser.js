const { resolveSession, operatorRole } = require('../services/authService');
async function requireUser(req, res, next) {
  try {
    req.user = await resolveSession(req);
    if (!req.user) return res.status(401).json({ detail: 'Please sign in.' });
    next();
  } catch (error) { next(error); }
}
// Operators (ADMIN/MANAGER/TECHNICIAN) only; residents have no operator role and use the household portal.
function requireRole(...roles) {
  return (req, res, next) => {
    const role = operatorRole(req.user);
    if (!role || (roles.length && !roles.includes(role))) {
      return res.status(403).json({ detail: 'Your role is not allowed to do this.' });
    }
    next();
  };
}
module.exports = { requireUser, requireRole };
