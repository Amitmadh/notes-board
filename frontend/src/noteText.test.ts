import { expect, test } from "vitest";
import { editText, joinUpdates, mergeText, openText, textOf } from "./noteText";

// What people type: Hebrew, Latin, spaces, and emoji of one or several code points.
const TYPED = ["א", "ב", "ג", "ד", "a", "b", " ", "😀", "👍🏽", "👨‍👩‍👧", "🇮🇱"];

// mulberry32: random numbers from a seed, so a failing run can be repeated
function random(seed: number) {
    return () => {
        seed = (seed + 0x6d2b79f5) | 0;
        let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

// Types or deletes a few characters somewhere, as the note's editor does: it
// never stops inside a character.
function edit(text: string, next: () => number) {
    const pick = (count: number) => Math.floor(next() * count);
    const chars = Array.from(text);
    const at = pick(chars.length + 1);
    if (chars.length === 0 || next() < 0.6) {
        chars.splice(at, 0, ...Array.from({ length: 1 + pick(3) }, () => TYPED[pick(TYPED.length)]));
    } else {
        chars.splice(at, 1 + pick(3));
    }
    return chars.join("");
}

test("random edits by two users end in the same text, with no broken characters", () => {
    for (let seed = 1; seed <= 50; seed++) {
        const next = random(seed);
        const first = "שלום 👋 note";
        const users = [openText({ text: first }), openText({ text: first })];
        // updates on their way to each user, in the order they were made
        const inboxes: string[][] = [[], []];
        for (let step = 0; step < 100; step++) {
            const me = next() < 0.5 ? 0 : 1;
            const inbox = inboxes[me];
            if (inbox.length > 0 && next() < 0.3) {
                mergeText(users[me], inbox.shift()!);
                continue;
            }
            const update = editText(users[me], edit(textOf(users[me]), next));
            if (update === null) continue;
            const theirs = inboxes[1 - me];
            // BoardSocket joins edits that wait behind one in flight
            if (theirs.length > 0 && next() < 0.3) theirs.push(joinUpdates(theirs.pop()!, update));
            else theirs.push(update);
        }
        for (const [me, inbox] of inboxes.entries()) {
            for (const update of inbox) mergeText(users[me], update);
        }
        const [mine, theirs] = users.map(textOf);
        expect(mine, `seed ${seed}`).toBe(theirs);
        expect(mine, `seed ${seed}`).not.toMatch(/\p{Surrogate}|�/u);
    }
});
