#!/usr/bin/env python3
"""leanagents: a PreToolUse hook on the Agent tool that sends default or general-purpose subagent calls to small-prompt
agent types, because the default agent carries a much larger base prompt.

Routing, for subagent_type unset, "general-purpose" or "chore":
  - prompt asks for web, MCP, skills or a browser  -> kept as is (the full agent is needed)
  - prompt asks for an edit, fix, build, ...       -> $LEANAGENTS_BUILD (default lean-build)
  - anything else (read-only)                      -> $LEANAGENTS_SEARCH (default lean-search); when the prompt is an
    analysis (audit, investigate, root cause, review, why ...) and no model was given, model is set to
    $LEANAGENTS_ANALYSIS_MODEL (default sonnet), a stronger model than plain triage.
Every other subagent_type is left alone. Both lean types must exist as agent definitions (see agents/*.md).
Kill switch: LEANAGENTS_OFF=1. Fail-open: any error ends in silence and the call goes through unchanged.

Commands:
  leanagents hook                 the hook (hook JSON on stdin)
  leanagents measure [PATH ...]   estimate the system-prompt tokens of agent definitions (chars / 4)
"""
import argparse
import glob
import json
import os
import re
import sys

__version__ = "0.1.0"
HEAVY = {None, "", "general-purpose", "chore"}
NEEDS_FULL = re.compile(
    r"https?://|\bweb\b(?!/)|\bWebFetch\b|\bWebSearch\b|\bmcp__|\bMCP\b|\bskill\b|\bbrowser\b|\bonline\b|\binternet\b", re.I)
# Read-only audits and root-cause work need a stronger model than a plain search.
ANALYSIS = re.compile(
    r"\b(?:audit|analy[sz]e|analysis|investigat\w*|root cause|trace|diagnos\w*|review|why)\b", re.I)
BUILDS = re.compile(
    r"\b(?:edit|write|fix|implement|build|create|add|change|refactor|commit|patch|install|update|rename|delete|remove|apply)\b",
    re.I)


def lean_type(tool_input):
    """The lean agent type for this call, or None to leave the call alone."""
    if tool_input.get("subagent_type") not in HEAVY:
        return None
    text = (tool_input.get("prompt") or "") + " " + (tool_input.get("description") or "")
    if NEEDS_FULL.search(text):
        return None
    if BUILDS.search(text):
        return os.environ.get("LEANAGENTS_BUILD", "lean-build")
    return os.environ.get("LEANAGENTS_SEARCH", "lean-search")


def rewrite(tool_input):
    """The updated tool input, or None."""
    new = lean_type(tool_input)
    if not new:
        return None
    updated = {**tool_input, "subagent_type": new}
    text = (tool_input.get("prompt") or "") + " " + (tool_input.get("description") or "")
    if (new == os.environ.get("LEANAGENTS_SEARCH", "lean-search") and not tool_input.get("model")
            and ANALYSIS.search(text)):
        updated["model"] = os.environ.get("LEANAGENTS_ANALYSIS_MODEL", "sonnet")
    return updated


def run_hook(stdin):
    if os.environ.get("LEANAGENTS_OFF"):
        return 0
    data = json.load(stdin)
    if data.get("tool_name") not in ("Agent", "Task"):
        return 0
    tool_input = data.get("tool_input") or {}
    updated = rewrite(tool_input)
    if not updated:
        return 0
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "allow",
        "permissionDecisionReason": "leanagents: %s -> %s (smaller base prompt)" % (
            tool_input.get("subagent_type") or "default", updated["subagent_type"]),
        "updatedInput": updated}}))
    return 0


def body_of(text):
    """The system prompt of an agent definition: everything after the front matter."""
    if text.startswith("---"):
        parts = text.split("\n---", 1)
        if len(parts) == 2:
            return parts[1].lstrip("-").lstrip("\n")
    return text


def estimate_tokens(text):
    """Rough token estimate: characters / 4, rounded up. Not a real tokenizer."""
    return (len(text) + 3) // 4


def measure(paths):
    """List of (name, chars, estimated_tokens) for each agent definition under the given files or folders."""
    files = []
    for path in paths:
        files += sorted(glob.glob(os.path.join(path, "*.md"))) if os.path.isdir(path) else [path]
    rows = []
    for f in files:
        with open(f, encoding="utf-8", errors="replace") as fh:
            body = body_of(fh.read()).strip()
        rows.append((os.path.splitext(os.path.basename(f))[0], len(body), estimate_tokens(body)))
    return rows


def main(argv=None):
    parser = argparse.ArgumentParser(prog="leanagents", description="Route subagent calls to small-prompt agent types.")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("hook", help="PreToolUse hook: hook JSON on stdin")
    p = sub.add_parser("measure", help="estimate system-prompt tokens (chars / 4) of agent definitions")
    p.add_argument("paths", nargs="*", help="agent .md files or folders (default: the agents/ folder next to this file)")
    args = parser.parse_args(argv)
    if args.cmd == "measure":
        paths = args.paths or [os.path.join(os.path.dirname(os.path.abspath(__file__)), "agents")]
        rows = measure(paths)
        for name, chars, tokens in rows:
            print(f"{name}: {chars} chars, about {tokens} tokens")
        print(f"total: {sum(r[1] for r in rows)} chars, about {sum(r[2] for r in rows)} tokens (chars / 4)")
        return 0
    try:
        return run_hook(sys.stdin)
    except Exception:
        return 0


if __name__ == "__main__":
    sys.exit(main())
