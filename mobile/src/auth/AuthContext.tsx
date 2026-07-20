import React, {createContext, useCallback, useContext, useEffect, useMemo, useState} from 'react';
import {apiFetch, tokenStore} from '../api/client';
import {User} from '../types';

type AuthState = {
  user: User | null; loading: boolean;
  signIn(email: string, password: string): Promise<void>;
  signOut(): Promise<void>;
};

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({children}: React.PropsWithChildren) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const restore = useCallback(async () => {
    try {
      if (await tokenStore.get()) {
        const response = await apiFetch<{user: User}>('/me/');
        setUser(response.user);
      }
    } catch {
      await tokenStore.clear();
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void restore(); }, [restore]);

  const value = useMemo<AuthState>(() => ({
    user, loading,
    signIn: async (email, password) => {
      const response = await apiFetch<{token: string; user: User}>('/auth/login/', {
        method: 'POST', body: JSON.stringify({email, password}),
      });
      await tokenStore.set(response.token);
      setUser(response.user);
    },
    signOut: async () => {
      try { await apiFetch('/auth/logout/', {method: 'POST'}); } catch { /* Clear locally even offline. */ }
      await tokenStore.clear();
      setUser(null);
    },
  }), [loading, user]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider.');
  return value;
}
