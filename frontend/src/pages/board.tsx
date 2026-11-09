import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import type { McNodeJSON } from "microcanvas";
import { messageOf, readJson } from "../api";
import { useAuth } from "../auth";
import AppHeader from "../components/appHeader";
import CanvasComponent, { type CanvasHandle } from "../components/canvas";
import SharePanel from "../components/sharePanel";
import { BoardSocket } from "../boardSocket";

interface BoardInDB {
    id: number;
    name: string;
    owner: string;
    nodes: McNodeJSON[];
}

function BoardPage() {
    const { id } = useParams();
    const { user, authFetch, accessToken, renewAccessToken } = useAuth();
    const [board, setBoard] = useState<BoardInDB | null>(null);
    const [socket, setSocket] = useState<BoardSocket | null>(null);
    const [error, setError] = useState<string | null>(null);
    const [showMembers, setShowMembers] = useState(false);
    const canvasRef = useRef<CanvasHandle>(null);

    useEffect(() => {
        let ignore = false;
        let opened: BoardSocket | null = null;
        authFetch(`/api/boards/${id}`)
            .then(async (response) => {
                if (response.status === 404) throw new Error("This board doesn't exist.");
                const loaded = await readJson<BoardInDB>(response, "Couldn't load the board");
                if (ignore) return;
                setBoard(loaded);
                opened = new BoardSocket(loaded.id, { accessToken, renewAccessToken }, {
                    onSync: (nodes, selections) => canvasRef.current?.sync(nodes, selections),
                    onRemoteChange: (change) => canvasRef.current?.applyChange(change),
                    onPeerLiveChange: (peer, noteId, changes) =>
                        canvasRef.current?.applyLiveChange(peer, noteId, changes),
                    onPeerSelect: (selection) => canvasRef.current?.showSelection(selection),
                    onPeerLeft: (peer) => canvasRef.current?.removePeer(peer),
                    onGone: (noteId) => {
                        canvasRef.current?.applyChange({ type: "delete_node", id: noteId });
                        setError("A note you changed was deleted by someone else.");
                    },
                    onNoAccess: () => setError("You no longer have access to this board."),
                    onError: setError,
                });
                setSocket(opened);
            })
            .catch((err) => {
                if (!ignore) setError(messageOf(err));
            });
        return () => {
            ignore = true;
            opened?.close();
        };
    }, [authFetch, accessToken, renewAccessToken, id]);

    const uploadImage = async (file: File) => {
        const form = new FormData();
        form.append("file", file);
        const response = await authFetch(`/api/boards/${id}/images`, { method: "POST", body: form });
        if (response.status === 413) throw new Error("Images can be at most 10 MB.");
        if (response.status === 415) throw new Error("Only PNG, JPEG and GIF images are supported.");
        const { url } = await readJson<{ url: string }>(response, "Couldn't upload the image");
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
            {board && socket && (
                <CanvasComponent
                    key={board.id}
                    ref={canvasRef}
                    nodes={board.nodes}
                    onAdd={socket.add}
                    onUpdate={socket.update}
                    onLiveUpdate={socket.liveUpdate}
                    onSelect={socket.select}
                    onDelete={socket.remove}
                    uploadImage={uploadImage}
                />
            )}
        </>
    );
}

export default BoardPage;
