import { createContext } from "react";

export interface User {
    username: string;
    full_name: string | null;
    disabled: boolean | null;
}

interface AuthContextValue {
    user: User | null;
    // True while the refresh cookie is checked on page load
    loading: boolean;
    login: (username: string, password: string) => Promise<void>;
    register: (username: string, password: string, fullName: string) => Promise<void>;
    logout: () => Promise<void>;
    authFetch: (input: string, init?: RequestInit) => Promise<Response>;
    // For connections that can't go through authFetch, like a board's socket
    accessToken: () => string | null;
    renewAccessToken: () => Promise<string | null>;
}

// Provided by AuthProvider, in authProvider.tsx, and read with useAuth, in
// hooks/useAuth.ts
export const AuthContext = createContext<AuthContextValue | null>(null);
