import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import analyze
import graph
import load_graph
import monitor

ON_VERCEL = bool(os.getenv("VERCEL"))


@asynccontextmanager
async def lifespan(_):
    if not ON_VERCEL:
        monitor.watch()
    yield


app = FastAPI(title="RegulTrace", lifespan=lifespan)
ROOT = os.path.dirname(os.path.abspath(__file__))
WEB = os.path.join(ROOT, "web")
INDEX = os.path.join(WEB, "index.html")
if not ON_VERCEL:
    app.mount("/static", StaticFiles(directory=os.path.join(ROOT, "public", "static")), name="static")


class Paste(BaseModel):
    text: str
    title: str = ""


class Mapping(BaseModel):
    clause: str
    policy: str
    user: str = "aarti"


class TaskUpdate(BaseModel):
    status: str
    note: str = ""


@app.get("/")
def landing():
    return FileResponse(os.path.join(WEB, "landing.html"))


@app.get("/app")
def index():
    return FileResponse(INDEX)


@app.get("/api/health")
def health():
    try:
        nodes = graph.rows(graph.connect(), "MATCH (n) RETURN count(n)")[0][0]
    except Exception as exc:
        raise HTTPException(503, {"message": f"FalkorDB is unreachable ({type(exc).__name__})", "kind": "database"})
    return {"ok": True, "graph": graph.GRAPH, "nodes": nodes}


@app.get("/api/status")
def status():
    state = analyze.status()
    return {**state, "llm": state["state"] == "ok", "key": state["state"] != "off"}


class Question(BaseModel):
    question: str


@app.post("/api/ask")
def ask(body: Question):
    try:
        import ask_docs
    except ImportError:
        raise HTTPException(503, "The GraphRAG SDK is not installed on this server.")
    if not ask_docs.ready():
        raise HTTPException(503, "Add GEMINI_API_KEY to enable Ask the docs.")
    if not body.question.strip():
        raise HTTPException(400, "Type a question first.")
    try:
        return ask_docs.ask(body.question.strip())
    except Exception as exc:
        limit = analyze.limit_info(exc)
        if limit:
            analyze.reason(exc)
            if limit["kind"] == "day":
                when = f"for {analyze.wait_text(limit['retry_after'])}" if limit["retry_after"] else "until tomorrow"
                message = f"Gemini's free daily limit is used up, so Ask the docs is paused {when}. Questions answered before still work from saved answers."
            else:
                message = f"Gemini's free per-minute limit was reached. Ask again in {analyze.wait_text(limit['retry_after'] or 60)}; questions answered before still work from saved answers."
            raise HTTPException(429, {"message": message, **limit})
        raise HTTPException(502, {"message": f"Ask the docs couldn't answer right now ({type(exc).__name__}). Please try again.", "kind": "error"})


@app.get("/api/regulations")
def regulations():
    g = graph.connect()
    return {"last_checked": graph.get_meta(g, "last_checked"), "triage_note": graph.get_meta(g, "triage_note"),
            "items": graph.circulars(g)}


@app.post("/api/monitor/check")
def check_now():
    try:
        return monitor.check()
    except OSError as exc:
        raise HTTPException(502, f"Could not reach the RBI feed: {exc}")


@app.get("/api/cron/check")
def cron_check(authorization: str | None = Header(default=None)):
    secret = os.getenv("CRON_SECRET")
    if secret and authorization != f"Bearer {secret}":
        raise HTTPException(401, "Unauthorized")
    return check_now()


@app.post("/api/regulations/paste")
def paste(body: Paste):
    if not body.text.strip():
        raise HTTPException(400, "Paste the regulation text first.")
    title = body.title.strip() or body.text.strip().split("\n")[0][:90]
    item = graph.add_pasted(graph.connect(), title, body.text.strip())
    return analyze.analyze(item["id"])


@app.get("/api/regulations/{cid}")
def regulation(cid: str):
    view = graph.regulation_view(graph.connect(), cid)
    if not view:
        raise HTTPException(404, f"Unknown regulation {cid}")
    return view


@app.post("/api/regulations/{cid}/analyze")
def run_analysis(cid: str):
    try:
        return analyze.analyze(cid)
    except KeyError:
        raise HTTPException(404, f"Unknown regulation {cid}")


@app.get("/api/company-graph")
def company_graph(regulation: str | None = None):
    return graph.company_graph(graph.connect(), regulation)


@app.get("/api/people")
def people():
    return graph.people(graph.connect())


@app.get("/api/inbox/{owner}")
def inbox(owner: str):
    return graph.tasks(graph.connect(), owner=owner)


@app.post("/api/tasks/{tid}")
def update_task(tid: str, body: TaskUpdate):
    if body.status not in ("open", "accepted", "done", "question"):
        raise HTTPException(400, "Unknown status")
    if not graph.update_task(graph.connect(), tid, body.status, body.note):
        raise HTTPException(404, f"Unknown task {tid}")
    return {"ok": True}


@app.get("/api/clauses")
def clauses():
    return graph.clauses(graph.connect())


@app.get("/api/trace/{clause}")
def trace(clause: str):
    result = graph.impact(graph.connect(), clause)
    if not result["clause"]:
        raise HTTPException(404, f"unknown clause {clause}")
    return result


@app.post("/api/confirm")
def confirm(mapping: Mapping):
    g = graph.connect()
    if not graph.confirm_mapping(g, mapping.clause, mapping.policy, mapping.user):
        raise HTTPException(404, "clause or policy not found")
    return graph.impact(g, mapping.clause)


@app.post("/api/reset")
def reset():
    load_graph.load()
    return {"ok": True}
