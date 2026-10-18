import json
import os
import sys

import graph

HERE = os.path.dirname(os.path.abspath(__file__))
g = graph.connect()
failures = 0


def check(name, ok, detail=""):
    global failures
    failures += 0 if ok else 1
    print(f"  [{'OK' if ok else 'FAIL'}] {name}" + (f"  {detail}" if detail else ""))


def found(clause):
    return set(graph.impact(g, clause)["found"])


def mappings():
    return graph.rows(g, "MATCH ()-[r:MAPS_TO]->() RETURN count(r)")[0][0]


print("SCENARIOS (live FalkorDB)")
for s in json.load(open(os.path.join(HERE, "data", "scenarios.json")))["scenarios"]:
    c, e = s["clause"], s["expected"]
    r = graph.impact(g, c)
    hit = set(r["found"])
    if s["type"] == "impact":
        ok = hit == set(e["impact"]) and set(r["keyword"]) == set(e["keyword_hits"])
        if "must_not_include" in e:
            ok &= not (hit & set(e["must_not_include"]))
        check(s["name"], ok, f"keyword={len(r['keyword'])} graph={len(hit)}")
    else:
        own = graph.rows(g, "MATCH (:Clause {id: $c})-[:MAPS_TO]->(p) RETURN count(p)", c=c)[0][0]
        ok = own == e["direct_mappings"] and hit == found(e["impact_equals"])
        check(s["name"], ok, f"own mappings={own}, inherited impact={len(hit)}")

print("\nOWNERS AND WRITE-BACK")
names = {o["name"] for o in graph.impact(g, "CL_DPDP_ERASURE")["owners"]}
check("Erasure pages Ravi, Meena, Aarti",
      names == {"Data Engineering - Ravi", "Security - Meena", "Legal and Compliance - Aarti"}, str(sorted(names)))
before = mappings()
ok = graph.confirm_mapping(g, "CL_DPDP_ERASURE", "POL_RETENTION", "aarti")
check("Confirm mapping writes back without duplicating", ok and mappings() == before)

print("\nAMENDMENT OF AN AMENDMENT")
cid = graph.register_clause(g, "Second amendment", "erasure deletion timeline", "REG_DPDP", "CL_DPDP_ERASURE_V2")
check("Impact inherits two amendments back", found(cid) == found("CL_DPDP_ERASURE"), f"graph={len(found(cid))}")
g.query("MATCH (c:Clause {id: $c}) DETACH DELETE c", {"c": cid})

print("\nNEW CLAUSE WITH NO PRECEDENT")
cid = graph.register_clause(g, "Consent withdrawal", "Consent must be revocable at any time with clear notice.", "REG_DPDP")
r = graph.impact(g, cid)
check("Unmapped clause returns policy suggestions", not r["found"] and r["suggest"],
      str([p["id"] for p in r["suggest"]]))
if r["suggest"]:
    graph.confirm_mapping(g, cid, r["suggest"][0]["id"], "aarti")
    check("Confirmed mapping lights up the impact", len(found(cid)) > 0, f"graph={len(found(cid))}")
g.query("MATCH (c:Clause {id: $c}) DETACH DELETE c", {"c": cid})

print(f"\n{'ALL GOOD' if not failures else f'{failures} FAILURE(S)'}")
sys.exit(1 if failures else 0)
