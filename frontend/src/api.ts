// Turns a FastAPI error response into a message to show the user. Uses the
// fallback, with the status code, when the response has no detail to show.
export async function errorMessage(response: Response, fallback = "Request failed") {
    try {
        const { detail } = await response.json();
        if (typeof detail === "string") return detail;
        if (Array.isArray(detail) && detail[0]?.msg) return String(detail[0].msg);
    } catch {}
    return `${fallback} (${response.status})`;
}

// Reads a successful response's JSON, or throws the error message
export async function readJson<T>(response: Response, fallback?: string): Promise<T> {
    if (!response.ok) throw new Error(await errorMessage(response, fallback));
    return (await response.json()) as T;
}

// Turns anything caught into text to show the user
export function messageOf(err: unknown) {
    return err instanceof Error ? err.message : String(err);
}
