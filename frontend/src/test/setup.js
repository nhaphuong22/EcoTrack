import '@testing-library/jest-dom';
import { vi } from 'vitest';

if (typeof window !== 'undefined') {
  window.HTMLElement.prototype.scrollIntoView = window.HTMLElement.prototype.scrollIntoView || vi.fn();
}

global.ResizeObserver = global.ResizeObserver || class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
};

const defaultTestUser = {
  id: 'usr_admin_01',
  email: 'admin@ecotrack.io',
  name: 'Building Admin',
  role: 'ADMIN',
};

if (typeof localStorage !== 'undefined') {
  localStorage.setItem('ecotrack_user', JSON.stringify(defaultTestUser));
  localStorage.setItem('ecotrack_access_token', 'mock_test_access_token');
  localStorage.setItem('ecotrack_refresh_token', 'mock_test_refresh_token');
}
