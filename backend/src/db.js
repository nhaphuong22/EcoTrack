const { PrismaClient } = require('@prisma/client');

let realPrisma = null;

function getPrisma() {
  if (global.__mockPrisma) {
    return global.__mockPrisma;
  }
  if (!realPrisma) {
    realPrisma = new PrismaClient({
      log: process.env.NODE_ENV === 'development' ? ['warn', 'error'] : ['error'],
    });
  }
  return realPrisma;
}

module.exports = new Proxy({}, {
  get(target, prop) {
    const client = getPrisma();
    const val = client[prop];
    if (typeof val === 'function') {
      return val.bind(client);
    }
    return val;
  },
});
