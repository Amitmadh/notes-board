import { useEffect, useState, type SubmitEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";
import AppHeader from "../components/appHeader";

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
                if (!response.ok) throw new Error(`Couldn't load boards (${response.status})`);
                const loaded = (await response.json()) as Board[];
                if (!ignore) setBoards(loaded);
            })
            .catch((err) => {
                if (!ignore) setError(err instanceof Error ? err.message : String(err));
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
            if (!response.ok) throw new Error(`Couldn't create the board (${response.status})`);
            const board = (await response.json()) as Board;
            navigate(`/boards/${board.id}`);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            setBusy(false);
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
                            </li>
                        ))}
                    </ul>
                )}
            </main>
        </>
    );
}

export default UserBoardsPage;
