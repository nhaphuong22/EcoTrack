const bcrypt = require('bcryptjs');
const prisma = require('../db');

async function seedDefaultAdminIfNeeded() {
  const adminEmail = process.env.ADMIN_EMAIL;
  const adminPassword = process.env.ADMIN_PASSWORD;

  if (!adminEmail || !adminPassword) {
    return;
  }

  try {
    if (!prisma.user || typeof prisma.user.count !== 'function') {
      return;
    }

    const count = await prisma.user.count();
    if (count === 0) {
      const passwordHash = await bcrypt.hash(adminPassword, 10);
      await prisma.user.create({
        data: {
          email: adminEmail,
          password_hash: passwordHash,
          name: process.env.ADMIN_NAME || 'System Admin',
          role: 'ADMIN',
        },
      });
      console.log(`[EcoTrack Express Backend] Default admin user initialized (${adminEmail}).`);
    }
  } catch (err) {
    console.error('[EcoTrack Express Backend] Error seeding default admin user:', err.message);
  }
}

module.exports = {
  seedDefaultAdminIfNeeded,
};
