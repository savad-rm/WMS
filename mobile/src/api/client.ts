import * as SecureStore from 'expo-secure-store';

const TOKEN_KEY = 'wms.mobile.token';
export const API_URL = (process.env.EXPO_PUBLIC_API_URL ?? 'http://10.0.2.2:8000/WMS/api/v1').replace(/\/$/, '');

export class ApiError extends Error {
  constructor(message: string, public status: number, public fields: Record<string, unknown> = {}) {
    super(message);
  }
}

export const tokenStore = {
  get: () => SecureStore.getItemAsync(TOKEN_KEY),
  set: (value: string) => SecureStore.setItemAsync(TOKEN_KEY, value),
  clear: () => SecureStore.deleteItemAsync(TOKEN_KEY),
};

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = await tokenStore.get();
  const isForm = init.body instanceof FormData;
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(isForm ? {} : {'Content-Type': 'application/json'}),
      ...(token ? {Authorization: `Bearer ${token}`} : {}),
      ...init.headers,
    },
  });
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = payload?.error;
    throw new ApiError(error?.message ?? 'Unable to complete the request.', response.status, error?.fields ?? {});
  }
  return payload as T;
}
