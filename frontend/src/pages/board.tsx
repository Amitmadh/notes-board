import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import type { CanvasJSON } from "microcanvas";
import { useAuth } from "../auth";
import AppHeader from "../components/appHeader";
import CanvasComponent from "../components/canvas";

interface BoardInDB {
    id: number;
    name: string;
    content: CanvasJSON | null;
}

function BoardPage() {
    const { id } = useParams();
    const { authFetch } = useAuth();
    const [board, setBoard] = useState<BoardInDB | null>(null);
    const [error, setError] = useState<string | null>(null);
    const unsavedRef = useRef<CanvasJSON | null>(null);
    const savingRef = useRef(false);

    useEffect(() => {
        let ignore = false;
        authFetch(`/api/boards/${id}`)
            .then(async (response) => {
                if (response.status === 404) throw new Error("This board doesn't exist.");
                if (!response.ok) throw new Error(`Couldn't load the board (${response.status})`);
                const loaded = (await response.json()) as BoardInDB;
                if (!ignore) setBoard(loaded);
            })
            .catch((err) => {
                if (!ignore) setError(err instanceof Error ? err.message : String(err));
            });
        return () => {
            ignore = true;
        };
    }, [authFetch, id]);

    const save = async (content: CanvasJSON) => {
        // for out of order writes
        unsavedRef.current = content;
        if (savingRef.current) return;
        savingRef.current = true;
        try {
            while (unsavedRef.current) {
                const next = unsavedRef.current;
                unsavedRef.current = null;
                const response = await authFetch(`/api/boards/${id}/content`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(next),
                });
                if (!response.ok) throw new Error(`Couldn't save the board (${response.status})`);
            }
            setError(null);
        } catch (err) {
            setError(err instanceof Error ? err.message : String(err));
        } finally {
            savingRef.current = false;
        }
    };

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

    return (
        <>
            <AppHeader />
            {error && <p className="entry-error board-error" role="alert">{error}</p>}
            {board && (
                <CanvasComponent key={board.id} content={board.content} onChange={save} uploadImage={uploadImage} />
            )}
        </>
    );
}

export default BoardPage;
