# Project Eagle — Head of Engineering
## Role Proposal & Mandate (Phase-aware)
**Version 1.0 | Confidential**

---

## 1. Context & Strategic Rationale

Project Eagle is an AI-native regulatory reporting factory, purpose-built to serve Alternative Investment Fund Managers (AIFMs) in meeting their obligations under AIFMD Annex IV. The system is deterministic at its core: compliance logic is codified, versioned and auditable. AI augments transformation and interpretation — it never makes regulated decisions autonomously.

The Head of Engineering is the **delivery engine** of this system. While the CTO/CPO owns architecture and product direction, the Head of Engineering owns **engineering execution** — translating architectural decisions into production-grade code, maintaining system reliability, and building the engineering team's capability over time.

This role is the first non-founder engineering hire and a direct report of the CTO. The timing of this hire is a critical signal: it should happen as soon as the product enters production, not when the engineering team reaches a size that has already overwhelmed the CTO.

The mandate of this role is fourfold:

1. **Engineering delivery** — execute the engineering roadmap to the quality, pace and reliability standards the product requires
2. **System reliability** — own the operational health of the production system: monitoring, incident response and SLA adherence
3. **Engineering capability** — build and develop the engineering team; define and enforce quality standards
4. **Cost efficiency** — manage infrastructure and operational costs per submission as a contribution to unit economics

---

## 2. Strategic Design Choice: Execution as a Discipline

In early-stage engineering, it is tempting to treat delivery as informal and architecture as the only real work. Project Eagle's model requires the opposite disposition:

> **In a regulatory reporting factory, execution quality is product quality. A missed deadline or a silent pipeline failure is not a technical inconvenience — it is a compliance event for the client.**

The Head of Engineering owns the discipline of engineering delivery: CI/CD, test coverage, monitoring, runbooks, on-call, incident response. These are not bureaucratic overhead — they are the structural properties of a system that clients trust with regulated obligations.

---

## 3. Operating Context

| Dimension | Detail |
|---|---|
| Product type | Regulatory reporting factory — deadline-driven, deterministic, auditable |
| Engineering model | Code-first execution model; AI components bounded and monitored; deterministic validation core |
| SLA regime | NCA submission deadlines are fixed; system failures near deadlines are MAJOR DORA incidents |
| Regulatory sensitivity | Pipeline failures can create compliance exposure for AIFM clients |
| Phase 1 constraint | CTO covers engineering execution in Phase 1; Head of Engineering is first non-founder hire at production |
| Cost sensitivity | Infrastructure cost per submission is a unit economics input tracked by CFO |

---

## 4. Responsibilities (Phase-aware)

### 4.1 Engineering Roadmap Delivery

**Phase 1**
- Own the sprint delivery of the engineering roadmap defined by CTO/CPO
- Translate architectural specifications into implementable tasks; flag dependencies and blockers early
- Maintain a delivery cadence that is predictable and transparent — no surprises to CTO or CEO
- Ensure every feature shipped meets the quality standards (test coverage, code review, documentation) defined by the CTO

**Phase 2**
- Manage a growing engineering team: sprint planning, backlog refinement, velocity tracking
- Delivery forecasting: provide CTO and CEO with reliable estimates for roadmap milestones
- Coordinate engineering dependencies across agent development, validation engine, API and infrastructure

---

### 4.2 Agent & Pipeline Development

**Phase 1**
- Build and maintain the AI agent components within the scope defined by the CTO's AI boundary document
- Implement the orchestration pipeline: ingestion → transformation → validation → output
- Ensure every pipeline step is logged, traceable and recoverable — no silent failures
- Build transformation agents that produce outputs for deterministic validation; never bypass the validation gate

**Phase 2**
- Pipeline performance optimisation: throughput, latency, error rates per submission type
- Agent capability expansion as new regulatory requirements or client data formats are introduced
- Regression testing suite for all agents — prevent regressions from new releases affecting existing submission types

---

### 4.3 Code Quality, Testing & CI/CD

**Phase 1**
- Define and enforce coding standards: style, documentation, review requirements
- Implement CI/CD pipeline from day one: automated testing, linting, deployment to staging and production
- Minimum test coverage thresholds for all production code — especially validation logic and agent outputs
- No manual deployments to production; all changes go through the automated pipeline

**Phase 2**
- Formal code review process with defined reviewer requirements
- Test pyramid: unit tests, integration tests, end-to-end tests for critical submission workflows
- Automated regression testing triggered on every release for validation rules
- Performance and load testing cadence aligned with client growth projections

---

### 4.4 System Monitoring, Reliability & SLA Adherence

**Phase 1**
- Implement monitoring infrastructure: system health, pipeline status, error rates, submission queue depth
- Define alerting thresholds: what triggers an automated alert, what triggers an on-call response
- Maintain a system health dashboard accessible to CTO and COO
- Ensure 99.5%+ system availability during NCA submission windows (deadlines are non-negotiable)

**Phase 2**
- Formal SLO (Service Level Objective) framework: availability, latency, error rate targets per system component
- On-call rota with defined escalation procedures
- Monthly reliability review: SLO performance, incident trend, improvement actions

---

### 4.5 DORA Incident Response — Technical Execution

DORA incident management is a shared responsibility. The Head of Engineering supports the CTO in the **technical lane**:

| Incident Lane | Owner |
|---|---|
| Technical detection, containment & resolution | CTO (accountable) + **Head of Engineering (executes)** |
| Operational impact, client communication & SLA management | COO |
| Regulatory notification — DORA Art.18 / NIS2 Art.23 | Head of Compliance & Risk |

**Phase 1**
- Implement and maintain the technical monitoring and alerting infrastructure
- Execute technical incident containment and resolution under CTO direction
- Produce the technical incident report (timeline, root cause, resolution, affected components) for consumption by CTO, COO and Head of Compliance & Risk
- Maintain incident runbooks for the most common failure modes from the first day of production

**Phase 2**
- Own the on-call engineering response for MAJOR and SIGNIFICANT incidents
- Post-incident root cause analysis: written RCA with timeline, contributing factors, and remediation actions
- Runbook maintenance: updated after every incident; reviewed quarterly

---

### 4.6 Data Architecture Implementation

Data ownership is divided across three roles. The Head of Engineering supports the CTO in implementing **data architecture**:

| Data Domain | Owner |
|---|---|
| Data architecture — data model, schema, versioning, lineage | CTO (defines) + **Head of Engineering (implements)** |
| Data operations — ingestion, pipeline execution, delivery | COO |
| Data correctness — regulatory accuracy of content | Head of Compliance & Risk |

**Phase 1**
- Implement the canonical data model as defined by the CTO: field types, version control, lineage tracking
- Ensure data model changes go through a formal review and migration process — no ad hoc schema changes in production
- Implement audit trail: every data transformation step produces a traceable log entry

**Phase 2**
- Schema migration framework for AIFMD 2.0 transition — implemented in advance of the regulatory deadline
- Data model versioning: old and new schema versions run in parallel during transition periods

---

### 4.7 Infrastructure Cost Management

**Phase 1**
- Track infrastructure costs per environment: development, staging, production
- Identify the largest cost drivers: compute, storage, AI model inference, third-party APIs
- Flag infrastructure cost trends to CTO and CFO monthly — cost-per-submission is a unit economics input

**Phase 2**
- Infrastructure cost optimisation programme: right-sizing, reserved capacity, spot instances where appropriate
- Cost per submission tracked as an engineering metric — reduction targets set in coordination with COO and CFO
- Build vs. buy analysis for new infrastructure components: coordinate with CTO on architectural implications

---

### 4.8 Engineering Team Development

**Phase 1**
- Define engineering hiring profile for the first 2–3 engineers: skills, experience level, cultural fit
- Establish onboarding process: codebase walkthrough, architecture documentation, development environment setup
- Define engineering culture: quality standards, review norms, documentation expectations

**Phase 2**
- Performance management: regular 1:1s, growth conversations, skill development plans
- Technical mentoring: senior engineers supporting junior engineers — knowledge transfer is structural, not informal
- Engineering hiring: work with CEO on headcount planning; own the technical interview process

---

## 5. Structural Position

```
CEO
 └── CTO / CPO  →  architecture + product direction
      └── Head of Engineering  →  delivery + reliability + team
           └── Engineering team  →  Phase 2 hires (2–3 engineers initially)
```

**Hire trigger:** As soon as the product enters production. The CTO should not carry engineering execution and architecture simultaneously beyond the first production release.

**Relationship with CTO:** The Head of Engineering executes what the CTO defines. Architectural decisions remain with the CTO. The Head of Engineering raises implementation risks, technical debt and capacity constraints — and expects architectural trade-offs to be decided at CTO level.

**Relationship with COO:** The Head of Engineering and COO share the system health boundary. The COO monitors operational pipeline performance (queue depth, submission success rates, SLA status). The Head of Engineering owns the technical health of the system that produces those outcomes. Both receive the same monitoring dashboard; each escalates different failure types.

**Three Lines of Defence:** The Head of Engineering contributes to the **first line** alongside the CTO — by implementing and maintaining the technical controls that the CTO has designed. The Head of Engineering does not independently own the control framework; that sits with the CTO.

---

## 6. Key Deliverables

### Phase 1
- CI/CD pipeline: automated testing, staging, production deployment
- Monitoring and alerting infrastructure: system health, pipeline status, error rates
- Incident runbooks v1: most common failure modes, response procedures
- DORA technical incident report template
- Infrastructure cost tracking: monthly cost-per-environment report to CTO and CFO
- Onboarding documentation: codebase, architecture, development environment

### Phase 1.5
- Formal SLO framework: availability, latency, error rate targets per component
- Regression test suite for validation rules
- Schema migration framework (in preparation for AIFMD 2.0)
- Engineering team hire 1–2: interviews, onboarding

### Phase 2
- Full test pyramid: unit, integration, end-to-end
- On-call rota with defined escalation procedures
- Post-incident RCA process (written, tracked)
- Infrastructure cost optimisation programme
- Engineering performance management framework

---

## 7. Guiding Principles

> **Principle 2 — Code-first, human-by-exception:** The engineering team builds systems that run without human intervention; humans intervene only for exceptions. The Head of Engineering is accountable for making this real in production — not just in principle.

> **Principle 5 — Deterministic core, probabilistic edge:** Validation logic is deterministic code; AI components are bounded and monitored. The Head of Engineering ensures this is true in every release, not just the first one.

> **Principle 7 — Resilience:** Every process has defined failure modes, fallback mechanisms and escalation paths. The Head of Engineering builds these into the system — they do not emerge from experience.

> **Principle 9 — Security by design:** Security properties are maintained through every engineering change. The Head of Engineering enforces security review as part of the standard delivery process.

> **Principle 10 — Founder-independent by design:** The engineering team, processes and codebase must be understandable and operable by people who were not there at the start. Documentation, onboarding and code quality are not optional.

> **Principle 14 — Database-first:** All operational state, metrics, scores and submission records are stored in the database as first-class records; file exports (PDF, CSV, JSON) are generated views of database data, never the system of record. The Head of Engineering implements this at the code level: no component writes to a file as its primary system of record, schema migrations preserve data integrity across versions, and the audit trail is a database-native, append-only structure.

> **Principle 15 — Platform-first, product-second:** Platform capabilities are product-agnostic; regulatory product logic is isolated in replaceable product modules. The Head of Engineering enforces this separation during delivery: new features that would introduce product-specific logic into platform modules require CTO review and architectural sign-off before merging to production.

> **Principle 16 — Location-independent by design:** Tooling, CI/CD pipelines, monitoring infrastructure and runbooks must be standardised and fully accessible from any location. No engineering process should depend on physical presence — on-call response, incident resolution and code review all operate remotely by default.

---

## 8. Key Engineering Metrics

| Metric | Definition | Owner |
|---|---|---|
| System availability | Uptime during NCA submission windows | Head of Engineering |
| Pipeline success rate | % of submissions processed without manual intervention | Head of Engineering (with COO) |
| Deployment frequency | Number of production deployments per week | Head of Engineering |
| Mean time to recovery (MTTR) | Average time to resolve a MAJOR or SIGNIFICANT incident | Head of Engineering |
| Test coverage | % of production code covered by automated tests | Head of Engineering |
| Infrastructure cost per submission | Total infrastructure cost / total submissions processed | Head of Engineering (reports to CFO) |
| Technical debt ratio | % of engineering capacity spent on maintenance vs. new capability | Head of Engineering (reports to CTO) |

---

## 9. Key Insight

> A regulatory reporting factory that fails silently is not just a technical failure — it is a client compliance event. The Head of Engineering builds systems that fail loudly, recover fast, and leave a trace.
