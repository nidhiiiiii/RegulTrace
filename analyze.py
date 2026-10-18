import json
import os
import re
import time

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
last_error = {"text": None, "kind": None, "retry_after": None, "at": 0}


def has_key():
    return provider() is not None


def limit_info(exc):
    text = str(exc)
    if "insufficient_quota" in text:
        return {"kind": "credits", "retry_after": None}
    if not ("429" in text or "RESOURCE_EXHAUSTED" in text or "quota" in text.lower()):
        return None
    wait = (re.search(r"retry in (\d+(?:\.\d+)?)\s*s", text, re.I)
            or re.search(r"retryDelay['\"]?\s*:\s*['\"](\d+(?:\.\d+)?)s", text))
    return {"kind": "day" if "PerDay" in text else "minute", "retry_after": int(float(wait[1])) + 1 if wait else None}


def wait_text(seconds):
    if not seconds:
        return None
    hours, minutes = divmod(int(seconds) // 60, 60)
    if hours:
        return f"about {hours} h {minutes} min" if minutes else f"about {hours} h"
    return f"about {max(1, minutes)} min" if seconds >= 90 else f"about {int(seconds)} seconds"


def reason(exc):
    name = (provider() or {}).get("name", "The AI provider")
    limit = limit_info(exc)
    if limit and limit["kind"] == "credits":
        message = f"the {name} account has no credits left"
    elif limit and limit["kind"] == "day":
        message = f"{name}'s free daily limit is used up; it resets in {wait_text(limit['retry_after'])}" if limit["retry_after"] else f"{name}'s free daily limit is used up; it resets tomorrow"
    elif limit:
        message = f"{name}'s free per-minute limit was reached; it's paused for {wait_text(limit['retry_after'] or 60)}"
    elif isinstance(exc, json.JSONDecodeError):
        message = f"{name} returned an unreadable answer"
    else:
        message = f"{name} is unavailable ({type(exc).__name__})"
    last_error.update(text=message, kind=limit["kind"] if limit else "error",
                      retry_after=limit["retry_after"] if limit else None, at=time.time())
    return message


def clear_error():
    last_error.update(text=None, kind=None, retry_after=None, at=0)


def status():
    if not has_key():
        return {"state": "off", "model": None, "problem": None, "kind": None, "retry_in": None}
    retry_in = None
    if last_error["kind"] in ("minute", "day") and (last_error["retry_after"] or last_error["kind"] == "minute"):
        retry_in = int(last_error["at"] + (last_error["retry_after"] or 60) - time.time())
        if retry_in <= 0:
            clear_error()
            retry_in = None
    kind = last_error["kind"]
    state = "ok" if not kind else ("limit" if kind in ("minute", "day", "credits") else "error")
    return {"state": state, "model": MODEL, "problem": last_error["text"], "kind": kind, "retry_in": retry_in}


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
    mode, note, issue, retry_after = "gpt", None, None, None
    if has_key():
        try:
            result = ask(ANALYZE_PROMPT, {"regulation": {"title": circular["title"], "text": circular["text"][:6000]},
                                          "sections": context})
            clear_error()
        except (OpenAIError, json.JSONDecodeError) as exc:
            mode, note, result = "offline", reason(exc), offline(circular, context)
            issue, retry_after = last_error["kind"], last_error["retry_after"]
    else:
        mode, note, issue, result = "offline", "no AI key is set (add GEMINI_API_KEY)", "off", offline(circular, context)
    graph.save_analysis(g, cid, validate(result, sections), mode, note, retrieval)
    g.query("MATCH (c:Circular {id: $id}) SET c.ai_issue = $issue, c.retry_after = $retry, c.model = $model",
            {"id": cid, "issue": issue, "retry": retry_after, "model": MODEL if mode == "gpt" else None})
    return graph.regulation_view(g, cid)
