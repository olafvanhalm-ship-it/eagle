# Project Eagle
*Blueprint for an AI-native reporting factory*
**Version 0.4**

> **Changelog v0.3 → v0.4:** Synced with detailed role documents (CEO v1.0, CTO/CPO v1.1, COO v1.1, CFO v1.1, Head of Compliance & Risk v1.3, Head of Engineering v1.0, CRO v1.0, Head of Customer Success v1.0). Added: Regulatory Framework & Immediate Priorities, Three Lines of Defence, DORA Incident Response Lanes, Data Ownership Model, Roadmap Constraint Model, Per-Client Risk Ownership. Role entries updated to reflect new ownership splits, automation ratio targets, early certification strategy, and EU AI Act governance.

---

## Principles

| # | Principle | Description |
|---|-----------|-------------|
| 1 | **Customer experience first** | Simplicity, reliability and predictability over customisation. |
| 2 | **Code-first, human-by-exception** | All processes run through a central orchestration layer; humans intervene only for exceptions, judgement and improvement. |
| 3 | **Standardised product with predictable output** | Fixed scope, reproducible quality and transparent pricing — no bespoke. |
| 4 | **Single source of truth** | One canonical data model; quality, lineage and ownership are explicit and controlled. |
| 5 | **Deterministic core, probabilistic edge** | Calculations and compliance logic are deterministic; AI is used only for interpretation, transformation and optimisation. |
| 6 | **Modular and portable technology** | Logic, data and rules are separated from AI models and infrastructure to minimise lock-in. |
| 7 | **Resilience** | Every process has defined failure modes, fallback mechanisms and escalation paths. |
| 8 | **Compliance-proof by design** | Compliance logic is deterministic, auditable and explainable; AI supports but never decides. |
| 9 | **Security by design** ✨ | Security is a structural property of all systems, not an afterthought; data is isolated per client, access is least-privilege by default, and all data is encrypted in transit and at rest. |
| 10 | **Founder-independent by design** | All knowledge, rules and processes are fully codified in systems, enabling independence within two years of launch. |
| 11 | **Continuous learning system** | Every process generates feedback data used to systematically improve models, rules and outputs. |
| 12 | **Ambitious growth and profitability** | Cash flow positive within two years, >€1M ARR and >50% EBITDA margin. |
| 13 | **Internationally oriented** | Products offered worldwide; all communication in English. |
| 14 | **Database-first** | All operational state, metrics, scores and reports are stored in the database as first-class records; file exports (PDF, CSV, JSON) are generated views of database data, never the system of record; no loose extract workflows. |
| 15 | **Platform-first, product-second** | Platform capabilities (multi-tenancy, IAM, audit trail, pipeline orchestration, AI layer, management intelligence) are product-agnostic; regulatory product logic (validation rules, NCA overrides, canonical models, submission channels) is isolated in product modules and replaceable without platform changes; adding a new regulatory reporting product must not require changes to any platform module. |
| 16 | **Location-independent by design** | Eagle operates as a virtual office — no physical headquarters required. Every role, process and communication channel is designed to function fully from any location. Async-first by default; real-time interaction by exception. Presence is never a proxy for performance or trust. |

---

## Regulatory Framework & Immediate Priorities

Eagle operates at the intersection of the following legal and technical frameworks. These are not background context — they are structural constraints on the product roadmap, certification timeline, and governance model.

| Framework | Relevance | Urgency |
|---|---|---|
| AIFMD (Directive 2011/61/EU) + Delegated Reg. 231/2013 | Core reporting obligations for AIFMs; Annex IV submission rules | Operational from day 1 |
| ESMA IT Technical Guidance Rev. 6 | XSD schema and technical submission standards | Operational from day 1 |
| ESMA DQEF (May 2025) | Data quality error framework — CAF/CAM error codes drive validation logic | Operational from day 1 |
| **AIFMD 2.0** (OJ March 2024, in force April 2024) | Member states must apply updated rules by **16 April 2026**; new ESMA XSD schemas expected ~April 2027 | ⚠️ Immediate — architecture must support schema versioning |
| DORA | ICT incident classification, notification, and contractual obligations (Art.30 for client contracts) | Operational from day 1 |
| NIS2 Art.23 | Eagle's own NCSC reporting obligation for MAJOR incidents (early warning within 24h) | Operational from day 1 |
| GDPR | Client data handling, retention and privacy obligations | Operational from day 1 |
| **EU AI Act** | AI component classification, documentation and governance requirements | Phase 1: classification; Phase 2: full compliance |
| ISAE 3402 / SOC 2 | External assurance standards for service organisations | Design from day 1; certify as early as feasible post-launch |
| EU Cyber Resilience Act (CRA) | Applies to products with digital elements placed on EU market | **Out of scope — SaaS exclusion.** Eagle is pure cloud-hosted SaaS; no software placed at the client. Scope exclusion documented in `eagle_company_requirements` (EL-006). Re-assess if a client-side component, SDK or on-premise option is introduced. |

> ⚠️ **AIFMD 2.0 is the most significant near-term technical risk.** The 16 April 2026 member-state application deadline and the ~April 2027 ESMA XSD schema changes must be planned into the architecture and roadmap from launch. The Head of Compliance & Risk owns the regulatory readiness assessment; the CTO owns the technical implementation.

---

## Role Structure — Phases 1 & 2

> **Legend:** 🟢 Phase 1 combination &nbsp;&nbsp; 🟡 When to split

---

### CEO — *Strategy, capital & key relationships*

**Responsibilities**
- Company strategy, vision and market positioning
- Fundraising, investor relations and board management
- Capital allocation and major investment decisions
- Relationship owner for top-tier AIFM clients and strategic partners
- Alignment between commercial, technology, operations and compliance
- External representation: press, conferences, industry bodies (EFAMA, ALFI, etc.)
- Ultimate governance accountability: risk appetite, AI ethics, Three Lines of Defence model

**Key decisions the CEO cannot delegate:** which clients to decline, when to raise capital and on what terms, when to separate combined roles, risk appetite, when to enter new markets, who to hire into the leadership team.

🟢 **Phase 1:** Founder — also covers CRO until dedicated hire; establish informal advisory board (minimum 2 advisors: AIFMD regulatory practice + institutional sales)

🟡 **When to split:** Hire CRO when pipeline exceeds single-person capacity (~€500K ARR)

---

### CRO — *New revenue, pipeline & commercial contracts*

**Responsibilities**
- Sales strategy and pipeline management (AIFM segment focus)
- Client acquisition: prospecting, demos, negotiation and closing
- Pricing strategy within financial guardrails set by CFO (pricing floor is CFO-owned; CRO operates within it)
- Commercial contract structuring — including DORA Art.30 required provisions (sourced from Compliance)
- **Scope discipline:** first line of protection against bespoke commitments; every deal qualified against standard product boundary before proposal
- **Commercial constraint log:** structured input to CTO/CPO on recurring capability gaps affecting pipeline ARR — not feature requests; CTO/CPO decides what to build
- Renewal coordination with Head of Customer Success

🟢 **Phase 1:** Combined with CEO (founder-led sales)

🟡 **When to split:** Hire at ~€500K ARR or when sales cycle complexity requires full-time focus

---

### CTO / CPO — *System architecture, product roadmap & AI governance*

**Responsibilities**
- Overall system architecture: orchestration layer, agents, data layer
- Design and maintenance of the code-first execution model and deterministic validation engine
- **Product roadmap ownership** — sole decision-maker on what is built and in what order; other functions provide constraints, not direction (see Roadmap Constraint Model)
- **Data architecture ownership** — canonical data model, schema versioning, lineage; publishes as shared reference for COO (operations) and Compliance (correctness validation)
- **AI system design** — define and implement the AI boundary: permitted use cases, inputs, outputs, technical monitoring; publish AI component inventory to Compliance for independent oversight
- Security, access control and infrastructure reliability (SOC 2 / ISAE 3402 controls by design)
- **DORA technical lane owner:** detection, containment and technical resolution; produces technical incident report for COO and Compliance
- AIFMD 2.0 technical readiness — schema versioning architecture must support transition without disrupting current submissions

🟢 **Phase 1:** Founder — carries both CTO and CPO responsibilities

🟡 **When to split:** Hire Head of Engineering when 3+ engineers or product enters production; separate CPO at ~€2M ARR / Series A

---

### Head of Engineering — *Engineering execution, reliability & delivery*

**Responsibilities**
- Day-to-day delivery of the engineering roadmap (executes what CTO defines)
- Agent and pipeline development and maintenance — no silent failures; every step logged and traceable
- Code quality, testing standards (CI/CD, test pyramid, regression suite for validation rules)
- System monitoring, alerting and SLA adherence (99.5%+ availability during NCA submission windows)
- **DORA technical execution:** supports CTO in technical incident containment and resolution; produces technical incident report
- **Data architecture implementation:** implements the canonical data model as CTO defines; formal migration process for all schema changes
- Infrastructure cost tracking per submission — reports monthly to CTO and CFO
- Engineering team onboarding, mentoring and capability development

🟢 **Phase 1:** First non-founder engineering hire; CTO covers in the interim

🟡 **When to split:** Hire as soon as product enters production — do not let the CTO carry execution and architecture simultaneously beyond first production release

---

### COO — *Operational performance, scalability & vendors*

**Responsibilities**
- End-to-end operational performance of the reporting factory
- Process design, documentation and continuous improvement
- SLA management, throughput optimisation and **automation ratio** (primary unit economics lever; CFO measures, COO drives)
- Exception handling framework and escalation procedures
- **DORA operational lane owner:** client impact register, SLA assessment, client communication during incidents (in coordination with Head of Customer Success)
- **Data operations ownership** — ingestion pipeline, pipeline execution, delivery; escalates data correctness questions to Compliance (COO does not self-adjudicate regulatory content)
- **Cost driver ownership** — manual processing time, third-party data costs, exception handling labour; shares inputs monthly with CFO for cost-per-submission reporting
- Capacity planning and operational scalability
- Vendor and third-party data partner management

**Automation ratio targets:**

| Phase | Target |
|---|---|
| Phase 1 (launch) | Establish baseline; identify all manual touchpoints |
| Phase 1.5 | >70% of submissions without manual intervention |
| Phase 2 | >90% across standard submission types |

🟢 **Phase 1:** Founder — combined with CFO responsibilities

🟡 **When to split:** Hire or upgrade to full-time CFO at ~€1M ARR or first institutional funding

---

### CFO — *Financial control, unit economics & third line coordination*

**Responsibilities**
- Financial management, reporting and control framework
- Budgeting, forecasting and cash flow management (rolling 12-month forecast; flag runway risks to CEO with 3+ months' lead)
- Billing, invoicing and revenue recognition (IFRS 15 / Dutch GAAP)
- **Financial threshold ownership** — sets and enforces: pricing floor (minimum per deal), margin minimum per client, cost-per-submission ceiling, maximum discount thresholds; CRO operates within these guardrails
- **Unit economics measurement** — measures and reports CAC, LTV, gross margin per client, cost-per-submission; COO drives the operational inputs, CFO owns the financial view
- Financial risk per client: revenue concentration (flag >30% ARR from single client), per-client gross margin, receivables
- **Third line coordination** — coordinates external audit (SOC 2 / ISAE 3402) as the independent assurance layer; Compliance defines what is audited, CFO coordinates the engagement and cost
- Series A financial due diligence readiness

**LTV / CAC targets:** >3× (Phase 2); >5× at scale.

🟢 **Phase 1:** Fractional CFO (2–3 days/week) or combined with COO (founder); fractional is viable provided the founder-COO maintains day-to-day financial oversight

🟡 **When to split:** Full-time at ~€1M ARR or first institutional funding — whichever comes first

---

### Head of Compliance & Risk — *Regulatory framework, AI oversight & audit*

**Responsibilities**
- Design and codification of the compliance framework (AIFMD-aligned; all rules traceable to regulatory source)
- **Early certification strategy:** design for SOC 2 / ISAE 3402 Type I from day 1; certify shortly after first clients go live; Type II in Phase 2
- **AIFMD 2.0 readiness** — regulatory assessment parallel to CTO technical assessment; member-state deadline 16 April 2026 is an immediate constraint
- Risk management: operational, technological and regulatory risk register; escalation thresholds approved by CEO
- **AI oversight (second line)** — independent validation that AI components stay within the boundary the CTO has designed; maintains AI component register with compliance annotations; EU AI Act classification for all components; flags boundary drift to CEO if unresolved
- **Data correctness ownership** — defines what "correct" means for each Annex IV field; validates CTO data model reflects regulatory definitions; reviews sample of submission outputs each period
- **DORA regulatory notification lane owner:** owns both notification streams — DORA Art.18 (supporting client AIFM's NCA notification) and NIS2 Art.23 (Eagle's own NCSC early warning within 24h of MAJOR incident); consumes technical report (CTO) and operational impact (COO) to produce notification
- Client regulatory risk: per-client risk profiles, NCA registrations, applicable overrides; owns consequence assessment for submission errors
- Independent validation of product specifications and outputs
- GDPR and data privacy policy ownership

🟢 **Phase 1:** Founder — **standalone from day 1** given regulatory sensitivity; independence is structural, not attitudinal

🟡 **When to split:** N/A — standalone from the start; add Compliance Analyst at scale

---

### Head of Customer Success — *Onboarding, retention & client trust*

**Responsibilities**
- End-to-end client onboarding: contract signature → first **correct** NCA submission (onboarding is not complete at training — it is complete at first successful submission)
- **Client health monitoring** incorporating compliance outcomes, not just satisfaction metrics; proactive intervention on deteriorating health
- Renewal tracker: initiate renewal conversations ≥90 days before expiry
- **Expansion revenue:** identify additional AIFs, NCAs, users within client base; flag to CRO with context; CRO closes commercial terms
- **SLA monitoring from client perspective** — COO owns internal SLA performance; Head of CS owns whether the client experience reflects that performance
- **DORA client communication lane** — executes client notifications during MAJOR and SIGNIFICANT incidents as directed by COO; maintains client contact register for incident communication; ensures post-incident follow-up is completed
- **Client experience constraint log:** structured input to CTO/CPO on friction points, workflow failures and retention risks affecting multiple clients — with evidence (frequency, client count, estimated retention impact); CTO/CPO decides whether and when to act
- Escalates compliance and regulatory interpretation queries to Head of Compliance & Risk — does not self-adjudicate

🟢 **Phase 1:** CRO or COO covers interim

🟡 **When to split:** Hire **at first client go-live** — not when the CS backlog becomes unmanageable; a poor first onboarding creates a reference account problem and a churn risk simultaneously

---

## Governance Architecture

### Three Lines of Defence

| Line | Role | Function |
|---|---|---|
| **First line** | CTO + COO | Own and operate controls embedded in technical systems and operational processes |
| **Second line** | Head of Compliance & Risk | Independent oversight — rule validation, AI oversight, data correctness, regulatory framework, DORA notification |
| **Third line** | External audit — coordinated by CFO | Independent assurance — SOC 2 / ISAE 3402 certification |

```
CEO
 ├── CTO / CPO  →  system + product          [1st line: technical controls]
 │    └── Head of Engineering  →  delivery + reliability
 ├── COO        →  factory operations         [1st line: operational controls]
 ├── CFO        →  financial control          [financial thresholds + 3rd line coordination]
 ├── CRO        →  revenue + commercial       [Phase 1: CEO covers]
 ├── Head of CS →  client success             [Phase 1: CRO or COO covers]
 └── Head of Compliance & Risk               [2nd line: independent oversight — standalone]
                    External Audit            [3rd line, CFO-coordinated]
```

---

### DORA Incident Response — Lane Ownership

DORA incident management is a **shared, structured responsibility**. Three roles own distinct lanes; no lane is combined.

| Incident Lane | Owner | Content |
|---|---|---|
| **Technical** | CTO (accountable) + Head of Engineering (executes) | Detection, containment, resolution; produces technical incident report |
| **Operational** | COO | Client impact register, SLA assessment, client communication (with Head of CS) |
| **Regulatory notification** | Head of Compliance & Risk | DORA Art.18 (supporting client AIFM's NCA notification) + NIS2 Art.23 (Eagle's own NCSC early warning within 24h); consumes technical + operational reports |

MAJOR incident target: regulatory notification available within 4 hours of classification.

---

### Data Ownership Model

Data ownership is explicitly divided across three roles. No role self-adjudicates another's domain.

| Data Domain | Owner | What they own |
|---|---|---|
| **Architecture** | CTO | Canonical data model, schema versioning, lineage tracking; publishes as shared reference |
| **Operations** | COO | Ingestion pipeline, execution, delivery; flags data completeness and timeliness issues |
| **Correctness** | Head of Compliance & Risk | Regulatory accuracy of content in every submission; defines field-level correctness against regulatory source |

Rule: the COO does not adjudicate whether submission content is regulatory-correct. The Head of Compliance & Risk does not operate the pipeline. Escalation path: COO flags data correctness questions → Compliance resolves.

---

### Roadmap Constraint Model

The CTO/CPO **owns the product roadmap** — sole decision-maker on what is built and in what order. Other functions define the constraints within which the roadmap must operate. They do not co-own or direct it.

| Function | Constraint type | What it is NOT |
|---|---|---|
| Head of Compliance & Risk | Regulatory deadlines and mandatory framework changes (AIFMD 2.0, DORA, AI Act) | Roadmap direction or feature ownership |
| CRO | Commercial constraints — revenue impact of capability gaps, ICP-fit requirements; supported by evidence (deals affected × ARR at stake) | Feature requests or deal-driven bespoke commitments |
| COO | Operational constraints — process bottlenecks, scalability limits, automation gaps; supported by evidence (cost per submission, % of submissions affected) | Process change requests that bypass prioritisation |
| CFO | Financial constraints — investment envelope, sequencing by ROI, build vs. buy financial case | Budget approval for individual features |
| CEO | Strategic constraints — market positioning, adjacency decisions | Day-to-day backlog management |
| Head of CS | Client experience constraints — friction points, retention risks; supported by evidence (frequency, client count, estimated retention impact) | Feature wishlist or client-driven roadmap |

---

### Per-Client Risk Ownership

Each client represents a distinct risk profile across six dimensions. One owner per dimension — no shared accountability.

| Client Risk Type | Owner |
|---|---|
| **Technical** — data model mismatch, ingestion failure, integration instability | CTO |
| **Operational** — SLA breach, pipeline failure, data latency | COO |
| **Regulatory** — incorrect submission, NCA error, compliance breach, client-specific NCA override | Head of Compliance & Risk |
| **Financial** — revenue concentration, pricing misalignment, payment default | CFO |
| **Commercial** — contract misalignment, scope dispute, renewal risk | CRO |
| **Relationship** — dissatisfaction, low engagement, churn signal | Head of Customer Success |

---

## Design Principles for Role Structure

- Commercial pressure (CEO/CRO) is structurally separated from client quality (Customer Success) and product integrity (CTO/CPO).
- Compliance is independent from day 1 — structurally, not attitudinally.
- Phase 1 combinations are explicitly time-limited, not permanent workarounds.
- Split triggers are revenue- or complexity-based, not calendar-based.
- The CTO/CPO owns the roadmap; every other function provides constraints, not direction.
- Three Lines of Defence is operational from launch — not retrofitted at Series A.
- DORA incident lanes are never combined: technical (CTO), operational (COO), regulatory notification (Compliance).
- Data correctness is owned by Compliance; data operations is owned by COO; data architecture is owned by CTO — these domains do not overlap.
- No role self-adjudicates another role's domain — escalation paths are defined and followed.
