# Regulatory Change-Impact Agent — ~1-Day Build & Demo Plan

**Track:** 03 (Company Brain) — connect regulations, policies, controls, systems, and people.
**Judging hook:** "Explainable results — show the path." Every answer is the enforcement chain, rendered.

## What you're building (one sentence)
Paste a new regulatory clause (RBI circular, DPDP provision) → the agent walks
PayNova's compliance graph and returns every affected policy, control, system,
and **owner to notify**, with the path that explains why — and it remembers each
confirmed mapping, so the next amendment is mapped instantly.

## Stack
- **Graph:** FalkorDB (Docker or Cloud). Required primary DB.
- **Loader:** Python `falkordb` client ingesting `data/nodes.csv` + `data/edges.csv`.
- **Agent:** 3 tools — `impact(clause)`, `owners_to_notify(clause)`, `confirm_mapping(clause, policy)`. LLM via Vercel AI Gateway (`"provider/model"`) turns results into a plain-English impact memo that cites the graph.
- **Clause intake (stretch):** LLM suggests which existing clause/policy a pasted circular paragraph maps to; a human clicks confirm → written back as precedent.
- **UI:** one page. Left: paste a clause. Middle: "Doc search found 2" vs "Graph found 8". Right: the impact subgraph (FalkorDB Browser side-by-side is the fastest path).

## Hour-by-hour (≈10–12 hrs)
1. **(1h)** FalkorDB up, load CSVs, eyeball the graph in the Browser.
2. **(2h)** The 3 Cypher queries from `data/README.md` returning the validated results.
3. **(3h)** Agent + impact memo ("Notify Ravi (Data Eng): deletion job on user DB + warehouse…").
4. **(3h)** UI with the keyword-vs-graph side-by-side and a Confirm button.
5. **(1–2h)** Rehearse, record a backup video.

## Demo script (≈2 min)
1. **Stakes (20s):** "Meet Aarti — PayNova's compliance lead. A DPDP update lands at 9 PM. Her map of 'what this touches' is a spreadsheet that went stale months ago. So she emails six teams: *does this affect you?* — and waits two weeks."
2. **The trap (20s):** Paste the erasure clause. Doc search: **2 hits** — the retention policy and the deletion job. "That's what search over the policy wiki gives you."
3. **The catch (40s):** Run the agent → **8 affected nodes**: encryption control, user DB, data warehouse, and **3 owners — Ravi, Meena, Aarti** — none of which contain the word "erasure". Flip to the Browser: the chain from clause → policy → controls → systems lights up.
4. **It remembers (20s):** Two months later the erasure timeline is amended. Paste it → **0 new mappings needed**, full impact instantly, because it supersedes a clause Aarti already confirmed.
5. **It doesn't panic (10s):** RBI grievance tweak → only Customer Support is pinged. No alert storm.
6. **Scale (10s):** "Every bank, NBFC, insurer and fintech in India lives on RBI circulars, and DPDP applies to anyone handling Indian personal data. Search tells you which documents match. We tell you who has to act."

## Why FalkorDB (say this)
- "What breaks if the law changes" is a multi-hop traversal across five entity types.
- The answer *is* a path — explainability is free, and it's the judging criterion.
- Amendments are edges (`SUPERSEDES`), so memory is native to the data model.

## Honesty guardrails
- Synthetic company + paraphrased clauses; decision support, not legal advice.
- Clause→policy mapping is human-confirmed; that's where the compounding memory comes from.
- Story is drier than UPI's — win it on the side-by-side (2 vs 8) and the owner list.
