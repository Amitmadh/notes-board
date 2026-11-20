import { expect, test, type APIRequestContext, type Browser, type Page } from "@playwright/test";

const PASSWORD = "e2e-password";
const LATENCY_MS = 100; // added to each ws message, both ways
const SHAPES = ["Rectangle", "Circle", "Triangle", "Diamond", "Hexagon", "Star", "Arrow"];
const COLORS = ["Navy", "Gold", "Red", "Green", "Teal", "Purple"];

interface User {
    username: string;
    token: string;
}

interface Point {
    x: number;
    y: number;
}

async function createUser(request: APIRequestContext): Promise<User> {
    const username = `e2e_${Math.random().toString(36).slice(2, 10)}`;
    await request.post("/api/register", { data: { username, password: PASSWORD } });
    const response = await request.post("/api/login", { form: { username, password: PASSWORD } });
    const { access_token } = await response.json();
    return { username, token: access_token };
}

async function createBoard(request: APIRequestContext, owner: User, members: User[]): Promise<number> {
    const headers = { Authorization: `Bearer ${owner.token}` };
    const response = await request.post("/api/boards", { headers, data: { name: "e2e" } });
    const board = await response.json();
    for (const member of members) {
        await request.post(`/api/boards/${board.id}/members`, { headers, data: { username: member.username } });
    }
    return board.id;
}

async function savedNodes(request: APIRequestContext, user: User, boardId: number) {
    const headers = { Authorization: `Bearer ${user.token}` };
    const response = await request.get(`/api/boards/${boardId}`, { headers });
    const { nodes } = await response.json();
    return nodes;
}

async function savedText(request: APIRequestContext, user: User, boardId: number) {
    const nodes = await savedNodes(request, user, boardId);
    return nodes[0]?.text;
}

async function openBoard(browser: Browser, user: User, boardId: number, latency = LATENCY_MS, online = () => true) {
    const page = await browser.newPage({ viewport: { width: 1100, height: 700 } });
    await page.routeWebSocket(/\/ws$/, (ws) => {
        if (!online()) return ws.close();
        const server = ws.connectToServer();
        const relay = (send: () => void) => setTimeout(() => {
            if (online()) return send();
            void ws.close();
            void server.close();
        }, latency);
        ws.onMessage((message) => relay(() => server.send(message)));
        server.onMessage((message) => relay(() => ws.send(message)));
    });
    await page.goto("/login");
    await page.getByLabel("Username").fill(user.username);
    await page.getByLabel("Password").fill(PASSWORD);
    await page.getByRole("button", { name: "Log in" }).click();
    await expect(page).toHaveURL("/");
    // don't page.goto() here, webkit drops the secure refresh cookie on http so a reload logs out
    await page.locator(`a[href="/boards/${boardId}"]`).click();
    await page.locator(".canvas canvas").waitFor();
    await page.waitForTimeout(500 + 4 * latency);
    return page;
}

async function canvasBox(page: Page) {
    const box = (await page.locator(".canvas canvas").boundingBox())!;
    return { ...box, centerX: box.x + box.width / 2, centerY: box.y + box.height / 2 };
}

// canvas center (where new nodes go) and some points around it
async function canvasPoints(page: Page) {
    const { centerX, centerY } = await canvasBox(page);
    return [[0, 0], [-300, -150], [300, -150], [-300, 150], [300, 150], [0, 180]]
        .map(([dx, dy]) => ({ x: centerX + dx, y: centerY + dy }));
}

// Checks that every page shows the board as the server saved it.
async function expectSavedBoard(browser: Browser, user: User, boardId: number, pages: Page[]) {
    // deselect and reset the view so the screenshots can be compared
    for (const page of pages) {
        const box = await canvasBox(page);
        await page.keyboard.press("Escape");
        await page.getByRole("button", { name: "Reset view" }).click();
        await page.mouse.click(box.x + 5, box.y + 5);
        await expect(page.getByRole("button", { name: "Delete", exact: true })).toBeDisabled();
    }
    await pages[0].waitForTimeout(2000);

    // a new page only has what the server saved
    const fresh = await openBoard(browser, user, boardId, 0);
    const expected = await fresh.locator(".canvas canvas").screenshot();
    await test.info().attach("saved", { body: expected, contentType: "image/png" });
    for (const [i, page] of pages.entries()) {
        const canvas = page.locator(".canvas canvas");
        await expect.poll(async () => (await canvas.screenshot()).equals(expected), `user ${i + 1}`).toBe(true);
    }
}

// mulberry32, seeded so a failing run can be replayed
function random(seed: number) {
    return () => {
        seed = (seed + 0x6d2b79f5) | 0;
        let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
        t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
        return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
}

async function drag(page: Page, from: Point, to: Point) {
    await page.mouse.move(from.x, from.y);
    await page.mouse.down();
    await page.mouse.move(to.x, to.y, { steps: 6 });
    await page.mouse.up();
}

// every page grabs `from` first, then they all move in small steps, then release
async function dragAtOnce(pages: Page[], from: Point, targets: Point[], steps = 6) {
    for (const page of pages) {
        await page.mouse.move(from.x, from.y);
        await page.mouse.down();
    }
    for (let step = 1; step <= steps; step++) {
        for (const [i, page] of pages.entries()) {
            const to = targets[i];
            await page.mouse.move(from.x + ((to.x - from.x) * step) / steps, from.y + ((to.y - from.y) * step) / steps);
        }
    }
    for (const page of pages) await page.mouse.up();
}

async function randomAction(page: Page, next: () => number, points: Point[]) {
    const pick = <T>(items: T[]) => items[Math.floor(next() * items.length)];
    const button = (name: string) => page.getByRole("button", { name, exact: true });
    const r = next();
    if (r < 0.22) {
        await button("Shapes").click();
        await page.getByRole("menuitem", { name: pick(SHAPES), exact: true }).click();
    } else if (r < 0.3) {
        await button("Note").click();
    } else if (r < 0.72) {
        await drag(page, pick(points), pick(points));
    } else if (r < 0.84 && (await button("Color").isEnabled())) {
        await button("Color").click();
        await page.getByRole("menuitem", { name: pick(COLORS), exact: true }).click();
    } else if (r < 0.92 && (await button("Rotate right").isEnabled())) {
        await button("Rotate right").click();
    } else if (await button("Delete").isEnabled()) {
        await button("Delete").click();
    }
}

test.afterEach(async ({ browser }) => {
    await Promise.all(browser.contexts().map((context) => context.close()));
});

test("three users making random edits end up with the same board", async ({ browser, browserName, request }) => {
    test.slow(browserName === "webkit"); // ~2s per click
    const users = [await createUser(request), await createUser(request), await createUser(request)];
    const boardId = await createBoard(request, users[0], users.slice(1));

    // pages are opened and driven one at a time, firefox loses input sent to several windows at once
    const pages: Page[] = [];
    for (const user of users) pages.push(await openBoard(browser, user, boardId));
    const points = await canvasPoints(pages[0]);

    // users take turns but the latency means their edits still overlap
    const randoms = pages.map((_, i) => random(i + 1));
    for (let round = 0; round < 30; round++) {
        for (const [i, page] of pages.entries()) {
            await randomAction(page, randoms[i], points);
            await page.waitForTimeout(15 + randoms[i]() * 85);
        }
    }

    // everyone drags the same new note at the same time
    for (const page of pages) await page.getByRole("button", { name: "Reset view" }).click();
    await pages[0].getByRole("button", { name: "Note", exact: true }).click();
    await pages[0].waitForTimeout(1000);
    await dragAtOnce(pages, points[0], points.slice(1));

    await expectSavedBoard(browser, users[0], boardId, pages);
});

test("edits made while cut off reach everyone once back online", async ({ browser, browserName, request }) => {
    test.slow(browserName === "webkit");
    const alice = await createUser(request);
    const bob = await createUser(request);
    const boardId = await createBoard(request, alice, [bob]);
    let bobOnline = true;
    const a = await openBoard(browser, alice, boardId);
    const b = await openBoard(browser, bob, boardId, LATENCY_MS, () => bobOnline);
    const addNote = (page: Page) => page.getByRole("button", { name: "Note", exact: true }).click();

    // alice adds a note, then bob's connection drops while his own new note is on its way
    await addNote(a);
    await b.waitForTimeout(1000);
    bobOnline = false;
    await addNote(b);
    const lost = b.getByText("Connection lost, reconnecting…");
    await expect(lost).toBeVisible();

    // cut off, bob moves his note off alice's and then hers, which she moves elsewhere and colors meanwhile
    const [bobsCenter, ...bobsPoints] = await canvasPoints(b); // the message moved his canvas down
    await drag(b, bobsCenter, bobsPoints[0]);
    await drag(b, bobsCenter, bobsPoints[1]);
    const [alicesCenter, ...alicesPoints] = await canvasPoints(a);
    await drag(a, alicesCenter, alicesPoints[2]);
    await a.getByRole("button", { name: "Color", exact: true }).click();
    await a.getByRole("menuitem", { name: "Red", exact: true }).click();

    bobOnline = true;
    await expect(lost).toBeHidden();
    await expectSavedBoard(browser, alice, boardId, [a, b]);
    // with bob's note, which the server didn't get before the connection dropped
    expect(await savedNodes(request, alice, boardId)).toHaveLength(2);
});

// CI also runs the tests tagged @stack against the app in docker compose
test("typing in the same note at the same time keeps every character", { tag: "@stack" }, async ({ browser, request }) => {
    const alice = await createUser(request);
    const bob = await createUser(request);
    const boardId = await createBoard(request, alice, [bob]);
    const [a, b] = await Promise.all([openBoard(browser, alice, boardId), openBoard(browser, bob, boardId)]);

    const { centerX, centerY } = await canvasBox(a);
    await a.getByRole("button", { name: "Note", exact: true }).click();
    await a.mouse.dblclick(centerX, centerY);
    await a.keyboard.press("Control+A");
    await a.keyboard.insertText("note");
    await expect.poll(() => savedText(request, alice, boardId)).toBe("note");

    await b.waitForTimeout(1000);
    await b.mouse.dblclick(centerX, centerY);
    await expect(b.locator("textarea")).toHaveValue("note");

    // alice types at the start, bob at the end
    await a.keyboard.press("Control+Home");
    await b.keyboard.press("Control+End");
    await Promise.all([
        a.keyboard.type("שלום 😀 ", { delay: 100 }),
        b.keyboard.type(" and Bob", { delay: 100 }),
    ]);

    const expected = "שלום 😀 note and Bob";
    await expect(a.locator("textarea")).toHaveValue(expected);
    await expect(b.locator("textarea")).toHaveValue(expected);
    await expect.poll(() => savedText(request, alice, boardId)).toBe(expected);
});
