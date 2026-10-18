import csv
import glob
import os
import re
import sys
from collections import defaultdict

from falkordb import FalkorDB

GRAPH = "paynova"
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def read(name):
    with open(os.path.join(DATA, name), newline="") as f:
        return list(csv.DictReader(f))


def policy_documents():
    versions, sections = {}, []
    for path in sorted(glob.glob(os.path.join(DATA, "policies", "*.md"))):
        pid = os.path.splitext(os.path.basename(path))[0]
        current = None
        with open(path) as f:
            for line in (l.strip() for l in f):
                heading = re.match(r"## (\d+)\. (.+)", line)
                if heading:
                    current = {"id": f"{pid}#{heading[1]}", "policy": pid, "number": heading[1],
                               "title": heading[2], "controls": [], "text": ""}
                    sections.append(current)
                elif line.startswith("version:"):
                    versions[pid] = line.split(":", 1)[1].strip()
                elif current and line.startswith("controls:"):
                    current["controls"] = [c.strip() for c in line.split(":", 1)[1].split(",") if c.strip()]
                elif current and line:
                    current["text"] = f'{current["text"]} {line}'.strip()
    return versions, sections


def load(host="localhost", port=6379):
    db = FalkorDB(host=host, port=port)
    if GRAPH in db.list_graphs():
        db.select_graph(GRAPH).delete()
    g = db.select_graph(GRAPH)

    nodes = read("nodes.csv")
    label_of = {n["id"]: n["type"] for n in nodes}
    by_label = defaultdict(list)
    for n in nodes:
        keywords = [k for k in n["keywords"].split(";") if k]
        by_label[n["type"]].append({"id": n["id"], "name": n["name"], "keywords": keywords})

    for label, rows in by_label.items():
        g.query(f"UNWIND $rows AS r CREATE (:{label} {{id: r.id, name: r.name, keywords: r.keywords}})",
                {"rows": rows})
        g.query(f"CREATE INDEX FOR (n:{label}) ON (n.id)")

    by_shape = defaultdict(list)
    for e in read("edges.csv"):
        by_shape[(label_of[e["src"]], e["rel"], label_of[e["dst"]])].append({"src": e["src"], "dst": e["dst"]})
    for (src_label, rel, dst_label), rows in by_shape.items():
        g.query(f"UNWIND $rows AS r MATCH (a:{src_label} {{id: r.src}}), (b:{dst_label} {{id: r.dst}}) "
                f"CREATE (a)-[:{rel}]->(b)", {"rows": rows})

    versions, sections = policy_documents()
    g.query("UNWIND $rows AS r MATCH (p:Policy {id: r.id}) SET p.version = r.version",
            {"rows": [{"id": k, "version": v} for k, v in versions.items()]})
    g.query("CREATE INDEX FOR (s:Section) ON (s.id)")
    g.query("UNWIND $rows AS r MATCH (p:Policy {id: r.policy}) "
            "CREATE (p)-[:HAS_SECTION]->(:Section {id: r.id, number: r.number, title: r.title, text: r.text})",
            {"rows": sections})
    g.query("UNWIND $rows AS r UNWIND r.controls AS cid MATCH (s:Section {id: r.id}), (c:Control {id: cid}) "
            "CREATE (s)-[:IMPLEMENTED_BY]->(c)", {"rows": sections})
    g.query("CALL db.idx.fulltext.createNodeIndex({label: 'Section', language: 'English'}, 'title', 'text')")

    n = g.query("MATCH (n) RETURN count(n)").result_set[0][0]
    m = g.query("MATCH ()-[r]->() RETURN count(r)").result_set[0][0]
    print(f"Loaded graph '{GRAPH}': {n} nodes, {m} edges")
    return g


if __name__ == "__main__":
    load(*(sys.argv[1:2] or ["localhost"]))
