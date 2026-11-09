import type { McNodeJSON } from "microcanvas";

type Changes = Record<string, unknown>;

// The server answers each change before it reads the next, and sends it on to
// the board's other sockets.
export type Change =
    { type: "add_node"; node: McNodeJSON } |
    { type: "update_node"; id: string; changes: Changes } |
    { type: "delete_node"; id: string };

// another user's selected note
export interface PeerSelection {
    peer: number;
    username: string;
    id: string | null;
}

type ServerMessage =
    Change |
    { type: "ready"; nodes: McNodeJSON[]; selections: PeerSelection[] } |
    { type: "live_update"; peer: number; id: string; changes: Changes } |
    ({ type: "select" } & PeerSelection) |
    { type: "left"; peer: number } |
    { type: "ack" } |
    { type: "error"; code: "exists" | "gone" | "invalid"; detail: unknown };

interface Auth {
    accessToken: () => string | null;
    renewAccessToken: () => Promise<string | null>;
}

interface BoardSocketCallbacks {
    onSync: (nodes: McNodeJSON[], selections: PeerSelection[]) => void;
    onRemoteChange: (change: Change) => void;
    onPeerLiveChange: (peer: number, id: string, changes: Changes) => void;
    onPeerSelect: (selection: PeerSelection) => void;
    onPeerLeft: (peer: number) => void;
    onGone: (id: string) => void;
    onNoAccess: () => void;
    onError: (message: string | null) => void;
}

const UNAUTHORIZED = 4401;
const NO_ACCESS = 4404;

const RETRY_DELAY_MS = 2000;
const LIVE_INTERVAL_MS = 50;

export class BoardSocket {
    private readonly url: string;
    private readonly auth: Auth;
    private readonly callbacks: BoardSocketCallbacks;

    private socket: WebSocket | null = null;
    private ready = false;
    private sent: Change | null = null;
    private readonly waiting: Change[] = [];
    private retryTimer: ReturnType<typeof setTimeout> | undefined;
    private failing = false;
    private closing = false;
    private stopped = false;
    private live: { id: string; changes: Changes } | null = null;
    private liveTimer: ReturnType<typeof setTimeout> | undefined;
    private selected: string | null = null;

    constructor(boardId: number | string, auth: Auth, callbacks: BoardSocketCallbacks) {
        const url = new URL(`/api/boards/${boardId}/ws`, location.href);
        url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
        this.url = url.href;
        this.auth = auth;
        this.callbacks = callbacks;
        void this.connect(false);
    }

    add = (node: McNodeJSON) => {
        this.push({ type: "add_node", node });
    };

    update = (id: string, changes: Changes) => {
        // it's older than this change
        if (this.live?.id === id) this.live = null;
        this.push({ type: "update_node", id, changes });
    };

    // throttled, and not saved or answered
    liveUpdate = (id: string, changes: Changes) => {
        if (this.closing || this.stopped) return;
        this.live = { id, changes };
        if (this.liveTimer === undefined) this.sendLive();
    };

    select = (id: string | null) => {
        if (this.closing || this.stopped) return;
        this.selected = id;
        if (this.ready) this.socket?.send(JSON.stringify({ type: "select", id }));
    };

    remove = (id: string) => {
        this.push({ type: "delete_node", id });
    };

    // Closes now, or once sendNext has saved the pending changes
    close = () => {
        this.closing = true;
        if (!this.sent && this.waiting.length === 0) this.stop();
    };

    private push(change: Change) {
        if (this.closing || this.stopped) return;
        const last = this.waiting.at(-1);
        if (change.type === "update_node" && last?.type === "update_node" && last.id === change.id) {
            Object.assign(last.changes, change.changes);
        } else {
            this.waiting.push(change);
        }
        this.sendNext();
    }

    private async connect(renewToken: boolean) {
        let token: string | null;
        try {
            token = renewToken ? await this.auth.renewAccessToken() : this.auth.accessToken();
        } catch {
            this.retryLater();
            return;
        }
        if (this.stopped) return;
        if (token === null) {
            this.stop();
            return;
        }

        const socket = new WebSocket(this.url);
        this.socket = socket;
        socket.onopen = () => socket.send(JSON.stringify({ type: "auth", token }));
        socket.onmessage = (event) => {
            if (this.socket === socket) this.receive(JSON.parse(event.data as string) as ServerMessage);
        };
        socket.onclose = (event) => {
            if (this.socket === socket) this.closed(event.code, renewToken);
        };
    }

    private receive(message: ServerMessage) {
        switch (message.type) {
            case "ready":
                this.ready = true;
                if (this.failing) {
                    this.failing = false;
                    this.callbacks.onError(null);
                }
                this.callbacks.onSync(this.withPending(message.nodes), message.selections);
                // lost with the old socket
                if (this.selected !== null) this.select(this.selected);
                break;
            case "add_node":
            case "delete_node":
                this.callbacks.onRemoteChange(message);
                break;
            case "update_node": {
                // This client's unsaved values win, since the server saves them later
                const changes = this.withoutPending(message.id, message.changes);
                if (Object.keys(changes).length > 0) this.callbacks.onRemoteChange({ ...message, changes });
                break;
            }
            case "live_update": {
                const changes = this.withoutPending(message.id, message.changes);
                if (Object.keys(changes).length > 0) this.callbacks.onPeerLiveChange(message.peer, message.id, changes);
                break;
            }
            case "select":
                this.callbacks.onPeerSelect(message);
                break;
            case "left":
                this.callbacks.onPeerLeft(message.peer);
                break;
            case "ack":
                this.sent = null;
                break;
            case "error": {
                const change = this.sent;
                this.sent = null;
                if (change?.type === "update_node" && message.code === "gone") {
                    this.callbacks.onGone(change.id);
                // "exists" means an add resent after a dropped connection was already saved
                } else if (!(change?.type === "add_node" && message.code === "exists")) {
                    this.callbacks.onError(`Couldn't save a change (${message.code}). Reload the page.`);
                }
                break;
            }
        }
        this.sendNext();
    }

    private pending() {
        return this.sent ? [this.sent, ...this.waiting] : this.waiting;
    }

    // Applies the unsaved changes the way the server will
    private withPending(nodes: McNodeJSON[]) {
        const board = new Map(nodes.map((node) => [node.id, node]));
        for (const change of this.pending()) {
            switch (change.type) {
                case "add_node":
                    if (!board.has(change.node.id)) board.set(change.node.id, change.node);
                    break;
                case "update_node": {
                    const node = board.get(change.id);
                    if (node) board.set(change.id, { ...node, ...change.changes } as McNodeJSON);
                    break;
                }
                case "delete_node":
                    board.delete(change.id);
                    break;
            }
        }
        return [...board.values()];
    }

    // drops the fields this client has unsaved changes to, since the server saves them later
    private withoutPending(id: string, changes: Changes) {
        const unsaved = new Set(this.pending().flatMap((change) =>
            change.type === "update_node" && change.id === id ? Object.keys(change.changes) : []));
        return Object.fromEntries(Object.entries(changes).filter(([key]) => !unsaved.has(key)));
    }

    private sendNext() {
        if (!this.socket || !this.ready || this.sent) return;
        const change = this.waiting.shift();
        if (change) {
            this.sent = change;
            this.socket.send(JSON.stringify(change));
        } else if (this.closing) {
            this.stop();
        }
    }

    private sendLive() {
        this.liveTimer = undefined;
        const live = this.live;
        this.live = null;
        if (!live || !this.socket || !this.ready) return;
        this.socket.send(JSON.stringify({ type: "live_update", ...live }));
        this.liveTimer = setTimeout(() => this.sendLive(), LIVE_INTERVAL_MS);
    }

    private closed(code: number, renewedToken: boolean) {
        this.socket = null;
        this.ready = false;
        if (this.sent) {
            this.waiting.unshift(this.sent);
            this.sent = null;
        }
        if (code === NO_ACCESS) {
            this.stop();
            this.callbacks.onNoAccess();
        } else if (code === UNAUTHORIZED && !renewedToken) {
            void this.connect(true);
        } else {
            this.retryLater();
        }
    }

    private retryLater() {
        if (!this.failing) {
            this.failing = true;
            this.callbacks.onError("Connection lost, reconnecting…");
        }
        this.retryTimer = setTimeout(() => void this.connect(false), RETRY_DELAY_MS);
    }

    private stop() {
        this.stopped = true;
        this.waiting.length = 0;
        this.sent = null;
        this.live = null;
        clearTimeout(this.retryTimer);
        clearTimeout(this.liveTimer);
        const socket = this.socket;
        this.socket = null;
        socket?.close();
    }
}
