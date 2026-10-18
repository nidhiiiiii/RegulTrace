# Regulatory Change-Impact Agent — Pitch, Users & Story

**One-liner:** *Search tells you which documents mention the new rule. We tell you who has to act, and show the path that proves it.*

**Track:** 03, Company Brain. A compliance team's "brain" is the map from *law → policy → control → system → person*. Today that map lives in a stale spreadsheet. We make it a graph an agent can walk.

---

## 1. The problem, in numbers (India)

| Fact | Why it matters for us |
|---|---|
| RBI regulates **9,291 NBFCs** (RBI list, as of 31 Dec 2024), plus banks, co-op banks, HFCs and payment players. | Thousands of companies run on RBI circulars. |
| In FY25 RBI imposed **353 penalties totalling ₹54.78 crore**. The breaches were in cyber security, KYC, fraud reporting and credit-info submission. | These are **control failures**, not unknown laws. The rule was known, but the control/owner link broke. That link is exactly what our graph holds. |
| **264 of those 353** penalties hit co-operative banks. | The smallest teams get fined the most. They can't afford an army of compliance analysts. |
| On **28 Nov 2025** RBI consolidated **9,000+ circulars into ~240 Master Directions** across 11 categories of regulated entities. | Every compliance map keyed to old circular numbers now points at superseded text. That is a mass `SUPERSEDES` event, and it's our memory beat at national scale. |
| RBI circular **RBI/2023-24/117 (31 Jan 2024)** told banks, NBFC-ML/UL, HFCs, larger UCBs and others to use **technology tools for compliance monitoring**. The tools must put all compliances in one place, run an identify-assess-monitor workflow, **escalate non-compliance to the right stakeholder**, and give management one dashboard. Deadline: 30 Jun 2024. | The regulator already **requires** the category we're building in. "Escalate to the right stakeholder" is literally our `owners_to_notify` query. |
| **DPDP Rules notified Nov 2025.** Most obligations (notice, consent, security safeguards, breach reporting, data-principal rights) apply from **13 May 2027**. Penalties go up to **₹250 crore** for serious failures. | Every company handling Indian personal data is mid-build *right now*, with about 7 months to go. Each DPDP clause has to be mapped to the policies, controls and systems it touches. |

### How it's handled today
A circular lands. Compliance reads it and updates an Excel "applicability matrix". Then they email every department: *"Does this affect you?"* They chase replies for 1–2 weeks, and the matrix is stale again by the next circular.

### Why existing approaches don't close it
- **Doc / vector search / plain LLM:** finds the documents that *use the same words*. In our validated DPDP scenario that's 2 of the 8 affected items. The engineer who owns the deletion job and the security lead who owns encryption never appear in a document containing "erasure". They are reachable only by walking the enforcement chain.
- **Compliance trackers** (e.g. TeamLease RegTech's RegTrack) and **GRC suites** (OneTrust, MetricStream, Vanta, Drata): their unit is the obligation row, the due date or the framework control. **Our unit is the path.** Position as the graph-native, explainable impact layer for regulatory *change*, not as a replacement suite. *(Don't claim they can't do it; say this is what we're built around.)*

---

## 2. Who is the user?

| Role | Who | What they get |
|---|---|---|
| **Primary user** | **Head of Compliance / CCO** at an NBFC, fintech or co-op bank. *Persona: Aarti, Legal & Compliance at PayNova.* | Paste a clause. Get every affected policy, control, system and owner in minutes, with the "why" path. |
| **Secondary users** | **Control owners**, e.g. Ravi (Data Eng), Meena (Security), Karan (Lending), Neha (Support) | A scoped ping with the path attached: *"you're on this because the erasure clause → retention policy → deletion job → user DB."* No more "does this really affect me?" |
| **Buyer** | CCO / CRO. For NBFC-UL and NBFC-ML, a CCO-led compliance function is **RBI-mandated** (since Apr 2023 and Oct 2023 respectively). | Meets the "escalate to the right stakeholder" expectation, with an audit trail. |
| **Beneficiary** | Internal audit / RBI inspection | Who confirmed which mapping, and when, is stored on the edge. The path is the evidence. |

### How many could use it (honest funnel)
1. **Beachhead: NBFC Middle + Upper Layer, about 593 companies** (582 ML + 11 UL on the Dec 2024 list). They have a mandated CCO, they're covered by the compliance-tool circular, and digital-lending rules change often. Fintech lenders sit here.
2. **Next: the rest of the circular-117 set.** That means scheduled commercial banks, small finance and payments banks, HFCs, larger urban co-op banks, CICs and AIFIs.
3. **Long tail: about 8,600 base-layer NBFCs and the co-op banks.** No tool mandate, but they take most of the penalties. A lightweight version fits here.
4. **Horizontal: DPDP.** Every company processing Indian digital personal data, including fintech, healthtech, edtech and e-commerce, has to map DPDP clauses to its systems before May 2027.

*We don't quote a rupee TAM. Judges at a dev hackathon trust a sourced count of mandated buyers more than a made-up market size.*

### Why would they actually use it (jobs to be done)
1. **Day-1 triage:** "Does this touch us? Where? Who acts?" Answered in minutes instead of two weeks of email.
2. **Notify the right person, with the reason.** The path removes pushback.
3. **No alert storm.** A grievance tweak pages Support only, not Security, Data or Lending. Trust comes from precision.
4. **Memory that compounds.** Every confirmed mapping becomes precedent. Amendments and Master Directions that supersede old circulars inherit it automatically.
5. **Audit evidence for free.** `confirmed_by` and `confirmed_at` live on the edge.

---

## 3. User stories (with acceptance criteria tied to the dataset)

| # | As a… | I want… | So that… | Acceptance (validated in `data/scenarios.json`) |
|---|---|---|---|---|
| 1 | Compliance lead (Aarti) | to paste a new regulatory clause and see every policy, control, system and owner it affects | I can assign actions the same day | DPDP erasure → 8 items incl. Ravi, Meena, Aarti; keyword search finds 2 |
| 2 | Control owner (Ravi) | to see *why* I'm being asked to act | I trust the request and don't push back | Impact path rendered clause → policy → control → system |
| 3 | Compliance lead | amendments to reuse what we already confirmed | I don't redo the analysis every time a clause changes | Amended erasure clause: 0 own mappings, full impact inherited via `SUPERSEDES` |
| 4 | Support lead (Neha) | to be pinged only for changes that touch my workflow, and everyone else to be left alone | alerts stay meaningful | RBI grievance → 5 items, never Security/Data/Lending |
| 5 | Lending PM (Karan) | to see knock-on systems, not just the document that names the rule | nothing downstream breaks silently | RBI APR → KFS generator + lending engine → user DB (2-hop `DEPENDS_ON`) |
| 6 | Internal auditor | to see who confirmed each mapping and when | I can evidence the decision to RBI | `MAPS_TO` edge carries `confirmed_by`, `confirmed_at` |

---

## 4. The story (how we tell it)

**Act 1: the 9 PM email.**
Aarti runs compliance at PayNova, a UPI + digital-lending fintech. A DPDP update on the right to erasure lands at 9 PM. Her map of "what this touches" is a spreadsheet last updated in spring. Tomorrow she'll email six teams, *"does this affect you?"*, and wait two weeks. Meanwhile the deadline clock is running, and DPDP penalties run up to ₹250 crore.

**Act 2: the trap.**
She tries search over the policy wiki and gets 2 hits: the retention policy and the deletion job. It looks done. It isn't. The encryption control, the user DB, the data warehouse, and the three people who must act never say "erasure".

**Act 3: the graph.**
She pastes the clause into our agent. It walks the company's compliance graph and returns 8 affected items and 3 owners, each with the path that explains why. She confirms one mapping. Two months later the clause is amended. She pastes it and gets the full impact instantly, with zero new mapping. When RBI tweaks the grievance rule, only Neha in Support is pinged.

**The turn to scale:**
"In November 2025 RBI replaced 9,000+ circulars with ~240 Master Directions. Every bank and NBFC in India had to ask 'what did my old mapping point to, and where does it live now?' That's a graph question. Each of those is a `SUPERSEDES` edge, and our agent carries the mapping across it."

---

## 5. The 2-minute pitch (spoken)

> **(Hook, 15s)** "Last year RBI fined regulated entities 353 times. The fines weren't for laws nobody knew about. They were for KYC, cyber security and fraud reporting: controls that broke when rules changed. The rule was known. The link from the rule to the person who had to act was lost."
>
> **(Problem, 20s)** "When a circular or a DPDP clause lands, compliance teams still email every department asking 'does this affect you?' Search and LLMs find documents with the same words. They can't find the engineer who owns the deletion job, because that name never appears next to the word 'erasure'."
>
> **(Demo, 60s)** *Run the DEMO_PLAN script: 2 vs 8 → path in FalkorDB Browser → amendment inherits → grievance stays scoped.*
>
> **(Why graph, 15s)** "'What breaks if this law changes' is a multi-hop traversal across six kinds of things. The answer *is* a path, so explainability is free. Amendments are `SUPERSEDES` edges, so memory is part of the data model, not bolted on. Each company gets its own isolated FalkorDB graph."
>
> **(Close, 10s)** "RBI already requires tools that escalate non-compliance to the right stakeholder, and DPDP obligations land in May 2027. Search tells you which documents match. We tell you who has to act."

---

## 6. Judge Q&A, pre-empted

- **"Wouldn't an LLM just do this?"** An LLM can read the clause. It cannot know that the encryption control is owned by Meena and runs on the user DB. That's private company structure, and it lives in the graph. The LLM writes the memo and suggests mappings; the graph is the source of truth.
- **"Where does the graph come from in a real company?"** From things that already exist as spreadsheets: control inventories (ISO 27001 / SOC 2 mappings), the CMDB for systems, the org chart for owners, and the policy library. Circular 117 is already pushing REs to digitise these.
- **"Who maps clauses to policies?"** The LLM suggests and a human confirms. Each confirmation is written back as a `MAPS_TO` edge with who and when. That is where the compounding memory comes from.
- **"Why not Postgres with joins?"** The depth varies: `SUPERSEDES` chains and `DEPENDS_ON` chains can be any length, and we return the path itself as the answer. In a graph that's one Cypher pattern; in SQL it's recursive CTEs with no native path.
- **"Isn't this Vanta / OneTrust?"** Those are compliance suites built around frameworks and evidence. We're the change-impact layer: *this clause changed → this path → these people.* It could feed any of them.
- **"Is this legal advice?"** No. It's decision support on a synthetic company with paraphrased clauses.

---

## 7. Honest risks
- **Drier story than UPI.** No victim losing money. Win on the visual (2 vs 8, the path lighting up) and the owner names.
- **Data is synthetic.** PayNova and its controls are made up, and the clauses are paraphrased. Say so up front.
- **Clause intake is the hard part in real life.** We demo the impact walk and memory; LLM-suggested mapping is a stretch goal.

---

## Sources
- RBI list of NBFCs and ARCs registered with RBI (as of 31 Dec 2024): https://website.rbi.org.in/documents/87730/39016390/ListofNBFCsandARCsregisteredwiththeRBI.pdf
- RBI penalties FY25, 353 penalties / ₹54.78 cr, by segment (PTI via Business Standard): https://www.business-standard.com/amp/finance/news/rbi-imposed-penalties-on-353-banks-other-regulated-entities-in-fy25-125060100307_1.html
- RBI consolidates 9,000+ circulars into Master Directions, 28 Nov 2025 (Business Today): https://www.businesstoday.in/amp/latest/economy/story/rbi-consolidates-9000-circulars-into-244-master-directions-for-enhanced-ease-of-doing-business-details-here-504215-2025-11-28
- RBI/2023-24/117, internal compliance monitoring tools (ClearTax summary): https://cleartax.in/s/internal-compliance-monitoring-rbi-circular-117
- RBI, Compliance Function and Role of CCO for NBFCs: https://website.rbi.org.in/web/rbi/-/notifications/compliance-function-and-role-of-chief-compliance-officer-cco-nbfcs-12290
- DPDP Rules 2025 (PIB document): https://static.pib.gov.in/WriteReadData/specificdocs/documents/2025/nov/doc20251117695301.pdf
- DPDP Rules phased timeline (iPleaders guide): https://blog.ipleaders.in/dpdp-rules-2025-operational-compliance-guide-for-indian-businesses/
- TeamLease RegTech RegTrack (example of an existing tracker): https://teamleaseregtech.com/product-services/regtrack-financial-institutions/

*Before the pitch, check the "~240 Master Directions" figure (reports say 238 or 244) and the DPDP May 2027 date against the RBI and MeitY originals.*
