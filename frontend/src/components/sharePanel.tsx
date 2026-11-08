import { useEffect, useState, type SubmitEvent } from "react";
import { useNavigate } from "react-router-dom";
import { errorMessage, messageOf, readJson } from "../api";
import { useAuth } from "../auth";

interface Member {
    username: string;
    full_name: string | null;
}

interface SharePanelProps {
    boardId: number;
    owner: string;
}

const byUsername = (a: Member, b: Member) => a.username.localeCompare(b.username);

function SharePanel({ boardId, owner }: SharePanelProps) {
    const { user, authFetch } = useAuth();
    const navigate = useNavigate();
    const [members, setMembers] = useState<Member[] | null>(null);
    const [username, setUsername] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);
    const isOwner = user?.username === owner;
    const url = `/api/boards/${boardId}/members`;

    useEffect(() => {
        let ignore = false;
        authFetch(url)
            .then(async (response) => {
                const loaded = await readJson<Member[]>(response, "Couldn't load the members");
                if (!ignore) setMembers(loaded);
            })
            .catch((err) => {
                if (!ignore) setError(messageOf(err));
            });
        return () => {
            ignore = true;
        };
    }, [authFetch, url]);

    const addMember = async (event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        const name = username.trim();
        setError(null);
        setBusy(true);
        try {
            const response = await authFetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username: name }),
            });
            if (response.status === 404) throw new Error(`There's no user called "${name}".`);
            if (response.status === 409) throw new Error(`"${name}" is already on this board.`);
            const member = await readJson<Member>(response, "Couldn't share the board");
            setMembers((current) => [...(current ?? []), member].sort(byUsername));
            setUsername("");
        } catch (err) {
            setError(messageOf(err));
        } finally {
            setBusy(false);
        }
    };

    const removeMember = async (name: string) => {
        setError(null);
        try {
            const response = await authFetch(`${url}/${encodeURIComponent(name)}`, { method: "DELETE" });
            if (!response.ok) throw new Error(await errorMessage(response, `Couldn't remove "${name}"`));
            if (name === user?.username) {
                void navigate("/");
                return;
            }
            setMembers((current) => current?.filter((member) => member.username !== name) ?? null);
        } catch (err) {
            setError(messageOf(err));
        }
    };

    return (
        <section className="share-panel" aria-label="Board members">
            <ul className="member-list">
                <li>
                    <span>{owner} <span className="optional">(owner)</span></span>
                </li>
                {members?.map((member) => (
                    <li key={member.username}>
                        <span>
                            {member.username}
                            {member.full_name && <span className="optional"> · {member.full_name}</span>}
                        </span>
                        {isOwner && (
                            <button onClick={() => void removeMember(member.username)}>Remove</button>
                        )}
                    </li>
                ))}
            </ul>
            {isOwner ? (
                <form className="share-form" onSubmit={addMember}>
                    <input
                        value={username}
                        onChange={(event) => setUsername(event.target.value)}
                        placeholder="Username"
                        aria-label="Username to share with"
                    />
                    <button type="submit" disabled={busy || !username.trim()}>
                        Share
                    </button>
                </form>
            ) : (
                user && <button onClick={() => void removeMember(user.username)}>Leave board</button>
            )}
            {error && <p className="entry-error" role="alert">{error}</p>}
        </section>
    );
}

export default SharePanel;
