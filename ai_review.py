#!/usr/bin/env python3
"""AI code review + risk gate (+ release notes) for CI.
Usage: ai_review.py review | ai_review.py notes"""
import json, os, re, subprocess, sys
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
from common.llm import ask, ask_json

MAX_DIFF = 30000
SYSTEM = """You are a senior reviewer. Review the git diff. Respond ONLY with JSON:
{"risk":"LOW|MEDIUM|HIGH","summary":"...","issues":["..."],"suggestions":["..."]}
HIGH = leaked secrets, auth/security holes, data loss, breaking prod. Be specific, no filler."""

RULES = [
    (r"AKIA[0-9A-Z]{16}", "HIGH", "Possible AWS access key"),
    (r"(?i)(password|secret|api[_-]?key)\s*=\s*['\"][^'\"]+['\"]", "HIGH", "Hard-coded secret"),
    (r"\beval\(|\bexec\(", "MEDIUM", "eval/exec usage"),
    (r"shell\s*=\s*True", "MEDIUM", "subprocess shell=True"),
    (r"verify\s*=\s*False", "MEDIUM", "TLS verification disabled"),
    (r"0\.0\.0\.0/0", "MEDIUM", "Open to the whole internet"),
]


def get_diff():
    base = os.getenv("BASE_REF", "main")
    out = subprocess.run(["git", "diff", f"origin/{base}...HEAD"], capture_output=True, text=True).stdout
    return out[:MAX_DIFF]


def heuristic(diff):
    rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}
    added = [l[1:] for l in diff.splitlines() if l.startswith("+") and not l.startswith("+++")]
    issues, risk = [], "LOW"
    for line in added:
        for pat, level, msg in RULES:
            if re.search(pat, line):
                issues.append(f"{msg}: `{line.strip()[:80]}`")
                if rank[level] > rank[risk]:
                    risk = level
    return {"risk": risk, "summary": "Rule-based review (no LLM key set).", "issues": issues, "suggestions": []}


def post_comment(body):
    repo, pr, token = os.getenv("GITHUB_REPOSITORY"), os.getenv("PR_NUMBER"), os.getenv("GITHUB_TOKEN")
    if not (repo and pr and token):
        return
    requests.post(
        f"https://api.github.com/repos/{repo}/issues/{pr}/comments",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
        json={"body": body}, timeout=15,
    )


def review():
    diff = get_diff()
    if not diff.strip():
        print("No diff to review."); return 0
    result = ask_json(SYSTEM, diff) or heuristic(diff)
    body = (f"### 🤖 AI Review — risk: **{result['risk']}**\n\n{result['summary']}\n\n"
            + "**Issues**\n" + "\n".join(f"- {i}" for i in result["issues"] or ["none found"])
            + "\n\n**Suggestions**\n" + "\n".join(f"- {s}" for s in result["suggestions"] or ["none"]))
    print(body)
    post_comment(body)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"risk={result['risk']}\n")
    if result["risk"] == "HIGH" and os.getenv("FAIL_ON_HIGH", "true") == "true":
        print("HIGH risk -> failing the check. A human can override by re-running with FAIL_ON_HIGH=false.")
        return 1
    return 0


def notes():
    log = subprocess.run(["git", "log", "-n", "30", "--pretty=- %s (%an)"], capture_output=True, text=True).stdout
    text = ask("Write concise release notes (Features / Fixes / Other) from these commits.", log) \
        or "## Changes\n" + log
    print(text)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(notes() if len(sys.argv) > 1 and sys.argv[1] == "notes" else review())
