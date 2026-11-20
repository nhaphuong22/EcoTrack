require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });
const fs = require('fs');
const path = require('path');
const { randomBytes } = require('crypto');
const { PrismaClient } = require('@prisma/client');
const { hashPassword } = require('../src/services/authService');
const prisma = new PrismaClient();
async function main() {
  const args = process.argv.slice(2);
  const arg = (name, fallback) => args.includes(name) ? args[args.indexOf(name) + 1] : fallback;
  const email = arg('--email', 'manager@ecotrack.local').trim().toLowerCase();
  const buildingId = arg('--building', 'office_tower_01');
  if (!await prisma.building.findUnique({ where: { id: buildingId } })) throw new Error('Building does not exist. Start the backend once first.');
  let user = await prisma.user.findUnique({ where: { email } });
  if (!user) {
    const password = randomBytes(24).toString('base64url');
    user = await prisma.user.create({ data: { email, name: 'EcoTrack Manager', password_hash: await hashPassword(password) } });
    const output = path.resolve(__dirname, '../.demo-manager.key');
    fs.writeFileSync(output, `Email: ${email}\nPassword: ${password}\nBuilding: ${buildingId}\n`, { mode: 0o600 });
    console.log('Created manager login. Credentials are in backend/.demo-manager.key (Git-ignored).');
  }
  await prisma.buildingStaff.upsert({ where: { building_id_user_id: { building_id: buildingId, user_id: user.id } },
    update: {}, create: { building_id: buildingId, user_id: user.id, role: 'MANAGER' } });
  console.log(`Granted building manager access for ${email} on ${buildingId}. No platform administrator privileges granted.`);
}
main().catch((error) => { console.error(error.message); process.exitCode = 1; }).finally(() => prisma.$disconnect());
