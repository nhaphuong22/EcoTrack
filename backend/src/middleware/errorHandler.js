const { ZodError } = require('zod');

function errorHandler(err, req, res, next) {
  if (err.code === 'P2002') return res.status(409).json({ detail: 'Record already exists or an active occupancy already exists.' });
  if (err instanceof ZodError) {
    return res.status(422).json({
      detail: err.errors.map((e) => ({
        loc: e.path,
        msg: e.message,
        type: e.code,
      })),
    });
  }

  const status = err.status || 500;
  const message = status >= 500 ? 'The service is temporarily unavailable.' : err.message || 'Request failed.';

  if (status >= 500) {
    console.error('Unhandled Server Error:', err);
  }

  res.status(status).json({
    detail: message,
    status,
    ...(process.env.NODE_ENV === 'development' && { stack: err.stack }),
  });
}

module.exports = errorHandler;
