# leanagents

[![tests](https://github.com/decentralizeallengineering/leanagents/actions/workflows/tests.yml/badge.svg)](https://github.com/decentralizeallengineering/leanagents/actions/workflows/tests.yml) ![license](https://img.shields.io/badge/license-Apache--2.0-blue)

A `PreToolUse` hook on Claude Code's Agent tool. It rewrites default or `general-purpose` subagent calls to small-prompt
agent types, so far fewer base tokens are spent on every subagent.

## The problem

Each subagent starts with a system prompt before it reads your task. The default agent carries a large one, and it is
paid again for every delegation, including the many that only need to find a line or make one edit.

## The fix

For calls with `subagent_type` unset, `general-purpose` or `chore`:

| Prompt asks for | Routed to | Model |
| --- | --- | --- |
| web, URL, MCP, skill, browser, "online", "internet" | unchanged (full agent) | unchanged |
| an edit, fix, build, add, commit, install ... | `lean-build` | from the agent file (`sonnet`) |
| read-only search or reading | `lean-search` | from the agent file (`haiku`) |
| read-only analysis (audit, investigate, root cause, trace, review, why) | `lean-search` | `sonnet`, unless the call named a model |

Analysis is read-only but needs a stronger model than triage, hence the model override. All other agent types, and all
other tools, are left alone. All other fields of the call (description, background flag, ...) are kept.

## Base-context saving, and how it was measured

The lean definitions are in `agents/`. Their system prompts were counted with a simple estimate of characters divided by
4 (rounded up), by `python3 leanagents.py measure`, which counts everything after the front matter:

    lean-build: 187 chars, about 47 tokens
    lean-search: 110 chars, about 28 tokens
    total: 297 chars, about 75 tokens (chars / 4)

So a routed subagent starts with a system prompt of roughly 28 to 47 tokens. This is an estimate, not a tokenizer count.

What was not measured: the built-in default agent's prompt is not part of this repo, so no "before" figure is claimed.
To get your own number, save the default prompt you want to compare against to a file and run
`leanagents measure that-file.md agents/`. The saving per delegation is the difference. The lean agents also list only
four to six tools, which should shrink tool definitions too; that was not counted either.

## Install

    mkdir -p ~/.claude/agents && cp agents/*.md ~/.claude/agents/
    pip install .        # gives the `leanagents` command; or call python3 leanagents.py directly

## Configure

Add to `~/.claude/settings.json` (use the full path to `leanagents.py` if you did not install it):

    {
      "hooks": {
        "PreToolUse": [
          {
            "matcher": "Agent|Task",
            "hooks": [{"type": "command", "command": "leanagents hook"}]
          }
        ]
      }
    }

| Variable | Default | Meaning |
| --- | --- | --- |
| `LEANAGENTS_OFF` | unset | kill switch: set to `1` and every call passes through unchanged |
| `LEANAGENTS_BUILD` | `lean-build` | agent type for edits |
| `LEANAGENTS_SEARCH` | `lean-search` | agent type for read-only work |
| `LEANAGENTS_ANALYSIS_MODEL` | `sonnet` | model for read-only analysis prompts |

The routed names must exist as agent definitions, hence the `cp` above. Edit the `agents/*.md` files to taste.

## Example

    echo '{"tool_name":"Agent","tool_input":{"prompt":"Investigate why the cache misses and trace the key."}}' | leanagents hook

prints a `permissionDecision: allow` JSON whose `updatedInput` has `"subagent_type": "lean-search"` and `"model": "sonnet"`.
Run the tests with `python3 -m pytest`.

## Limits

- Routing is keyword matching on the prompt and description, not understanding. A read-only prompt that says "fix" goes to
  the agent that can edit; a prompt that mentions "web" in prose keeps the full agent. Check the reason string in the
  transcript when a routing surprises you.
- The rewrite is silent to the lead model, which still believes it called the original type. Audit tools such as
  anti-lobotomy flag any hook that returns `updatedInput` for this reason.
- The hook answers `allow`, so a call it rewrites does not ask for permission. If you depend on a prompt for Agent calls,
  do not use this hook.
- The lean agents are deliberately thin: no skills, no web, no MCP. Work that needs them is kept on the full agent only
  when the prompt says so in words the patterns know.
- Routed `lean-search` calls run on the small model named in the agent file, unless the prompt is an analysis or the call named a model.
- The hook fails open: on any error it prints nothing and the call goes through unchanged.

## License

Apache-2.0, see `LICENSE` and `NOTICE`. Related: intentpin (session-start rules), fleetwarden (more hooks).
