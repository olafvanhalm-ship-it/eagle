# Project Eagle — Chief Technology Officer / Chief Product Officer (CTO / CPO)
## Role Proposal & Mandate (Phase-aware)
**Version 1.1 | Confidential**

---

## 1. Context & Strategic Rationale

Project Eagle is an AI-native regulatory reporting factory, purpose-built to serve Alternative Investment Fund Managers (AIFMs) in meeting their obligations under AIFMD Annex IV. The system is deterministic at its core: compliance logic is codified, auditable and explainable. AI augments interpretation and data transformation — it never makes regulated decisions autonomously.

The CTO / CPO is the **technical and product architect** of this system. In Phase 1, one founder carries both the CTO and CPO mandates. This is a deliberate design choice: at early stage, product direction and technical architecture must be unified. Premature separation creates misalignment between what is built and what should be built.

The mandate of this combined role is fivefold:

1. **Architecture ownership** — design and maintain a system that is deterministic, auditable and scalable
2. **Product roadmap** — translate regulatory and client requirements into a prioritised, coherent product
3. **AI system design** — define what AI does, how it does it, and where its boundary ends
4. **Security and reliability** — deliver a system that is secure by design and operationally dependable
5. **First line of defence** — owning technical controls as the first layer of the governance model

---

## 2. Strategic Design Choice: Code-First, Deterministic Core

The foundational technical philosophy of Project Eagle is explicit:

> **Calculations and compliance logic are deterministic. AI is used only for interpretation, transformation and optimisation — never for regulated decisions.**

This is not a limitation — it is a competitive differentiator. Clients (AIFMs and their compliance officers) need to be able to explain every output to an NCA. A black-box AI system cannot provide that. The CTO/CPO is the guardian of this principle at the architectural level.

The **code-first execution model** means:
- Validation rules are explicit, versioned code — not emergent model behaviour
- Every transformation step is logged and traceable
- NCA-specific overrides are configuration, not bespoke engineering
- The system can be audited by external parties

---

## 3. Technical & Regulatory Context

| Domain | Relevance |
|---|---|
| AIFMD Annex IV (Directive 2011/61/EU) | Defines the reporting obligations the system automates |
| ESMA IT Technical Guidance Revision 6 | XSD schema and technical submission standards |
| ESMA DQEF (May 2025) | Data quality error framework — CAF/CAM error codes drive validation logic |
| AIFMD 2.0 (in force April 2024; member state application by 16 April 2026) | New ESMA XSD schemas expected ~April 2027 — significant re-architecture trigger |
| DORA (Digital Operational Resilience Act) | ICT incident detection, classification and technical resolution |
| GDPR | Data architecture, isolation, retention and access control obligations |
| ISO 27001 / SOC 2 / ISAE 3402 | Security and control frameworks relevant to system design and audit readiness |
| AI Act (EU) | AI component classification, documentation and governance obligations |

> ⚠️ **Immediate technical priority:** AIFMD 2.0 XSD schema changes (~April 2027) must be planned into the technical roadmap from launch. The architecture must support schema versioning without full system rework.

---

## 4. Responsibilities (Phase-aware)

### 4.1 System Architecture

**Phase 1**
- Design and implement the orchestration layer, agent framework and data layer
- Establish the single source of truth data model with full version control
- Ensure all components are modular and replaceable — minimal vendor lock-in
- Define the API contract for all ingestion channels and downstream integrations

**Phase 2**
- Architecture review cadence aligned with product scaling and regulatory changes
- Formal component dependency map and upgrade strategy
- Multi-region or multi-cloud readiness assessment (if required by client data residency obligations)

---

### 4.2 Code-First Execution Model & Validation Engine

**Phase 1**
- Implement the deterministic validation engine against ESMA validation rules and NCA overrides
- Ensure all rules are versioned, traceable and explainable (rule ID → regulatory source)
- Build the audit trail: input → transform → validate → output, with full lineage

**Phase 2**
- Automated regression testing for all validation rules on each release
- Rule change management process aligned with ESMA and NCA guidance updates
- Schema versioning to support AIFMD 2.0 transition without disrupting current submissions

---

### 4.3 AI System Design — Scope, Boundaries & Technical Implementation

The CTO/CPO owns **AI system design**: what AI components exist, what they are permitted to do, and how they are technically implemented, monitored and constrained.

**This is distinct from AI oversight**, which is owned by the Head of Compliance & Risk and covers independent validation that AI usage stays within the regulatory and product boundary the CTO has designed.

| AI Responsibility | Owner |
|---|---|
| **Design the AI boundary: define permitted use cases, inputs, outputs** | **CTO** |
| **Implement AI components: models, prompts, pipelines, versioning** | **CTO** |
| **Technical monitoring: model drift, accuracy, retraining triggers** | **CTO** |
| Independent oversight: validate AI usage stays within the permitted boundary | Head of Compliance & Risk |
| Regulatory assessment: AI Act classification, audit readiness of AI components | Head of Compliance & Risk |

**Phase 1**
- Document and publish the AI boundary definition: permitted use cases, prohibited use cases, technical constraints
- Implement model versioning and change logging for all AI components
- Ensure every AI output passes the deterministic validation gate before use in any submission
- Provide the AI component inventory to Head of Compliance & Risk for independent oversight

**Phase 2**
- Formal model monitoring framework: drift detection, accuracy tracking, retraining triggers
- AI component change process: no AI change deployed to production without documented impact assessment
- Technical implementation of EU AI Act requirements (as classified by Head of Compliance & Risk)

---

### 4.4 Data Architecture Ownership

Data ownership within Project Eagle is divided across three roles. The CTO owns **data architecture**:

| Data Domain | Owner |
|---|---|
| **Data architecture — data model, schema, versioning, lineage** | **CTO** |
| Data operations — ingestion, pipeline execution, delivery | COO |
| Data correctness — regulatory accuracy of content | Head of Compliance & Risk |

**Phase 1**
- Define the canonical data model: field definitions, types, version control, lineage tracking
- Design the schema to support current ESMA XSD requirements and be extensible for AIFMD 2.0
- Ensure the data model enforces the single source of truth principle: one canonical record, all processes read from it
- Publish the data model as a shared reference for COO (operations) and Compliance (correctness validation)

**Phase 2**
- Schema versioning architecture — AIFMD 2.0 transition without disrupting current submissions
- Data model review process triggered by ESMA guidance changes
- Formal data architecture documentation maintained as a living reference

---

### 4.5 DORA Incident Response — Technical Lane

DORA incident management is a shared responsibility across three roles. The CTO owns the **technical lane**:

| Incident Lane | Owner |
|---|---|
| **Technical detection, containment & resolution** | **CTO** |
| Operational impact, client communication & SLA management | COO |
| Regulatory notification (DORA Art.18 / NIS2 Art.23) | Head of Compliance & Risk |

**Phase 1**
- Implement technical monitoring and alerting infrastructure (system health, pipeline failures, security events)
- Define the technical incident classification framework (MAJOR / SIGNIFICANT / MINOR per DORA severity criteria)
- Own technical containment and resolution for all ICT incidents
- Produce the technical incident report for consumption by COO (operational impact) and Compliance (regulatory notification)

**Phase 2**
- Formal incident response runbooks for each incident category
- Post-incident root cause analysis and remediation tracking
- Business continuity and disaster recovery (BC/DR) plan tested annually
- DORA-aligned technical evidence package maintained for regulatory use

---

### 4.6 Security, Access Control & Infrastructure Reliability

**Phase 1**
- Implement security-by-design: data isolated per client (tenant), least-privilege access, encryption in transit and at rest
- Define the role-based access control (RBAC) model and enforce it from day one
- Ensure security architecture supports SOC 2 / ISAE 3402 control requirements from launch

**Phase 2**
- Full ISO 27001 / SOC 2 control framework embedded in infrastructure design
- Penetration testing programme
- BC/DR plan with defined RTO / RPO targets
- Access control review cadence (quarterly at minimum)

---

### 4.7 Product Roadmap & Prioritisation

The CTO/CPO **owns the product roadmap** — prioritisation, sequencing and delivery commitments are decisions made by this role alone. Other functions define the constraints within which the roadmap must operate; they do not co-own or direct it.

| Function | Constraint they provide | What it is NOT |
|---|---|---|
| Head of Compliance & Risk | Regulatory deadlines and mandatory framework changes (AIFMD 2.0, DORA, AI Act) | Roadmap direction or feature ownership |
| CRO | Commercial constraints — revenue impact of capability gaps, ICP-fit requirements | Feature requests or deal-driven commitments |
| COO | Operational constraints — process bottlenecks that the product must resolve to scale | Process change requests that bypass prioritisation |
| CFO | Financial constraints — investment envelope, sequencing by ROI | Budget approval for individual features |
| CEO | Strategic constraints — market positioning, adjacency decisions, build vs. buy | Day-to-day backlog management |

**Phase 1**
- Own the product backlog and sprint priorities — sole decision-maker on what is built, in what order
- Gather constraints from all functions via a structured input process; translate them into prioritised functional specifications
- Maintain the roadmap as a published, versioned document — visible to the whole leadership team, owned by CTO/CPO
- Enforce scope discipline: configuration handles client variation; bespoke development requires explicit CEO sign-off

**Phase 2**
- Quarterly roadmap review: CTO/CPO presents the roadmap; other functions present their constraints; CTO/CPO decides
- Formal product council when CPO role is separated — CPO owns roadmap, CTO owns architecture; constraint input process unchanged
- 12-month rolling roadmap with a constraint log: which regulatory, commercial, operational and financial constraints have been registered, and how each has been addressed or deferred

---

### 4.8 Client-Level Technical Risk

Each client represents a distinct technical risk profile. The CTO owns **technical risk per client**:

| Client Risk Type | Owner |
|---|---|
| **Technical risk** — data model mismatch, ingestion failure, integration instability | **CTO** |
| Operational risk — SLA breach, pipeline latency, exception volumes | COO |
| Regulatory risk — incorrect submission, NCA error | Head of Compliance & Risk |
| Financial risk — revenue concentration, pricing misalignment | CFO |
| Commercial risk — contract misalignment, scope dispute | CRO |
| Relationship risk — dissatisfaction, low engagement, churn signal | Head of Customer Success |

**Phase 1**
- Maintain awareness of client-specific technical complexity: number of AIFs, NCA submissions, data formats
- Flag technical integration risks to COO before they become operational incidents
- Ensure the data model supports each client's reporting structure without bespoke architecture

**Phase 2**
- Formal client technical risk register, updated per onboarding and per major product release
- Client technical tiering: standard vs. elevated-complexity client architecture profiles

---

### 4.9 Engineering Team Leadership

**Phase 1**
- CTO covers all engineering execution in the interim (no Head of Engineering yet)
- Define code quality standards, testing practices and CI/CD pipeline from the outset
- Hire Head of Engineering as the first priority when product enters production

**Phase 2**
- Delegate day-to-day engineering execution to Head of Engineering
- CTO focus shifts to architecture, governance, roadmap and external relationships
- CPO separation at ~€2M ARR or Series A; CTO retains technical depth, CPO owns product strategy

---

## 5. Structural Position & Three Lines of Defence

Project Eagle operates a **Three Lines of Defence** model. The CTO is part of the **first line**, alongside the COO:

| Line | Role | Function |
|---|---|---|
| **First line** | **CTO + COO** | Own and operate controls embedded in technical systems and operational processes |
| Second line | Head of Compliance & Risk | Independent oversight, rule validation, AI oversight and regulatory framework |
| Third line | External audit (coordinated by CFO) | Independent assurance — SOC 2 / ISAE 3402 certification |

```
CEO
 ├── CTO / CPO  →  system + product   [1st line: technical controls]
 │    └── Head of Engineering  →  day-to-day delivery
 ├── COO        →  factory operations  [1st line: operational controls]
 ├── CFO        →  financial control   [financial thresholds & reporting]
 └── Head of Compliance & Risk  →  independent oversight  [2nd line]
                                      External Audit  [3rd line]
```

**Phase 1 combination:** One founder carries both CTO and CPO responsibilities. This is explicitly time-limited.

**Split triggers:**
- Hire **Head of Engineering** when the engineering team reaches 3+ engineers
- Separate **CPO** at approximately €2M ARR or Series A

**Relationship with Head of Compliance & Risk:** The CTO designs the system, defines the AI boundary and publishes the AI component inventory. The Head of Compliance & Risk independently validates that what is built stays within the permitted regulatory boundary. These mandates are complementary and must not collapse into each other.

---

## 6. Key Deliverables

### Phase 1
- System architecture documentation (orchestration layer, agents, data model, API contracts)
- Canonical data model v1.0 — published as shared reference
- Deterministic validation engine v1.0 (ESMA rules + CSSF overrides)
- Full audit trail implementation (input → transform → validate → output)
- AI boundary definition document — published to Head of Compliance & Risk
- AI component inventory and governance documentation
- Security architecture: tenant isolation, RBAC, encryption
- DORA technical incident classification framework and monitoring infrastructure

### Phase 1.5
- Head of Engineering hired and onboarded
- Regression test suite for validation rules
- AIFMD 2.0 technical readiness assessment
- DORA incident response runbooks v1

### Phase 2
- Schema versioning architecture for AIFMD 2.0 transition
- AI governance policy — technical implementation layer
- ISO 27001 / SOC 2 technical controls embedded
- BC/DR plan with tested RTO/RPO
- CPO separation planning and knowledge transfer

---

## 7. Guiding Principles

> **Principle 1 — Customer experience first:** Simplicity, reliability and predictability over customisation. For the CTO, this means every architectural decision is evaluated against whether it makes the product more auditable, more explainable and more trustworthy to AIFM compliance officers — the people who ultimately stake their professional reputation on Eagle's outputs.

> **Principle 2 — Code-first, human-by-exception:** All processes run through a central orchestration layer; humans intervene only for exceptions, judgement and improvement. This is the foundational design philosophy of the Eagle system: the validation engine runs without human intervention; humans review only flagged exceptions and approve regulated outputs.

> **Principle 4 — Single source of truth:** One canonical data model; quality, lineage and ownership are explicit and controlled. The CTO defines and publishes this model as a shared reference for all downstream processes. No process holds its own copy of a data point; all derive from the canonical record.

> **Principle 5 — Deterministic core, probabilistic edge:** Calculations and compliance logic are deterministic; AI is used only for interpretation, transformation and optimisation.

> **Principle 7 — Resilience:** The system is operationally resilient; no single point of failure; security is structural, not bolted on.

> **Principle 9 — Security by design:** Data is isolated per client, access is least-privilege by default, and all data is encrypted in transit and at rest.

> **Principle 10 — Founder-independent by design:** All knowledge, rules and processes are fully codified in systems, enabling independence within two years of launch.

> **Principle 11 — Continuous learning system:** Every process generates feedback data used to systematically improve models, rules and outputs.

> **Principle 14 — Database-first:** All operational state, metrics, scores and reports are stored in the database as first-class records; file exports (PDF, CSV, JSON) are generated views of database data, never the system of record; no loose extract workflows. The CTO is the architectural owner of this principle: the canonical data model, the audit trail and all submission records are database-native, and any component that writes to a file as its primary system of record is a design violation requiring CTO-level remediation.

> **Principle 15 — Platform-first, product-second:** Platform capabilities (multi-tenancy, IAM, audit trail, pipeline orchestration, AI layer, management intelligence) are product-agnostic; regulatory product logic (validation rules, NCA overrides, canonical models, submission channels) is isolated in product modules and replaceable without platform changes. The CTO enforces this boundary: adding a new regulatory reporting product must never require changes to any platform module. Architecture decisions that blur the platform/product boundary require explicit CTO sign-off.

> **Principle 16 — Location-independent by design:** System architecture, tooling choices and engineering workflows must support a fully distributed team. Access controls, development environments, deployment pipelines and monitoring dashboards are designed to be operated from any location — not from a shared office or a single machine.

---

## 8. Key Technical Risks & Mitigations

| Risk | Mitigation |
|---|---|
| AIFMD 2.0 XSD schema changes break existing submissions | Schema versioning built into architecture from day 1; readiness assessment by Phase 1.5 |
| AI component produces incorrect transformation, enters submission | Deterministic validation gate mandatory; AI output and validation result both logged |
| AI boundary drift — AI used beyond its permitted scope | CTO publishes boundary definition; Head of Compliance & Risk independently monitors compliance with it |
| Vendor lock-in limits future architectural flexibility | Modularity principle enforced: all components replaceable; no exclusive single-vendor dependency |
| Security breach exposes client regulatory data | Tenant isolation, encryption, least-privilege access, DORA incident response — all structural |
| Scope creep erodes standardised product model | CTO enforces configuration-not-customisation; bespoke requests escalated to CEO |

---

## 9. Key Insight

> The system is the product. Architectural decisions made in Phase 1 determine the ceiling of what is achievable in Phase 2 and beyond.
