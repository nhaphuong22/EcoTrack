import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000';

const TOKEN_KEY = 'ecotrack_access_token';
const REFRESH_TOKEN_KEY = 'ecotrack_refresh_token';
const USER_KEY = 'ecotrack_user';

export function getStoredAuth() {
  try {
    const token = localStorage.getItem(TOKEN_KEY);
    const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
    const userStr = localStorage.getItem(USER_KEY);
    const user = userStr ? JSON.parse(userStr) : null;
    return { token, refreshToken, user };
  } catch {
    return { token: null, refreshToken: null, user: null };
  }
}

export function saveAuthTokens({ token, refreshToken, user }) {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  if (refreshToken) localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  if (user) localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function clearAuthTokens() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export async function loginApi(email, password) {
  const res = await axios.post(`${API_BASE_URL}/api/v1/auth/login`, {
    email,
    password,
  });
  const data = res.data;
  saveAuthTokens({
    token: data.token,
    refreshToken: data.refreshToken,
    user: data.user,
  });
  return data;
}

export async function refreshApi(refreshToken) {
  const res = await axios.post(`${API_BASE_URL}/api/v1/auth/refresh`, {
    refreshToken,
  });
  const data = res.data;
  saveAuthTokens({
    token: data.token,
    refreshToken: data.refreshToken,
    user: data.user,
  });
  return data;
}

export async function logoutApi(refreshToken) {
  try {
    if (refreshToken) {
      await axios.post(`${API_BASE_URL}/api/v1/auth/logout`, { refreshToken });
    }
  } catch (err) {
    console.warn('Backend logout error (safe to ignore on client):', err.message);
  } finally {
    clearAuthTokens();
  }
}
