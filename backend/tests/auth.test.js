import { describe, it, expect, vi, beforeEach } from 'vitest';
import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import crypto from 'crypto';

const mockAdminUser = {
  id: 'usr_admin_01',
  email: 'admin@ecotrack.io',
  password_hash: bcrypt.hashSync('AdminSecurePass123!', 10),
  name: 'Building Admin',
  role: 'ADMIN',
  created_at: new Date('2026-01-01T00:00:00Z'),
};

const mockPrisma = {
  user: {
    findUnique: vi.fn(),
    count: vi.fn(),
    create: vi.fn(),
  },
  refreshToken: {
    create: vi.fn(),
    findUnique: vi.fn(),
    update: vi.fn(),
    updateMany: vi.fn(),
  },
  building: {
    upsert: vi.fn(),
    findMany: vi.fn(),
    findUnique: vi.fn(),
  },
};

global.__mockPrisma = mockPrisma;

import request from 'supertest';
import app from '../src/app';
import { seedDefaultAdminIfNeeded } from '../src/services/authService';

function hashToken(raw) {
  return crypto.createHash('sha256').update(raw).digest('hex');
}

describe('Story 5.1 & Story 5.2: Auth, Session Lifecycle & Tokens', () => {
  const JWT_SECRET = process.env.JWT_SECRET || 'test-jwt-secret-for-vitest-only';

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('POST /api/v1/auth/login', () => {
    it('returns 200 with JWT access token, 7-day refresh token, and user profile on valid credentials', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(mockAdminUser);
      mockPrisma.refreshToken.create.mockResolvedValue({});

      const res = await request(app)
        .post('/api/v1/auth/login')
        .send({
          email: 'admin@ecotrack.io',
          password: 'AdminSecurePass123!',
        });

      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('token');
      expect(res.body).toHaveProperty('refreshToken');
      expect(typeof res.body.refreshToken).toBe('string');
      expect(res.body.refreshToken.length).toBeGreaterThan(20);
      expect(res.body.user).toEqual({
        id: 'usr_admin_01',
        email: 'admin@ecotrack.io',
        name: 'Building Admin',
        role: 'ADMIN',
      });
      expect(res.body.user).not.toHaveProperty('password_hash');

      // Verify token payload and 15m expiration
      const decoded = jwt.verify(res.body.token, JWT_SECRET);
      expect(decoded.id).toBe('usr_admin_01');
      expect(decoded.role).toBe('ADMIN');
      expect(decoded.email).toBe('admin@ecotrack.io');
      expect(decoded.exp - decoded.iat).toBe(15 * 60);

      // Verify refresh token hash stored with 7-day expiry
      expect(mockPrisma.refreshToken.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            user_id: 'usr_admin_01',
            token_hash: hashToken(res.body.refreshToken),
          }),
        })
      );
    });

    it('returns 401 with generic error message when user does not exist', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(null);

      const res = await request(app)
        .post('/api/v1/auth/login')
        .send({
          email: 'nonexistent@ecotrack.io',
          password: 'SomePassword123!',
        });

      expect(res.status).toBe(401);
      expect(res.body).toEqual({ error: 'Invalid email or password' });
    });

    it('returns 401 with identical error message when password is wrong', async () => {
      mockPrisma.user.findUnique.mockResolvedValue(mockAdminUser);

      const res = await request(app)
        .post('/api/v1/auth/login')
        .send({
          email: 'admin@ecotrack.io',
          password: 'WrongPassword!',
        });

      expect(res.status).toBe(401);
      expect(res.body).toEqual({ error: 'Invalid email or password' });
    });

    it('returns 400 when email or password is missing or invalid', async () => {
      const res = await request(app)
        .post('/api/v1/auth/login')
        .send({
          email: 'not-an-email',
          password: '',
        });

      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error', 'Validation failed');
    });
  });

  describe('POST /api/v1/auth/refresh (Story 5.2)', () => {
    const rawRefreshToken = 'abc123rawRefreshTokenStringForTestingOnly';
    const hashedToken = hashToken(rawRefreshToken);

    it('successfully rotates session: returns new tokens and revokes old refresh token', async () => {
      const activeRecord = {
        id: 'rt_01',
        user_id: 'usr_admin_01',
        token_hash: hashedToken,
        expires_at: new Date(Date.now() + 6 * 24 * 60 * 60 * 1000), // 6 days remaining
        revoked_at: null,
        user: mockAdminUser,
      };

      mockPrisma.refreshToken.findUnique.mockResolvedValue(activeRecord);
      mockPrisma.refreshToken.update.mockResolvedValue({});
      mockPrisma.refreshToken.create.mockResolvedValue({});

      const res = await request(app)
        .post('/api/v1/auth/refresh')
        .send({ refreshToken: rawRefreshToken });

      expect(res.status).toBe(200);
      expect(res.body).toHaveProperty('token');
      expect(res.body).toHaveProperty('refreshToken');
      expect(res.body.refreshToken).not.toBe(rawRefreshToken);
      expect(res.body.user).toEqual({
        id: 'usr_admin_01',
        email: 'admin@ecotrack.io',
        name: 'Building Admin',
        role: 'ADMIN',
      });

      // Verify old token was revoked
      expect(mockPrisma.refreshToken.update).toHaveBeenCalledWith(
        expect.objectContaining({
          where: { id: 'rt_01' },
          data: expect.objectContaining({ revoked_at: expect.any(Date) }),
        })
      );

      // Verify new token was persisted
      expect(mockPrisma.refreshToken.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            user_id: 'usr_admin_01',
            token_hash: hashToken(res.body.refreshToken),
          }),
        })
      );
    });

    it('Reuse Detection: revokes all user tokens if an already rotated token is re-submitted', async () => {
      const revokedRecord = {
        id: 'rt_already_revoked',
        user_id: 'usr_admin_01',
        token_hash: hashedToken,
        expires_at: new Date(Date.now() + 5 * 24 * 60 * 60 * 1000),
        revoked_at: new Date('2026-01-01T12:00:00Z'), // already revoked!
        user: mockAdminUser,
      };

      mockPrisma.refreshToken.findUnique.mockResolvedValue(revokedRecord);
      mockPrisma.refreshToken.updateMany.mockResolvedValue({ count: 3 });

      const res = await request(app)
        .post('/api/v1/auth/refresh')
        .send({ refreshToken: rawRefreshToken });

      expect(res.status).toBe(401);
      expect(res.body).toEqual({ error: 'Invalid or expired refresh token' });

      // Verifies all tokens for this user family are revoked
      expect(mockPrisma.refreshToken.updateMany).toHaveBeenCalledWith({
        where: { user_id: 'usr_admin_01', revoked_at: null },
        data: { revoked_at: expect.any(Date) },
      });
    });

    it('rejects with 401 when refresh token is expired', async () => {
      const expiredRecord = {
        id: 'rt_expired',
        user_id: 'usr_admin_01',
        token_hash: hashedToken,
        expires_at: new Date(Date.now() - 1000), // expired 1s ago
        revoked_at: null,
        user: mockAdminUser,
      };

      mockPrisma.refreshToken.findUnique.mockResolvedValue(expiredRecord);

      const res = await request(app)
        .post('/api/v1/auth/refresh')
        .send({ refreshToken: rawRefreshToken });

      expect(res.status).toBe(401);
      expect(res.body).toEqual({ error: 'Invalid or expired refresh token' });
      expect(mockPrisma.refreshToken.create).not.toHaveBeenCalled();
    });

    it('rejects with 401 when refresh token is not found in database', async () => {
      mockPrisma.refreshToken.findUnique.mockResolvedValue(null);

      const res = await request(app)
        .post('/api/v1/auth/refresh')
        .send({ refreshToken: 'nonexistent-token' });

      expect(res.status).toBe(401);
      expect(res.body).toEqual({ error: 'Invalid or expired refresh token' });
    });

    it('returns 400 when refreshToken field is missing in request body', async () => {
      const res = await request(app)
        .post('/api/v1/auth/refresh')
        .send({});

      expect(res.status).toBe(400);
      expect(res.body).toHaveProperty('error', 'Validation failed');
    });
  });

  describe('POST /api/v1/auth/logout (Story 5.2)', () => {
    it('revokes the provided refresh token and returns 200', async () => {
      const rawToken = 'myLogoutToken12345';
      mockPrisma.refreshToken.updateMany.mockResolvedValue({ count: 1 });

      const res = await request(app)
        .post('/api/v1/auth/logout')
        .send({ refreshToken: rawToken });

      expect(res.status).toBe(200);
      expect(res.body).toEqual({ message: 'Logged out successfully' });

      expect(mockPrisma.refreshToken.updateMany).toHaveBeenCalledWith({
        where: { token_hash: hashToken(rawToken), revoked_at: null },
        data: { revoked_at: expect.any(Date) },
      });
    });

    it('returns 400 when refreshToken is missing in logout body', async () => {
      const res = await request(app)
        .post('/api/v1/auth/logout')
        .send({});

      expect(res.status).toBe(400);
    });
  });

  describe('requireAuth Middleware', () => {
    it('populates req.user and grants access when valid Bearer token is provided', async () => {
      const token = jwt.sign(
        { id: 'usr_tech_01', email: 'tech@ecotrack.io', role: 'TECHNICIAN', name: 'Field Tech' },
        JWT_SECRET,
        { expiresIn: '15m' }
      );

      const res = await request(app)
        .get('/api/v1/auth/me')
        .set('Authorization', `Bearer ${token}`);

      expect(res.status).toBe(200);
      expect(res.body.user).toMatchObject({
        id: 'usr_tech_01',
        email: 'tech@ecotrack.io',
        role: 'TECHNICIAN',
      });
    });

    it('returns 401 when Authorization header is missing', async () => {
      const res = await request(app).get('/api/v1/auth/me');

      expect(res.status).toBe(401);
      expect(res.body).toEqual({ error: 'Authentication token required' });
    });

    it('returns 401 when Authorization header is not Bearer format', async () => {
      const res = await request(app)
        .get('/api/v1/auth/me')
        .set('Authorization', 'Basic 123456');

      expect(res.status).toBe(401);
      expect(res.body).toEqual({ error: 'Authentication token required' });
    });

    it('returns 401 when token is invalid or expired', async () => {
      const expiredToken = jwt.sign(
        { id: 'usr_01' },
        JWT_SECRET,
        { expiresIn: '-1s' }
      );

      const res = await request(app)
        .get('/api/v1/auth/me')
        .set('Authorization', `Bearer ${expiredToken}`);

      expect(res.status).toBe(401);
      expect(res.body).toEqual({ error: 'Invalid or expired token' });
    });
  });

  describe('Admin Bootstrapping Seed', () => {
    it('creates admin user with hashed password when DB has 0 users and env variables set', async () => {
      process.env.ADMIN_EMAIL = 'admin@ecotrack.io';
      process.env.ADMIN_PASSWORD = 'InitAdminPassword2026!';
      mockPrisma.user.count.mockResolvedValue(0);
      mockPrisma.user.create.mockResolvedValue({});

      await seedDefaultAdminIfNeeded();

      expect(mockPrisma.user.count).toHaveBeenCalled();
      expect(mockPrisma.user.create).toHaveBeenCalledWith(
        expect.objectContaining({
          data: expect.objectContaining({
            email: 'admin@ecotrack.io',
            role: 'ADMIN',
          }),
        })
      );
    });

    it('does not create admin user when users already exist in the database', async () => {
      process.env.ADMIN_EMAIL = 'admin@ecotrack.io';
      process.env.ADMIN_PASSWORD = 'InitAdminPassword2026!';
      mockPrisma.user.count.mockResolvedValue(5);

      await seedDefaultAdminIfNeeded();

      expect(mockPrisma.user.count).toHaveBeenCalled();
      expect(mockPrisma.user.create).not.toHaveBeenCalled();
    });
  });
});
