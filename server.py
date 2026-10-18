import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import analyze
import graph
import load_graph
import monitor


@asynccontextmanager
async def lifespan(_):
    monitor.watch()
    yield


app = FastAPI(title="RegulTrace", lifespan=lifespan)
STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
INDEX = os.path.join(STATIC, "index.html")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


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
    return FileResponse(os.path.join(STATIC, "landing.html"))


@app.get("/app")
def index():
    return FileResponse(INDEX)


@app.get("/api/status")
def status():
    return {"llm": analyze.has_key() and not analyze.last_error["text"], "key": analyze.has_key(),
            "model": analyze.MODEL, "problem": analyze.last_error["text"]}


@app.get("/api/regulations")
def regulations():
    g = graph.connect()
    return {"last_checked": graph.get_meta(g, "last_checked"), "items": graph.circulars(g)}


@app.post("/api/monitor/check")
def check_now():
    try:
        return monitor.check()
    except OSError as exc:
        raise HTTPException(502, f"Could not reach the RBI feed: {exc}")


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
    load_graph.load(os.getenv("FALKORDB_HOST", "localhost"), int(os.getenv("FALKORDB_PORT", "6379")))
    return {"ok": True}
