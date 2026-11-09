import { useEffect, useImperativeHandle, useLayoutEffect, useRef, useState, type Ref } from "react";
import {
    Canvas, Circle, McImage, McText, nodeFromJSON, Rectangle, Shape, type McNode, type McNodeJSON,
} from "microcanvas";
import { messageOf } from "../api";
import type { Change } from "../boardSocket";
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

// a node's JSON fields by name, or just the ones that changed
type Fields = Record<string, unknown>;
const FIXED_FIELDS = new Set(["id", "type", "src"]);

const changedFields = (fields: Fields, from: Fields | undefined) => Object.fromEntries(
    Object.entries(fields).filter(([key, value]) => JSON.stringify(value) !== JSON.stringify(from?.[key]))
);

const setFields = (node: McNode, fields: Fields) => {
    Object.assign(node, Object.fromEntries(Object.entries(fields).filter(([key]) => !FIXED_FIELDS.has(key))));
};

export interface CanvasHandle {
    applyChange: (change: Change) => void;
    sync: (nodes: McNodeJSON[]) => void;
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

    // each note's fields as the server knows them
    const sentRef = useRef(new Map<string, Fields>());
    // the board's notes by id
    const nodesRef = useRef(new Map<string, McNode>());

    const update = (node: McNode) => {
        const fields: Fields = node.toJSON();
        const changes = changedFields(fields, sentRef.current.get(node.id));
        sentRef.current.set(node.id, fields);
        if (Object.keys(changes).length > 0) onUpdate(node.id, changes);
    };

    // New update from the parent doesn't rebuild the board
    const updateRef = useRef(update);
    useEffect(() => {
        updateRef.current = update;
    }, [update]);

    useLayoutEffect(() => {
        const element = canvasRef.current;
        if (!element) return;
        const board = new Canvas(element, { background: BACKGROUND });
        const loaded = nodes.map(nodeFromJSON).filter((node) => node !== null);
        board.add(...loaded);
        nodesRef.current = new Map(loaded.map((node) => [node.id, node]));
        sentRef.current = new Map(nodes.map((node) => [node.id, { ...node }]));
        board.requestRender();
        board.onSelect = (node) => setHasSelection(node !== null);
        board.onChange = (node) => updateRef.current(node);
        boardRef.current = board;
        return () => {
            board.destroy();
            boardRef.current = null;
        };
    }, [nodes]);

    const addNode = (board: Canvas, json: McNodeJSON) => {
        const node = nodeFromJSON(json);
        if (!node) return;
        board.add(node);
        nodesRef.current.set(node.id, node);
        sentRef.current.set(node.id, { ...json });
    };

    const removeNode = (board: Canvas, id: string) => {
        const node = nodesRef.current.get(id);
        if (node) board.remove(node);
        nodesRef.current.delete(id);
        sentRef.current.delete(id);
    };

    // A change from another user, marked as sent so it isn't sent back
    const applyChange = (change: Change) => {
        const board = boardRef.current;
        if (!board) return;
        switch (change.type) {
            case "add_node":
                if (!nodesRef.current.has(change.node.id)) addNode(board, change.node);
                break;
            case "update_node": {
                const node = nodesRef.current.get(change.id);
                if (!node) break;
                setFields(node, change.changes);
                sentRef.current.set(node.id, { ...sentRef.current.get(node.id), ...change.changes });
                break;
            }
            case "delete_node":
                removeNode(board, change.id);
                break;
        }
        board.requestRender();
    };

    // Makes the board match the server's notes, after connecting
    const sync = (nodes: McNodeJSON[]) => {
        const board = boardRef.current;
        if (!board) return;
        const ids = new Set(nodes.map((json) => json.id));
        for (const id of [...nodesRef.current.keys()]) {
            if (!ids.has(id)) removeNode(board, id);
        }
        for (const json of nodes) {
            const node = nodesRef.current.get(json.id);
            if (!node) {
                addNode(board, json);
                continue;
            }
            setFields(node, changedFields({ ...json }, node.toJSON()));
            sentRef.current.set(json.id, { ...json });
        }
        board.requestRender();
    };

    useImperativeHandle(ref, () => ({ applyChange, sync }));

    const screenCenter = (board: Canvas) => ({ x: board.width / 2, y: board.height / 2 });

    const place = (board: Canvas, node: McNode) => {
        board.add(node).bringToFront(node);
        board.selected = node;
        setHasSelection(true);
        board.requestRender();
        const json = node.toJSON() as McNodeJSON;
        sentRef.current.set(node.id, { ...json });
        nodesRef.current.set(node.id, node);
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
            alert(`Could not add "${file.name}". ${messageOf(err)}`);
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
        removeNode(board, node.id);
        board.requestRender();
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
