# Project Eagle — Chief Operating Officer (COO)
## Role Proposal & Mandate (Phase-aware)
**Version 1.1 | Confidential**

---

## 1. Context & Strategic Rationale

Project Eagle is an AI-native regulatory reporting factory, purpose-built to serve Alternative Investment Fund Managers (AIFMs) in meeting their obligations under AIFMD Annex IV. The product delivers deterministic, auditable compliance outputs at scale — with AI augmenting transformation and interpretation, never replacing human accountability.

The COO is the **operational engine** of this model. While the CTO builds and maintains the system, and the Head of Compliance & Risk owns the regulatory framework, the COO owns the **end-to-end performance of the reporting factory** — the processes, throughput, quality standards, vendor relationships, and scalability mechanisms that determine whether clients receive correct, on-time outputs consistently.

The mandate of this role is fourfold:

1. **Operational ownership** — end-to-end process performance, SLA adherence and exception management
2. **Scalability architecture** — designing processes that scale without proportional headcount growth
3. **Vendor and data ecosystem** — managing third-party data partners and external dependencies
4. **First line of defence** — owning operational controls as the first layer of the governance model

---

## 2. Strategic Design Choice: Process-as-Product

Project Eagle's commercial proposition is built on reliability and repeatability. Unlike bespoke consulting, the reporting factory must produce consistent outputs across all clients and all reporting periods. This makes the COO role structurally distinct from a traditional operations leader:

> **The COO does not just run the business — they co-design the product.**

Process design decisions made by the COO directly affect product quality, client SLA performance, and the scalability of the unit economics. The automation ratio — the proportion of submissions processed without human intervention — is a core financial metric that this role drives. The CFO measures and reports it; the COO owns its improvement.

---

## 3. Operating Context

| Dimension | Detail |
|---|---|
| Reporting factory model | Standardised, repeatable outputs — not bespoke per client |
| AI-augmented pipeline | Deterministic validation core; AI used for transformation and interpretation |
| SLA regime | Deadline-driven (NCA submission calendars); tolerance for error is low |
| Regulatory sensitivity | Outputs are regulatory filings; quality failures have direct compliance consequences for clients |
| Growth model | Revenue scales faster than operational headcount — automation ratio is a key lever |
| Phase 1 constraint | COO and CFO responsibilities combined in the founder until ~€1M ARR |

---

## 4. Responsibilities (Phase-aware)

### 4.1 Operational Performance & Reporting Factory Management

**Phase 1**
- Monitor end-to-end pipeline throughput for each reporting period
- Track submission success rates and identify recurring failure patterns
- Maintain a simple operational dashboard covering SLA status, queue depth, and exception volumes

**Phase 2**
- Full operational reporting framework with client-level SLA tracking
- Automated alerting for pipeline anomalies and deadline proximity
- Periodic operational review cadence with structured reporting to CEO

---

### 4.2 Process Design & Continuous Improvement

**Phase 1**
- Document all operational processes — ingestion, transformation, validation, review, submission
- Define exception handling procedures and escalation paths
- Identify manual steps that are candidates for automation

**Phase 2**
- Formal continuous improvement programme with tracked automation ratio
- Process versioning and change control aligned with product releases
- Quarterly process review against SLA and quality targets

**Operational constraints for the product roadmap:** The CTO/CPO owns the product roadmap. The COO's role is to define **operational constraints** — process bottlenecks, scalability limits, exception patterns and automation gaps that the product must address for the factory to scale. The COO registers these as constraints; the CTO/CPO decides if and when to address them in the roadmap. The COO does not raise feature requests — they raise operational evidence: this manual step costs X minutes per submission, affects Y% of submissions, and will become a capacity bottleneck at Z clients.

---

### 4.3 SLA Management & Quality Assurance

**Phase 1**
- Define client-facing SLA standards (in coordination with CRO and Head of Customer Success)
- Track SLA performance per client and per reporting period
- Own the internal quality gate: no submission leaves the factory without passing output checks

**Phase 2**
- Formal SLA measurement and reporting framework
- Quality scorecard per client, per period
- Root cause analysis for any SLA breach, with remediation tracking

---

### 4.4 Exception Handling & Escalation

**Phase 1**
- Define exception categories and severity thresholds
- Maintain an exceptions log with resolution tracking
- Escalation path to Head of Compliance & Risk for any exception with regulatory significance
- Escalation path to CTO for any exception with technical root cause

**Phase 2**
- Structured exception management system integrated with the platform
- Pattern analysis to identify systemic issues
- Formal escalation matrix covering operational, technical and regulatory dimensions

---

### 4.5 DORA Incident Response — Operational Impact Lane

DORA incident management is a shared responsibility across three roles. The COO owns the **operational impact lane**:

| Incident Lane | Owner |
|---|---|
| Technical detection, containment & resolution | CTO |
| **Operational impact, client communication & SLA management** | **COO** |
| Regulatory notification (DORA Art.18 / NIS2 Art.23) | Head of Compliance & Risk |

**Phase 1**
- Maintain the client impact register for all MAJOR and SIGNIFICANT incidents
- Own client communication during incidents — in coordination with Head of Customer Success
- Assess SLA impact of each incident and document remediation obligations
- Feed operational impact assessment into the regulatory notification process owned by Compliance

**Phase 2**
- Formal incident impact assessment procedure with defined timelines
- Post-incident operational review within 5 business days for MAJOR incidents
- Operational lessons-learned fed into process improvement programme

---

### 4.6 Data Operations Ownership

Data ownership within Project Eagle is divided across three roles. The COO owns **data operations**:

| Data Domain | Owner |
|---|---|
| Data architecture and data model | CTO |
| **Data operations — ingestion, pipeline execution, delivery** | **COO** |
| Data correctness — regulatory accuracy of content | Head of Compliance & Risk |

**Phase 1**
- Own the ingestion pipeline operationally: monitor data receipt from clients, flag missing or delayed feeds
- Manage data delivery SLAs from third-party data partners (aligned to submission deadlines)
- Maintain the operational data quality log — volumes, completeness, timeliness per client per period
- Escalate data correctness questions to Head of Compliance & Risk; do not self-adjudicate regulatory content

**Phase 2**
- Formal data operations dashboard: ingestion status, pipeline health, delivery confirmation per client
- Vendor data SLA tracking with contractual escalation triggers

---

### 4.7 Cost Driver Ownership

The COO owns **operational cost drivers** — the inputs that determine cost-per-submission. The CFO measures, reports, and sets financial thresholds against those drivers.

| Cost Driver | COO Action | CFO Role |
|---|---|---|
| Manual processing time per submission | Reduce via process design and automation | Measure, report and set margin floor |
| Third-party data supplier costs | Negotiate and optimise contractually | Track as % of gross margin |
| Infrastructure usage per submission | Optimise in coordination with CTO | Report trend; flag threshold breaches |
| Exception handling cost (labour) | Reduce via root cause elimination | Include in cost-per-submission model |

**Phase 1**
- Maintain a cost-per-submission baseline (operational inputs: time, exceptions, vendor cost)
- Identify the top three cost drivers and produce an improvement plan
- Share cost driver data with CFO monthly for financial reporting

**Phase 2**
- Formal cost optimisation programme with quarterly targets
- Automation ratio improvement roadmap (target: >90% by Phase 2) as primary cost lever
- Coordinate infrastructure cost management with CTO

---

### 4.8 Client-Level Risk

Each client represents a distinct risk profile — operationally, financially, and regulatorily. The COO owns **operational risk per client**:

| Client Risk Type | Owner |
|---|---|
| Technical risk — data model mismatch, ingestion failure, integration instability | CTO |
| **Operational risk** — SLA breach, data latency, pipeline failure | **COO** |
| Regulatory risk — incorrect submission, NCA error, compliance breach | Head of Compliance & Risk |
| Financial risk — revenue concentration, payment default | CFO |
| Commercial risk — contract misalignment, scope dispute, renewal risk | CRO |
| Relationship risk — dissatisfaction, low engagement, churn signal | Head of Customer Success |

**Phase 1**
- Maintain a per-client operational health score: SLA performance, exception frequency, data quality
- Flag clients with deteriorating operational health to Head of Customer Success and CEO
- Identify clients where operational complexity (e.g. many AIFs, multiple NCAs) requires additional capacity

**Phase 2**
- Formal client risk register (operational dimension) updated per reporting period
- Client operational tiering: standard vs. elevated-care client management
- Escalation protocol for clients approaching SLA breach threshold before deadline

---

### 4.9 Capacity Planning & Scalability

**Phase 1**
- Track reporting calendar load and identify peak-period resource requirements
- Stress-test the factory process against projected client growth
- Flag capacity constraints to CTO and CEO before they become SLA risks

**Phase 2**
- Formal capacity model updated quarterly
- Scenario planning for 2× and 5× client volume
- Defined triggers for headcount additions, tooling upgrades and infrastructure scaling

---

### 4.10 Vendor & Third-Party Data Partner Management

**Phase 1**
- Maintain a register of all third-party data suppliers and service providers
- Manage contractual and operational relationships with data partners
- Ensure data delivery SLAs from vendors are aligned with client submission deadlines

**Phase 2**
- Formal vendor assessment and review programme
- Contingency arrangements for critical data suppliers
- Cost optimisation reviews; cost data shared with CFO for margin tracking

---

## 5. Structural Position & Three Lines of Defence

Project Eagle operates a **Three Lines of Defence** model. The COO is the **first line**:

| Line | Role | Function |
|---|---|---|
| **First line** | **COO + CTO** | Own and operate the controls embedded in day-to-day processes |
| Second line | Head of Compliance & Risk | Independent oversight, rule validation and regulatory framework |
| Third line | External audit (coordinated by CFO) | Independent assurance — SOC 2 / ISAE 3402 certification |

```
CEO
 ├── CTO / CPO  →  builds the system  [1st line: technical controls]
 ├── COO        →  runs the factory   [1st line: operational controls]
 ├── CFO        →  financial control  [financial thresholds & reporting]
 └── Head of Compliance & Risk  →  independent oversight  [2nd line]
                                      External Audit  [3rd line]
```

**Phase 1 combination:** The founding COO also carries CFO responsibilities until financial complexity warrants separation (~€1M ARR or first external funding).

**Independence principle:** The COO does not own regulatory compliance decisions or data correctness — those are owned by the Head of Compliance & Risk. The COO owns the operational process through which compliant outputs are produced.

---

## 6. Key Deliverables

### Phase 1
- Operational process documentation (ingestion → transformation → validation → review → submission)
- Exception handling framework and escalation procedures
- SLA definition and tracking dashboard
- Vendor register and data partner SLA map
- Automation ratio baseline measurement
- Data operations dashboard (ingestion status, pipeline health per client)
- Cost-per-submission baseline (operational inputs)
- Client operational health scorecard

### Phase 1.5
- Capacity model v1 (current + projected volume)
- Quality assurance framework
- DORA operational impact procedure
- COO / CFO separation planning (if not already split)

### Phase 2
- Full operational reporting suite
- Formal continuous improvement programme
- Vendor review and contingency framework
- Automation ratio improvement roadmap (target >90%)
- Formal client risk register (operational dimension)

---

## 7. Guiding Principles

> **Principle 2 — Code-first, human-by-exception:** All processes run through a central orchestration layer; humans intervene only for exceptions, judgement and improvement. For the COO, this means the reporting factory is designed to run without manual intervention; humans act only on flagged exceptions, not on routine processing steps.

> **Principle 3 — Standardised product with predictable output:** Fixed scope, reproducible quality and transparent pricing — no bespoke. The COO enforces this operationally: configuration handles client variation; any deviation from the standard process is an exception to be managed, not a design choice to be accommodated.

> **Principle 4 — Single source of truth:** The COO owns the operational pipeline that writes to the canonical database. All operational state — ingestion status, pipeline outcomes, SLA measurements, exception logs, automation ratio — is stored in the database as the primary system of record. The COO escalates to the CTO any pipeline component that writes to a file as its authoritative output rather than to the canonical database. No parallel operational data store is permitted.

> **Principle 6 — Modular and portable technology:** Logic, data and rules are separated from AI models and infrastructure to minimise lock-in. For the COO, this means vendor relationships and operational dependencies are managed so that no single supplier can hold the factory hostage — operationally or contractually.

> **Principle 7 — Resilience:** Every operational process has defined failure modes, fallback mechanisms and escalation paths. The COO designs the factory to degrade gracefully — exception handling, SLA breach escalation, DORA operational impact assessment and capacity buffers are not reactive measures but structural properties of the reporting factory.

> **Principle 10 — Founder-independent by design:** All knowledge, rules and processes are fully codified in systems, enabling independence within two years of launch.

> **Principle 11 — Continuous learning system:** Every process generates feedback data used to systematically improve models, rules and outputs.

> **Principle 12 — Ambitious growth and profitability:** Cash flow positive within two years, >€1M ARR and >50% EBITDA margin.

> **Principle 14 — Database-first:** All operational state, metrics, scores and reports are stored in the database as first-class records; file exports (PDF, CSV, JSON) are generated views of database data, never the system of record; no loose extract workflows. The COO owns the operational pipeline that produces these records — the automation ratio dashboard, SLA tracking, submission queue depth and exception logs are all DB-native views, never standalone file extracts. If a pipeline component writes to a file as its primary system of record, the COO escalates to the CTO as a design violation.

> **Principle 16 — Location-independent by design:** All operational processes, exception handling procedures, vendor management workflows and SLA monitoring must function fully regardless of where team members are located. Async-first documentation is not optional — it is the operational standard.

---

## 8. Key Metric: Automation Ratio

The automation ratio — the share of submissions processed end-to-end without manual intervention — is the single most important operational metric for Project Eagle's unit economics.

| Phase | Target Automation Ratio |
|---|---|
| Phase 1 (launch) | Establish baseline; identify manual touchpoints |
| Phase 1.5 | >70% of submissions processed without manual intervention |
| Phase 2 | >90% automation ratio across standard submission types |

> **The COO drives this metric. The CFO measures it. Improvement in automation ratio is a direct contribution to margin expansion.**

---

## 9. Key Insight

> Operational excellence is not a support function — it is a core product property.
