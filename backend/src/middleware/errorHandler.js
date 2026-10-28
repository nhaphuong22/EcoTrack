const { ZodError } = require('zod');

function errorHandler(err, req, res, next) {
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
  const message = err.message || 'Internal Server Error';

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
