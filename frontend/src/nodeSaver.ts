import type { McNodeJSON } from "microcanvas";

type AuthFetch = (input: string, init?: RequestInit) => Promise<Response>;
type Changes = Record<string, unknown>;

type Operation =
    | { kind: "add"; node: McNodeJSON }
    | { kind: "update"; id: string; changes: Changes }
    | { kind: "delete"; id: string };

interface NodeSaverCallbacks {
    onGone: (id: string) => void;
    onNoAccess: () => void;
    onError: (message: string | null) => void;
}

const RETRY_DELAY_MS = 2000;

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

// Saves a board's notes one change at a time, in the order they were made, so
// a note is always added before it's updated. Changes that can't reach the
// server are kept and sent again.
export class NodeSaver {
    private readonly url: string;
    private readonly authFetch: AuthFetch;
    private readonly callbacks: NodeSaverCallbacks;

    private readonly waiting: Operation[] = [];
    private sending = false;
    private failing = false;
    private stopped = false;

    constructor(boardId: number | string, authFetch: AuthFetch, callbacks: NodeSaverCallbacks) {
        this.url = `/api/boards/${boardId}/nodes`;
        this.authFetch = authFetch;
        this.callbacks = callbacks;
    }

    add = (node: McNodeJSON) => {
        this.push({ kind: "add", node });
    };

    update = (id: string, changes: Changes) => {
        const last = this.waiting.at(-1);
        if (last?.kind === "update" && last.id === id) {
            Object.assign(last.changes, changes);
        } else {
            this.push({ kind: "update", id, changes });
        }
    };

    remove = (id: string) => {
        this.push({ kind: "delete", id });
    };

    private push(operation: Operation) {
        if (this.stopped) return;
        this.waiting.push(operation);
        void this.sendAll();
    }

    private async sendAll() {
        if (this.sending) return;
        this.sending = true;
        try {
            while (!this.stopped) {
                const operation = this.waiting.shift();
                if (!operation) break;
                while (!(await this.send(operation))) {
                    await wait(RETRY_DELAY_MS);
                }
            }
        } finally {
            this.sending = false;
        }
    }

    // Returns false when the change should be sent again later.
    private async send(operation: Operation) {
        let response: Response;
        try {
            response = await this.request(operation);
        } catch {
            return this.retryLater();
        }
        if (response.status >= 500) return this.retryLater();

        if (this.failing) {
            this.failing = false;
            this.callbacks.onError(null);
        }
        if (response.status === 404) {
            this.stopped = true;
            this.waiting.length = 0;
            this.callbacks.onNoAccess();
        } else if (response.status === 409 && operation.kind === "update") {
            this.callbacks.onGone(operation.id);
        } else if (!response.ok) {
            this.callbacks.onError(`Couldn't save a change (${response.status}). Reload the page.`);
        }
        return true;
    }

    private retryLater() {
        this.failing = true;
        this.callbacks.onError("Couldn't save, retrying…");
        return false;
    }

    private request(operation: Operation) {
        const headers = { "Content-Type": "application/json" };
        switch (operation.kind) {
            case "add":
                return this.authFetch(this.url, {
                    method: "POST", headers, body: JSON.stringify(operation.node),
                });
            case "update":
                return this.authFetch(`${this.url}/${encodeURIComponent(operation.id)}`, {
                    method: "PATCH", headers, body: JSON.stringify(operation.changes),
                });
            case "delete":
                return this.authFetch(`${this.url}/${encodeURIComponent(operation.id)}`, {
                    method: "DELETE",
                });
        }
    }
}
