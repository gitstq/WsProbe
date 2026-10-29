<div align="center">

# 🔭 WsProbe

**A zero-dependency WebSocket probe with a hand-rolled RFC 6455 stack**

[简体中文](README.md) · [繁體中文](README.zh-TW.md) · [English](README.en.md)

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python&logoColor=white)
![Dependencies](https://img.shields.io/badge/dependencies-0-brightgreen)
![License](https://img.shields.io/badge/license-MIT-green)
![RFC](https://img.shields.io/badge/RFC-6455-orange)

</div>

---

## 🎉 About

**WsProbe** is a command-line probe and Python library for debugging WebSocket services.
The whole pitch fits in one sentence:

> **The entire WebSocket protocol stack (RFC 6455) is implemented from scratch — with zero third-party dependencies at runtime.**

No `websockets`. No `websocket-client`. No `aiohttp`, `requests`, or `numpy`.
Just a Python 3.8+ interpreter. Clone the repo and run it — air-gapped networks,
locked-down intranets and minimal containers included.

### 🤔 The problems it solves

| # | Pain point | How WsProbe helps |
|---|------------|-------------------|
| 1 | 🔌 WebSocket has no "curl-grade" tool; debugging means writing throwaway scripts | Connect, send, filter and record from a single command |
| 2 | 📦 Existing tools are heavy and simply won't install offline | **Zero runtime dependencies**, standard library only |
| 3 | 🕶️ Handshake failures are a black box — "it doesn't connect" is all you get | `inspect` prints status code, request key, Accept check and resolved IP |
| 4 | 🌊 Dozens of pushes per second bury the one message you care about | Built-in filter DSL: `--filter '$.price > 100'` |
| 5 | 🔁 A bug "was just there a second ago" and you can't reproduce it | Record to JSONL, replay at original or accelerated speed |
| 6 | 🧪 WebSocket endpoints can't be regression-tested the way HTTP ones can | Declarative JSON scripts, CI-ready, non-zero exit on failure |
| 7 | 📊 "It feels slow" is not a measurement | `bench` reports throughput plus P50 / P95 / P99 latency |

### 💎 What makes it different

* 🧬 **A stack written from scratch**: frame codec, XOR masking, extended length (7/16/64-bit),
  fragment reassembly, handshake Accept computation, heartbeats and the closing handshake —
  byte by byte, not a wrapper around someone else's library.
* 🎯 **Both sides are ours**: the client *and* the bundled server are self-implemented.
  `wsprobe serve` doubles as a demo target and as the fixture for end-to-end tests.
* 🔍 **Our own filter language**: no jsonpath, no JMESPath — a tiny query language with paths,
  wildcards and comparison operators, written in-house.
* 🩺 **Observable by default**: handshake diagnostics, RTT, byte/message counters, latency percentiles.
* 🔌 **CLI *and* library**: `from wsprobe import WebSocketClient` drops straight into your own code.

### 🌱 Where the idea came from

WsProbe is what happens when you fuse **curl** (immediacy), **tcpdump** (record and replay) and
**wscat** (interactive sessions) — then compress them into a single dependency-free, auditable,
CI-friendly pure-Python package.

> 📸 *Screenshot / GIF placeholder: add a terminal recording here once available.*

---

## ✨ Features

### 🧬 Protocol layer (all self-implemented)

* ✅ **Complete frame codec**: FIN / RSV / opcode / MASK / 7-16-64-bit extended payload length
* ✅ **Client masking**: 4-byte CSPRNG mask, XOR applied with a self-inverse operation
* ✅ **Fragment reassembly**: continuation frames merged, with checks such as "no interleaved data frames"
* ✅ **Handshake**: `Sec-WebSocket-Key` generation, `Sec-WebSocket-Accept` via SHA-1 + GUID, verified
* ✅ **Heartbeats**: active PING with RTT measurement; **automatic** PONG replies (required by the RFC)
* ✅ **Closing handshake**: send close → wait for peer close → tear down TCP, then decode code and reason
* ✅ **Protocol guards**: RSV bits, unknown opcodes, fragmented control frames, invalid UTF-8, oversized payloads
* ✅ **TLS and proxies**: `wss://` plus HTTP CONNECT tunnelling

### 🛠️ Tooling

* 🔭 **`connect`**: connect, send, filter, record — with an interactive REPL mode
* 🩺 **`inspect`**: run only the handshake and print a full diagnostic report
* 📈 **`bench`**: concurrent load test with throughput and P50/P95/P99
* 🎬 **`script`**: declarative JSON steps (send / expect / wait / sleep / ping / close)
* ♻️ **`replay`**: push a recorded session at any target
* 🖥️ **`serve`**: built-in echo / timed-push / broadcast server
* 🧪 **`selftest`**: 10 protocol self-checks in a single command
* 🎨 **Friendly output**: colors, JSON Lines, hexdump, and a `--no-color` fallback

---

## 🚀 Quick start

### 📋 Requirements

| Item | Requirement |
|------|-------------|
| Python | **>= 3.8** (standard library only) |
| Third-party deps | **None** |
| OS | Windows / macOS / Linux |
| Network | Outbound TCP; use `--proxy` when behind a proxy |

### 📦 Install

```bash
# Option 1: pip (recommended)
git clone https://github.com/gitstq/WsProbe.git
cd WsProbe
pip install .

# Option 2: no install at all — run it as a module
python -m wsprobe --help
```

Installing exposes the `wsprobe` command.

### ⚡ Three steps to see it work

**Step 1** In one terminal, start the bundled server (one push per second):

```bash
wsprobe serve --port 8765 --pump 1
```

**Step 2** In another terminal, connect:

```bash
wsprobe ws://127.0.0.1:8765
```

You'll see something like:

```
✓ HTTP 101 Switching Protocols · 127.0.0.1:8765 (127.0.0.1)
[10:32:01] ← {"type": "pump", "seq": 1, "ts": 1793290921.1, "value": 12.33}
[10:32:02] ← {"type": "pump", "seq": 2, "ts": 1793290922.1, "value": 24.67}
```

**Step 3** Keep only what you care about:

```bash
wsprobe ws://127.0.0.1:8765 --filter '$.value > 20' --count 5 --stats
```

> 💡 No WebSocket service handy? That's exactly what `wsprobe serve` is for.

---

## 📖 Usage guide

### 🗂️ Subcommands

| Command | Purpose | Example |
|---------|---------|---------|
| `connect` | Connect and exchange messages (default, may be omitted) | `wsprobe ws://host/p --send hi` |
| `inspect` | Handshake only, print diagnostics | `wsprobe inspect wss://host/p` |
| `bench` | Concurrent load test | `wsprobe bench ws://host -c 20 -m 200` |
| `script` | Run a declarative script | `wsprobe script flow.json` |
| `replay` | Replay a recording | `wsprobe replay rec.jsonl --to ws://host` |
| `serve` | Start the built-in server | `wsprobe serve --port 8765 --pump 1` |
| `selftest` | Protocol self-check | `wsprobe selftest` |

### 🔭 Connecting and sending

```bash
# Connect and drop into interactive mode (type to send, /quit to leave)
wsprobe ws://127.0.0.1:8765

# Send one text frame and receive one response
wsprobe ws://127.0.0.1:8765 --send '{"cmd":"ping"}' --count 1

# Send several messages, 0.5s apart
wsprobe ws://127.0.0.1:8765 --send a --send b --send-interval 0.5

# Send the contents of a file
wsprobe ws://127.0.0.1:8765 --send-file payload.json

# Listen for 30 seconds
wsprobe ws://127.0.0.1:8765 --duration 30

# Custom headers / subprotocol / proxy / skip cert verification
wsprobe wss://host/p \
  --header "Authorization: Bearer TOKEN" \
  --subprotocol json \
  --proxy http://127.0.0.1:7890 \
  --insecure
```

**Built-in REPL commands:**

| Input | Effect |
|-------|--------|
| `any text` | Sent as a text frame |
| `/ping` | Measure one round trip |
| `/wait 3` | Silently collect messages for 3 seconds |
| `/stats` | Print session statistics |
| `/quit` | Close and exit |

### 🔍 Filter expressions

Syntax is `<path> [<operator> <value>]`:

| Expression | Meaning |
|------------|---------|
| `$.price > 100` | Top-level `price` above 100 |
| `data.status == "error"` | Nested field equals `error` |
| `items[*].id` | Any array element has an `id` field |
| `text ~ "timeout"` | Text contains `timeout` |
| `name ^ "ws"` | Starts with `ws` |
| `name $ "probe"` | Ends with `probe` |

Supported operators: `==` `!=` `>` `>=` `<` `<=` `~` (contains) `^` (prefix) `$` (suffix).
Text frames are parsed as JSON when possible, otherwise treated as plain strings.
Incomparable types are reported as "no match" instead of raising an error.

### 🎬 Record and replay

```bash
# Record (all traffic lands in JSONL, regardless of whether it matched the filter)
wsprobe ws://host/p --duration 60 --record session.jsonl

# Inspect a recording without sending anything
wsprobe replay session.jsonl --preview

# Replay against another host at original speed
wsprobe replay session.jsonl --to ws://staging-host/p

# Replay at 2x; --speed 0 means "as fast as possible"
wsprobe replay session.jsonl --to ws://host/p --speed 2
```

Each JSONL line looks like:

```json
{"ts": 1793290921.106, "dir": "in", "op": "text", "size": 64, "data": "{\"type\":\"pump\"}"}
```

### 🧪 Declarative scripts (CI-friendly)

```json
{
  "url": "ws://127.0.0.1:8765",
  "steps": [
    { "action": "send",   "data": { "cmd": "subscribe", "channel": "ticker" } },
    { "action": "expect", "filter": "cmd == \"subscribe\"", "timeout": 5 },
    { "action": "sleep",  "seconds": 0.5 },
    { "action": "wait",   "count": 3, "timeout": 10 },
    { "action": "ping" },
    { "action": "close" }
  ]
}
```

```bash
wsprobe script flow.json --json     # machine-readable output, easy to assert on in CI
```

Exit code is `0` when every step passes and `1` if any step fails, so it plugs straight into a pipeline gate.

### 📈 Load testing

```bash
wsprobe bench ws://127.0.0.1:8765 --connections 20 --messages 200 --payload 128
```

```
url                     : ws://127.0.0.1:8765
connections             : 20
messages_per_connection : 200
completed               : 4000
errors                  : 0
throughput_msg_per_s    : 6098.68
latency_p50_ms          : 0.364
latency_p95_ms          : 0.932
latency_p99_ms          : 1.022
```

### 🩺 Handshake diagnostics

```bash
wsprobe inspect wss://echo.example.com
```

```
HTTP 101 Switching Protocols
  Target      : wss://echo.example.com
  Resolved IP : 93.184.216.34
  Request Key : xUFq46M2kCNjLVU859PCwQ==
  Expected Acc: HN2CMetJ8CJC/UA3cp1YIJXqG9Y=
  Accept      : HN2CMetJ8CJC/UA3cp1YIJXqG9Y= (verified)
  First RTT   : 42.15 ms
```

When a connection fails, this output is your first real evidence: is the status not 101?
Did the Accept check fail? Or is the culprit TLS or the proxy?

### 🐍 Use it as a library

```python
from wsprobe import WebSocketClient
from wsprobe.filters import MessageFilter

matcher = MessageFilter("value >= 10")

with WebSocketClient("ws://127.0.0.1:8765", timeout=5) as ws:
    ws.send_json({"cmd": "subscribe", "channel": "ticker"})
    for message in ws.iter_messages(count=100, timeout=10):
        if matcher.match(message):
            print(message.json)

    rtt = ws.ping()          # round trip in seconds
    print(ws.stats.to_dict())
```

More examples in [`examples/library_usage.py`](examples/library_usage.py).

### ❓ FAQ

<details>
<summary><b>The handshake fails with HTTP 4xx / 5xx. What now?</b></summary>

Run `wsprobe inspect <url>` first and read the status code and response headers.
401/403 usually means a missing auth header (add `--header`); 404 usually means a wrong path;
301/302 means you should connect to the redirect target instead.
</details>

<details>
<summary><b>Getting <code>Sec-WebSocket-Accept verification failed</code>?</b></summary>

The peer's Accept doesn't match the standard algorithm — often a sign that something
in the middle is intercepting, or that the endpoint isn't really a WebSocket service.
Once you're sure the target is correct, `--no-strict-accept` lets you skip the check and keep digging.
</details>

<details>
<summary><b>Need to go through a corporate proxy?</b></summary>

Use `--proxy http://host:port`. WsProbe issues an HTTP CONNECT first, then runs TLS
and the handshake on top of that tunnel.
</details>

<details>
<summary><b>Self-signed certificate errors?</b></summary>

Add `--insecure` to skip verification (recommended only for internal debugging).
</details>

<details>
<summary><b>A message was rejected for being too large?</b></summary>

The default per-message cap is 64 MiB; adjust it with `--max-payload`.
It's a guard against a hostile server exhausting your memory.
</details>

---

## 💡 Design notes and roadmap

### 🏗️ Layered architecture

```
┌──────────────────────────────────────────────┐
│  cli.py        arg parsing, rendering, REPL   │  ← application
├──────────────────────────────────────────────┤
│  script.py / session.py / stats.py / filters  │  ← capabilities
├──────────────────────────────────────────────┤
│  client.py     state machine, heartbeat, close│  ← session
├──────────────────────────────────────────────┤
│  handshake.py  HTTP Upgrade / Key / Accept    │  ← handshake
├──────────────────────────────────────────────┤
│  frame.py      RFC 6455 codec / mask / frags  │  ← protocol (the core of it)
└──────────────────────────────────────────────┘
```

### 🤔 Key decisions

| Decision | Why |
|----------|-----|
| **Zero third-party dependencies** | A debugging tool has to work in the worst environment imaginable. Fewer dependencies, higher availability |
| **Blocking sockets + threads** | Keeps `asyncio` complexity out; timeouts and behaviour are far more predictable in a debugging tool |
| **Masking via big-integer XOR** | A per-byte Python loop crawls on 64 KB payloads; a single `int.from_bytes` XOR is roughly an order of magnitude faster |
| **Filter DSL written in-house** | jsonpath / JMESPath are heavy for what debugging needs — paths plus comparisons, nothing more |
| **Bundled server** | The tool ships with its own target: zero-setup demos and end-to-end tests that never touch the internet |
| **Non-zero exit on script failure** | Turns WebSocket endpoints into something a CI gate can actually enforce |

### 🗺️ Roadmap

* [ ] 🔐 Detect and negotiate the `permessage-deflate` compression extension
* [ ] 🧩 Pluggable message codecs (Protobuf / MessagePack, installed only when needed)
* [ ] 📊 HTML reports that render a recording as a timeline
* [ ] 🔄 Automatic reconnect with exponential backoff (`--reconnect`)
* [ ] 🌐 SOCKS5 proxy support
* [ ] 🧵 Optional asyncio client
* [ ] 📦 Publish to PyPI

### 🤝 Where contributions help most

Three kinds are especially welcome: **compatibility testing against more real-world servers**,
**making the filter DSL more expressive**, and **localising docs and examples**.

---

## 📦 Packaging and deployment

WsProbe is a **library / CLI** project, so **no binary release assets are required** —
install it as below and you're ready to go.

### 🐍 Option 1: pip (recommended)

```bash
pip install .
# or editable, so changes take effect immediately
pip install -e .
```

You get two entry points:

* CLI: `wsprobe --help`
* Library: `from wsprobe import WebSocketClient`

### 📄 Option 2: run without installing

```bash
git clone https://github.com/gitstq/WsProbe.git
cd WsProbe
python -m wsprobe --help       # equivalent to wsprobe --help
```

Because there are no dependencies, you can also copy the `wsprobe/` directory straight into your own project.

### 🧊 Option 3: single-file executable (optional)

When you need a dependency-free binary, use PyInstaller:

```bash
pip install pyinstaller
./scripts/build.sh              # output: dist/wsprobe plus a .sha256 checksum
./scripts/build.sh clean        # clean up
```

> ⚠️ PyInstaller **cannot cross-compile**. Build Windows / macOS artifacts on those
> platforms (or on their CI runners — see `.github/workflows/release.yml`).

### 🌍 Supported environments

| Environment | Status |
|-------------|--------|
| Python 3.8 / 3.9 / 3.10 / 3.11 / 3.12 | ✅ Supported |
| Windows 10+ / macOS 11+ / Linux | ✅ Supported |
| Offline / air-gapped networks | ✅ Supported (zero deps) |
| Minimal Docker images (e.g. `python:3.11-slim`) | ✅ Supported |

### 🧪 Verify the installation

```bash
wsprobe selftest
```

All 10 protocol self-checks passing means your environment is good.

---

## 🤝 Contributing

### 🔀 Pull request guidelines

1. Fork the repo and create a feature branch: `git checkout -b feat/your-feature`
2. Write commit messages in the **Angular convention**:

   ```
   feat: add xxx
   fix: correct xxx
   docs: update xxx
   refactor: restructure xxx
   test: cover xxx
   chore: adjust build config
   ```

3. Keep the **zero third-party dependency** rule intact (test-only dependencies are fine)
4. Add or update unit tests, and make sure everything passes:

   ```bash
   python -m unittest discover tests
   wsprobe selftest
   ```

5. If you change CLI behaviour, update the README in **all three languages**

### 🐛 Reporting issues

Please include:

* WsProbe version (`wsprobe --version`) and Python version
* Operating system
* The exact command you ran (redact the target if needed)
* Full output of `wsprobe inspect <url>`
* Expected vs. actual behaviour

### 🧭 Code style

* Follow PEP 8; document public interfaces with docstrings
* Protocol-layer changes must ship with unit tests (protocol bugs hide in edge-case inputs)
* Keep modules single-purpose: `frame.py` handles bytes, `client.py` handles sessions

---

## 📄 License

Released under the **MIT License** — see [LICENSE](LICENSE) for the full text.

* ✅ Commercial use, modification, distribution and private use allowed
* ✅ May be used inside closed-source projects
* ⚠️ Keep the original copyright and license notice
* ❌ Provided without warranty of any kind

---

<div align="center">

**🔭 WsProbe — turning the WebSocket black box into bytes you can actually see.**

Made with ❤️ by WsProbe Contributors

</div>
