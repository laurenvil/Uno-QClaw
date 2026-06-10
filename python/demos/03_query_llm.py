#!/usr/bin/env python3
"""One-shot query against the local llama-server (the `yzma` engine).

QClaw's TUI keeps a `llama-server` process bound to 127.0.0.1:8083 with the
OpenAI-compatible `/v1/chat/completions` endpoint. This script issues a single
chat completion and prints the reply — useful as a smoke test that the engine
is up before launching the TUI.

Usage:
    python3 python/demos/03_query_llm.py "Why is the sky blue?"
    python3 python/demos/03_query_llm.py --port 8083 "Explain pin D2 on Uno Q"
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request


def query(prompt: str, port: int, model: str, timeout: float) -> str:
    url = f"http://127.0.0.1:{port}/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": 256,
        "temperature": 0.3,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = json.loads(resp.read().decode())
    return body["choices"][0]["message"]["content"]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("prompt", nargs="?", default="Say 'hello, world'.")
    parser.add_argument("--port", type=int, default=8083, help="llama-server port (default 8083 = yzma)")
    parser.add_argument("--model", default="yzma", help="model_name to send (default yzma)")
    parser.add_argument("--timeout", type=float, default=120.0, help="HTTP timeout in seconds")
    args = parser.parse_args()

    try:
        reply = query(args.prompt, args.port, args.model, args.timeout)
    except urllib.error.URLError as exc:
        print(f"ERROR: cannot reach llama-server on 127.0.0.1:{args.port} — {exc.reason}")
        print("       Is the TUI running? It launches the server on startup.")
        return 1
    except (KeyError, json.JSONDecodeError) as exc:
        print(f"ERROR: malformed response from llama-server: {exc}")
        return 2

    print(reply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
