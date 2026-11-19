# notes-board

A shared board you fill with notes and images, edited by several people at the same
time — like a Google Doc, but a canvas instead of a page.

## Stack

- **Backend** — Python 3.14, FastAPI, WebSockets
- **Storage** — PostgreSQL
- **Frontend** — React, TypeScript
- **Tooling** — `uv`, `ruff`, `ty`, `pytest`, pre-commit, Docker Compose

## Run with Docker

```sh
cp .env.example .env   # then set DB_PASSWORD and SECRET_KEY
docker compose up --build
```

Then open http://localhost:8080. Boards are kept in the `db-data` volume.

The sign-in cookie is `Secure`, which browsers accept over plain HTTP only on
`localhost`. Anywhere else, put HTTPS in front.

## Scaling

Each board lives in one backend process: nginx hashes the board id, so backends share no
state. Compose runs one; adding one is a service in `compose.yaml` and its `server` lines
in `frontend/nginx.conf`, as the comments there explain.
