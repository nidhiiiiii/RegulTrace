import json
import os
import re
from collections import defaultdict

from dotenv import load_dotenv
from falkordb import FalkorDB

load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
GRAPH = "paynova"

SUBGRAPH = """
MATCH chain = (c:Clause {id: $clause})-[:SUPERSEDES*0..]->(:Clause)-[:MAPS_TO]->(p:Policy)
OPTIONAL MATCH run = (p)-[:ENFORCED_BY]->(:Control)-[:RUNS_ON]->(:System)
OPTIONAL MATCH dep = (p)-[:ENFORCED_BY]->(:Control)-[:RUNS_ON]->(:System)-[:DEPENDS_ON]->(:System)
OPTIONAL MATCH own = (p)-[:ENFORCED_BY*0..1]->()-[:OWNED_BY]->(:Owner)
WITH collect(chain) + collect(run) + collect(dep) + collect(own) AS paths
UNWIND paths AS path
UNWIND relationships(path) AS r
RETURN DISTINCT startNode(r).id, type(r), endNode(r).id
"""

AMENDS = """
MATCH chain = (c:Clause {id: $clause})-[:SUPERSEDES*1..]->(:Clause)
UNWIND relationships(chain) AS r
RETURN DISTINCT startNode(r).id, type(r), endNode(r).id
"""

OWNERS = """
MATCH path = (c:Clause {id: $clause})-[:SUPERSEDES*0..]->(:Clause)-[:MAPS_TO]->(:Policy)
             -[:ENFORCED_BY*0..1]->()-[:OWNED_BY]->(o:Owner)
RETURN o.id, o.name, [n IN nodes(path) | n.name]
"""

KEYWORD = """
MATCH (c:Clause {id: $clause}), (n)
WHERE NOT n:Clause AND any(k IN n.keywords WHERE k IN c.keywords)
RETURN n.id
"""

NODES = """
MATCH (n) WHERE n.id IN $ids
RETURN n.id, labels(n)[0], CASE WHEN n:Section THEN n.number + '. ' + n.title ELSE coalesce(n.name, n.title) END
"""

SECTIONS = """
MATCH (p:Policy)-[:HAS_SECTION]->(s:Section)
OPTIONAL MATCH (s)-[:IMPLEMENTED_BY]->(c:Control)
OPTIONAL MATCH (c)-[:OWNED_BY]->(o:Owner)
WITH p, s, collect(CASE WHEN c IS NULL THEN NULL ELSE {id: c.id, name: c.name, owner: o.name} END) AS controls
RETURN s.id, p.id, p.name, s.number, s.title, s.text, controls ORDER BY s.id
"""

BLAST = """
MATCH change = (c:Circular {id: $id})-[:PROPOSES]->(:Change)-[:EDITS]->(s:Section)<-[:HAS_SECTION]-(p:Policy)
OPTIONAL MATCH run = (s)-[:IMPLEMENTED_BY]->(:Control)-[:RUNS_ON]->(:System)
OPTIONAL MATCH dep = (s)-[:IMPLEMENTED_BY]->(:Control)-[:RUNS_ON]->(:System)-[:DEPENDS_ON]->(:System)
OPTIONAL MATCH own = (s)-[:IMPLEMENTED_BY]->(:Control)-[:OWNED_BY]->(:Owner)
OPTIONAL MATCH approver = (p)-[:OWNED_BY]->(:Owner)
WITH collect(change) + collect(run) + collect(dep) + collect(own) + collect(approver) AS paths
UNWIND paths AS path
UNWIND relationships(path) AS r
RETURN DISTINCT startNode(r).id, type(r), endNode(r).id
"""

CHANGES = """
MATCH (:Circular {id: $id})-[:PROPOSES]->(ch:Change)-[:EDITS]->(s:Section)<-[:HAS_SECTION]-(p:Policy)
RETURN ch.id, ch.current, ch.proposed, ch.reason, ch.status, s.id, p.name, p.version, s.number, s.title ORDER BY ch.id
"""

TASKS = """
MATCH (t:Task)-[:ASSIGNED_TO]->(o:Owner)
MATCH (t)-[:FOR]->(ch:Change)<-[:PROPOSES]-(c:Circular)
MATCH (ch)-[:EDITS]->(s:Section)<-[:HAS_SECTION]-(p:Policy)
WHERE ($id IS NULL OR c.id = $id) AND ($owner IS NULL OR o.id = $owner)
RETURN properties(t), o.id, o.name, c.id, c.title, p.name, s.number, s.title, ch.current, ch.proposed, ch.reason
ORDER BY c.date DESC, t.id
"""

CLAUSES = """
MATCH (c:Clause)
OPTIONAL MATCH (r:Regulation)-[:HAS_CLAUSE]->(c)
OPTIONAL MATCH (c)-[:SUPERSEDES]->(old:Clause)
OPTIONAL MATCH (c)-[m:MAPS_TO]->(:Policy)
RETURN c.id, c.name, r.name, old.id, count(m) ORDER BY c.id
"""

SUGGEST = """
MATCH (c:Clause {id: $clause}), (p:Policy)
WHERE any(k IN p.keywords WHERE k IN c.keywords)
RETURN p.id, p.name
"""

CONFIRM = """
MATCH (c:Clause {id: $clause}), (p:Policy {id: $policy})
MERGE (c)-[m:MAPS_TO]->(p)
SET m.confirmed_by = $user, m.confirmed_at = timestamp()
RETURN count(m)
"""


COMPANY_NODES = """
MATCH (n) WHERE n:Policy OR n:Section OR n:Control OR n:System OR n:Owner
OPTIONAL MATCH (n)-[:OWNED_BY]->(own:Owner)
OPTIONAL MATCH (doc:Policy)-[:HAS_SECTION]->(n)
OPTIONAL MATCH (doc)-[:OWNED_BY]->(approver:Owner)
OPTIONAL MATCH (ctl:Control)-[:RUNS_ON]->(n)
OPTIONAL MATCH (ctl)-[:OWNED_BY]->(operator:Owner)
RETURN n.id, labels(n)[0], coalesce(n.name, n.title), n.number, n.text, n.version, doc.name,
       collect(DISTINCT own.name) + collect(DISTINCT approver.name) + collect(DISTINCT operator.name)
"""

COMPANY_EDGES = """
MATCH (a)-[r:HAS_SECTION|IMPLEMENTED_BY|RUNS_ON|DEPENDS_ON|OWNED_BY]->(b)
WHERE a:Policy OR a:Section OR a:Control OR a:System
RETURN a.id, type(r), b.id
"""


RETRIEVE = """
UNWIND $terms AS term
CALL db.idx.fulltext.queryNodes('Section', term) YIELD node
WITH node, count(DISTINCT term) AS matched
WHERE matched >= 2
WITH node, matched ORDER BY matched DESC LIMIT 4
OPTIONAL MATCH (node)-[:IMPLEMENTED_BY]->(:Control)<-[:IMPLEMENTED_BY]-(related:Section)
RETURN collect(DISTINCT node.id), collect(DISTINCT related.id)
"""

GENERIC = {"personal", "data", "within", "days", "hours", "customer", "customers", "regulated", "entities", "entity",
           "shall", "including", "rules", "earlier", "partial", "modification", "receiving", "held", "reserve",
           "bank", "india", "directions", "circular", "notification", "dated", "with", "from", "that", "this",
           "their", "which", "under", "will", "must", "every", "have", "been", "such", "these", "those", "into"}


def search_terms(text):
    words = [w for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in GENERIC]
    return list(dict.fromkeys(words))[:25]


def retrieve(g, text):
    terms = search_terms(text)
    if not terms:
        return {"terms": [], "seeds": [], "related": [], "ms": 0}
    found, ms = timed(g, RETRIEVE, terms=terms)
    seeds, related = found[0] if found else ([], [])
    return {"terms": terms, "seeds": seeds, "related": [r for r in related if r not in seeds], "ms": ms}


RIPPLE = """
MATCH (:Circular {id: $id})-[:PROPOSES]->(:Change)-[:EDITS]->(s:Section)-[:IMPLEMENTED_BY]->(ctl:Control)
      <-[:IMPLEMENTED_BY]-(other:Section)<-[:HAS_SECTION]-(p:Policy)
OPTIONAL MATCH (ctl)-[:OWNED_BY]->(o:Owner)
OPTIONAL MATCH (p)-[:OWNED_BY]->(po:Owner)
RETURN other.id, p.name, other.number, other.title, other.text, collect(DISTINCT ctl.name),
       collect(DISTINCT s.title), collect(DISTINCT o.name) + collect(DISTINCT po.name)
"""


def timed(g, query, **params):
    result = g.query(query, params)
    return result.result_set, result.run_time_ms


def client():
    return FalkorDB(
        host=os.getenv("FALKORDB_HOST") or "localhost",
        port=int(os.getenv("FALKORDB_PORT") or "6379"),
        username=os.getenv("FALKORDB_USERNAME") or None,
        password=os.getenv("FALKORDB_PASSWORD") or None,
        ssl=os.getenv("FALKORDB_SSL", "").lower() == "true",
    )


def connect():
    return client().select_graph(GRAPH)


def rows(g, query, **params):
    return g.query(query, params).result_set


def clauses(g):
    return [{"id": i, "name": n, "regulation": r, "amends": a, "mapped": m}
            for i, n, r, a, m in rows(g, CLAUSES)]


def node_details(g, ids):
    return {i: {"id": i, "type": t, "name": n} for i, t, n in rows(g, NODES, ids=list(ids))}


def owners(g, clause):
    grouped = defaultdict(lambda: {"paths": []})
    for oid, name, path in rows(g, OWNERS, clause=clause):
        grouped[oid].update(id=oid, name=name)
        if path not in grouped[oid]["paths"]:
            grouped[oid]["paths"].append(path)
    return list(grouped.values())


def impact(g, clause):
    edges = rows(g, SUBGRAPH, clause=clause) + rows(g, AMENDS, clause=clause)
    edges = [list(e) for e in dict.fromkeys(map(tuple, edges))]
    ids = {clause} | {e[0] for e in edges} | {e[2] for e in edges}
    nodes = node_details(g, ids)
    found = sorted(i for i, n in nodes.items() if n["type"] != "Clause")
    keyword = sorted(r[0] for r in rows(g, KEYWORD, clause=clause))
    result = {
        "clause": nodes.get(clause),
        "nodes": list(nodes.values()),
        "edges": [{"src": s, "rel": r, "dst": d} for s, r, d in edges],
        "found": found,
        "keyword": keyword,
        "missed": sorted(set(found) - set(keyword)),
        "owners": owners(g, clause),
        "suggest": [],
    }
    if not any(nodes[i]["type"] == "Policy" for i in found):
        result["suggest"] = [{"id": i, "name": n} for i, n in rows(g, SUGGEST, clause=clause)]
    return result


def vocabulary(g):
    return {k for (ks,) in rows(g, "MATCH (n) RETURN n.keywords") for k in (ks or [])}


def stem(word):
    for suffix in ("ation", "ition", "ure", "ion", "ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def keywords_in(g, text):
    stems = {stem(w) for w in re.findall(r"[a-z]+", text.lower())}
    return sorted(k for k in vocabulary(g) if stem(k) in stems)


def register_clause(g, name, text, regulation=None, amends=None):
    keywords = keywords_in(g, text)
    count = rows(g, "MATCH (c:Clause) WHERE c.id STARTS WITH 'CL_NEW_' RETURN count(c)")[0][0]
    cid = f"CL_NEW_{count + 1}"
    g.query("CREATE (:Clause {id: $id, name: $name, text: $text, keywords: $kw})",
            {"id": cid, "name": name, "text": text, "kw": keywords})
    if regulation:
        g.query("MATCH (r:Regulation {id: $r}), (c:Clause {id: $c}) CREATE (r)-[:HAS_CLAUSE]->(c)",
                {"r": regulation, "c": cid})
    if amends:
        g.query("MATCH (n:Clause {id: $n}), (o:Clause {id: $o}) CREATE (n)-[:SUPERSEDES]->(o)",
                {"n": cid, "o": amends})
    return cid


def confirm_mapping(g, clause, policy, user):
    return rows(g, CONFIRM, clause=clause, policy=policy, user=user)[0][0] > 0


def add_circular(g, item):
    if rows(g, "MATCH (c:Circular {id: $id}) RETURN count(c)", id=item["id"])[0][0]:
        return False
    g.query("CREATE (:Circular {id: $id, source: $source, title: $title, url: $url, date: $date, "
            "text: $text, status: 'new'})", item)
    return True


def add_pasted(g, title, text):
    count = rows(g, "MATCH (c:Circular) WHERE c.id STARTS WITH 'PASTED-' RETURN count(c)")[0][0]
    item = {"id": f"PASTED-{count + 1}", "source": "Pasted", "title": title, "url": "",
            "date": rows(g, "RETURN toString(date())")[0][0], "text": text}
    add_circular(g, item)
    return item


def set_triage(g, cid, relevant, reason, by):
    g.query("MATCH (c:Circular {id: $id}) WHERE c.status <> 'analyzed' "
            "SET c.relevant = $relevant, c.reason = $reason, c.triaged_by = $by, c.status = 'triaged'",
            {"id": cid, "relevant": relevant, "reason": reason, "by": by})


def sections(g):
    return [{"id": sid, "policy_id": pid, "policy": pname, "number": num, "title": title, "text": text,
             "controls": [c for c in controls if c]}
            for sid, pid, pname, num, title, text, controls in rows(g, SECTIONS)]


def save_analysis(g, cid, result, mode, note, retrieval):
    g.query("MATCH (:Circular {id: $id})-[:PROPOSES]->(ch:Change) OPTIONAL MATCH (t:Task)-[:FOR]->(ch) "
            "DETACH DELETE t, ch", {"id": cid})
    g.query("MATCH (c:Circular {id: $id}) SET c.summary = $summary, c.relevant = $relevant, c.status = 'analyzed', "
            "c.mode = $mode, c.note = $note, c.retrieval = $retrieval",
            {"id": cid, "summary": result["summary"], "relevant": result["relevant"], "mode": mode, "note": note,
             "retrieval": json.dumps(retrieval)})
    for i, change in enumerate(result["changes"], 1):
        chid = f"{cid}-C{i}"
        g.query("MATCH (c:Circular {id: $cid}), (s:Section {id: $sid}) "
                "CREATE (c)-[:PROPOSES]->(:Change {id: $id, current: $current, proposed: $proposed, "
                "reason: $reason, status: 'proposed'})-[:EDITS]->(s)",
                {"cid": cid, "sid": change["section_id"], "id": chid, "current": change["current"],
                 "proposed": change["proposed"], "reason": change["reason"]})
        g.query("MATCH (ch:Change {id: $ch})-[:EDITS]->(s:Section)<-[:HAS_SECTION]-(p:Policy)-[:OWNED_BY]->(o:Owner) "
                "CREATE (t:Task {id: $tid, kind: 'approve', status: 'open', "
                "text: 'Review and approve the new wording for ' + p.name + ', section ' + s.number + '.'}) "
                "CREATE (t)-[:ASSIGNED_TO]->(o) CREATE (t)-[:FOR]->(ch)",
                {"ch": chid, "tid": f"{chid}-T0"})
        for j, action in enumerate(change["actions"], 1):
            g.query("MATCH (ch:Change {id: $ch}), (ctl:Control {id: $ctl})-[:OWNED_BY]->(o:Owner) "
                    "CREATE (t:Task {id: $tid, kind: 'implement', status: 'open', text: $text, control: ctl.name}) "
                    "CREATE (t)-[:ASSIGNED_TO]->(o) CREATE (t)-[:FOR]->(ch) CREATE (t)-[:ON]->(ctl)",
                    {"ch": chid, "ctl": action["control_id"], "tid": f"{chid}-T{j}", "text": action["action"]})


def tasks(g, cid=None, owner=None):
    keys = ["owner_id", "owner", "regulation_id", "regulation", "policy", "number", "section", "current", "proposed", "reason"]
    return [{**props, **dict(zip(keys, rest))} for props, *rest in rows(g, TASKS, id=cid, owner=owner)]


def blast_radius(g, cid):
    raw, ms = timed(g, BLAST, id=cid)
    change_from = {d: s for s, r, d in raw if r == "PROPOSES"}
    edges = [(s, r, d) for s, r, d in raw if r not in ("PROPOSES", "EDITS")]
    edges += [(change_from[s], "CHANGES", d) for s, r, d in raw if r == "EDITS" and s in change_from]
    edges = list(dict.fromkeys(edges))
    ids = {cid} | {e[0] for e in edges} | {e[2] for e in edges}
    return list(node_details(g, ids).values()), [{"src": s, "rel": r, "dst": d} for s, r, d in edges], ms


def regulation_view(g, cid):
    circ = circular(g, cid)
    if not circ:
        return None
    nodes, edges, blast_ms = blast_radius(g, cid)
    retrieval = json.loads(circ["retrieval"]) if circ.get("retrieval") else None
    titles = {s["id"]: f'{s["policy"]} §{s["number"]} {s["title"]}' for s in sections(g)} if retrieval else {}
    if retrieval:
        retrieval["seed_titles"] = [titles.get(i, i) for i in retrieval["seeds"]]
        retrieval["related_titles"] = [titles.get(i, i) for i in retrieval["related"]]
    queries = []
    if retrieval:
        queries.append({"name": "GraphRAG retrieval: full-text search per term, then expand through shared processes",
                        "cypher": RETRIEVE.strip(), "ms": retrieval["ms"]})
    queries.append({"name": "Blast radius: regulation to sections, processes, systems and people",
                    "cypher": BLAST.strip(), "ms": blast_ms})
    changes = [dict(zip(["id", "current", "proposed", "reason", "status", "section_id", "policy", "version",
                         "number", "section"], r)) for r in rows(g, CHANGES, id=cid)]
    changed = {c["section_id"] for c in changes}
    ripple, ripple_ms = timed(g, RIPPLE, id=cid)
    suggestions = [{"section_id": sid, "policy": pname, "number": num, "section": title, "text": text, "via": via,
                    "because": because, "owners": [o for o in dict.fromkeys(owners) if o]}
                   for sid, pname, num, title, text, via, because, owners in ripple if sid not in changed]
    if changes:
        queries.append({"name": "Proactive review: other sections that rely on the processes that are changing",
                        "cypher": RIPPLE.strip(), "ms": ripple_ms})
    people = {}
    for t in tasks(g, cid=cid):
        people.setdefault(t["owner_id"], {"id": t["owner_id"], "name": t["owner"], "tasks": []})["tasks"].append(t)
    counts = {}
    for n in nodes:
        counts[n["type"]] = counts.get(n["type"], 0) + 1
    return {"regulation": {k: v for k, v in circ.items() if k not in ("text", "retrieval")}, "text": circ.get("text", ""),
            "nodes": nodes, "edges": edges, "changes": changes, "people": list(people.values()), "counts": counts,
            "retrieval": retrieval, "queries": queries, "suggestions": suggestions}


def company_graph(g, cid=None):
    node_rows, node_ms = timed(g, COMPANY_NODES)
    edge_rows, edge_ms = timed(g, COMPANY_EDGES)
    nodes = []
    for nid, kind, name, number, text, version, policy, responsible in node_rows:
        nodes.append({"id": nid, "type": kind, "name": name, "number": number, "text": text, "version": version,
                      "policy": policy, "responsible": [r for r in dict.fromkeys(responsible) if r and r != name]})
    affected, blast_ms = [], 0
    if cid:
        raw, blast_ms = timed(g, BLAST, id=cid)
        affected = sorted({x for s, _, d in raw for x in (s, d)} - {cid})
    return {
        "nodes": nodes,
        "edges": [{"src": s, "rel": r, "dst": d} for s, r, d in edge_rows],
        "affected": affected,
        "queries": [
            {"name": "Company documents and who is responsible", "cypher": COMPANY_NODES.strip(), "ms": node_ms},
            {"name": "How they connect", "cypher": COMPANY_EDGES.strip(), "ms": edge_ms},
        ] + ([{"name": "What this regulation touches", "cypher": BLAST.strip(), "ms": blast_ms}] if cid else []),
    }


def people(g):
    return [{"id": i, "name": n, "open": c} for i, n, c in rows(
        g, "MATCH (o:Owner) OPTIONAL MATCH (t:Task {status: 'open'})-[:ASSIGNED_TO]->(o) "
           "RETURN o.id, o.name, count(t) ORDER BY o.name")]


def update_task(g, tid, status, note):
    found = rows(g, "MATCH (t:Task {id: $id}) SET t.status = $status, t.note = $note RETURN count(t)",
                 id=tid, status=status, note=note)
    return found[0][0] > 0


def circulars(g):
    fields = ["id", "source", "title", "url", "date", "relevant", "reason", "status", "summary", "triaged_by"]
    query = "MATCH (c:Circular) RETURN " + ", ".join(f"c.{f}" for f in fields) + " ORDER BY c.date DESC, c.id DESC"
    return [dict(zip(fields, r)) for r in rows(g, query)]


def circular(g, cid):
    found = rows(g, "MATCH (c:Circular {id: $id}) RETURN properties(c)", id=cid)
    return found[0][0] if found else None


def set_meta(g, key, value):
    g.query("MERGE (m:Meta {id: 'monitor'}) SET m += $props", {"props": {key: value}})


def get_meta(g, key):
    found = rows(g, "MATCH (m:Meta {id: 'monitor'}) RETURN properties(m)")
    return found[0][0].get(key) if found else None
