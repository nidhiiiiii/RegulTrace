# Regulatory Change-Impact Agent — Seed Dataset

Synthetic compliance graph for **PayNova**, a fictional Indian fintech (UPI payments
+ digital lending). When a regulation changes, the agent answers: *which of our
policies, controls, systems, and owners are affected — and why?* Built for Graph
Hacks (WeMakeDevs × FalkorDB), Track 03 "Company Brain". **All company data is
fabricated.** Regulation clauses are paraphrased for the demo, not legal text.

Scope: 35 nodes, 53 edges, 4 demo scenarios.

## Files
| File | What it is |
|---|---|
| `nodes.csv` | `id, type, name, keywords` — Regulation, Clause, Policy, Control, System, Owner |
| `edges.csv` | `src, rel, dst` |
| `scenarios.json` | 4 demo scenarios, the impact model, and expected results |

## Graph model
```
(Regulation)-[:HAS_CLAUSE]->(Clause)-[:MAPS_TO]->(Policy)-[:ENFORCED_BY]->(Control)-[:RUNS_ON]->(System)
(Clause)-[:SUPERSEDES]->(Clause)          // amendments: the memory/precedent link
(Policy|Control)-[:OWNED_BY]->(Owner)
(System)-[:DEPENDS_ON]->(System)          // blast radius into the data layer
```
`keywords` on each node simulate what a doc search / vector search over the
circular's text would match. That's the baseline the graph has to beat.

## Why the graph is load-bearing
A doc or vector search finds the policies that *use the same words* as the new
clause. The people who actually have to act — the engineer who owns the deletion
job, the security lead who owns encryption — are reachable only by **walking the
enforcement chain**. Their names and systems never contain the word "erasure".
That chain is a traversal. Validated:

| Scenario | Keyword search finds | Graph finds |
|---|---|---|
| DPDP erasure | 2 | 8 (incl. 3 owners) |
| RBI APR disclosure | 2 | 8 (incl. a 2-hop system dependency) |
| RBI grievance | 2 | 5 — and correctly **stays scoped** |

## The queries that carry the demo

**1. Impact path (render this in the FalkorDB Browser).**
```cypher
MATCH path = (c:Clause {id:$clause})-[:SUPERSEDES*0..]->(:Clause)
             -[:MAPS_TO]->(:Policy)-[:ENFORCED_BY]->(:Control)-[:RUNS_ON]->(:System)
RETURN path
```

**2. Who do I page?**
```cypher
MATCH (c:Clause {id:$clause})-[:SUPERSEDES*0..]->(:Clause)-[:MAPS_TO]->(p:Policy)
MATCH (p)-[:ENFORCED_BY]->(ctl:Control)
OPTIONAL MATCH (ctl)-[:OWNED_BY]->(o:Owner)
OPTIONAL MATCH (p)-[:OWNED_BY]->(po:Owner)
RETURN p.name AS policy, collect(DISTINCT ctl.name) AS controls,
       collect(DISTINCT o.name) + collect(DISTINCT po.name) AS owners
```

**3. Memory — confirm a mapping, it becomes precedent.**
```cypher
MATCH (c:Clause {id:$clause}), (p:Policy {id:$policy})
MERGE (c)-[m:MAPS_TO]->(p)
SET m.confirmed_by = $user, m.confirmed_at = timestamp()
```
The next amendment that `SUPERSEDES` this clause inherits the mapping with zero
manual work, however long the amendment chain gets (`*0..` is unbounded on
purpose: with `*0..1` an amendment of an amendment finds nothing). The
regulation↔control map is the asset that compounds.

## Demo scenarios (see scenarios.json)
1. **Headline — DPDP erasure:** keyword = 2, graph = 8; surfaces encryption control + both data stores + 3 owners.
2. **Memory — erasure amendment:** new clause has 0 mappings, inherits via `SUPERSEDES`, full impact instantly.
3. **Scoped — RBI grievance:** only support workflow + its owner; security/data/lending not paged.
4. **Data-layer reach — RBI APR:** KFS generator (never says "APR") + lending engine → user DB dependency.

## Honesty / framing
- Synthetic company, paraphrased clauses, illustrative model — not legal advice.
- In a real deployment the hard part is **mapping clauses to policies**. Pitch it as LLM-suggested, human-confirmed — each confirmation is written back as precedent (query 3). That's the memory story.
- Incumbent GRC tools exist (Vanta, Drata, OneTrust, MetricStream). Position this as the **graph-native, explainable impact path** for regulation change, not a full GRC suite.

## Scale path (post-hackathon)
- Regulation source: RBI circulars/master directions (public on rbi.org.in), the DPDP Act text, SEBI/IRDAI circulars.
- Internal side: policy docs, control inventories (ISO 27001 / SOC 2 mappings), CMDB for systems, HR/org chart for owners.
- One isolated FalkorDB graph per company/tenant.
