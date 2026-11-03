import { useState, type SubmitEvent } from "react";
import { useAuth } from "../auth";

type Mode = "login" | "register";

function EntryPage() {
    const { login, register } = useAuth();
    const [mode, setMode] = useState<Mode>("login");
    const [username, setUsername] = useState("");
    const [fullName, setFullName] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    const submit = async (event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError(null);
        setBusy(true);
        try {
            if (mode === "login") {
                await login(username, password);
            } else {
                await register(username, password, fullName);
            }
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setBusy(false);
        }
    };

    const switchMode = () => {
        setMode(mode === "login" ? "register" : "login");
        setError(null);
    };

    return (
        <main className="entry">
            <h1>Notes Board</h1>
            <form className="entry-form" onSubmit={submit}>
                <h2>{mode === "login" ? "Log in" : "Create an account"}</h2>
                <label>
                    Username
                    <input
                        value={username}
                        onChange={(event) => setUsername(event.target.value)}
                        autoComplete="username"
                        required
                    />
                </label>
                {mode === "register" &&
                <label>
                    <span>Full name <span className="optional">(optional)</span></span>
                    <input
                        value={fullName}
                        onChange={(event) => setFullName(event.target.value)}
                        autoComplete="name"
                    />
                </label>}
                <label>
                    Password
                    <input
                        type="password"
                        value={password}
                        onChange={(event) => setPassword(event.target.value)}
                        autoComplete={mode === "login" ? "current-password" : "new-password"}
                        required
                    />
                </label>
                {error && <p className="entry-error" role="alert">{error}</p>}
                <button type="submit" disabled={busy}>
                    {mode === "login" ? "Log in" : "Register"}
                </button>
            </form>
            <p>
                {mode === "login" ? "No account yet?" : "Already have an account?"}{" "}
                <button type="button" className="link-button" onClick={switchMode}>
                    {mode === "login" ? "Register" : "Log in"}
                </button>
            </p>
        </main>
    );
}

export default EntryPage;
