const { timingSafeEqual } = require('crypto');

function requireApiKey(environmentName, headerName) {
  return (req, res, next) => {
    const expected = process.env[environmentName];
    if (!expected) {
      return res.status(503).json({ detail: `${environmentName} is not configured.` });
    }
    const provided = req.get(headerName) || '';
    const actualBuffer = Buffer.from(provided);
    const expectedBuffer = Buffer.from(expected);
    if (actualBuffer.length !== expectedBuffer.length || !timingSafeEqual(actualBuffer, expectedBuffer)) {
      return res.status(401).json({ detail: `Unauthorized: Invalid or missing ${headerName} header.` });
    }
    next();
  };
}

module.exports = { requireApiKey };
