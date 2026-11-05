# Cognichat 📚

A **RAG chatbot** over our own notes — FastAPI + Groq + ChromaDB, running as a
two-container application orchestrated with Docker Compose.


> **What it does:** we drop `.md` / `.txt` notes into `docs/`, run one ingest command,
> and then ask questions in plain English. The app finds the most relevant passages and
> has GPT answer using only those passages.

---

## ⚠️ Read this first — three rules that prevent 90% of problems

**1. After editing ANY file, we must rebuild.**
```bash
docker compose up -d --build
```
Without `--build`, Compose reuses the cached image and our edits never reach the
container. You will edit a file, restart, see no change, and lose ten minutes.

> **Mental model:** the image is a *photograph*, not a *mirror*. Editing the source file
> does not update the photograph — we have to take a new one.

**2. Do not paste commands with trailing `#` comments into zsh.**
macOS zsh does not treat `#` as a comment in interactive mode. If we paste
`docker compose ps -a   # some note` and the note contains an apostrophe, our terminal
hangs showing `quote>`. Press **Ctrl+C** and re-run the command without the comment.

**3. `docker compose ps` hides dead containers.**
If a service is missing from the list, it exited. Use `docker compose ps -a` to see it,
then `docker compose logs <service>` for the reason.

---

## 🆕 What's new versus the ML project

| New concept | Why it appears here |
|---|---|
| **Secrets via `.env`** | We now call a GROQ API. The key must never be baked into the image. |
| **Docker Compose** | Two containers (app + vector DB) that start together and talk to each other. |
| **Service-name networking** | The app reaches the database at `http://chroma:8000` — no IP addresses. |
| **Volumes** | The vector DB has *state*. It must survive `docker compose down`. |

---

## 📁 What's in this folder

| File | Purpose |
|---|---|
| `app.py` | FastAPI service — `/query` runs retrieve → augment → generate |
| `ingest.py` | Reads `docs/*.md` and `docs/*.txt`, chunks them, embeds them into Chroma |
| `docs/` | Sample knowledge base (3 markdown notes). Replace with our own! |
| `requirements.txt` | Pinned Python dependencies |
| `Dockerfile` | Recipe for the **app** container (Chroma uses a prebuilt image) |
| `docker-compose.yaml` | Defines both services, the network, and the volume |
| `.env.example` | Template for API key — copy to `.env` |
| `.dockerignore` | Keeps `.env`, `venv/`, `.git/` out of the image |
| `.gitignore` | Keeps `.env` out of version control |

---

## ✅ Prerequisites

1. **Docker Desktop** running (whale 🐳 icon steady in the menu bar).
2. **An Grog API key** 

This project makes real API calls, but they are tiny: embedding the three sample
docs plus a handful of questions using
`all-MiniLM-L6-v2`.

You do **not** need Python installed locally.

---

## 🚀 Step-by-step

### Step 1 — Extract and open in VS Code
Unzip and move the folder to e.g. `~/Projects/cognichat`, then:
```bash
code ~/Projects/cognichat
```
Or VS Code → **File → Open Folder**.

### Step 2 — Create our `.env` file ⚠️ don't skip
In the VS Code terminal (`` Ctrl + ` ``):
Open `.env` and add GROQ_API_KEY
```
GROQ_API_KEY=gsk-proj-our-actual-key-here
```
No quotes, no spaces around the `=`. `.env` is already gitignored and dockerignored.

Verify it exists:
```bash
ls -la .env
```

### Step 3 — Confirm Docker Desktop is running
Whale 🐳 icon steady in the menu bar.

### Step 4 — Start both containers
```bash
docker compose up -d --build
```
First run takes 2–4 minutes (builds our app image, pulls Chroma from Docker Hub).

### Step 5 — Verify both are up
```bash
docker compose ps -a
```
Both `cognichat-app` and `cognichat-chroma` should show **Up**. If `app` shows
**Exited**, jump to Troubleshooting below.

Check the startup log:
```bash
docker compose logs app
```
Look for `[Cognichat] Connected to chroma at chroma:8000`.

### Step 6 — Health check
```bash
curl http://localhost:8000/
```
```json
{"status":"Cognichat is running.","docs_indexed":15,"chroma_host":"chroma","chroma_port":8000,"embedding_model":"all-MiniLM-L6-v2","llm_provider":"Groq"}
```
`docs_indexed: 0` is expected — nothing loaded yet.

### Step 7 — Ingest the documents
```bash
docker compose exec app python ingest.py
```
```
Ingested 15 chunks from 3 file(s) ✅
Collection now holds 15 chunks total.
```
Note what just happened: we ran a script **inside a live container**. This is exactly
how we'd run database migrations or one-off jobs in production.

Re-check `curl http://localhost:8000/` — `docs_indexed` is now greater than zero.

### Step 8 — Ask a question 🎉
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Why should I copy requirements.txt before the rest of my code?"}'
```

Or use the **Swagger UI** at **<http://localhost:8000/docs>** — expand `POST /ask`,
click *Try it out*, type a question, hit *Execute*. Better for live demos.

Questions worth trying:
- *What is the difference between an image and a container?*
- *What happens to my data when I run docker compose down?*
- *Why does chunk size matter in RAG?*
- *What is the capital of France?* ← should say it doesn't know

That last one is the important one. It proves answers are **grounded in our documents**
rather than the model's general memory.

### Step 9 — The volume persistence demo 💡
The strongest moment in this project. Destroy everything, bring it back, watch the data
survive:
```bash
docker compose down
docker compose up -d
curl http://localhost:8000/
```
`docs_indexed` is still greater than zero. You never re-ran `ingest.py`, yet the
embeddings are intact — they live in the `chroma_data` volume, not inside the container.

To actually delete them we must remove the volume:
```bash
docker compose down -v
```

### Step 10 — Watch the logs
```bash
docker compose logs -f          # both services, interleaved
docker compose logs -f app      # just the app
```
`Ctrl+C` to stop following.

### Step 11 — Use our own notes
```bash
rm docs/*.md
cp ~/path/to/our/notes.md docs/
docker compose up -d --build
docker compose exec app python ingest.py
```

### Step 12 — Clean up
```bash
docker compose down       # stop, keep the data
docker compose down -v    # stop and wipe the vector DB
```

---

## 🔑 Things that can confuse

### 1. Published port vs internal port

```yaml
  app:
    environment:
      - CHROMA_HOST=chroma
      - CHROMA_PORT=8000     # <-- INTERNAL port

  chroma:
    ports:
      - "8001:8000"          # <-- PUBLISHED port, for our Mac only
```

Chroma listens on port **8000 inside its own container**. The `8001:8000` mapping exists
purely so *we* can reach it from our Mac at `localhost:8001` for debugging.

The app is already **inside** the Docker network, so it uses the internal port `8000`.
Setting `CHROMA_PORT=8001` gives we connection-refused.

> **Analogy:** `8001` is the building's street gate, used by visitors from outside.
> `8000` is the flat number, used by people who already live in the building.

### 2. `depends_on` waits for START, not for READY

`depends_on: [chroma]` only guarantees Chroma's container has been *started* — not that
it is accepting connections. Chroma needs several seconds to boot. If the app connects
immediately it gets `Connection refused` and uvicorn exits.

This is why `app.py` wraps the connection in `connect_to_chroma()`, which retries for up
to 60 seconds and prints its progress. The alternative fix is a `healthcheck` on chroma
plus `depends_on: condition: service_healthy`.

This is one of the most common Compose gotchas in the wild.

---


## 🔑 Key concepts demonstrated

- **Secrets management** — `.env` + `env_file`, never `ENV KEY=...` in a Dockerfile
  (anyone can read that back with `docker history`)
- **Multi-container orchestration** — one `docker compose up` instead of many `docker run`
- **Service discovery** — containers reach each other by service name, never by IP
- **Published vs internal ports**
- **Startup ordering vs startup readiness** — why `depends_on` isn't enough
- **Volumes** — separating disposable compute from persistent state
- **`docker compose exec`** — running one-off commands inside a live container
- **Thin-client architecture** — `chromadb-client` keeps the app image small because the
  heavy database runs in its own container
- **Image immutability** — code is baked in at build time; `--build` is mandatory after edits

---
