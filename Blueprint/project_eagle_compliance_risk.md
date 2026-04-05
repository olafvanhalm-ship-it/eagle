# Project Eagle — Head of Compliance & Risk
## Role Proposal & Mandate (Phase-aware with early certification)
**Version 1.4 | Confidential**

---

## 1. Context & Strategic Rationale

Project Eagle is an AI-native regulatory reporting factory, purpose-built to serve Alternative Investment Fund Managers (AIFMs) in meeting their obligations under AIFMD Annex IV. The product is deterministic at its core: compliance logic is codified, auditable and explainable. AI augments interpretation and transformation but never makes regulated decisions autonomously.

This philosophy makes the Head of Compliance & Risk not just a gatekeeper — but a **structural co-designer** of the product itself.

The mandate of this role is fourfold:

1. **Framework ownership** — build and maintain the compliance and risk infrastructure
2. **Independent oversight** — provide the second line of defence: validate that what is built and operated stays within the regulatory and ethical boundary
3. **Trust signal** — enable rapid client adoption through auditability and early certification
4. **Regulatory notification** — own the regulatory reporting obligations triggered by incidents, breaches or changes in the operating environment

---

## 2. Strategic Design Choice: Early Certification

Given the target client base (AIFMs), **external trust must be established rapidly after launch**.

Therefore:

> **Design for certification from day 1, certify as early as feasible post-launch.**

- Controls and audit trails are designed upfront
- The organisation is audit-ready by design
- Certification (SOC 2 / ISAE 3402 Type I) follows shortly after first clients

---

## 3. Regulatory Landscape

The role operates at the intersection of the following legal and technical frameworks:

| Framework | Relevance |
|---|---|
| Directive 2011/61/EU (AIFMD), Articles 3(3)(d), 24(1), 24(2), 24(4) | Core reporting obligations for AIFMs |
| Commission Delegated Regulation (EU) No 231/2013, Articles 2, 10, 110–127 | Detailed rules on data content and frequency |
| ESMA Guidelines on AIFMD Reporting (ESMA/2014/869rev) | Interpretive guidance on Annex IV submissions |
| ESMA DQEF (ESMA50-1605533872-8305, May 2025) | Data quality error framework and CAF/CAM error codes |
| IT Technical Guidance Revision 6 (applicable from 22 Nov 2023) | XSD schema and technical submission standards |
| AIFMD 2.0 (OJ March 2024, in force April 2024) | Member states must apply new rules by **16 April 2026**; new ESMA XSD schemas expected ~April 2027 |
| DORA (Digital Operational Resilience Act) | ICT incident regulatory notification — DORA Art.18 (client NCA reporting) and NIS2 Art.23 (Eagle's own NCSC reporting) |
| GDPR / applicable data protection regulation | Client data handling, retention and privacy obligations |
| EU AI Act | AI component classification, documentation obligations, governance requirements |
| ISAE 3402 / SOC 2 | External assurance standards for service organisations |

> ⚠️ **Immediate priority:** AIFMD 2.0 implementation deadline is 16 April 2026. Horizon scanning and readiness planning for the updated technical and regulatory standards must begin at launch.

---

## 4. Responsibilities (Phase-aware)

### 4.1 Compliance Framework

**Phase 1**
- Define and codify core validation rules with full traceability to regulatory source (rule ID → framework article)
- Maintain a simple change log: every rule change is dated, attributed and reasoned
- Publish the compliance framework as the reference document for CTO (implementation) and COO (operations)

**Phase 2**
- Full governance cycles with formal review cadence
- NCA override governance: version-controlled profiles, documented rationale, review triggers
- Regulatory horizon scanning programme: ESMA, AIFMD 2.0, ESG reporting, AI Act — translated into **regulatory constraints** for the CTO/CPO's roadmap, not into roadmap direction. The Head of Compliance & Risk defines what must be built and by when (the regulatory envelope); the CTO/CPO decides how and in what sequence.

---

### 4.2 Internal Controls & Auditability

**Phase 1**
- Define the control framework: which controls exist, who operates them, and what evidence they produce
- Validate that the full audit trail (input → transform → validate → output) is in place and complete
- Ensure all documented decisions are traceable — no black-box steps anywhere in the pipeline

**Phase 2**
- Full ISAE 3402 / SOC 2 evidence framework: control objectives, control descriptions, evidence collection
- Continuous audit readiness: controls are evidenced as a matter of routine, not assembled for audit
- Formal control review cadence aligned with certification renewal

---

### 4.3 Risk Management

**Phase 1**
- Maintain a simple risk register covering operational, technological and regulatory risk
- Define escalation triggers: which risk events require immediate escalation to CEO, and which can be managed within the role
- Ensure risk register is a living document — updated at each reporting period and after any incident

**Phase 2**
- Formal risk appetite statement approved by CEO / board
- Quarterly risk reviews with structured reporting
- Risk taxonomy aligned with ISAE / SOC 2 control framework

---

### 4.4 AI Oversight — Second Line

The Head of Compliance & Risk owns **AI oversight**: independent validation that AI components stay within the boundary defined and implemented by the CTO. This is explicitly distinct from AI design, which is owned by the CTO.

| AI Responsibility | Owner |
|---|---|
| Design the AI boundary: permitted use cases, inputs, outputs, technical constraints | CTO |
| Implement AI components: models, prompts, pipelines, versioning, monitoring | CTO |
| **Independent oversight: validate that AI usage stays within the permitted boundary** | **Head of Compliance & Risk** |
| **Regulatory assessment: EU AI Act classification, audit documentation of AI components** | **Head of Compliance & Risk** |
| **Rule: AI never produces final regulatory output; all AI output passes deterministic validation** | **Head of Compliance & Risk (enforcement)** |

**Phase 1**
- Receive and review the AI boundary definition published by the CTO
- Independently validate that AI components operate within the stated boundary — through audit log review, not re-implementation
- Maintain the AI component register (sourced from CTO inventory) with compliance annotations: risk level, regulatory classification, oversight status
- Flag any AI usage that approaches or exceeds the permitted boundary — escalate to CEO if unresolved

**Phase 2**
- EU AI Act classification assessment for all AI components in the pipeline
- Formal AI governance policy: roles, responsibilities, change process, incident protocol
- Periodic independent testing: sample AI outputs against expected deterministic results
- AI oversight evidence incorporated into SOC 2 / ISAE 3402 audit documentation

---

### 4.5 Data Correctness Ownership

Data ownership within Project Eagle is divided across three roles. The Head of Compliance & Risk owns **data correctness**:

| Data Domain | Owner |
|---|---|
| Data architecture — data model, schema, versioning, lineage | CTO |
| Data operations — ingestion, pipeline execution, delivery | COO |
| **Data correctness — regulatory accuracy of content in every submission** | **Head of Compliance & Risk** |

**Phase 1**
- Define what "correct" means for each Annex IV field: regulatory source, permitted values, cross-field dependencies
- Validate that the CTO's data model reflects the regulatory definition of each field accurately
- Review validation rule outputs for a sample of submissions each period — not to re-validate operationally, but to confirm the rules are working as designed
- Escalate any data correctness question raised by the COO (operations) — do not leave the COO to self-adjudicate regulatory content

**Phase 2**
- Formal data correctness review programme: sampled review per reporting period, documented findings
- Data correctness sign-off as part of the internal approval gate before NCA submission
- Correctness issues tracked in the risk register with root cause and remediation

---

### 4.6 DORA Incident Response — Regulatory Notification Lane

DORA incident management is a shared responsibility across three roles. The Head of Compliance & Risk owns the **regulatory notification lane**:

| Incident Lane | Owner |
|---|---|
| Technical detection, containment & resolution | CTO |
| Operational impact, client communication & SLA management | COO |
| **Regulatory notification — DORA Art.18 / NIS2 Art.23** | **Head of Compliance & Risk** |

**Phase 1**
- Own the regulatory notification workflow: structured authority notification reports for DORA Art.18 (supporting client NCA reporting) and NIS2 Art.23 (Eagle's own NCSC reporting)
- Define the two notification streams and ensure they are operationally ready before first client goes live:
  - **DORA Art.18** — supporting the client AIFM's own NCA notification obligation
  - **NIS2 Art.23** — Eagle's own full three-stage notification lifecycle to NCSC:
    - **Stage 1 — Early warning** (Art.23(1)(a)): within 24 hours of becoming aware of a significant incident — indication of suspected unlawful/malicious cause and potential cross-border impact
    - **Stage 2 — Incident notification** (Art.23(1)(b)): within 72 hours — initial severity and impact assessment, indicators of compromise where available
    - **Stage 3 — Final report** (Art.23(1)(c)): within 1 month of Stage 2 submission — detailed incident description, root cause / threat type, applied and ongoing mitigation measures, cross-border impact; reviewed and signed off by Head of Compliance & Risk before submission
    - **Interim report** (Art.23(1) in fine): if the incident is still ongoing when the 1-month deadline is reached, an interim report is submitted at that point and a final report within 1 month of incident closure
    - **CSIRT extension** (Art.23(3)–(4)): if additional time is needed for the 72-hour notification, submit a reasoned extension request to NCSC/CSIRT before the deadline expires; document the grant reference on the incident dossier
- Make the significance threshold decision (NIS2 Art.23(3)) — whether an incident meets the criteria for severe operational disruption or considerable damage to third parties — before authorising any NIS2 submission (not automatable; NA-004)
- Consume the technical incident report from CTO and the operational impact assessment from COO to produce the regulatory notification
- Maintain the regulatory notification log: all incidents classified, all notifications filed, all deadlines met across all three stages

**Phase 2**
- Formal regulatory incident reporting procedure with defined timelines and templates for all three NIS2 stages
- MAJOR incident: Stage 1 early warning available within 4 hours (aligned with DORA Art.18 window + NIS2 24h requirement)
- Post-incident regulatory review: lessons learned, regulatory disclosure obligations, remediation tracking
- Regulatory notification evidence (all three stages) incorporated into SOC 2 / ISAE 3402 audit documentation

---

### 4.7 Client-Level Regulatory Risk

Each client represents a distinct regulatory risk profile. The Head of Compliance & Risk owns **regulatory risk per client**:

| Client Risk Type | Owner |
|---|---|
| Operational risk — SLA breach, pipeline failure, data latency | COO |
| Technical risk — data model mismatch, integration instability | CTO |
| Financial risk — revenue concentration, pricing misalignment | CFO |
| Commercial risk — contract misalignment, scope dispute | CRO |
| Relationship risk — dissatisfaction, low engagement, churn signal | Head of Customer Success |
| **Regulatory risk — incorrect submission, NCA error, compliance breach, client-specific override** | **Head of Compliance & Risk** |

**Phase 1**
- Maintain a per-client regulatory risk profile: reporting regime, NCA registrations, applicable overrides, known complexity factors
- Flag clients where regulatory complexity is elevated (e.g. multiple NCAs, non-standard reporting structures, AIFMD 2.0 transition impact)
- Own the consequence assessment for any submission error: what is the regulatory exposure for the client AIFM, and what is Eagle's obligation?
- Define the internal threshold: at what point does a submission error require client notification, NCA disclosure, or escalation to CEO?

**Phase 2**
- Formal client regulatory risk register updated per reporting period
- Client regulatory tiering: standard vs. elevated-complexity clients requiring enhanced oversight
- Client-specific compliance review for onboarding of any new client with non-standard reporting requirements
- Regulatory consequences framework: documented escalation path for errors at each severity level

---

### 4.8 External Audit & Certification

**Phase 1**
- Design controls aligned with SOC 2 / ISAE 3402 requirements from day one — audit-ready by design, not by retrofit
- Select auditor (coordinate engagement and cost with CFO)
- Produce the certification roadmap: control objectives, evidence approach, timeline

**Post-launch**
- Initiate SOC 2 / ISAE 3402 Type I certification immediately after first clients are live
- Target: Type I within first operating period

**Phase 2**
- Type II certification
- Continuous audit readiness: evidence collected as routine, not assembled for audit
- Certification scope reviewed annually for alignment with regulatory and product changes

---

## 5. Structural Position & Three Lines of Defence

The Head of Compliance & Risk is the **second line of defence** — structurally independent from the first line (CTO and COO) and the coordinator of the third line (external audit, engaged and funded via CFO).

| Line | Role | Function |
|---|---|---|
| First line | CTO + COO | Own and operate controls embedded in technical systems and operational processes |
| **Second line** | **Head of Compliance & Risk** | **Independent oversight, rule validation, AI oversight, regulatory framework, data correctness** |
| Third line | External audit — coordinated by CFO | Independent assurance — SOC 2 / ISAE 3402 certification |

```
CEO
 ├── CTO / CPO  →  system + product          [1st line: technical controls]
 ├── COO        →  factory operations         [1st line: operational controls]
 ├── CFO        →  financial control          [financial thresholds + 3rd line coordination]
 └── Head of Compliance & Risk               [2nd line: independent oversight]
                   External Audit             [3rd line, CFO-coordinated]
```

**Independence in Phase 1** is ensured via structural separation of responsibilities:
- The CTO designs the system; Compliance independently validates it
- The COO operates the pipeline; Compliance independently validates its outputs
- The CFO coordinates external audit; Compliance defines what is audited

This independence must be preserved even when multiple roles are combined in a founder. If the CTO and Head of Compliance & Risk are the same person in Phase 1, that overlap must be explicitly acknowledged and mitigated through documented decision trails and external review.

---

## 6. Key Deliverables

### Phase 1
- Validation rules v1.0 — with full regulatory traceability
- Audit trail validation (confirm CTO implementation meets the control framework)
- Risk register v1.0
- Certification roadmap
- AI boundary review — receive from CTO, annotate with compliance assessment
- AI component register (compliance-annotated)
- Client regulatory risk profiles (all onboarded clients)
- DORA regulatory notification workflow (both streams: Art.18 + NIS2 Art.23 — all three stages: 24h early warning, 72h notification, 1-month final report)
- Data correctness definition — field-by-field regulatory reference

### Phase 1.5
- Auditor selected; certification initiated
- DORA regulatory notification procedure — tested and documented (NIS2: all three stages tested including interim-report scenario and CSIRT extension request flow)
- Client regulatory tiering v1 (standard vs. elevated-complexity)
- AIFMD 2.0 regulatory readiness assessment (parallel to CTO technical assessment)

### Phase 2
- SOC 2 / ISAE 3402 Type I certification completed
- Type II certification initiated
- AI governance policy (EU AI Act aligned)
- Formal client regulatory risk register
- Full ISAE / SOC 2 evidence framework
- Governance expanded: NCA override governance, formal review cadence, risk appetite statement

---

## 7. Guiding Principles

> **Principle 5 — Deterministic core, probabilistic edge:** Calculations and compliance logic are deterministic; AI is used only for interpretation, transformation and optimisation. This role ensures that boundary is maintained — independently of the team that built it.

> **Principle 7 — Resilience:** Every compliance process — and in particular the DORA Art.18 / NIS2 Art.23 regulatory notification workflow — has defined failure modes, fallback procedures and delegated authorities. The 24-hour early warning and 72-hour incident notification obligations cannot depend on a single individual being available. Resilience for this role means the regulatory notification lane is always staffed, documented and executable regardless of personnel availability.

> **Principle 8 — Compliance-proof by design:** Compliance logic is deterministic, auditable and explainable; AI supports but never decides. This role is accountable for evidencing that commitment to external auditors and clients.

> **Principle 9 — Security by design:** Security is a structural property of all systems; data is isolated per client, access is least-privilege by default, and all data is encrypted in transit and at rest. This role validates the compliance implications of the security architecture.

> **Principle 10 — Founder-independent by design:** All knowledge, rules and processes are fully codified in systems, enabling independence within two years of launch. This role ensures the compliance framework is documented and operable independently of any individual.

> **Principle 14 — Database-first:** All operational state, metrics, scores and reports are stored in the database as first-class records; file exports (PDF, CSV, JSON) are generated views of database data, never the system of record. The Head of Compliance & Risk validates that the audit trail — as the primary evidence layer for SOC 2 / ISAE 3402 and regulatory enquiries — is implemented as a database-native, immutable record and not as a loose file-based extract workflow.

> **Principle 15 — Platform-first, product-second:** Platform capabilities, including the audit trail layer and AI oversight register, are product-agnostic and must not be entangled with AIFMD-specific product logic. The Head of Compliance & Risk validates that compliance controls and oversight mechanisms are portable across regulatory reporting products — consistent with the platform-first architecture boundary owned by the CTO.

> **Principle 16 — Location-independent by design:** All compliance processes — rule validation, risk register maintenance, regulatory notifications and external audit coordination — are designed to be fully executable from any location. The time-critical DORA Art.18 / NIS2 Art.23 notification workflow (early warning within 24 hours) and the ISAE 3402 evidence collection process must not depend on physical presence or access to a shared office environment. Async-first documentation is an operational requirement for this role, not a preference.

These principles are not aspirational — they are enforceable commitments that this role is responsible for upholding, evidencing and defending to external parties.

---

## 8. Key Insight

> The second line is only credible if it is genuinely independent. Independence is structural, not attitudinal — it is built into how responsibilities are divided, not into how collaboratively people work.
