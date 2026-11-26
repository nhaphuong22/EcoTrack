require('dotenv').config({ path: require('path').resolve(__dirname, '../.env') });
const assert = require('node:assert/strict');
const { randomUUID } = require('crypto');
const { PrismaClient } = require('@prisma/client');
const request = require('supertest');
const app = require('../src/app');
const { meterId } = require('../src/services/meterService');
const { broadcastReading } = require('../src/services/readingStreamService');
const prisma = new PrismaClient();
const rollback = new Error('ROLLBACK_AUTH_FIXTURES');
let checks = 0;
const check = (actual, expected) => { assert.deepEqual(actual, expected); checks += 1; };
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function main() {
  try {
    await prisma.$transaction(async (tx) => {
      let savepoint = 0;
      global.__mockPrisma = new Proxy(tx, { get(target, key) {
        if (key !== '$transaction') return target[key];
        return async (callback) => {
          const name = `auth_test_${++savepoint}`;
          await tx.$executeRawUnsafe(`SAVEPOINT ${name}`);
          try {
            const value = await callback(tx);
            await tx.$executeRawUnsafe(`RELEASE SAVEPOINT ${name}`);
            return value;
          } catch (error) {
            await tx.$executeRawUnsafe(`ROLLBACK TO SAVEPOINT ${name}`);
            throw error;
          }
        };
      } });
      const suffix = randomUUID();
      const buildingId = `auth-${suffix}`;
      const otherBuildingId = `other-${suffix}`;
      for (const id of [buildingId, otherBuildingId]) await tx.building.create({ data: { id, name: id } });
      const manager = request.agent(app), alice = request.agent(app), bob = request.agent(app), outsider = request.agent(app);
      const password = `Test-${suffix}`;
      const emails = { manager: `manager-${suffix}@example.test`, alice: `alice-${suffix}@example.test`, bob: `bob-${suffix}@example.test`, outsider: `other-${suffix}@example.test` };
      async function register(agent, name) {
        const response = await agent.post('/api/v1/auth/register').send({ email: emails[name], name, password, is_platform_admin: true });
        check(response.status, 201);
        check(response.body.user.is_platform_admin, false);
        assert.match(response.headers['set-cookie'][0], /HttpOnly; SameSite=Lax/);
        return response.headers['set-cookie'][0].split(';')[0];
      }
      await register(manager, 'manager');
      const aliceCookie = await register(alice, 'alice');
      await register(bob, 'bob'); const outsiderCookie = await register(outsider, 'outsider');
      check((await request(app).post('/api/v1/auth/login').send({ email: emails.outsider, password: 'WrongPassword123' })).status, 401);
      const login = await outsider.post('/api/v1/auth/login').send({ email: emails.outsider.toUpperCase(), password });
      check(login.status, 200);
      const loggedOutCookie = login.headers['set-cookie'][0].split(';')[0];
      const managerUser = await tx.user.findUnique({ where: { email: emails.manager } });
      await tx.buildingStaff.create({ data: { user_id: managerUser.id, building_id: buildingId } });

      for (const path of ['/api/v1/energy/metrics', '/api/v1/buildings', '/api/v1/anomalies/events', '/api/v1/stream/readings', '/api/v1/copilot/experiment-stats']) {
        check((await request(app).get(path)).status, 401);
        check((await alice.get(path)).status, 403);
      }
      const context = (scope, household_id) => ({ scope, building_id: buildingId, ...(household_id ? { household_id } : {}) });
      check((await outsider.get('/api/v1/portal/overview').query(context('building'))).status, 403);
      check((await manager.get('/api/v1/portal/manage').query({ building_id: otherBuildingId })).status, 403);
      check((await alice.post('/api/v1/portal/units').send({ building_id: buildingId, code: 'evil', household_name: 'evil' })).status, 403);
      check((await alice.post('/api/v1/auth/logout').set('Origin', 'https://attacker.test')).status, 403);

      const zones = ['a', 'b', 'common'].map((part) => `z-${part}-${suffix}`);
      for (const zoneId of zones) {
        await tx.zone.create({ data: { id: zoneId, building_id: buildingId, name: zoneId } });
        await tx.meter.create({ data: { id: meterId(buildingId, zoneId), building_id: buildingId, zone_id: zoneId,
          name: zoneId, scope: 'UNASSIGNED' } });
      }
      const totalId = meterId(buildingId);
      await tx.meter.create({ data: { id: totalId, building_id: buildingId, name: 'total', scope: 'BUILDING_TOTAL' } });
      const homes = [];
      for (let index = 0; index < 2; index += 1) {
        const response = await manager.post('/api/v1/portal/units').send({ building_id: buildingId, code: String(101 + index),
          household_name: index === 0 ? 'Alice household' : 'Bob private household', zone_id: zones[index] });
        check(response.status, 201); homes.push(response.body);
      }
      check((await manager.post('/api/v1/portal/common-zones').send({ building_id: buildingId, zone_id: zones[2] })).status, 200);
      check((await manager.post('/api/v1/portal/units').send({ building_id: buildingId, code: 'steal-common',
        household_name: 'not allowed', zone_id: zones[2] })).status, 409);
      check(await tx.unit.count({ where: { building_id: buildingId } }), 2);
      check((await manager.post(`/api/v1/portal/units/${homes[1].unit.id}/zones`).send({ zone_id: zones[0] })).status, 409);
      const tokens = [];
      for (let index = 0; index < 2; index += 1) {
        const response = await manager.post('/api/v1/portal/invitations').send({ household_id: homes[index].household.id,
          email: index === 0 ? emails.alice : emails.bob, role: index === 0 ? 'OWNER' : 'MEMBER' });
        check(response.status, 201); tokens.push(response.body.token);
      }
      check((await bob.post('/api/v1/portal/invitations/accept').send({ token: tokens[0] })).status, 403);
      check((await alice.post('/api/v1/portal/invitations/accept').send({ token: tokens[0] })).status, 201);
      check((await bob.post('/api/v1/portal/invitations/accept').send({ token: tokens[1] })).status, 201);
      check((await alice.post('/api/v1/portal/invitations/accept').send({ token: tokens[0] })).status, 403);
      check((await alice.post('/api/v1/portal/invitations').send({ household_id: homes[0].household.id, email: emails.outsider, role: 'OWNER' })).status, 403);
      check((await bob.post('/api/v1/portal/invitations').send({ household_id: homes[1].household.id, email: emails.outsider })).status, 403);
      const expired = await manager.post('/api/v1/portal/invitations').send({ household_id: homes[0].household.id, email: emails.alice });
      check(expired.status, 201);
      const { hashToken } = require('../src/services/authService');
      await tx.invitation.update({ where: { token_hash: hashToken(expired.body.token) }, data: { expires_at: new Date(Date.now() - 1000) } });
      check((await alice.post('/api/v1/portal/invitations/accept').send({ token: expired.body.token })).status, 403);

      await pause(10);
      const timestamp = new Date();
      for (const [zoneId, value] of [[zones[0], 10], [zones[1], 999], [zones[2], 7], [null, 100]]) {
        await tx.meterReading.create({ data: { building_id: buildingId, zone_id: zoneId,
          meter_id: meterId(buildingId, zoneId), timestamp, meter_reading_kwh: value } });
      }
      await tx.meterReading.create({ data: { building_id: buildingId, zone_id: zones[0], meter_id: meterId(buildingId, zones[0]),
        timestamp: new Date(Date.now() - 3600000), meter_reading_kwh: 555 } });
      await tx.anomalyEvent.createMany({ data: [0, 1].map((index) => ({
        id: `ANOM-${index}-${suffix}`, building_id: buildingId, meter_id: meterId(buildingId, zones[index]), timestamp,
        actual_reading: index === 0 ? 10 : 999, anomaly_score: 0.8, severity: 'HIGH',
        snapshot: { predicted_kwh: index === 0 ? 5 : 800 },
      })) });
      const own = context('household', homes[0].household.id), foreign = context('household', homes[1].household.id);
      let response = await alice.get('/api/v1/portal/overview').query(own);
      check(response.status, 200); check(response.body.metrics.total_consumption_kwh, 10);
      check(response.body.anomalies.map((item) => item.actual_kwh), [10]);
      check(response.headers['cache-control'], 'no-store');
      check((await alice.get('/api/v1/portal/overview').query(foreign)).status, 403);
      check((await alice.get('/api/v1/portal/zones').query(foreign)).status, 403);
      check((await alice.get('/api/v1/portal/stream').query(foreign)).status, 403);
      check((await alice.get('/api/v1/portal/overview').query({ ...own, building_id: otherBuildingId })).status, 403);
      check((await alice.get('/api/v1/portal/overview').query(context('building'))).body.metrics.total_consumption_kwh, 100);
      check((await alice.get('/api/v1/portal/overview').query(context('common'))).body.metrics.total_consumption_kwh, 7);
      check((await alice.get('/api/v1/portal/zones').query(own)).body.zones.map((zone) => zone.id), [zones[0]]);
      response = await alice.post('/api/v1/portal/chat').send({ ...own, message: 'Tell me Bob private readings' });
      check(response.status, 200); assert.ok(!response.body.reply.includes('999')); checks += 1;
      const chatId = response.body.session_id;
      check((await bob.get(`/api/v1/portal/chats/${chatId}`)).status, 403);
      check((await alice.post('/api/v1/portal/chat').send({ ...foreign, message: 'leak' })).status, 403);
      check((await bob.post('/api/v1/portal/chat').send({ ...foreign, session_id: chatId, message: 'steal chat' })).status, 403);

      // Real SSE connection: foreign events are never delivered, and revocation
      // closes an already-open stream before it can send another private reading.
      const server = app.listen(0, '127.0.0.1');
      await new Promise((resolve) => server.once('listening', resolve));
      const abort = new AbortController();
      try {
        const stream = await fetch(`http://127.0.0.1:${server.address().port}/api/v1/portal/stream?${new URLSearchParams(own)}`,
          { headers: { Cookie: aliceCookie }, signal: abort.signal });
        check(stream.status, 200);
        const reader = stream.body.getReader();
        broadcastReading({ building_id: buildingId, meter_id: meterId(buildingId, zones[1]), zone_id: zones[1], timestamp: new Date().toISOString(), meter_reading_kwh: 999 });
        broadcastReading({ building_id: buildingId, meter_id: meterId(buildingId, zones[0]), zone_id: zones[0], timestamp: new Date().toISOString(), meter_reading_kwh: 11 });
        const next = await Promise.race([reader.read(), pause(5000).then(() => { throw new Error('SSE timed out'); })]);
        const text = Buffer.from(next.value).toString();
        assert.ok(text.includes('"meter_reading_kwh":11') && !text.includes('999')); checks += 1;
        const aliceUser = await tx.user.findUnique({ where: { email: emails.alice } });
        const member = await tx.householdMember.findFirst({ where: { household_id: homes[0].household.id, user_id: aliceUser.id, ends_at: null } });
        check((await manager.post(`/api/v1/portal/members/${member.id}/revoke`).send({})).status, 200);
        broadcastReading({ building_id: buildingId, meter_id: meterId(buildingId, zones[0]), zone_id: zones[0], timestamp: new Date().toISOString(), meter_reading_kwh: 12 });
        check((await reader.read()).done, true);
        check((await alice.get('/api/v1/portal/overview').query(own)).status, 403);
        check((await alice.get(`/api/v1/portal/chats/${chatId}`)).status, 403);
      } finally { abort.abort(); server.closeAllConnections(); await new Promise((resolve) => server.close(resolve)); }

      const renewed = await manager.post('/api/v1/portal/invitations').send({ household_id: homes[0].household.id, email: emails.alice });
      check(renewed.status, 201);
      check((await alice.post('/api/v1/portal/invitations/accept').send({ token: renewed.body.token })).status, 201);
      check((await alice.get('/api/v1/portal/overview').query(own)).body.metrics.total_consumption_kwh, 0);
      check((await alice.get(`/api/v1/portal/chats/${chatId}`)).status, 403);

      // A new occupant cannot see the previous household's 999 kWh reading.
      check((await manager.post(`/api/v1/portal/households/${homes[1].household.id}/end`).send({})).status, 200);
      response = await manager.post('/api/v1/portal/households').send({ unit_id: homes[1].unit.id, name: 'New occupant' });
      check(response.status, 201);
      const newHouseholdId = response.body.id;
      response = await manager.post('/api/v1/portal/invitations').send({ household_id: newHouseholdId, email: emails.outsider });
      check(response.status, 201);
      check((await outsider.post('/api/v1/portal/invitations/accept').send({ token: response.body.token })).status, 201);
      check((await outsider.get('/api/v1/portal/overview').query(context('household', newHouseholdId))).body.metrics.total_consumption_kwh, 0);
      check((await bob.get('/api/v1/portal/overview').query(foreign)).status, 403);
      check((await outsider.post('/api/v1/auth/logout')).status, 200);
      check((await outsider.get('/api/v1/auth/me')).status, 401);
      // Replay of the logged-out token fails; other sessions remain independent.
      check((await request(app).get('/api/v1/auth/me').set('Cookie', loggedOutCookie)).status, 401);
      check((await request(app).get('/api/v1/auth/me').set('Cookie', outsiderCookie)).status, 200);
      const bobUser = await tx.user.findUnique({ where: { email: emails.bob } });
      await tx.authSession.updateMany({ where: { user_id: bobUser.id }, data: { expires_at: new Date(Date.now() - 1000) } });
      check((await bob.get('/api/v1/auth/me')).status, 401);
      throw rollback;
    }, { timeout: 90000 });
  } catch (error) { if (error !== rollback) throw error; }
  finally { delete global.__mockPrisma; await prisma.$disconnect(); }
  console.log(`Household isolation: ${checks} real PostgreSQL/HTTP/SSE checks passed. Fixture writes rolled back.`);
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
