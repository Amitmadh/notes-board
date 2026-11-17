import * as Y from "yjs";

const toBase64 = (bytes: Uint8Array) => {
    let binary = "";
    for (const byte of bytes) binary += String.fromCharCode(byte);
    return btoa(binary);
};

const fromBase64 = (text: string) => Uint8Array.from(atob(text), (char) => char.charCodeAt(0));

// the state every client and the server build from a note's first text
const firstState = (text: string) => {
    const doc = new Y.Doc();
    doc.clientID = 0;
    doc.getText("text").insert(0, text);
    return Y.encodeStateAsUpdate(doc);
};

export const textOf = (doc: Y.Doc) => doc.getText("text").toJSON();

export function openText(note: Record<string, unknown>) {
    const doc = new Y.Doc();
    const firstText = typeof note.text === "string" ? note.text : "";
    Y.applyUpdate(doc, typeof note.ytext === "string" ? fromBase64(note.ytext) : firstState(firstText));
    return doc;
}

export function mergeText(doc: Y.Doc, update: string) {
    Y.applyUpdate(doc, fromBase64(update));
    return textOf(doc);
}

const isHighSurrogate = (code: number) => code >= 0xd800 && code <= 0xdbff;
const isLowSurrogate = (code: number) => code >= 0xdc00 && code <= 0xdfff;

// makes the document say text.
// Returns the update that does it, or null if it already says it.
export function editText(doc: Y.Doc, text: string) {
    const shared = doc.getText("text");
    const before = shared.toJSON();
    if (before === text) return null;

    let start = 0;
    while (start < before.length && start < text.length && before[start] === text[start]) start++;
    let end = 0;
    while (end < before.length - start && end < text.length - start && before.at(-1 - end) === text.at(-1 - end)) end++;
    // don't cut emojis in half
    if (isHighSurrogate(before.charCodeAt(start - 1))) start--;
    if (end > 0 && isLowSurrogate(before.charCodeAt(before.length - end))) end--;
    const known = Y.encodeStateVector(doc);
    doc.transact(() => {
        shared.delete(start, before.length - start - end);
        shared.insert(start, text.slice(start, text.length - end));
    });
    return toBase64(Y.encodeStateAsUpdate(doc, known));
}

export const joinUpdates = (first: string, second: string) =>
    toBase64(Y.mergeUpdates([fromBase64(first), fromBase64(second)]));
