import { useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import { Canvas, Circle, McImage, McText, Rectangle, Shape, type McNode, type McNodeJSON } from "microcanvas";
import ToolBar from "./toolBar";

const ZOOM_STEP = 1.25;
const MAX_IMAGE_SIZE = 300;
const BACKGROUND = "#f4f5f7";

const newNodeOptions = () => ({ id: crypto.randomUUID(), selectable: true, draggable: true, resizable: true });

function createShape(kind: string, x: number, y: number): McNode | undefined {
    switch (kind) {
        case "rectangle":
            return new Rectangle({ ...newNodeOptions(), x, y, width: 100, height: 60, fill: "#2b4d7d" });
        case "circle":
            return new Circle({ ...newNodeOptions(), x, y, radius: 40, fill: "#2b4d7d" });
    }
}

function createText(x: number, y: number) {
    return new McText({
        ...newNodeOptions(), x, y, text: "Double-click to edit",
        align: "left", baseline: "middle", padding: 32, background: "#d4ac63", writable: true,
    });
}

type Fields = Record<string, unknown>;

export interface CanvasHandle {
    removeNode: (id: string) => void;
}

interface CanvasProps {
    nodes: McNodeJSON[];
    onAdd: (node: McNodeJSON) => void;
    onUpdate: (id: string, changes: Fields) => void;
    onDelete: (id: string) => void;
    uploadImage: (file: File) => Promise<string>;
    ref?: Ref<CanvasHandle>;
}

function CanvasComponent({ nodes, onAdd, onUpdate, onDelete, uploadImage, ref }: CanvasProps) {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const boardRef = useRef<Canvas | null>(null);
    const [hasSelection, setHasSelection] = useState(false);

    const sentRef = useRef(new Map<string, Fields>());
    const changedRef = useRef(new Map<string, McNode>());

    const update = (node: McNode) => {
        const fields: Fields = node.toJSON();
        const sent = sentRef.current.get(node.id);
        const changes = Object.fromEntries(Object.entries(fields).filter(
            ([key, value]) => JSON.stringify(value) !== JSON.stringify(sent?.[key])));
        sentRef.current.set(node.id, fields);
        changedRef.current.set(node.id, node);
        if (Object.keys(changes).length > 0) onUpdate(node.id, changes);
    };

    // New update from the parent doesn't rebuild the board
    const updateRef = useRef(update);
    useEffect(() => {
        updateRef.current = update;
    }, [update]);

    useEffect(() => {
        const element = canvasRef.current;
        if (!element) return;
        const board = new Canvas(element, { background: BACKGROUND });
        board.fromJSON({ background: BACKGROUND, nodes });
        sentRef.current = new Map(nodes.map((node) => [node.id, { ...node }]));
        changedRef.current.clear();
        board.requestRender();
        board.onSelect = (node) => setHasSelection(node !== null);
        board.onChange = (node) => updateRef.current(node);
        boardRef.current = board;
        return () => {
            board.destroy();
            boardRef.current = null;
        };
    }, [nodes]);

    useImperativeHandle(ref, () => ({
        removeNode: (id: string) => {
            const board = boardRef.current;
            const node = changedRef.current.get(id);
            if (!board || !node) return;
            board.remove(node);
            board.requestRender();
            sentRef.current.delete(id);
            changedRef.current.delete(id);
        },
    }), []);

    const screenCenter = (board: Canvas) => ({ x: board.width / 2, y: board.height / 2 });

    const place = (board: Canvas, node: McNode) => {
        board.add(node).bringToFront(node);
        board.selected = node;
        setHasSelection(true);
        board.requestRender();
        const json = node.toJSON() as McNodeJSON;
        sentRef.current.set(node.id, { ...json });
        changedRef.current.set(node.id, node);
        onAdd(json);
    };

    const addShape = (kind: string) => {
        const board = boardRef.current;
        if (!board) return;
        const { x, y } = board.screenToBoard(screenCenter(board));
        const node = createShape(kind, x, y);
        if (node === undefined) return;
        place(board, node);
    };

    const addText = () => {
        const board = boardRef.current;
        if (!board) return;
        const { x, y } = board.screenToBoard(screenCenter(board));
        place(board, createText(x, y));
    };

    const addImage = async (file: File) => {
        let image: McImage;
        try {
            image = await McImage.load(await uploadImage(file), newNodeOptions());
        } catch (err) {
            alert(`Could not add "${file.name}". ${err instanceof Error ? err.message : String(err)}`);
            return;
        }
        // Read after loading, since the board may have been destroyed meanwhile
        const board = boardRef.current;
        if (!board) return;
        const scale = Math.min(1, MAX_IMAGE_SIZE / Math.max(image.width, image.height));
        image.width *= scale;
        image.height *= scale;
        const { x, y } = board.screenToBoard(screenCenter(board));
        image.x = x - image.width / 2;
        image.y = y - image.height / 2;
        place(board, image);
    };

    const deleteSelected = () => {
        const board = boardRef.current;
        const node = board?.selected;
        if (!board || !node) return;
        board.remove(node);
        board.requestRender();
        sentRef.current.delete(node.id);
        changedRef.current.delete(node.id);
        onDelete(node.id);
    };

    const changeColor = (color: string) => {
        const board = boardRef.current;
        if (!board?.selected) return;
        if (board.selected instanceof Shape) {
            board.selected.fill = color;
        } else if (board.selected instanceof McText) {
            board.selected.background = color;
        }
        board.requestRender();
        update(board.selected);
    }

    const zoomBy = (factor: number) => {
        const board = boardRef.current;
        if (!board) return;
        board.zoomAt(screenCenter(board), board.zoom * factor);
        board.requestRender();
    };

    const resetView = () => {
        const board = boardRef.current;
        if (!board) return;
        board.zoom = 1;
        board.panX = 0;
        board.panY = 0;
        board.requestRender();
    };

    return (
        <div className="board">
            <ToolBar
                onAddShape={addShape}
                onAddText={addText}
                onAddImage={addImage}
                onDelete={deleteSelected}
                onColor={changeColor}
                nodeSelected={hasSelection}
                onZoomIn={() => zoomBy(ZOOM_STEP)}
                onZoomOut={() => zoomBy(1 / ZOOM_STEP)}
                onResetView={resetView}
            />
            <div className="canvas">
                <canvas ref={canvasRef} />
            </div>
        </div>
    );
}

export default CanvasComponent;
