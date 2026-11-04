import { useEffect, useRef, useState, type ReactNode } from "react";

export interface MenuItem<T> {
    value: T;
    label: string;
    icon?: ReactNode;
}

interface DropdownMenuProps<T> {
    label: string;
    items: MenuItem<T>[];
    onSelect: (value: T) => void;
    disabled?: boolean;
}

function DropdownMenu<T>({ label, items, onSelect, disabled = false }: DropdownMenuProps<T>) {
    const [open, setOpen] = useState(false);
    const containerRef = useRef<HTMLDivElement>(null);

    // While open, a press outside the menu or Escape closes it.
    useEffect(() => {
        if (!open) return;
        const closeOnPressOutside = (event: PointerEvent) => {
            if (!containerRef.current?.contains(event.target as Node)) setOpen(false);
        };
        const closeOnEscape = (event: KeyboardEvent) => {
            if (event.key === "Escape") setOpen(false);
        };
        document.addEventListener("pointerdown", closeOnPressOutside);
        document.addEventListener("keydown", closeOnEscape);
        return () => {
            document.removeEventListener("pointerdown", closeOnPressOutside);
            document.removeEventListener("keydown", closeOnEscape);
        };
    }, [open]);

    const choose = (value: T) => {
        setOpen(false);
        onSelect(value);
    };

    return (
        <div className="dropdown" ref={containerRef}>
            <button
                aria-haspopup="menu"
                aria-expanded={open}
                disabled={disabled}
                onClick={() => setOpen(!open)}
            >
                {label} <span aria-hidden="true">▾</span>
            </button>
            {open && !disabled && <div className="dropdown-menu" role="menu">
                {items.map((item) => <button key={item.label} role="menuitem" onClick={() => choose(item.value)}>
                    {item.icon}
                    {item.label}
                </button>)}
            </div>}
        </div>
    );
}

export default DropdownMenu;
