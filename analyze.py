import json
import os
import re

from dotenv import load_dotenv
from openai import BadRequestError, OpenAI, OpenAIError

import graph

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"


def provider():
    if os.getenv("GEMINI_API_KEY"):
        return {"name": "Gemini", "key": os.getenv("GEMINI_API_KEY"), "base_url": GEMINI_URL,
                "model": os.getenv("GEMINI_MODEL") or "gemini-3.1-flash-lite"}
    if os.getenv("OPENAI_API_KEY"):
        return {"name": "OpenAI", "key": os.getenv("OPENAI_API_KEY"), "base_url": os.getenv("OPENAI_BASE_URL") or None,
                "model": os.getenv("OPENAI_MODEL") or "gpt-5.5"}
    return None


MODEL = (provider() or {}).get("model", "gpt-5.5")

TRIAGE_PROMPT = """You screen regulator publications for PayNova, an Indian fintech that runs UPI payments, offers digital loans through NBFC partners, and holds customer personal data.
For each item decide whether it could require PayNova to change a policy, process or system. Treasury and bond auctions, bank capital adequacy, forex dealing, money market operations and statistics never do.
Reply as JSON: {"items": [{"id": "...", "relevant": true or false, "reason": "one short plain-English sentence"}]}"""

ANALYZE_PROMPT = """You are PayNova's compliance analyst. You get a new regulation and PayNova's current policy sections, each with the controls that implement it and who owns them.

Find every section the regulation forces PayNova to change. For each one:
- current: copy the exact sentence from the section that no longer complies
- proposed: the replacement sentence
- reason: one sentence citing what the regulation now requires
- actions: for each control on that section that must change, one concrete instruction for its owner

Only use section ids and control ids from the input. If nothing has to change, return an empty changes list.
Reply as JSON: {"relevant": true or false, "summary": "two plain-English sentences on what the regulation changes for PayNova", "changes": [{"section_id": "...", "current": "...", "proposed": "...", "reason": "...", "actions": [{"control_id": "...", "action": "..."}]}]}"""

DURATION = re.compile(r"within (\d+) (days?|hours?)", re.I)
last_error = {"text": None}


def has_key():
    return provider() is not None


def reason(exc):
    text, name = str(exc), (provider() or {}).get("name", "The AI provider")
    if "insufficient_quota" in text or "credit" in text:
        message = f"the {name} account has no credits left"
    elif "RESOURCE_EXHAUSTED" in text or "quota" in text.lower():
        message = f"the {name} free quota is used up for now"
    elif isinstance(exc, json.JSONDecodeError):
        message = f"{name} returned an unreadable answer"
    else:
        message = f"{name} is unavailable ({type(exc).__name__})"
    last_error["text"] = message
    return message


def ask(system, payload):
    p = provider()
    client = OpenAI(api_key=p["key"], base_url=p["base_url"], max_retries=1)
    request = {"model": p["model"], "messages": [{"role": "system", "content": system},
                                                 {"role": "user", "content": json.dumps(payload)}]}
    try:
        response = client.chat.completions.create(**request, response_format={"type": "json_object"})
    except BadRequestError:
        response = client.chat.completions.create(**request)
    text = response.choices[0].message.content or ""
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1] if start >= 0 else text)


def triage(items):
    payload = [{"id": i["id"], "title": i["title"], "text": i["text"][:700]} for i in items]
    answer = ask(TRIAGE_PROMPT, {"items": payload})
    known = {i["id"] for i in items}
    return {a["id"]: (bool(a["relevant"]), a["reason"]) for a in answer.get("items", []) if a.get("id") in known}


COMMON = {"within", "day", "hour", "data", "shall", "with", "from", "that", "this", "their", "which", "under",
           "will", "must", "every", "paynova", "customer"}


def stems(text):
    return {graph.stem(w).rstrip("e") for w in re.findall(r"[a-z]{4,}", text.lower())} - COMMON


def limit_to_replace(sentence, new_limit, words):
    candidates = [m for m in DURATION.finditer(sentence) if m[2][0] == new_limit[2][0] and m[1] != new_limit[1]]
    for m in candidates:
        before = re.findall(r"[a-z]+", sentence[:m.start()].lower())
        if before and graph.stem(before[-1]).rstrip("e") in words:
            return m
    return candidates[0] if candidates else None


def offline(circular, sections):
    text = f'{circular["title"]} {circular["text"]}'
    words, new_limit = stems(text), DURATION.search(text)
    changes = []
    for s in sections:
        for sentence in re.split(r"(?<=\.)\s+", s["text"]):
            old_limit = limit_to_replace(sentence, new_limit, words) if new_limit else None
            if not old_limit or len(words & stems(sentence)) < 2:
                continue
            proposed = sentence[:old_limit.start()] + new_limit[0] + sentence[old_limit.end():]
            changes.append({
                "section_id": s["id"],
                "current": sentence,
                "proposed": proposed,
                "reason": f"The new regulation requires this {new_limit[0]}.",
                "actions": [{"control_id": c["id"], "action": f'Check {c["name"]} against the new rule and update it so that: {proposed}'}
                            for c in s["controls"]],
            })
            break
    summary = re.split(r"(?<=\.)\s+", circular["text"].strip())[0][:300]
    return {"relevant": bool(changes), "summary": summary, "changes": changes}


def validate(result, sections):
    by_id = {s["id"]: s for s in sections}
    changes = []
    for change in result.get("changes", []):
        section = by_id.get(change.get("section_id"))
        if not section:
            continue
        allowed = {c["id"] for c in section["controls"]}
        change["actions"] = [a for a in change.get("actions", []) if a.get("control_id") in allowed]
        changes.append(change)
    return {"relevant": bool(result.get("relevant")) or bool(changes), "summary": result.get("summary", ""), "changes": changes}


def analyze(cid):
    g = graph.connect()
    circular = graph.circular(g, cid)
    if not circular:
        raise KeyError(cid)
    sections = graph.sections(g)
    retrieval = graph.retrieve(g, f'{circular["title"]} {circular["text"]}')
    picked = set(retrieval["seeds"]) | set(retrieval["related"])
    context = [s for s in sections if s["id"] in picked] or sections
    retrieval.update(context=len(context), total=len(sections), fallback=not picked)
    mode, note = "gpt", None
    if has_key():
        try:
            result = ask(ANALYZE_PROMPT, {"regulation": {"title": circular["title"], "text": circular["text"][:6000]},
                                          "sections": context})
            last_error["text"] = None
        except (OpenAIError, json.JSONDecodeError) as exc:
            mode, note, result = "offline", reason(exc), offline(circular, context)
    else:
        mode, note, result = "offline", "OPENAI_API_KEY is not set", offline(circular, context)
    graph.save_analysis(g, cid, validate(result, sections), mode, note, retrieval)
    return graph.regulation_view(g, cid)
