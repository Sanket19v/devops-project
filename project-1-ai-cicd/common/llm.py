"""Tiny LLM helper. Without ANTHROPIC_API_KEY every caller falls back to rules,
so you can run the whole lab for free and add the key later."""
import json, os, re


def ask(system: str, prompt: str, max_tokens: int = 1200):
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=key)
        r = client.messages.create(
            model=os.getenv("LLM_MODEL", "claude-sonnet-5-5"),
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in r.content if b.type == "text")
    except Exception as e:  # never let the AI step break the pipeline
        print(f"[llm] call failed: {e}")
        return None


def ask_json(system: str, prompt: str, max_tokens: int = 1200):
    text = ask(system, prompt, max_tokens)
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.S)
    try:
        return json.loads(m.group(0)) if m else None
    except json.JSONDecodeError:
        return None
