import type { McNodeJSON } from "microcanvas";

type Changes = Record<string, unknown>;

// The server answers each change before it reads the next.
type Change =
    { type: "add_node"; node: McNodeJSON } |
    { type: "update_node"; id: string; changes: Changes } |
    { type: "delete_node"; id: string };

type ServerMessage =
    { type: "ready" } |
    { type: "ack" } |
    { type: "error"; code: "exists" | "gone" | "invalid"; detail: unknown };

interface Auth {
    accessToken: () => string | null;
    renewAccessToken: () => Promise<string | null>;
}

interface BoardSocketCallbacks {
    onGone: (id: string) => void;
    onNoAccess: () => void;
    onError: (message: string | null) => void;
}

const UNAUTHORIZED = 4401;
const NO_ACCESS = 4404;

const RETRY_DELAY_MS = 2000;

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
        this.push({ type: "update_node", id, changes });
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
        clearTimeout(this.retryTimer);
        const socket = this.socket;
        this.socket = null;
        socket?.close();
    }
}
