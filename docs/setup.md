# Local setup

How to run the Credit Evidence Engine on your own computer: install it, point it at the
models, start the web UI and run a first small test. About 15 minutes.

For what the screens do, see the [underwriter guide](underwriter-guide.md). For how the
parts fit together, see [architecture](architecture.md).

## What you need

| | Why | Notes |
|---|---|---|
| Python 3.12 or newer | The engine and the web UI | `python3.12 --version` |
| git | To get the code | |
| A browser | The UI | Chrome, Edge, Firefox or Safari |
| Access to the models | The assistant being tested, and the judge | Either the team's GPU node over the VPN (no key needed), or an NVIDIA API key from [build.nvidia.com](https://build.nvidia.com) |
| Chrome or Chromium | Only to download reports as PDF | Optional |
| Docker | Only if you prefer containers to a Python install | Optional |

No customer data is needed. Every test case is generated from the credit policy.

## 1. Get the code and install it

```bash
git clone https://github.com/Algoritmica-ai/open-credit-evidence.git
```

```bash
cd open-credit-evidence
```

```bash
python3.12 -m venv .venv
```

```bash
.venv/bin/pip install -e ".[web,dev]"
```

`web` installs the UI and the Synthetic Data Designer that generates test cases; `dev` adds
the tests and the linter. Everything is installed into `.venv/`, inside the project folder,
and nothing is installed system-wide.

## 2. Point it at the models

The engine uses three models, each called a *role*:

| Role | Model | What it does |
|---|---|---|
| Assistant | Nemotron 3.5 Lightning | The AI being tested: it writes the credit memos |
| Judge | Nemotron 3 Super | The three AI reviewers (the "second opinion") and the coach |
| Embedder | Nemotron 3 Embed | Searches regulation texts; only some reports use it |

Copy the example settings file:

```bash
cp .env.example .env
```

`.env` is ignored by git, so the values you put in it stay on your computer. Then choose
one of these:

**A. The team's GPU node (no key).** Connect to the VPN (see [cluster.md](cluster.md)).
The servers job on the cluster writes the node's address and ports to
`/data/team08/runs/servers.env`. Copy its six `EVIDENCE_..._BASE_URL` and `..._MODEL` lines
into `.env`, replacing the ones there.

**B. NVIDIA's cloud (with a key).** In `.env`, put your key after `NVIDIA_API_KEY=`, and put
a `#` in front of the six `EVIDENCE_..._BASE_URL` and `..._MODEL` lines. A role whose lines
are commented out runs on NVIDIA's cloud.

You can mix the two: for example, run the assistant on the node and the judge in the cloud.

**Behind a company proxy?** If your shell sets `HTTP_PROXY` or `HTTPS_PROXY`, the calls to
the node's address can go to the proxy and fail. Exclude the node:

```bash
export NO_PROXY=10.130.232.21,localhost,127.0.0.1
```

Replace `10.130.232.21` with the node address in your `.env`.

## 3. Check the install

The tests need no network and no models:

```bash
.venv/bin/pytest -q
```

All tests should pass. Then check that the three models answer, with one call to each:

```bash
.venv/bin/python scripts/smoke_nvidia.py
```

It prints each model's reply with its pinned model id and timing. An error here is almost
always the VPN, the proxy, or a missing key.

## 4. Start the web UI

```bash
.venv/bin/evidence ui
```

Open <http://127.0.0.1:8765>. Stop it with Ctrl+C.

| Address | What is there |
|---|---|
| <http://127.0.0.1:8765> | The UI: Test, Review, Improve |
| <http://127.0.0.1:8765/sdd/> | The Synthetic Data Designer, where the recipe for test cases can be opened and changed |
| <http://127.0.0.1:8765/advanced/> | The full console: packs, runs, verification, the tamper demo |

To use another port: `.venv/bin/evidence ui --port 8800`. To keep test data somewhere else:
`.venv/bin/evidence ui --root /path/to/folder` (the folder holds `packs/` and `runs/`).

## 5. Run a first small test

1. On the home page, press **Start a new test**.
2. Leave the assistant and the German rules as they are.
3. Press **Generate new cases**. Choose **5** cases, run **Twice**, and press **Generate**.
4. For the quickest first run, untick **Also get a second opinion from three AI
   reviewers**.
5. Press **Start test**. Ten memos take a minute or two; with the second opinion, a few
   minutes more.

When it finishes, the result page opens. Continue with the
[underwriter guide](underwriter-guide.md).

## Settings

All are optional and go in `.env` or the shell.

| Setting | Default | What it does |
|---|---|---|
| `NVIDIA_API_KEY` | none | Key for any role on NVIDIA's cloud |
| `EVIDENCE_ASSISTANT_BASE_URL`, `EVIDENCE_ASSISTANT_MODEL` | NVIDIA's cloud | Where the assistant runs |
| `EVIDENCE_JUDGE_BASE_URL`, `EVIDENCE_JUDGE_MODEL` | NVIDIA's cloud | Where the judge, the AI reviewers and the coach run |
| `EVIDENCE_EMBED_BASE_URL`, `EVIDENCE_EMBED_MODEL` | NVIDIA's cloud | Where the embedder runs |
| `EVIDENCE_WORKERS` | 8 | Memos written and checked at the same time |
| `EVIDENCE_PANEL_WORKERS` | 8 | Memos the AI reviewers work on at the same time |
| `EVIDENCE_PANEL_SSH` | not set | Runs the AI reviewers inside the NemoClaw sandbox on the cluster (for example `"codefest rtx-3se-06-04"`); see [cluster.md](cluster.md) |
| `EVIDENCE_CHROME` | found automatically | The Chrome or Chromium used to print PDFs |
| `EVIDENCE_MODELS_FILE` | `models.json` | The node's model fingerprints (image digests, weights hashes), written by the servers job |
| `EVIDENCE_ANCHOR` | `on` | `off` stops anchoring each test's seal in Bitcoin; see [anchoring](anchoring.md) for its other settings |

## Where your data goes

Everything stays in the project folder (or the `--root` folder):

| Folder | What is in it |
|---|---|
| `packs/` | Case sets. `underwriter-de` and `underwriter-sample` come with the code; generated sets are named like `underwriter-de-s78137` |
| `runs/` | One folder per test: the memos, the check results, the review, the feedback pack, and `checksums.sha256`, which seals it all |
| `runs/<test>/anchors/` | The Bitcoin proofs of the test's seal ([anchoring](anchoring.md)); copied with the test |
| `runs/test-numbers.json` | The short test numbers shown in the UI (Test 1, Test 2, …) |

To tidy up, move old runs or case sets to a folder outside the project. Don't delete them:
a sealed run is evidence.

## With Docker instead

```bash
docker compose up ui
```

This builds the image, reads `.env`, and serves the UI on <http://localhost:8765>, with
`runs/` kept on your computer.

## When something goes wrong

| What you see | What to do |
|---|---|
| `address already in use` | Another program uses port 8765. Start with `--port 8800` |
| A test stops with "NVIDIA_API_KEY is not set" | The assistant is on NVIDIA's cloud but `.env` has no key. Add it, or point the assistant at the node |
| A test stops with a connection error | Check the VPN, the proxy (`NO_PROXY`) and the node address in `.env`; `scripts/smoke_nvidia.py` shows which model fails |
| "Could not run this time" for the second opinion | The judge was unreachable. The test result stands without it |
| The PDF download fails | Install Chrome, or set `EVIDENCE_CHROME` to its path |
| The page looks out of date after an update | Reload the page; the UI tells the browser not to keep old copies |
