import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import leanagents  # noqa: E402


def run(tool_input, tool="Agent", **env):
    e = {k: v for k, v in os.environ.items() if not k.startswith("LEANAGENTS_")}
    e.update(env)
    r = subprocess.run([sys.executable, os.path.join(ROOT, "leanagents.py"), "hook"],
                       input=json.dumps({"tool_name": tool, "tool_input": tool_input}),
                       capture_output=True, text=True, env=e)
    assert r.returncode == 0
    return json.loads(r.stdout)["hookSpecificOutput"] if r.stdout.strip() else None


def routed(tool_input, **env):
    out = run(tool_input, **env)
    return out["updatedInput"]["subagent_type"] if out else None


def test_read_only_goes_to_search_and_analysis_gets_stronger_model():
    out = run({"subagent_type": "general-purpose", "prompt": "Find where tickets.py opens sqlite; report file:line."})
    assert out["permissionDecision"] == "allow" and out["updatedInput"]["subagent_type"] == "lean-search"
    assert "model" not in out["updatedInput"]  # triage keeps the agent file's own model
    deep = run({"prompt": "Investigate the root cause of the slow login and report the trace."})["updatedInput"]
    assert deep["subagent_type"] == "lean-search" and deep["model"] == "sonnet"
    kept = run({"prompt": "Audit the cache layer.", "model": "opus"})["updatedInput"]
    assert kept["model"] == "opus"
    assert run({"prompt": "Review the diff for bugs."}, LEANAGENTS_ANALYSIS_MODEL="opus")["updatedInput"]["model"] == "opus"


def test_edits_go_to_build_for_chore_default_and_general_purpose():
    assert routed({"subagent_type": "chore", "prompt": "Fix the typo in tools/gate.sh and run its test."}) == "lean-build"
    assert routed({"prompt": "Implement the archive flag in tools/release.py."}) == "lean-build"
    assert routed({"subagent_type": "general-purpose", "prompt": "Review and fix the parser."}) == "lean-build"
    assert routed({"prompt": "fix x"}, LEANAGENTS_BUILD="my-build") == "my-build"


def test_web_mcp_skill_browser_keep_the_full_agent():
    for p in ("Search the web for llama.cpp ctx flags.", "Read https://example.invalid/doc",
              "Use mcp__slack to read unreads.", "Run the formatting skill.", "Open the page in a browser."):
        assert routed({"subagent_type": "general-purpose", "prompt": p}) is None, p
    assert routed({"subagent_type": "general-purpose", "prompt": "Fix web/static/shell.js icon."}) == "lean-build"


def test_other_types_other_tools_kill_switch_fields_and_bad_json():
    assert routed({"subagent_type": "Explore", "prompt": "find x"}) is None
    assert routed({"subagent_type": "lean-build", "prompt": "fix x"}) is None
    assert run({"command": "ls"}, tool="Bash") is None
    assert routed({"subagent_type": "chore", "prompt": "fix x"}, LEANAGENTS_OFF="1") is None
    u = run({"subagent_type": "chore", "prompt": "fix x", "run_in_background": True, "description": "d"})["updatedInput"]
    assert u["run_in_background"] is True and u["description"] == "d" and u["prompt"] == "fix x"
    r = subprocess.run([sys.executable, os.path.join(ROOT, "leanagents.py"), "hook"], input="x",
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == ""


def test_shipped_agents_are_small_and_measure_uses_chars_over_four(tmp_path, capsys):
    rows = {name: (chars, tokens) for name, chars, tokens in leanagents.measure([os.path.join(ROOT, "agents")])}
    assert set(rows) == {"lean-build", "lean-search"}
    for name, (chars, tokens) in rows.items():
        assert 0 < tokens <= 100 and tokens == (chars + 3) // 4, name
        text = open(os.path.join(ROOT, "agents", name + ".md"), encoding="utf-8").read()
        assert f"name: {name}\n" in text
    f = tmp_path / "x.md"
    f.write_text("---\nname: x\n---\n" + "a" * 400 + "\n")
    assert leanagents.measure([str(f)]) == [("x", 400, 100)]
    assert leanagents.main(["measure", str(f)]) == 0
    assert "x: 400 chars, about 100 tokens" in capsys.readouterr().out
