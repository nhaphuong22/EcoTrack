require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });
const fs = require('fs');
const path = require('path');
const { randomBytes } = require('crypto');
const { PrismaClient } = require('@prisma/client');
const { z } = require('zod');
const { hashPassword } = require('../src/services/authService');
const prisma = new PrismaClient();
async function main() {
  const args = process.argv.slice(2);
  const index = args.indexOf('--email');
  const email = z.string().email().max(254).parse(index >= 0 ? args[index + 1] : 'admin@ecotrack.local').toLowerCase();
  const existing = await prisma.user.findUnique({ where: { email } });
  if (existing) {
    await prisma.user.update({ where: { id: existing.id }, data: { is_platform_admin: true } });
    console.log('Platform administrator access granted. Existing password preserved.');
    return;
  }
  const password = randomBytes(24).toString('base64url');
  await prisma.user.create({ data: { email, name: 'EcoTrack Administrator',
    password_hash: await hashPassword(password), is_platform_admin: true } });
  fs.writeFileSync(path.resolve(__dirname, '../.demo-admin.key'),
    `Email: ${email}\nPassword: ${password}\nRole: Platform administrator\n`, { mode: 0o600 });
  console.log('Platform administrator created. Credentials: backend/.demo-admin.key (Git-ignored).');
}
main().catch((error) => { console.error(error.message); process.exitCode = 1; }).finally(() => prisma.$disconnect());
