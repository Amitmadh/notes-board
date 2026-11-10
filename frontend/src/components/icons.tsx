/** SVG icons taken from https://www.svgrepo.com/collection/dazzle-line-icons/ */

import type { ReactNode } from "react";

// a line icon in the text's color, as tall as a line of text
function Icon({ size = 16, children }: { size?: number; children: ReactNode }) {
    return (
        <svg
            className="icon" width={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}
            strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"
        >
            {children}
        </svg>
    );
}

export const RotateLeftIcon = () => (
    <Icon>
        <path d="M12.5 20.5C17.1944 20.5 21 16.6944 21 12C21 7.30558 17.1944 3.5 12.5 3.5C7.80558 3.5 4 7.30558 4 12C4 13.5433 4.41128 14.9905 5.13022 16.238M1.5 15L5.13022 16.238M6.82531 12.3832L5.47107 16.3542L5.13022 16.238" />
    </Icon>
);

export const RotateRightIcon = () => (
    <Icon>
        <path d="M11.5 20.5C6.80558 20.5 3 16.6944 3 12C3 7.30558 6.80558 3.5 11.5 3.5C16.1944 3.5 20 7.30558 20 12C20 13.5433 19.5887 14.9905 18.8698 16.238M22.5 15L18.8698 16.238M17.1747 12.3832L18.5289 16.3542L18.8698 16.238" />
    </Icon>
);

export const DeleteIcon = () => (
    <Icon>
        <path d="M4 6H20M16 6L15.7294 5.18807C15.4671 4.40125 15.3359 4.00784 15.0927 3.71698C14.8779 3.46013 14.6021 3.26132 14.2905 3.13878C13.9376 3 13.523 3 12.6936 3H11.3064C10.477 3 10.0624 3 9.70951 3.13878C9.39792 3.26132 9.12208 3.46013 8.90729 3.71698C8.66405 4.00784 8.53292 4.40125 8.27064 5.18807L8 6M18 6V16.2C18 17.8802 18 18.7202 17.673 19.362C17.3854 19.9265 16.9265 20.3854 16.362 20.673C15.7202 21 14.8802 21 13.2 21H10.8C9.11984 21 8.27976 21 7.63803 20.673C7.07354 20.3854 6.6146 19.9265 6.32698 19.362C6 18.7202 6 17.8802 6 16.2V6M14 10V17M10 10V17" />
    </Icon>
);

export const ZoomInIcon = () => (
    <Icon>
        <path d="M14 10L21 3M21 3H16.5M21 3V7.5M10 14L3 21M3 21H7.5M3 21L3 16.5" />
    </Icon>
);

export const ZoomOutIcon = () => (
    <Icon>
        <path d="M14 10L21 3M14 10H18.5M14 10V5.5M10 14L3 21M10 14H5.5M10 14L10 18.5" />
    </Icon>
);

export const DownArrowIcon = () => (
    <Icon size={12}>
        <path d="M12 5V19M12 19L6 13M12 19L18 13" />
    </Icon>
);
