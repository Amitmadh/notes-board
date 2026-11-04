import { useEffect, useRef, useState } from "react";
import { Canvas, Circle, McImage, McText, Rectangle, Shape, type CanvasJSON, type McNode } from "microcanvas";
import ToolBar from "./toolBar";

const ZOOM_STEP = 1.25;
const MAX_IMAGE_SIZE = 300;
const NODE_OPTIONS = { selectable: true, draggable: true, resizable: true };

function createShape(kind: string, x: number, y: number): McNode | undefined {
    switch (kind) {
        case "rectangle":
            return new Rectangle({ ...NODE_OPTIONS, x, y, width: 100, height: 60, fill: "#2b4d7d" });
        case "circle":
            return new Circle({ ...NODE_OPTIONS, x, y, radius: 40, fill: "#2b4d7d" });
    }
}

function createText(x: number, y: number) {
    return new McText({
        ...NODE_OPTIONS, x, y, text: "Double-click to edit",
        align: "left", baseline: "middle", padding: 32, background: "#d4ac63", writable: true,
    });
}

// Reads a file as a data: URL, so the image still loads once the board is saved
function readAsDataURL(file: File) {
    return new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(file);
    });
}

interface CanvasProps {
    content: CanvasJSON | null;
    onChange: (content: CanvasJSON) => void;
}

function CanvasComponent({ content, onChange }: CanvasProps) {
    const canvasRef = useRef<HTMLCanvasElement | null>(null);
    const boardRef = useRef<Canvas | null>(null);
    const [hasSelection, setHasSelection] = useState(false);
    // Kept in a ref, so a new onChange from the parent doesn't rebuild the board
    const onChangeRef = useRef(onChange);
    useEffect(() => {
        onChangeRef.current = onChange;
    });

    useEffect(() => {
        const element = canvasRef.current;
        if (!element) return;
        const board = new Canvas(element, {background: "#f4f5f7"});
        if (content) board.fromJSON(content);
        board.requestRender();
        board.onSelect = (node) => setHasSelection(node !== null);
        board.onChange = () => onChangeRef.current(board.toJSON());
        boardRef.current = board;
        return () => {
            board.destroy();
            boardRef.current = null;
        };
    }, [content]);

    const screenCenter = (board: Canvas) => ({ x: board.width / 2, y: board.height / 2 });

    // For changes made from the toolbar
    const changed = (board: Canvas) => onChangeRef.current(board.toJSON());

    const place = (board: Canvas, node: McNode) => {
        board.add(node).bringToFront(node);
        board.selected = node;
        setHasSelection(true);
        board.requestRender();
        changed(board);
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
            image = await McImage.load(await readAsDataURL(file), NODE_OPTIONS);
        } catch {
            alert(`Could not load "${file.name}" as an image.`);
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
        if (!board?.selected) return;
        board.remove(board.selected);
        board.requestRender();
        changed(board);
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
        changed(board);
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
