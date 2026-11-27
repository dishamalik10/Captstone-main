import axios from 'axios';
export const BASE_URL =
  process.env.EXPO_PUBLIC_API_URL?.replace(/\/$/, '') ??
  'http://127.0.0.1:8000';

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 120000,
});

export function setApiToken(token: string | null): void {
  if (token) {
    api.defaults.headers.common.Authorization = `Bearer ${token}`;
  } else {
    delete api.defaults.headers.common.Authorization;
  }
}

export function resolveApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return `${BASE_URL}${path.startsWith('/') ? path : `/${path}`}`;
}

export const SERVER_UNREACHABLE_MESSAGE =
  "Can't reach AURA's server. It may be offline for a while; check your connection and try again.";

/** True when the request never got an HTTP response (offline, server down, timeout). */
export function isNetworkError(error: unknown): boolean {
  return axios.isAxiosError(error) && !error.response;
}

export function apiStatus(error: unknown): number | undefined {
  return axios.isAxiosError(error) ? error.response?.status : undefined;
}

/** The server's own message (`detail`) when it sent one, a "can't reach" message when
 *  nothing came back, otherwise the caller's fallback. */
export function apiErrorMessage(error: unknown, fallback: string): string {
  if (isNetworkError(error)) return SERVER_UNREACHABLE_MESSAGE;
  const detail = axios.isAxiosError(error) ? (error.response?.data as { detail?: unknown } | undefined)?.detail : undefined;
  return typeof detail === 'string' ? detail : fallback;
}

let unauthorizedHandler: (() => void) | null = null;

/** Called when an authenticated request gets 401 (the session expired or was revoked). */
export function onUnauthorized(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

const NO_SESSION_ROUTES = ['/auth/login', '/auth/signup'];

api.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error) && error.response?.status === 401) {
      const url = error.config?.url ?? '';
      const sentToken = Boolean(error.config?.headers?.Authorization);
      if (sentToken && !NO_SESSION_ROUTES.some((route) => url.endsWith(route))) {
        unauthorizedHandler?.();
      }
    }
    return Promise.reject(error);
  },
);
