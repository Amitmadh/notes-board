import { McText, Rectangle, type McNodeJSON } from "microcanvas";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { BoardSocket } from "./boardSocket";
import { editText, mergeText, openText } from "./noteText";

const NOTE = new Rectangle({ id: "note", width: 10, height: 10 }).toJSON();
const OTHER_NOTE = new Rectangle({ id: "other", width: 20, height: 20 }).toJSON();
const TEXT_NOTE = new McText({ id: "text", text: "" }).toJSON();

// Stands in for the browser's WebSocket. The test plays the server: it reads
// what the client sent and answers through receive and drop.
class FakeSocket {
    static last: FakeSocket;
    sent: Record<string, unknown>[] = [];
    onopen = () => {};
    onmessage = (_event: { data: string }) => {};
    onclose = (_event: { code: number }) => {};

    constructor() {
        FakeSocket.last = this;
    }

    send(data: string) {
        this.sent.push(JSON.parse(data));
    }

    close() {}

    receive(message: object) {
        this.onmessage({ data: JSON.stringify(message) });
    }

    drop(code = 1006) {
        this.onclose({ code });
    }

    changes() {
        return this.sent.filter((message) => message.type !== "auth");
    }
}

beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal("WebSocket", FakeSocket);
    vi.stubGlobal("location", { href: "http://localhost/" });
});

afterEach(() => {
    vi.useRealTimers();
});

// What the server does with a new socket: takes its token and sends the board.
function signIn(socket: FakeSocket, nodes: McNodeJSON[] = []) {
    socket.onopen();
    expect(socket.sent).toEqual([{ type: "auth", token: "token" }]);
    socket.receive({ type: "ready", nodes, selections: [] });
    return socket;
}

function openBoard(nodes: McNodeJSON[] = []) {
    const callbacks = {
        onSync: vi.fn(),
        onRemoteChange: vi.fn(),
        onPeerLiveChange: vi.fn(),
        onPeerSelect: vi.fn(),
        onPeerLeft: vi.fn(),
        onGone: vi.fn(),
        onNoAccess: vi.fn(),
        onError: vi.fn(),
    };
    const auth = { accessToken: () => "token", renewAccessToken: async () => "token" };
    const board = new BoardSocket(1, auth, callbacks);
    return { board, callbacks, socket: signIn(FakeSocket.last, nodes) };
}

test("keeps one change in flight", () => {
    const { board, socket } = openBoard();
    board.add(NOTE);
    board.add(OTHER_NOTE);
    expect(socket.changes()).toEqual([{ type: "add_node", node: NOTE }]);
    socket.receive({ type: "ack" });
    expect(socket.changes()).toEqual([
        { type: "add_node", node: NOTE },
        { type: "add_node", node: OTHER_NOTE },
    ]);
});

test("merges consecutive updates to a note", () => {
    const { board, socket } = openBoard([NOTE]);
    board.update("note", { x: 5 });
    board.update("note", { x: 6 });
    board.update("note", { y: 7 });
    socket.receive({ type: "ack" });
    expect(socket.changes()).toEqual([
        { type: "update_node", id: "note", changes: { x: 5 } },
        { type: "update_node", id: "note", changes: { x: 6, y: 7 } },
    ]);
});

test("merges consecutive text edits to a note", () => {
    const { board, socket } = openBoard([TEXT_NOTE]);
    const doc = openText({ text: "" });
    for (const text of ["h", "hi", "hi!"]) board.editText("text", editText(doc, text)!);
    socket.receive({ type: "ack" });
    const [alone, joined] = socket.changes() as { update: string }[];
    expect(socket.changes()).toHaveLength(2);
    const server = openText({ text: "" });
    mergeText(server, alone.update);
    expect(mergeText(server, joined.update)).toBe("hi!");
});

test("replays unsaved changes after a reconnect", () => {
    const { board, socket, callbacks } = openBoard();
    board.add(NOTE);
    board.update("note", { x: 5 });
    socket.drop();
    expect(callbacks.onError).toHaveBeenLastCalledWith("Connection lost, reconnecting…");
    vi.advanceTimersByTime(2000);
    // the add didn't reach the server, so the board comes back without it
    const again = signIn(FakeSocket.last, []);
    expect(callbacks.onError).toHaveBeenLastCalledWith(null);
    expect(callbacks.onSync).toHaveBeenLastCalledWith([{ ...NOTE, x: 5 }], []);
    expect(again.changes()).toEqual([{ type: "add_node", node: NOTE }]);
    again.receive({ type: "ack" });
    expect(again.changes().at(-1)).toEqual({ type: "update_node", id: "note", changes: { x: 5 } });
});

test("ignores exists on an add resent after a reconnect", () => {
    const { board, socket, callbacks } = openBoard();
    board.add(NOTE);
    // the add was saved, but its ack was lost with the connection
    socket.drop();
    vi.advanceTimersByTime(2000);
    const again = signIn(FakeSocket.last, [NOTE]);
    expect(again.changes()).toEqual([{ type: "add_node", node: NOTE }]);
    again.receive({ type: "error", code: "exists", detail: null });
    expect(callbacks.onError).toHaveBeenLastCalledWith(null);
});

test("reports a note deleted under its update as gone", () => {
    const { board, socket, callbacks } = openBoard([NOTE]);
    board.update("note", { x: 5 });
    socket.receive({ type: "error", code: "gone", detail: null });
    expect(callbacks.onGone).toHaveBeenCalledWith("note");
    expect(callbacks.onError).not.toHaveBeenCalled();
});

test("keeps its unsaved values over incoming ones", () => {
    const { board, socket, callbacks } = openBoard([NOTE]);
    const updated = (changes: object) => ({ type: "update_node", id: "note", changes });
    board.update("note", { x: 5 });
    socket.receive(updated({ x: 1, y: 2 }));
    socket.receive({ type: "live_update", peer: 7, id: "note", changes: { x: 3, y: 4 } });
    expect(callbacks.onRemoteChange).toHaveBeenLastCalledWith(updated({ y: 2 }));
    expect(callbacks.onPeerLiveChange).toHaveBeenLastCalledWith(7, "note", { y: 4 });
    // once saved, later values from others apply again
    socket.receive({ type: "ack" });
    socket.receive(updated({ x: 1 }));
    expect(callbacks.onRemoteChange).toHaveBeenLastCalledWith(updated({ x: 1 }));
});

test("drops the change in flight when the server closes with 1009", () => {
    const { board, socket, callbacks } = openBoard();
    board.add(NOTE);
    board.add(OTHER_NOTE);
    socket.drop(1009);
    expect(callbacks.onError).toHaveBeenLastCalledWith(
        "Couldn't save a change (too large). Reload the page.",
    );
    // reconnects at once, and sends what was waiting
    const again = signIn(FakeSocket.last, []);
    expect(again).not.toBe(socket);
    expect(again.changes()).toEqual([{ type: "add_node", node: OTHER_NOTE }]);
});
