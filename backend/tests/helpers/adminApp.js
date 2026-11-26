import { createApp } from '../../src/app';

// Legacy route tests exercise route behavior after an authenticated platform
// administrator has passed the perimeter. Production still uses requireUser.
export default createApp({ authenticate(req, res, next) {
  req.user = { id: '00000000-0000-4000-8000-000000000001', is_platform_admin: true, staff: [], memberships: [] };
  next();
} });

export const meterMock = {
  findMany: async ({ where }) => where.building_id.in.flatMap((buildingId) =>
    [null, 'z1', 'z2', 'zone_01'].map((zoneId) => ({
      id: `meter-${buildingId}-${zoneId || 'total'}`, building_id: buildingId, zone_id: zoneId,
    }))),
  create: async ({ data }) => data,
};
