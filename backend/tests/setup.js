const jwt = require('jsonwebtoken');

process.env.INTERNAL_API_KEY = process.env.INTERNAL_API_KEY || 'test-internal-token-for-vitest';
process.env.JWT_SECRET = process.env.JWT_SECRET || 'test-jwt-secret-for-vitest-only';

function generateTestToken(role = 'ADMIN', userId = 'usr_test_01') {
  return jwt.sign(
    {
      id: userId,
      sub: userId,
      email: `${role.toLowerCase()}@ecotrack.io`,
      role,
      name: `Test ${role}`,
    },
    process.env.JWT_SECRET,
    { expiresIn: '1h' }
  );
}

function authHeaderFor(role = 'ADMIN', userId = 'usr_test_01') {
  return {
    Authorization: `Bearer ${generateTestToken(role, userId)}`,
  };
}

global.generateTestToken = generateTestToken;
global.authHeaderFor = authHeaderFor;

module.exports = {
  generateTestToken,
  authHeaderFor,
};
