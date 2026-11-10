import { useEffect, useState, type SubmitEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { errorMessage, messageOf, readJson } from "../api";
import { useAuth } from "../auth";
import AppHeader from "../components/appHeader";
import { DeleteIcon } from "../components/icons";

interface Board {
    id: number;
    name: string;
    owner: string;
}

function UserBoardsPage() {
    const { user, authFetch } = useAuth();
    const navigate = useNavigate();
    // Null until the first load finishes.
    const [boards, setBoards] = useState<Board[] | null>(null);
    const [name, setName] = useState("");
    const [error, setError] = useState<string | null>(null);
    const [busy, setBusy] = useState(false);

    useEffect(() => {
        // Drops a response that arrives after the page has closed.
        let ignore = false;
        authFetch("/api/boards")
            .then(async (response) => {
                const loaded = await readJson<Board[]>(response, "Couldn't load boards");
                if (!ignore) setBoards(loaded);
            })
            .catch((err) => {
                if (!ignore) setError(messageOf(err));
            });
        return () => {
            ignore = true;
        };
    }, [authFetch]);

    // Creates the board and opens it.
    const createBoard = async (event: SubmitEvent<HTMLFormElement>) => {
        event.preventDefault();
        setError(null);
        setBusy(true);
        try {
            const response = await authFetch("/api/boards", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ name: name.trim() }),
            });
            const board = await readJson<Board>(response, "Couldn't create the board");
            navigate(`/boards/${board.id}`);
        } catch (err) {
            setError(messageOf(err));
        } finally {
            setBusy(false);
        }
    };

    // Deletes a board the user owns, or leaves one shared with them
    const removeBoard = async (board: Board) => {
        if (!user) return;
        const owned = board.owner === user.username;
        const question = owned
            ? `Delete "${board.name}"? This can't be undone.`
            : `Leave "${board.name}"? ${board.owner} would have to share it with you again.`;
        if (!confirm(question)) return;
        setError(null);
        const url = owned
            ? `/api/boards/${board.id}`
            : `/api/boards/${board.id}/members/${encodeURIComponent(user.username)}`;
        try {
            const response = await authFetch(url, { method: "DELETE" });
            if (!response.ok) {
                throw new Error(await errorMessage(response, `Couldn't ${owned ? "delete" : "leave"} "${board.name}"`));
            }
            setBoards((current) => current?.filter((other) => other.id !== board.id) ?? null);
        } catch (err) {
            setError(messageOf(err));
        }
    };

    return (
        <>
            <AppHeader />
            <main className="boards">
                <h2>My Boards</h2>
                <form className="new-board" onSubmit={createBoard}>
                    <input
                        value={name}
                        onChange={(event) => setName(event.target.value)}
                        placeholder="New board name"
                        aria-label="New board name"
                    />
                    <button type="submit" disabled={busy || !name.trim()}>
                        Create board
                    </button>
                </form>
                {error && <p className="entry-error" role="alert">{error}</p>}
                {boards?.length === 0 && <p>No boards yet. Create your first one above.</p>}
                {boards && boards.length > 0 && (
                    <ul className="board-list">
                        {boards.map((board) => (
                            <li key={board.id}>
                                <Link to={`/boards/${board.id}`}>
                                    {board.name}
                                    {board.owner !== user?.username && (
                                        <span className="board-owner">Shared by {board.owner}</span>
                                    )}
                                </Link>
                                <button
                                    className="board-remove"
                                    onClick={() => void removeBoard(board)}
                                    aria-label={`${board.owner === user?.username ? "Delete" : "Leave"} ${board.name}`}
                                    title={board.owner === user?.username ? "Delete board" : "Leave board"}
                                >
                                    <DeleteIcon />
                                </button>
                            </li>
                        ))}
                    </ul>
                )}
            </main>
        </>
    );
}

export default UserBoardsPage;
