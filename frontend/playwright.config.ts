import { defineConfig, devices } from "@playwright/test";

// Starts a backend on a database of its own and a dev server in front of it, on
// ports apart from the ones you develop on. With BASE_URL set, tests the app
// already running there instead, such as docker compose's http://localhost:8080.
const baseURL = process.env.BASE_URL;

export default defineConfig({
    testDir: "./e2e",
    testMatch: "*.e2e.ts",
    timeout: 120000,

    // Run tests serially for consistent state
    fullyParallel: false,
    workers: 1,

    // Fail the build on CI if you accidentally left test.only in the source code
    forbidOnly: !!process.env.CI,

    retries: 0,

    // Reporter configuration
    reporter: [
        ['html'],
        ['list']
    ],

    // Shared settings for all projects
    use: {
        // Base URL for the application
        baseURL: baseURL ?? 'http://localhost:3000',

        // A click or wait that gets stuck fails here, naming the step, rather than at the test timeout
        actionTimeout: 10_000,

        trace: 'retain-on-failure',

        // Screenshot on failure
        screenshot: 'only-on-failure',

        // Video on failure
        video: 'retain-on-failure',
    },

    // Configure projects for major browsers
    projects: [
        {
        name: 'chromium',
        use: { ...devices['Desktop Chrome'] },
        },
        {
        name: 'firefox',
        use: { ...devices['Desktop Firefox'] },
        },
        {
        name: 'webkit',
        use: { ...devices['Desktop Safari'] },
        },
    ],

    // Run local dev server before starting tests
    webServer: baseURL ? undefined : [
        {
            command: "uv run python tests/e2e_server.py 8001",
            cwd: "../backend",
            url: "http://127.0.0.1:8001/api/docs",
        },
        {
            command: "npm run dev -- --port 3000 --strictPort",
            env: { API_URL: "http://127.0.0.1:8001" },
            url: "http://localhost:3000",
        },
    ],
});
