import { useRef, type ChangeEvent } from "react";
import DropdownMenu, { type MenuItem } from "./dropdownMenu";
import { DeleteIcon, RotateLeftIcon, RotateRightIcon, ZoomInIcon, ZoomOutIcon } from "./icons";

const SHAPES: MenuItem<string>[] = [
    { value: "rectangle", label: "Rectangle" },
    { value: "circle", label: "Circle" },
    { value: "triangle", label: "Triangle" },
    { value: "diamond", label: "Diamond" },
    { value: "hexagon", label: "Hexagon" },
    { value: "star", label: "Star" },
    { value: "arrow", label: "Arrow" },
    { value: "cursor", label: "Cursor" },
];

const COLORS: MenuItem<string>[] = [
    { value: "#2b4d7d", label: "Navy" },
    { value: "#d4ac63", label: "Gold" },
    { value: "#cd2435", label: "Red" },
    { value: "#4caf50", label: "Green" },
    { value: "#2a9d8f", label: "Teal" },
    { value: "#8e6cc0", label: "Purple" },
    { value: "#ffffff", label: "White" },
    { value: "#000000", label: "Black" },
    { value: "#555555", label: "grey" },
].map((item) => ({ ...item, icon: <span className="swatch" style={{ background: item.value }} /> }));

// null is transparent, which only fills can be
const FILLS: MenuItem<string | null>[] = [
    { value: null, label: "Transparent", icon: <span className="swatch swatch-none" /> },
    ...COLORS,
];

const TEXT_SIZES: MenuItem<number>[] = [
    { value: 12, label: "Small" },
    { value: 14, label: "Medium" },
    { value: 20, label: "Large" },
    { value: 28, label: "Huge" },
];

interface ToolBarProps {
    onAddShape: (kind: string) => void;
    onAddNote: () => void;
    onAddImage: (file: File) => void;
    onDelete: () => void;
    onRotateLeft: () => void;
    onRotateRight: () => void;
    onColor: (color: string | null) => void;
    onBorderColor: (color: string) => void;
    onTextColor: (color: string) => void;
    onTextSize: (size: number) => void;
    nodeSelected: boolean;
    shapeSelected: boolean;
    noteSelected: boolean;
    onZoomIn: () => void;
    onZoomOut: () => void;
    onResetView: () => void;
}

function ToolBar({
    onAddShape, onAddNote, onAddImage, onDelete, onRotateLeft, onRotateRight, onColor, onBorderColor, onTextColor, onTextSize,
    nodeSelected, shapeSelected, noteSelected, onZoomIn, onZoomOut, onResetView,
}: ToolBarProps) {
    const imageInputRef = useRef<HTMLInputElement>(null);

    const pickImage = (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (file) onAddImage(file);
        event.target.value = "";
    };

    return (
        <div className="toolbar" role="toolbar" aria-label="Canvas tools">
            <button onClick={onAddNote}>Note</button>
            <span className="toolbar-separator" />
            <DropdownMenu label="Shapes" items={SHAPES} onSelect={onAddShape} />
            <button onClick={() => imageInputRef.current?.click()}>Image</button>
            <input ref={imageInputRef} type="file" accept="image/png,image/jpeg,image/gif" hidden onChange={pickImage} />
            <span className="toolbar-separator" />
            <button onClick={onDelete} disabled={!nodeSelected} aria-label="Delete" title="Delete">
                <DeleteIcon />
            </button>
            <button onClick={onRotateLeft} disabled={!nodeSelected} aria-label="Rotate left" title="Rotate left">
                <RotateLeftIcon />
            </button>
            <button onClick={onRotateRight} disabled={!nodeSelected} aria-label="Rotate right" title="Rotate right">
                <RotateRightIcon />
            </button>
            <DropdownMenu label="Color" items={FILLS} onSelect={onColor} disabled={!nodeSelected} />
            <DropdownMenu label="Border color" items={COLORS} onSelect={onBorderColor} disabled={!shapeSelected} />
            <DropdownMenu label="Text color" items={COLORS} onSelect={onTextColor} disabled={!noteSelected} />
            <DropdownMenu label="Text size" items={TEXT_SIZES} onSelect={onTextSize} disabled={!noteSelected} />
            <span className="toolbar-separator" />
            <button onClick={onZoomOut} aria-label="Zoom out" title="Zoom out"><ZoomOutIcon /></button>
            <button onClick={onZoomIn} aria-label="Zoom in" title="Zoom in"><ZoomInIcon /></button>
            <button onClick={onResetView}>Reset view</button>
        </div>
    );
}

export default ToolBar;
