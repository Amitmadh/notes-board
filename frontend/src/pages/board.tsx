import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import type { McNodeJSON } from "microcanvas";
import { useAuth } from "../auth";
import AppHeader from "../components/appHeader";
import CanvasComponent, { type CanvasHandle } from "../components/canvas";
import SharePanel from "../components/sharePanel";
import { NodeSaver } from "../nodeSaver";

interface BoardInDB {
    id: number;
    name: string;
    owner: string;
    nodes: McNodeJSON[];
}

function BoardPage() {
    const { id } = useParams();
    const { user, authFetch } = useAuth();
    const [board, setBoard] = useState<BoardInDB | null>(null);
    const [saver, setSaver] = useState<NodeSaver | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [showMembers, setShowMembers] = useState(false);
    const canvasRef = useRef<CanvasHandle>(null);

    useEffect(() => {
        let ignore = false;
        authFetch(`/api/boards/${id}`)
            .then(async (response) => {
                if (response.status === 404) throw new Error("This board doesn't exist.");
                if (!response.ok) throw new Error(`Couldn't load the board (${response.status})`);
                const loaded = (await response.json()) as BoardInDB;
                if (ignore) return;
                setBoard(loaded);
                setSaver(new NodeSaver(loaded.id, authFetch, {
                    onGone: (noteId) => {
                        canvasRef.current?.removeNode(noteId);
                        setError("A note you changed was deleted by someone else.");
                    },
                    onNoAccess: () => setError("You no longer have access to this board."),
                    onError: setError,
                }));
            })
            .catch((err) => {
                if (!ignore) setError(err instanceof Error ? err.message : String(err));
            });
        return () => {
            ignore = true;
        };
    }, [authFetch, id]);

    const uploadImage = async (file: File) => {
        const form = new FormData();
        form.append("file", file);
        const response = await authFetch(`/api/boards/${id}/images`, { method: "POST", body: form });
        if (response.status === 413) throw new Error("Images can be at most 10 MB.");
        if (response.status === 415) throw new Error("Only PNG, JPEG and GIF images are supported.");
        if (!response.ok) throw new Error(`Couldn't upload the image (${response.status})`);
        const { url } = (await response.json()) as { url: string };
        return url;
    };

    const isOwner = board?.owner === user?.username;

    return (
        <>
            <AppHeader />
            {board && (
                <div className="board-bar">
                    <h2>{board.name}</h2>
                    <button onClick={() => setShowMembers((shown) => !shown)}>
                        {isOwner ? "Share" : "Members"}
                    </button>
                </div>
            )}
            {board && showMembers && <SharePanel boardId={board.id} owner={board.owner} />}
            {error && <p className="entry-error board-error" role="alert">{error}</p>}
            {board && saver && (
                <CanvasComponent
                    key={board.id}
                    ref={canvasRef}
                    nodes={board.nodes}
                    onAdd={saver.add}
                    onUpdate={saver.update}
                    onDelete={saver.remove}
                    uploadImage={uploadImage}
                />
            )}
        </>
    );
}

export default BoardPage;
