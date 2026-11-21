import { useEffect, useRef, useState, type ReactNode } from "react";
import { errorMessage, readJson } from "./api";
import { AuthContext, type User } from "./auth";

async function fetchUser(token: string) {
    const response = await fetch("/api/users/me/", {
        headers: { Authorization: `Bearer ${token}` },
    });
    return readJson<User>(response);
}

let refreshing: Promise<string | null> | null = null;

// Gets a new access token with the refresh cookie, or null when signed out
function refreshAccessToken() {
    refreshing ??= fetch("/api/refresh", { method: "POST" })
        .then(async (response) => {
            if (!response.ok) return null;
            const { access_token } = await response.json();
            return access_token as string;
        })
        .finally(() => {
            refreshing = null;
        });
    return refreshing;
}

export function AuthProvider({ children }: { children: ReactNode }) {
    const [user, setUser] = useState<User | null>(null);
    const [loading, setLoading] = useState(true);
    const tokenRef = useRef<string | null>(null);

    // Restores the session after a reload
    useEffect(() => {
        refreshAccessToken()
            .then(async (token) => {
                if (!token) return;
                tokenRef.current = token;
                setUser(await fetchUser(token));
            })
            .catch(() => {})
            .finally(() => setLoading(false));
    }, []);

    const clearSession = () => {
        tokenRef.current = null;
        setUser(null);
    };

    const login = async (username: string, password: string) => {
        const response = await fetch("/api/login", {
            method: "POST",
            // OAuth2's password flow sends a form
            body: new URLSearchParams({ username, password }),
        });
        const { access_token } = await readJson<{ access_token: string }>(response);
        setUser(await fetchUser(access_token));
        tokenRef.current = access_token;
    };

    const register = async (username: string, password: string, fullName: string) => {
        const response = await fetch("/api/register", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password, full_name: fullName || null }),
        });
        if (!response.ok) throw new Error(await errorMessage(response));
        await login(username, password);
    };

    const logout = async () => {
        try {
            await fetch("/api/logout", { method: "POST" });
        } finally {
            clearSession();
        }
    };

    const accessToken = () => tokenRef.current;

    const renewAccessToken = async () => {
        const token = await refreshAccessToken();
        if (!token) {
            clearSession();
            return null;
        }
        tokenRef.current = token;
        return token;
    };

    // Sends the access token with the request. When it has expired, gets a
    // new one and tries once more, signing out if that isn't possible.
    const authFetch = async (input: string, init: RequestInit = {}) => {
        const send = () => {
            const headers = new Headers(init.headers);
            headers.set("Authorization", `Bearer ${tokenRef.current}`);
            return fetch(input, { ...init, headers });
        };
        const response = await send();
        if (response.status !== 401) return response;
        if (!(await renewAccessToken())) return response;
        return send();
    };

    return <AuthContext value={{
        user, loading, login, register, logout, authFetch, accessToken, renewAccessToken,
    }}>
        {children}
    </AuthContext>;
}
