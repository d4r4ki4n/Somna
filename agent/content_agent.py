"""
content_agent.py — Somna Content Generation Studio
====================================================
A local-LLM-powered content authoring tool for Somna sessions.
Gives a local LLM (Ollama, LM Studio, or any OpenAI-compatible endpoint)
the tools it needs to write affirmations, author session YAML, and generate
background images.

This is NOT a session controller. It does not touch live_control.json.
It writes content to disk for use by the runtime.

Usage
-----
    # Interactive studio — knows all tools and all knowledge
    python content_agent.py

    # Pre-load a specific session's content into context
    python content_agent.py gateway_f10

    # Non-interactive: pipe a single request and exit
    echo "Write 15 deep-theta subliminal phrases for a feminization session" | python content_agent.py default

Configuration (environment variables or .env file in project root)
-------------------------------------------------------------------
    SOMNA_LLM_URL   = http://localhost:11434   (Ollama default)
    SOMNA_LLM_MODEL = llama3.1                 (any tool-capable model)
    SOMNA_IMG_URL   = http://localhost:7860    (A1111 default)
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path when run directly from the terminal.
_ROOT = Path(__file__).parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ── Load .env if present ──────────────────────────────────────────────────────

def _load_dotenv() -> None:
    env_path = _ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        os.environ.setdefault(key.strip(), val.strip())

_load_dotenv()

# ── Configuration ─────────────────────────────────────────────────────────────

def _yaml_cfg() -> dict:
    cfg_path = _ROOT / "agent_config.yaml"
    if not cfg_path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

def _llm_url() -> str:
    # env var → agent_config.yaml base_url → default
    env = os.environ.get("SOMNA_LLM_URL")
    if env:
        return env
    cfg_url = _yaml_cfg().get("base_url", "")
    if cfg_url:
        # base_url in agent_config.yaml already includes /v1 for the main agent;
        # strip it here because LLMClient appends /v1 itself
        return cfg_url.rstrip("/").removesuffix("/v1")
    return "http://localhost:11434"

def _llm_model() -> str:
    env = os.environ.get("SOMNA_LLM_MODEL")
    if env:
        return env
    return _yaml_cfg().get("model", "llama3.1")


# ── Knowledge base injection ──────────────────────────────────────────────────

_KNOWLEDGE_DIR = _ROOT / "knowledge"

def _load_knowledge() -> str:
    """Concatenate all knowledge/*.md files into a single system-prompt block."""
    if not _KNOWLEDGE_DIR.exists():
        return ""
    files = sorted(_KNOWLEDGE_DIR.glob("*.md"))
    if not files:
        return ""
    parts = []
    for f in files:
        parts.append(f"## {f.stem.replace('_', ' ').title()}\n\n{f.read_text(encoding='utf-8')}")
    return "\n\n---\n\n".join(parts)


def _build_system_prompt(session_context: str = "") -> str:
    knowledge = _load_knowledge()

    base = (
        "You are an expert Somna session content author. Somna is a hypnotic "
        "entrainment and subliminal affirmation system that uses binaural beats, "
        "visual spirals, and layered affirmation delivery to induce trance states "
        "and deliver subliminal content.\n\n"
        "You have access to a library of tools that let you:\n"
        "  - Read and write affirmations.txt files (tagged phrase pools)\n"
        "  - Read and write session.yaml files (keyframed session timelines)\n"
        "  - Generate background images via the local Stable Diffusion API\n"
        "  - List available sessions\n\n"
        "Always read existing session content before writing to it. "
        "Match phrase length and tone to the trance depth of the target phase. "
        "Follow the session design principles from the knowledge base.\n\n"
    )

    if knowledge:
        base += "# Knowledge Base\n\n" + knowledge + "\n\n"

    if session_context:
        base += f"# Current Session Context\n\n{session_context}\n\n"

    return base


# ── LLM client ────────────────────────────────────────────────────────────────

class LLMClient:
    """Minimal OpenAI-compatible client with tool-calling support.

    Works with Ollama (openai-compat mode), LM Studio, OpenAI, etc.
    Falls back to ReAct-style JSON extraction if the model does not return
    tool_calls in the expected format.
    """

    def __init__(self, base_url: str, model: str, api_key: str = "sk-nokey"):
        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key, base_url=base_url + "/v1")
        except ImportError:
            print(
                "[ContentAgent] 'openai' package not found.\n"
                "Install with: pip install openai\n"
                "Then rerun this script."
            )
            sys.exit(1)
        self._model = model

    def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        temperature: float = 0.7,
    ) -> dict:
        """Send a chat completion request and return the raw response message dict.

        Returns a dict with at least 'content' (str|None) and optionally
        'tool_calls' (list of tool call objects).
        """
        kwargs: dict[str, Any] = {
            "model":       self._model,
            "messages":    messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"]       = tools
            kwargs["tool_choice"] = "auto"

        resp = self._client.chat.completions.create(**kwargs)
        msg  = resp.choices[0].message

        # Normalise to a plain dict for consistent handling
        result: dict[str, Any] = {"content": msg.content}
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            result["tool_calls"] = [
                {
                    "id":   tc.id,
                    "name": tc.function.name,
                    "args": json.loads(tc.function.arguments),
                }
                for tc in msg.tool_calls
            ]
        else:
            # ReAct fallback: look for JSON tool call embedded in content
            tc = _extract_react_tool_call(msg.content or "")
            if tc:
                result["tool_calls"] = [tc]

        return result


def _extract_react_tool_call(text: str) -> dict | None:
    """Try to extract a tool call from ReAct-style text.

    Matches patterns like:
        Action: tool_name
        Action Input: { ... }
    or a bare JSON object containing "tool" and "arguments" keys.
    """
    import re

    # Pattern 1: Action / Action Input
    m = re.search(
        r"Action:\s*(\w+)\s*\nAction Input:\s*(\{.*?\})",
        text, re.DOTALL
    )
    if m:
        try:
            return {
                "id":   "react_0",
                "name": m.group(1).strip(),
                "args": json.loads(m.group(2)),
            }
        except json.JSONDecodeError:
            pass

    # Pattern 2: bare {"tool": "name", "arguments": {...}}
    m = re.search(r'\{"tool":\s*"(\w+)"[^}]*"arguments":\s*(\{.*?\})\s*\}',
                  text, re.DOTALL)
    if m:
        try:
            return {
                "id":   "react_0",
                "name": m.group(1),
                "args": json.loads(m.group(2)),
            }
        except json.JSONDecodeError:
            pass

    return None


# ── Tool result formatting ────────────────────────────────────────────────────

def _tool_result_message(tool_call_id: str, result: Any) -> dict:
    return {
        "role":         "tool",
        "tool_call_id": tool_call_id,
        "content":      json.dumps(result, ensure_ascii=False, default=str),
    }


def _assistant_tool_call_message(tool_calls: list[dict]) -> dict:
    """Reconstruct the assistant message with tool_calls for history."""
    from openai.types.chat import ChatCompletionMessageToolCall  # noqa: F401
    # We store a simplified version for our own message list
    return {
        "role":       "assistant",
        "content":    None,
        "tool_calls": [
            {
                "id":   tc["id"],
                "type": "function",
                "function": {
                    "name":      tc["name"],
                    "arguments": json.dumps(tc["args"]),
                },
            }
            for tc in tool_calls
        ],
    }


# ── Main agent loop ───────────────────────────────────────────────────────────

class ContentAgent:

    def __init__(self, session_name: str | None = None):
        self._llm     = LLMClient(_llm_url(), _llm_model())
        self._session = session_name
        self._messages: list[dict] = []
        self._tools   = None   # lazy import

    def _get_tools(self) -> list[dict]:
        if self._tools is None:
            from content_tools import TOOLS
            self._tools = TOOLS
        return self._tools

    def _get_session_context(self) -> str:
        if not self._session:
            return ""
        from content_tools.sessions import read_session, list_sessions
        available = list_sessions()
        if self._session not in available:
            return f"Session '{self._session}' does not exist yet (will be created on first write)."
        content = read_session(self._session)
        yaml_snippet    = (content["yaml"][:2000] + "\n...(truncated)")     if len(content["yaml"])    > 2000 else content["yaml"]
        aff_snippet     = (content["affirmations"][:1500] + "\n...(truncated)") if len(content["affirmations"]) > 1500 else content["affirmations"]
        return (
            f"Active session: {self._session!r}\n\n"
            f"session.yaml:\n```yaml\n{yaml_snippet}\n```\n\n"
            f"affirmations.txt:\n```\n{aff_snippet}\n```"
        )

    def _system_prompt(self) -> str:
        return _build_system_prompt(self._get_session_context())

    def _run_tool_calls(self, tool_calls: list[dict]) -> list[dict]:
        """Execute a batch of tool calls and return tool result messages."""
        from content_tools import dispatch
        result_messages = []
        for tc in tool_calls:
            print(f"[Tool] {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)[:120]})")
            try:
                result = dispatch(tc["name"], tc["args"])
            except Exception as exc:
                result = {"error": str(exc)}
            print(f"[Tool] → {json.dumps(result, ensure_ascii=False, default=str)[:160]}")
            result_messages.append(_tool_result_message(tc["id"], result))
        return result_messages

    def chat(self, user_input: str) -> str:
        """Send one user message, execute any tool calls, and return final reply."""
        self._messages.append({"role": "user", "content": user_input})

        tools = self._get_tools()

        # Loop: call LLM → execute tools → feed results back → repeat until no more tool calls
        for _ in range(10):   # max 10 tool-call rounds per turn
            response = self._llm.chat(
                messages=[{"role": "system", "content": self._system_prompt()}]
                         + self._messages,
                tools=tools,
            )

            tool_calls = response.get("tool_calls")
            content    = response.get("content") or ""

            if not tool_calls:
                # No more tool calls — final answer
                self._messages.append({"role": "assistant", "content": content})
                return content

            # Append assistant's tool-calling message
            self._messages.append(_assistant_tool_call_message(tool_calls))
            # Execute tools and append results
            result_messages = self._run_tool_calls(tool_calls)
            self._messages.extend(result_messages)
            # If there was also a content fragment alongside tool calls, print it
            if content:
                print(f"[Agent] {content}")

        # If we somehow exhaust the loop, return what we have
        return content

    def run_interactive(self) -> None:
        """Run the interactive terminal loop."""
        session_info = f" ({self._session})" if self._session else ""
        print(f"\nSomna Content Studio{session_info}")
        print(f"Model: {_llm_model()}  URL: {_llm_url()}")
        print("Type your request. Ctrl+C or 'exit'/'quit' to stop.\n")

        while True:
            try:
                user_input = input("> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n[ContentAgent] Stopped.")
                break

            if not user_input:
                continue
            if user_input.lower() in {"exit", "quit", "q"}:
                break

            reply = self.chat(user_input)
            if reply:
                print(f"\n{reply}\n")


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    import argparse

    p = argparse.ArgumentParser(
        description="Somna Content Generation Studio — LLM-powered session authoring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "session",
        nargs="?",
        default=None,
        help="Session folder name to pre-load into context (optional).",
    )
    p.add_argument(
        "--model",
        default=None,
        help="Override SOMNA_LLM_MODEL env var.",
    )
    p.add_argument(
        "--url",
        default=None,
        help="Override SOMNA_LLM_URL env var (base URL without /v1).",
    )
    p.add_argument(
        "--list-sessions",
        action="store_true",
        help="Print available sessions and exit.",
    )

    args = p.parse_args()

    if args.model:
        os.environ["SOMNA_LLM_MODEL"] = args.model
    if args.url:
        os.environ["SOMNA_LLM_URL"] = args.url

    if args.list_sessions:
        from content_tools.sessions import list_sessions
        sessions = list_sessions()
        print("Available sessions:")
        for s in sessions:
            print(f"  {s}")
        return

    agent = ContentAgent(session_name=args.session)

    # Non-interactive mode: if stdin is not a tty, read one request and exit
    if not sys.stdin.isatty():
        request = sys.stdin.read().strip()
        if request:
            reply = agent.chat(request)
            if reply:
                print(reply)
        return

    agent.run_interactive()


if __name__ == "__main__":
    main()
