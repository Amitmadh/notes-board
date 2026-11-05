import { useRef, type ChangeEvent } from "react";
import DropdownMenu, { type MenuItem } from "./dropdownMenu";

const SHAPES: MenuItem<string>[] = [
    { value: "rectangle", label: "Rectangle" },
    { value: "circle", label: "Circle" },
];

const COLORS: MenuItem<string>[] = [
    { value: "#2b4d7d", label: "Navy" },
    { value: "#d4ac63", label: "Gold" },
    { value: "#cd2435", label: "Red" },
    { value: "#4caf50", label: "Green" },
    { value: "#2a9d8f", label: "Teal" },
    { value: "#8e6cc0", label: "Purple" },
    { value: "#ffffff", label: "White" },
    { value: "#222222", label: "Black" },
].map((item) => ({ ...item, icon: <span className="swatch" style={{ background: item.value }} /> }));

interface ToolBarProps {
    onAddShape: (kind: string) => void;
    onAddText: () => void;
    onAddImage: (file: File) => void;
    onDelete: () => void;
    onColor: (color: string) => void
    nodeSelected: boolean;
    onZoomIn: () => void;
    onZoomOut: () => void;
    onResetView: () => void;
}

function ToolBar({ onAddShape, onAddText, onAddImage, onDelete, onColor, nodeSelected: nodeSelected, onZoomIn, onZoomOut, onResetView }: ToolBarProps) {
    const imageInputRef = useRef<HTMLInputElement>(null);

    const pickImage = (event: ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (file) onAddImage(file);
        event.target.value = "";
    };

    return (
        <div className="toolbar" role="toolbar" aria-label="Canvas tools">
            <DropdownMenu label="Shapes" items={SHAPES} onSelect={onAddShape} />
            <span className="toolbar-separator" />
            <button onClick={onAddText}>Text</button>
            <button onClick={() => imageInputRef.current?.click()}>Image</button>
            <input ref={imageInputRef} type="file" accept="image/png,image/jpeg,image/gif" hidden onChange={pickImage} />
            <span className="toolbar-separator" />
            <button onClick={onDelete} disabled={!nodeSelected}>Delete</button>
            <DropdownMenu label="Color" items={COLORS} onSelect={onColor} disabled={!nodeSelected} />
            <span className="toolbar-separator" />
            <button onClick={onZoomOut} aria-label="Zoom out">−</button>
            <button onClick={onZoomIn} aria-label="Zoom in">+</button>
            <button onClick={onResetView}>Reset view</button>
        </div>
    );
}

export default ToolBar;
