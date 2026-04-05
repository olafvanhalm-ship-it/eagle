# Project Eagle — Software Architecture

**Version:** 1.5
**Date:** 2026-04-03
**Owner:** CTO / CPO
**Status:** Draft — derived from Blueprint v1.0 (baselined 2026-03-23) and Developer Security Guidelines v2.0; updated for dual canonical module structure (2026-04-03)
**Scope:** Complete technical architecture for the Eagle multi-product regulatory reporting platform with AIFMD Annex IV as the initial product.

---

## Table of Contents

1. [Architecture Principles](#1-architecture-principles)
2. [System Overview](#2-system-overview)
3. [Infrastructure Layer (AWS)](#3-infrastructure-layer-aws)
4. [Multi-Tenancy Architecture](#4-multi-tenancy-architecture)
5. [Pipeline Architecture (L1–L11)](#5-pipeline-architecture-l1l11)
6. [Database Architecture](#6-database-architecture)
7. [API Layer](#7-api-layer)
8. [AI Boundary Architecture](#8-ai-boundary-architecture)
9. [Security and IAM Architecture](#9-security-and-iam-architecture)
10. [Module Architecture](#10-module-architecture)
11. [Platform–Product Isolation](#11-platformproduct-isolation)
12. [Deployment and CI/CD](#12-deployment-and-cicd)
13. [Observability and Operations](#13-observability-and-operations)
14. [Resilience and Disaster Recovery](#14-resilience-and-disaster-recovery)
15. [Principle Traceability Matrix](#15-principle-traceability-matrix)

---

## 1. Architecture Principles

The architecture is governed by 16 principles (P1–P16) defined in the Blueprint. The following are the architectural implications that drive every design decision in this document.

**P5 — Deterministic core, probabilistic edge.** AI (Claude) operates exclusively at L2 for extraction and transformation. All compliance logic (L3 validation, L4 DQEF, L6 packaging) is deterministic, rule-based, and version-controlled. AI output never flows to an NCA submission without passing the deterministic gate at L3 and the human review gate at L5.

**P6 — Modular and portable.** Validation rules, NCA override profiles, canonical data model schemas, packaging configuration, smart defaults, and the product registry are all version-controlled configuration files loaded at runtime — never hard-coded. Replacing the AI model is a configuration change, not a code change (REQ-MOD-002).

**P9 — Security by design.** Row-level security enforces tenant isolation at the database layer. All data encrypted in transit (TLS 1.3) and at rest (AES-256 via AWS KMS). Least-privilege IAM with five predefined roles. NCA credentials stored in an encrypted vault with per-session retrieval and dual-scope resolution (service-provider-level or AIFM-specific). All engineers complete mandatory security training (ST-001..003) before contributing code.

**P14 — Database-first.** All operational state, metrics, scores, and reports are stored in PostgreSQL as first-class records. File exports (PDF, CSV, JSON, XML) are generated views of database data — never the system of record.

**P15 — Platform-first, product-second.** Platform capabilities (multi-tenancy, IAM, audit trail, pipeline orchestration, AI layer, management intelligence) are product-agnostic. AIFMD-specific logic is isolated in product modules. Adding a new regulatory reporting product must not require changes to any platform module (REQ-ARCH-001).

---

## 2. System Overview

### 2.1 High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    USERS & ENTRY POINTS                                          │
│                                                                                                  │
│  Client Users                    Eagle Team                     External                         │
│  TENANT_ADMIN                    EAGLE_ADMIN                    API Clients (REST)               │
│  COMPLIANCE_REVIEWER             COO · CFO · CRO                Service Providers                │
│  DATA_PREPARER · READ_ONLY       CCO · CCO_DELEGATE             White-label Partners             │
└──────────┬───────────────────────────┬───────────────────────────────┬────────────────────────────┘
           │          Browser          │        Browser                │    REST API / SFTP
           ▼                           ▼                               ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│  EAGLE PLATFORM  ──  AWS eu-west-1  ──  ECS Fargate  ──  Aurora PostgreSQL  ──  S3              │
│                                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────────────────────────┐ │
│  │ ACCESS LAYER          ALB (TLS 1.3 · WAF · CloudFront)      SFTP (AWS Transfer Family)     │ │
│  └────────────────────────────────┬────────────────────────────────────┬────────────────────────┘ │
│                                   │                                    │                          │
│  ┌────────────────────────────────▼────────────────────────────────────▼────────────────────────┐ │
│  │ APPLICATION TIER (ECS Fargate)                                                              │ │
│  │    Next.js Frontend (SSR)                    FastAPI Backend (Python 3.12+)                  │ │
│  └─────────────────────────────────────────────────────┬───────────────────────────────────────┘ │
│                                                        │                                         │
│  ┌─────────────────────────────────────────────────────▼───────────────────────────────────────┐ │
│  │ FUNCTIONAL MODULES                                                                         │ │
│  │                                                                                            │ │
│  │  Client-Facing              Internal Eagle            Commercial                           │ │
│  │  ┌──────────────────────┐   ┌──────────────────────┐  ┌──────────────────────┐             │ │
│  │  │ MOD-CLIENT           │   │ MOD-ADMIN            │  │ MOD-GTM              │             │ │
│  │  │ Compliance Portal    │   │ Internal Operations  │  │ Go-to-Market         │             │ │
│  │  ├──────────────────────┤   ├──────────────────────┤  ├──────────────────────┤             │ │
│  │  │ MOD-TRIAL            │   │ MOD-MANAGEMENT       │  │ MOD-BILLING          │             │ │
│  │  │ Trial Onboarding     │   │ Company Intelligence │  │ Subscriptions (v1.5) │             │ │
│  │  └──────────────────────┘   └──────────────────────┘  └──────────────────────┘             │ │
│  │                                                                                            │ │
│  │  Reporting Pipeline ── AIFMD Annex IV                                                      │ │
│  │  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐       │ │
│  │  │ MOD-DATA         │ │ MOD-COMP         │ │ MOD-REVIEW       │ │ MOD-SUB          │       │ │
│  │  │ Data Ingest & AI │ │ Validation Engine│ │ Human Review Gate│ │ Packaging & NCA  │       │ │
│  │  │ L1 · L1B · L2   │ │ L3 · L4          │ │ L5               │ │ L6 · L7          │       │ │
│  │  └──────────────────┘ └──────────────────┘ └──────────────────┘ └──────────────────┘       │ │
│  │                                                                                            │ │
│  │  Platform API                                                                              │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐                       │ │
│  │  │ MOD-API  ──  External REST API · OAuth 2.0 · OpenAPI 3.0 · L10 │                       │ │
│  │  └──────────────────────────────────────────────────────────────────┘                       │ │
│  └────────────────────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ CROSS-CUTTING PLATFORM SERVICES                                                           │  │
│  │                                                                                           │  │
│  │ MOD-AUDIT ── L8        L9 Orchestration            L11 IAM                                │  │
│  │ Immutable Audit Trail  SQS + PG State Machine       Cognito (SRP + TOTP MFA)              │  │
│  │ Field Lineage          State Machine · SLO          RLS · RBAC · Credential Vault         │  │
│  │ ISAE 3402 · SOC 2     Auto-scaling Workers          GDPR · DORA · ISO 27001              │  │
│  └────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ DATA & INFRASTRUCTURE                                                                     │  │
│  │                                                                                           │  │
│  │ Aurora PostgreSQL       SQS Queues              S3 Buckets             Secrets Manager     │  │
│  │ RLS · KMS (IS-003)      Pipeline Stages         Submissions · Archive  + 1Password Teams  │  │
│  │ Multi-AZ · Read Replica DLQ · FIFO Sequencing   Object Lock · Glacier  RL-001 · RL-006    │  │
│  └────────────────────────────────────────────────────────────────────────────────────────────┘  │
│                                                                                                  │
│  ┌────────────────────────────────────────────────────────────────────────────────────────────┐  │
│  │ SECURITY & CI/CD                                                                          │  │
│  │                                                                                           │  │
│  │ CI/CD ── 11 Gates (G1–G11)    Container Signing         Observability                     │  │
│  │ GitHub Actions · OIDC          cosign (ECDSA P-256)     CloudWatch · Container Insights    │  │
│  │ CodeQL · Trivy · Checkov · ZAP CycloneDX SBOM (SRI-002) CloudTrail · Structured Logging   │  │
│  └────────────────────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
           │                              │                                    │
           ▼                              ▼                                    ▼
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                                    EXTERNAL SYSTEMS                                              │
│                                                                                                  │
│  Reference Data               Anthropic Claude API          NCA Portals             AWS          │
│  GLEIF (LEI-lookup)           AI Transformation (L2)        CSSF · AFM · BaFin      ECS · RDS   │
│  ECB (FX rates)               EU Endpoints                  Direct API · Robot      S3 · SQS    │
│  ESMA (Codelists · DQEF)     Structured output (SC-014)    SFTP · S3 · Manual      KMS · IAM   │
│  ── inbound → L1B, L3        ── bidirectional → L2         ── outbound → L7        Cloud Host   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘

  REPORTING PIPELINE FLOW
  L1 Ingest → L1B Legacy Adapters → L2 AI Transform → L3 Validate → L4 DQEF → L5 Review → L6 Package → L7 Deliver
              │                      │ SC-014          │ Deterministic │        │ APPROVED  │ XML/CSV   │ NCA
              │ M/ESMA               │ RL-005          │ Rules Only    │ Quality│ Required  │ Packaging │ Submission
              │ Template Conversion  │ Human Confirm   │ No AI         │ Scores │ No Bypass │ SRI-001   │ Multi-channel
```

*Figuur 1 — Eagle platformarchitectuur: modules, gebruikersrollen, pipeline-lagen en externe integraties (v1.2)*

### 2.2 Technology Stack

| Layer | Technology | Rationale |
|---|---|---|
| Frontend | Next.js 14+ (App Router) on ECS Fargate | Server-side rendering for compliance dashboards; React component model for complex validation UIs |
| Backend API | FastAPI (Python 3.12+) on ECS Fargate | Async-native; Pydantic for schema validation; OpenAPI 3.0 auto-generated |
| Database | PostgreSQL 16 (Amazon Aurora) | Row-level security for multi-tenancy; JSON columns for flexible canonical records; 10-year audit retention |
| Queue | Amazon SQS (Standard + FIFO) | Durable message queues for pipeline stages; dead-letter queues; native AWS integration |
| Object Storage | Amazon S3 | Submission files, SFTP staging, source documents, report archives |
| AI | Anthropic Claude API (EU endpoints) | L2 transformation only; model-agnostic interface per REQ-MOD-002 |
| Authentication | Amazon Cognito | User pools with SRP protocol; TOTP MFA (not SMS); 1h access tokens, 30d refresh tokens (SC-003) |
| Secrets | AWS Secrets Manager + 1Password Teams | Secrets Manager for runtime secrets (ECS secretsFrom); 1Password for team credential vault (RL-001) |
| Workflow Engine | SQS + PostgreSQL state machine | Pipeline orchestration via SQS message routing and PostgreSQL-persisted state transitions; explicit retry policies per SC-013; no external workflow cluster required |
| Monitoring | Amazon CloudWatch (Container Insights + Logs + Alarms) | Operational metrics, SLA monitoring, alerting; native AWS — no additional infrastructure. Grafana/Prometheus can be added later if monitoring needs outgrow CloudWatch |
| CI/CD | GitHub Actions (OIDC → AWS) | 11 mandatory gates (G1–G11); OIDC-based deployment — no long-lived CI/CD credentials (RL-004) |
| Image Signing | cosign (Sigstore) | ECDSA P-256 container image signing; signature verified at Fargate deploy (SRI-001) |
| IaC Scanning | Checkov | Terraform and Dockerfile policy enforcement; blocks port-22, missing encryption, unpinned actions (G8) |
| SAST | CodeQL (GitHub GHAS) | Static analysis with push protection for secret scanning (G4/G5) |
| DAST | OWASP ZAP | Active scan against staging mapped to OWASP Top 10:2025; runs before every production release (G10) |
| Container Scanning | Trivy | Image vulnerability scan + CycloneDX SBOM generation per build (G7/SRI-002) |
| Endpoint Security | CrowdStrike Falcon Go | Mandatory on all developer devices; Google Workspace MDM enrolment (EL-006) |
| SFTP | AWS Transfer Family | Managed SFTP with tenant-scoped paths |
| CDN/Edge | Amazon CloudFront | Static asset delivery; WAF integration |
| Container Registry | Amazon ECR | Private Docker image registry |

### 2.3 Module-to-Service Mapping

Eagle follows a **modular monolith** architecture within the backend service. Each module (MOD-ADMIN, MOD-CLIENT, MOD-DATA, etc.) is a Python package within the FastAPI application with strict import boundaries enforced by architectural fitness tests. This avoids the operational complexity of microservices for a small team while preserving the ability to extract services later.

```
eagle-backend/
├── app/
│   ├── platform/              # Product-agnostic platform layer
│   │   ├── iam/               # L11 — Identity, access, tenant management
│   │   ├── orchestration/     # L9 — Pipeline orchestration, queues, state machine
│   │   ├── audit/             # L8 — Immutable audit trail, lineage
│   │   ├── api_gateway/       # L10 — External API routing, auth, rate limiting
│   │   ├── notifications/     # Cross-cutting notification dispatch
│   │   ├── management/        # MOD-MANAGEMENT — company intelligence views
│   │   └── ai/               # AI abstraction layer (model-agnostic interface)
│   │
│   ├── products/              # Product-specific modules (REQ-ARCH-001)
│   │   └── aifmd/             # AIFMD Annex IV product
│   │       ├── ingestion/     # L1 — Data ingestion channels
│   │       ├── adapters/      # L1B — Legacy template adapters
│   │       ├── transformation/# L2 — AI transformation + deterministic derivation
│   │       ├── validation/    # L3 — Deterministic validation core
│   │       ├── quality/       # L4 — DQEF quality layer
│   │       ├── review/        # L5 — Human review gate
│   │       ├── packaging/     # L6 — NCA file packaging
│   │       ├── submission/    # L7 — NCA delivery channels
│   │       ├── models/        # Canonical data model (Pydantic + SQLAlchemy)
│   │       └── config/        # Validation rules, NCA overrides, smart defaults
│   │
│   ├── admin/                 # MOD-ADMIN — Eagle administration
│   ├── client/                # MOD-CLIENT — Client compliance portal
│   ├── gtm/                   # MOD-GTM — Go-to-market automation
│   ├── trial/                 # MOD-TRIAL — Trial account lifecycle
│   └── billing/               # MOD-BILLING — Billing (stub, Phase 1.5)
│
├── config/                    # Runtime configuration files (REQ-MOD-001)
│   ├── product_registry.yaml  # REQ-ARCH-002
│   ├── validation_rules/      # aifmd_annex_iv_validation_rules.yaml
│   ├── nca_overrides/         # Per-NCA override profiles
│   ├── smart_defaults/        # Smart default rules
│   ├── packaging/             # NCA packaging configuration
│   └── prompts/               # AI system prompts (version-controlled)
│
└── tests/
    ├── regression/            # REQ-REL-001 regression suite
    ├── integration/           # Pipeline end-to-end tests
    └── unit/                  # Per-module unit tests
```

---

## 3. Infrastructure Layer (AWS)

### 3.1 Network Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      VPC: 10.0.0.0/16                          │
│                                                                 │
│  ┌─────────────────────┐  ┌─────────────────────────────────┐  │
│  │  Public Subnets      │  │  Private Subnets                │  │
│  │  (2 AZs)            │  │  (2 AZs)                        │  │
│  │                      │  │                                  │  │
│  │  ┌────────────────┐  │  │  ┌──────────────────────────┐   │  │
│  │  │  ALB           │  │  │  │  ECS Fargate Tasks       │   │  │
│  │  │  (internet-    │──┼──┼─▶│  - Frontend service      │   │  │
│  │  │   facing)      │  │  │  │  - Backend API service   │   │  │
│  │  └────────────────┘  │  │  │  - Worker pool           │   │  │
│  │                      │  │  └──────────────┬───────────┘   │  │
│  │  ┌────────────────┐  │  │                 │               │  │
│  │  │  NAT Gateway   │  │  │  ┌──────────────▼───────────┐   │  │
│  │  │  (single, AZ1) │  │  │  │  Aurora PostgreSQL       │   │  │
│  │  └────────────────┘  │  │  │  (Multi-AZ, encrypted)   │   │  │
│  └─────────────────────┘  │  └──────────────────────────┘   │  │
│                            │                                  │  │
│                            │  ┌──────────────────────────┐   │  │
│                            │  │  Isolated Subnets        │   │  │
│                            │  │  (no internet route)     │   │  │
│                            │  │  - RDS (database layer)  │   │  │
│                            │  └──────────────────────────┘   │  │
│                            └─────────────────────────────────┘  │
│                                                                 │
│  VPC Endpoints: S3, SQS, Secrets Manager, KMS, CloudWatch,    │
│                 ECR, STS                                        │
└─────────────────────────────────────────────────────────────────┘
```

**Key decisions:**
- Two Availability Zones for cost efficiency with Aurora Multi-AZ for database resilience (RTO 4h, RPO 1h per REQ-RES-002).
- VPC endpoints for all AWS service traffic to keep data off the public internet.
- Single NAT Gateway in the primary AZ for outbound connectivity (Claude API, GLEIF, ESMA register, NCA APIs). Phase 1 cost optimisation — if the NAT Gateway AZ fails, inbound traffic (ALB) continues; outbound-dependent operations (L2 AI, L7 NCA delivery) pause until failover. Within 99.5% uptime target. **Failure detection:** CloudWatch alarm on `NatGateway` → `ErrorPortAllocation` and `PacketsDropCount > 0` metrics, plus a synthetic health check (Lambda, every 5 minutes) that verifies outbound HTTPS connectivity to `api.anthropic.com`. Alarm triggers SNS → CTO notification. **Manual failover:** Terraform variable `nat_gateway_az` can be switched and applied in <15 minutes. **Upgrade trigger:** Second NAT Gateway added when monthly tenant count exceeds 30 or when a single NAT Gateway failure would affect >3 active NCA submission deadlines simultaneously.
- ALB with AWS WAF for edge protection (OWASP Top 10:2025 rule set).
- All subnets tagged with cost allocation tags for P12 margin tracking.
- **No SSH/RDP access to production (RL-002):** All production access via AWS Systems Manager Session Manager. No security group permits inbound port 22 or 3389. Fargate tasks have no inbound security group rules; ECS Exec via SSM is the only shell access path.
- **Egress allowlist (IS-007):** Security groups enforce explicit egress rules — TCP 443 to AWS VPC endpoints, Anthropic API (`api.anthropic.com`), and NCA portal CIDRs. Explicit DENY for 169.254.0.0/16 (link-local/IMDS) and RFC 1918 ranges outside VPC. Application-layer SSRF prevention via `OutboundURLValidator` (SC-011).
- **CloudTrail immutable logging (IS-004):** Multi-region trail capturing all management and data events. Logs stored in S3 with Object Lock (COMPLIANCE mode, 7-year retention) and SHA-256 digest validation. Alerts on: root login, CreateUser, DeleteTrail, StopLogging.

### 3.2 Compute (ECS Fargate)

Three ECS services, all on Fargate (serverless containers — no EC2 instance management):

| Service | Min Tasks | Max Tasks | CPU/Memory | Auto-scale Trigger |
|---|---|---|---|---|
| `eagle-frontend` | 2 | 8 | 0.5 vCPU / 1 GB | CPU > 70% |
| `eagle-api` | 2 | 16 | 1 vCPU / 2 GB | Request count > 500/min |
| `eagle-worker` | 2 | 32 | 2 vCPU / 4 GB | SQS queue depth > 100 |

The worker pool scales based on combined queue depth across all pipeline stage queues. Per-tenant resource quotas (REQ-SCL-004: max 40% of worker capacity per tenant) are enforced at the orchestration layer — not at the infrastructure level — by tagging queue messages with `tenant_id` and applying admission control before task dispatch.

**Container hardening (IS-006):** All Fargate task definitions enforce:
- `readonlyRootFilesystem: true` — container filesystem is read-only
- `privileged: false` — no privileged execution
- `user: '1000:1000'` — non-root user
- `linuxParameters.capabilities.drop: ['ALL']` — all Linux capabilities dropped
- `awsvpc` network mode only (private subnets); no `hostNetwork`
- All stdout/stderr captured to CloudWatch via `awslogs` driver
- Container images signed with cosign (ECDSA P-256) at build time; signature verified before Fargate deployment (SRI-001)
- Base image: `python:3.12-slim-bookworm` pinned to digest; rebuilt on Dependabot PR

### 3.3 Database (Aurora PostgreSQL)

- **Engine:** Aurora PostgreSQL 16, Multi-AZ deployment.
- **Instance:** `db.r6g.large` (Phase 1), vertically scalable.
- **Storage:** Aurora auto-scaling storage (up to 128 TB), encrypted with AWS KMS (AES-256). KMS CMK with automatic annual rotation enabled (IS-003); no AWS-managed default keys.
- **Read replicas:** None in Phase 1. MOD-MANAGEMENT analytical queries run against the primary instance, which has sufficient capacity for <50 tenants. **Upgrade triggers (any one):** (a) OLTP p99 latency exceeds 200ms during MOD-MANAGEMENT dashboard refresh, (b) MOD-MANAGEMENT queries consistently take >5 seconds, (c) tenant count exceeds 40, (d) Aurora CPU utilisation >70% sustained during business hours. When triggered, a read replica (`db.r6g.large`) is provisioned via Terraform and MOD-MANAGEMENT queries are routed to the replica endpoint via a `REPLICA` connection string in Secrets Manager. No application code change required — the analytics query service reads the connection string at startup.
- **Backup:** Continuous backup with point-in-time recovery (35-day window). Daily snapshots retained for 90 days. Cross-region snapshot copy for DR.
- **Connection pooling:** Amazon RDS Proxy for managed connection pooling. Eliminates per-task PgBouncer sidecars, reducing container count and operational complexity. RDS Proxy supports IAM authentication and is transparent to RLS (`SET app.current_tenant_id` passes through correctly). **RLS isolation verification:** Automated integration tests (`test_rls_proxy_isolation`) verify that: (a) `SET app.current_tenant_id` persists correctly per connection via RDS Proxy, (b) a connection returned to the pool does not leak the previous tenant context (RDS Proxy resets session state on checkout), (c) under concurrent load, no cross-tenant data leakage occurs. These tests run as part of G3 (integration tests) on every CI/CD build.
- **Parameters:** `row_security = on` enforced at the cluster level; cannot be disabled without infrastructure-level change.

### 3.4 Object Storage (S3)

| Bucket | Purpose | Lifecycle | Encryption |
|---|---|---|---|
| `eagle-ingestion-{env}` | Upload staging for structured files | Delete after successful ingestion | SSE-KMS |
| `eagle-source-docs-{env}` | Unstructured documents for AI extraction | Delete immediately after extraction | SSE-KMS |
| `eagle-submissions-{env}` | Packaged NCA submission files | 10-year retention (Glacier after 90 days) | SSE-KMS |
| `eagle-client-delivery-{env}` | S3_EAGLE_BUCKET delivery channel | Delete after download or 7 days | SSE-KMS |
| `eagle-archive-{env}` | Long-term canonical record archive | 10-year retention (Glacier Deep Archive after 1 year) | SSE-KMS |
| `eagle-config-{env}` | Versioned configuration files | Version-enabled, no deletion | SSE-KMS |

All buckets: versioning enabled, public access blocked, access logging to dedicated log bucket, Object Lock on `eagle-submissions` and `eagle-archive` for immutability. All S3 SSE-KMS keys use customer-managed CMKs with automatic annual rotation (IS-003).

### 3.5 Queue Architecture (SQS)

Pipeline queues are consolidated for Phase 1 simplicity. Workers route messages by `stage` message attribute. This reduces operational surface (fewer queues, fewer DLQs, fewer alarms) without sacrificing durability.

| Queue | Purpose | Visibility Timeout | DLQ Max Receives |
|---|---|---|---|
| `eagle-pipeline-{env}` | All pipeline stages (L1–L6) — routed by `stage` attribute (TRANSFORM, VALIDATE, QUALITY, PACKAGE) | 120s | 3 |
| `eagle-submit-{env}` | L7 submission delivery (longer timeout for NCA portal interactions) | 300s | 3 |
| `eagle-notify-{env}` | Notification dispatch (decoupled from pipeline) | 30s | 5 |

FIFO queue for ordered operations:

| Queue | Purpose |
|---|---|
| `eagle-submission-sequence-{env}.fifo` | AIFM-before-AIF sequencing per REQ-SCL-005 |

Dead-letter queues trigger CloudWatch alarms → SNS → EAGLE_ADMIN notification.

**Growth path:** If pipeline stages develop significantly different throughput or timeout requirements, individual stage queues can be split out from `eagle-pipeline` without code changes (worker reads `stage` attribute regardless of source queue).

### 3.6 SFTP (AWS Transfer Family)

- Managed SFTP server with tenant-scoped home directories.
- Path structure: `/inbound/{tenant_id}/{aif_id}/` and `/outbound/{tenant_id}/{period}/` per REQ-DEL-001.
- Authentication: SSH key pairs generated per tenant, stored in Secrets Manager.
- S3 as backing store; new file in `/inbound/` triggers EventBridge rule → SQS ingestion queue.
- Polling interval effectively zero (event-driven); dashboard visibility within 10 minutes per REQ-DEL-002.

---

## 4. Multi-Tenancy Architecture

### 4.1 Tenant Model

Eagle supports two tenancy models per REQ-TEN-002:

```
┌─────────────────────────────────────────┐
│           Eagle Platform                │
│                                         │
│  ┌─────────────────┐  ┌──────────────┐  │
│  │  Direct AIFM    │  │  Service     │  │
│  │  Tenant         │  │  Provider    │  │
│  │                 │  │  Tenant      │  │
│  │  ┌───────────┐  │  │  ┌────────┐  │  │
│  │  │ AIFM-A    │  │  │  │ AIFM-X │  │  │
│  │  │ (single)  │  │  │  ├────────┤  │  │
│  │  └───────────┘  │  │  │ AIFM-Y │  │  │
│  │                 │  │  ├────────┤  │  │
│  │                 │  │  │ AIFM-Z │  │  │
│  │                 │  │  └────────┘  │  │
│  └─────────────────┘  └──────────────┘  │
└─────────────────────────────────────────┘
```

A **tenant** is the top-level billing and access entity. A tenant of type `SERVICE_PROVIDER` contains multiple **AIFM sub-entities**, each with isolated data, NCA identifiers, and DORA register entries. NCA portal credentials can be stored at two scopes: per service-provider tenant (shared across all AIFMs) or per individual AIFM sub-entity (overrides the provider-level credential). See Sections 6.2 and 9.6 for the credential model and resolution logic.

### 4.2 Row-Level Security (RLS)

All tenant data isolation is enforced at the PostgreSQL level using RLS policies. This is the primary security boundary per REQ-TEN-001.

```sql
-- Every data table includes tenant_id as a non-nullable column
-- RLS policy ensures queries only see rows for the current tenant

ALTER TABLE canonical_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE canonical_records FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON canonical_records
  USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Set at connection level by the application middleware:
SET app.current_tenant_id = '<tenant_uuid>';
```

**Enforcement guarantees:**
- `FORCE ROW LEVEL SECURITY` applies even to table owners (prevents admin bypass).
- Background jobs set `app.current_tenant_id` per job; cross-tenant access is architecturally impossible.
- The `tenant_id` column is included in every table's primary key or has a NOT NULL constraint and foreign key to `tenants`.
- Automated integration tests verify isolation: insert data for tenant A, authenticate as tenant B, assert zero rows returned.

### 4.3 Tenant Lifecycle

```
TRIAL_REQUEST → [Legitimacy Gate (REQ-GTM-002)] → TRIAL_TENANT
                                                        │
                    HIGH score: auto-provision (10min)   │
                    MEDIUM/LOW: CCO review queue         │
                                                        │
TRIAL_TENANT → [CS Manager conversion (REQ-TRIAL-006)] → ACTIVE_TENANT
                                                        │
                    Paid checklist (REQ-TEN-003)         │
                    GDPR DPA confirmed (REQ-GDPR-004)    │
                    ISAE CUECs acknowledged              │
                                                        │
ACTIVE_TENANT → [Offboarding (REQ-SEC-003)] → ARCHIVED_TENANT
                                                        │
                    Data retained per retention policy    │
                    User accounts anonymised (30 days)   │
```

### 4.4 Data Residency and Deletion (DH-001, DH-004)

**Non-production data policy (DH-001 / RL-003):** All development, test, and staging environments use synthetic data generated by the Eagle synthetic data generator. No real client data (AIF data, NAV figures, AIFM identity, NCA submission content) is ever present in non-production environments. This is architecturally enforced: production Aurora has no replication link to non-prod accounts, S3 IAM policies deny cross-account access, and there is no automated data copy mechanism. Use of real client data in non-production environments is a GDPR breach and a red line violation (RL-003).

**Tenant offboarding and data deletion (DH-004):** When a tenant transitions to `ARCHIVED` status, an automated deletion workflow is triggered:

1. **Day 0:** Tenant status set to `ARCHIVED`; all user sessions invalidated; API keys revoked.
2. **Day 0–30:** User accounts associated with the tenant are anonymised (PII replaced with hashed placeholders). Audit trail preserved with anonymised references.
3. **Day 30:** Automated deletion job removes all non-archived tenant data from RDS (canonical records, field-level data, configuration). S3 objects in `eagle-ingestion` and `eagle-source-docs` purged.
4. **Retention-governed data:** Submission archives (`eagle-submissions`) and audit trail records follow the 10-year regulatory retention policy before deletion.
5. **Failure handling:** Deletion jobs that fail are retried (max 3 attempts). Persistent failure triggers a MEDIUM incident notification to EAGLE_ADMIN. Deletion must be re-run and verified — failures are never silenced.
6. **Exception process:** Any deviation from the standard deletion timeline requires written approval from CTO + Head of Compliance & Risk, documented in the tenant offboarding log.

All deletion actions are logged in the `audit_events` table with `event_type = 'TENANT_DATA_DELETION'` and include a hash manifest of deleted records for audit verification.

### 4.5 Tenant-Product Assignment

Per REQ-ARCH-002 and REQ-ARCH-003, each tenant is associated with one or more products from the product registry:

```yaml
# config/product_registry.yaml
products:
  - product_id: AIFMD_ANNEX_IV
    product_name: "AIFMD Annex IV Regulatory Reporting"
    status: ACTIVE
    applicable_client_types: [DIRECT_AIFM, SERVICE_PROVIDER]
    regulatory_frameworks: [AIFMD, CDR231, DQEF, IT_TECH_R6]
    product_module_ref: "app.products.aifmd"
```

In Phase 1, `AIFMD_ANNEX_IV` is auto-assigned to every tenant at provisioning. The platform resolves the product module at runtime via the registry — no hard-coded product references in the platform layer.

---

## 5. Pipeline Architecture (L1–L11)

### 5.1 Pipeline Overview

The pipeline processes a single reporting submission from data ingestion through NCA delivery. Each AIF record in a batch is an independent work item (REQ-SCL-001), enabling parallelism at scale.

```
                    ┌──────────────────┐
     Ingestion      │   L1 INGESTION   │  REST API, File Upload,
     Channels  ────▶│                  │  SFTP, Manual, AI-assisted
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
     Known Legacy   │  L1B ADAPTER     │  M adapter, ESMA legacy
     Templates ────▶│  (deterministic) │  AuM, leverage, FX calc
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
     AI Transform   │  L2 TRANSFORM    │  Claude: unstructured → canonical
     + Derivation   │                  │  Deterministic: position derivations
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
     Rule Engine    │  L3 VALIDATION   │  ESMA rules + NCA overrides
                    │  (deterministic) │  → CAF / CAM / PASS per field
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
     DQEF Checks    │  L4 QUALITY      │  Statistical + plausibility
                    │  (deterministic) │  → DQ_WARNING / 01_STATS
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
     Human Gate     │  L5 REVIEW       │  Mandatory pre-submission
     (non-bypass)   │                  │  Individual or bulk approval
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
     NCA Packaging  │  L6 PACKAGING    │  XML generation, compression,
                    │  (deterministic) │  NCA-specific file naming
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
     Delivery       │  L7 SUBMISSION   │  DIRECT_API, ROBOT_PORTAL,
                    │                  │  S3, SFTP, MANUAL
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
     Immutable Log  │  L8 AUDIT        │  Append-only event log
                    │                  │  Field lineage, 10yr retention
                    └─────────────────┘

     Cross-cutting layers:
     L9  ORCHESTRATION — State machine, priority queues, scheduling
     L10 API           — External REST API, OAuth 2.0, rate limiting
     L11 IAM           — Identity, access control, tenant management
```

### 5.2 Pipeline State Machine

Each submission batch transitions through defined states. The orchestration layer (L9) manages these transitions as an explicit state machine persisted in the database.

```
DRAFT
  │
  ▼ [trigger validation]
VALIDATION_PENDING
  │
  ├─── validation fails with engine error ──▶ SYSTEM_ERROR
  │
  ├─── CAF errors present ──▶ CAF_FAILED ──▶ [correction] ──▶ DRAFT
  │
  ▼ [validation passes]
REVIEW_PENDING
  │
  ▼ [reviewer approves]
APPROVED
  │
  ▼ [trigger submission]
SUBMITTING
  │
  ├─── DIRECT_API / ROBOT ──▶ SUBMITTED ──▶ ACCEPTED / REJECTED
  │
  ├─── S3_CLIENT / S3_EAGLE / SFTP / MANUAL ──▶ PENDING_CONFIRMATION
  │                                                     │
  │                                    [client confirms] ▼
  │                                                  ACCEPTED
  │
  ▼ [amendment initiated]
AMENDMENT_INITIATED ──▶ AMENDED
```

State transitions are atomic database operations. Each transition emits an audit event to L8. The state machine definition is loaded from configuration (not hard-coded) to support product-specific workflows.

### 5.3 L1 — Data Ingestion

Five ingestion channels converge to a single channel-agnostic raw payload:

```python
# Platform interface — product modules implement this
class IngestionChannel(Protocol):
    async def receive(self, request: IngestionRequest) -> RawPayload: ...
    async def detect_format(self, payload: RawPayload) -> FormatDetectionResult: ...

# AIFMD product implementations
class RESTAPIChannel(IngestionChannel): ...       # REQ-ING-001
class FileUploadChannel(IngestionChannel): ...    # REQ-ING-002
class SFTPChannel(IngestionChannel): ...          # REQ-DEL-002
class ManualEntryChannel(IngestionChannel): ...   # REQ-ING-003 (Phase 2)
class AIAssistedChannel(IngestionChannel): ...    # REQ-ING-004
```

**Format detection** (REQ-LEG-002): 3-factor detection (sheet names, header patterns, version cells) runs in < 2 seconds for files up to 50 MB. Result confirmed by user; override available.

**Idempotency** (REQ-ING-001): API ingestion uses idempotency keys stored in a Redis cache (TTL 24h) to prevent duplicate processing.

### 5.4 L1B — Legacy Template Adapters

Pluggable, independently versioned adapters per REQ-LEG-001:

```python
class LegacyAdapter(Protocol):
    """Interface: raw file bytes → normalised intermediate JSON."""
    adapter_id: str
    version: str

    def transform(self, raw: bytes, metadata: AdapterMetadata) -> IntermediateRecord: ...
    def get_enrichment_calculations(self) -> list[EnrichmentCalc]: ...

# Registry loaded from config — new adapter requires no code changes to pipeline
ADAPTER_REGISTRY = {
    "M_REGISTERED": MRegisteredAdapter,   # REQ-LEG-004
    "M_AUTHORISED": MAuthorisedAdapter,   # REQ-LEG-005
    "ESMA_LEGACY": ESMALegacyAdapter,                       # REQ-LEG-006
}
```

**Enrichment calculations** (REQ-LEG-003): AuM aggregation, gross/commitment leverage derivation, currency conversion using ECB rates from the reference data store (REQ-REF-001). All calculations are deterministic with full before/after audit trail per field.

### 5.5 L2 — AI Transformation and Derivation

Two distinct functions at this layer:

**(a) AI Transformation (Claude):** Normalises unstructured input to the Eagle canonical data model. Output is always a candidate mapping requiring human confirmation. Per-field confidence scores (HIGH / MEDIUM / LOW). LOW confidence fields require explicit user confirmation before pipeline proceeds (REQ-ING-004).

**(b) Deterministic Derivation Engine:** Position-level calculations (rankings, leverage, unencumbered cash, AuM aggregation). All rule-based, fully auditable. No AI involvement.

```python
# AI abstraction layer (REQ-MOD-002 — model-agnostic)
class AITransformationService(Protocol):
    async def extract_fields(
        self,
        document: bytes,
        schema: CanonicalSchema,
        system_prompt_version: str
    ) -> ExtractionResult: ...

class ExtractionResult:
    fields: list[ExtractedField]  # field_name, value, confidence, source_text
    model_version: str
    prompt_version: str

# Current implementation
class ClaudeTransformationService(AITransformationService):
    """Anthropic Claude API — EU inference endpoints."""
    # Replaceable by configuration per REQ-MOD-002
```

#### 5.5.1 L2 Resilience and Error Handling (SC-013)

The AI transformation layer implements explicit error handling for all Claude API failure modes. No exceptions are swallowed in the L2 critical path:

| Error Type | Strategy | Max Retries | Backoff |
|---|---|---|---|
| `APITimeoutError` | Retry with exponential backoff | 3 | 2s, 4s, 8s |
| `RateLimitError` | Backoff per `Retry-After` header | 3 | Server-directed |
| `APIConnectionError` | Retry with exponential backoff | 3 | 1s, 2s, 4s |
| `APIStatusError` (5xx) | Retry with exponential backoff | 3 | 2s, 4s, 8s |
| `APIStatusError` (4xx) | No retry — log at ERROR and fail | 0 | N/A |

**Constraints:** `max_tokens` is set per extraction type (field extraction: 4096, document summary: 8192). Response size is validated before parsing — responses exceeding the expected token count are rejected and logged as anomalies. All exceptions are logged at ERROR level with correlation ID before returning an error state to the pipeline. After max retries exhausted, the record enters `AI_ERROR` state and triggers the BCP S3 fallback (manual extraction path per Section 14.4).

#### 5.5.2 Prompt Injection Defence (SC-014)

Defence-in-depth approach to prompt injection for AI-assisted document extraction:

1. **Document pre-processing:** Before L2 processing, uploaded documents pass through a sanitisation step that strips content outside expected field boundaries (e.g., removing embedded scripts, instruction-like patterns such as "ignore previous instructions", and unexpected control characters).
2. **System/user prompt separation:** Claude API calls use a strict architecture where the system prompt (extraction instructions, schema definition) is never mixed with user-supplied content. User document content is passed exclusively in the user message with structured delimiters.
3. **Structured output enforcement:** All Claude API calls use structured output mode (JSON schema) — the model returns only typed field values, never free-form instructions or executable content.
4. **Suspicious content detection:** A pre-L2 classifier flags documents containing instruction-like patterns (e.g., "as an AI", "disregard", "new instructions"). Flagged documents are routed to manual extraction with an `AI_FLAGGED` audit event.
5. **L3 validation as final catch:** Even if prompt injection produced anomalous extraction results, the deterministic L3 validation engine rejects values that fall outside legal ranges, schema constraints, or cross-field consistency rules (RL-005).

Cross-references: SC-001 (input validation), RL-005 (AI boundary), Section 8.3 (AI Safety Controls).

### 5.6 L3 — Deterministic Validation Core

The regulatory heart of Eagle. Every canonical record validated against the rule engine loaded from `aifmd_annex_iv_validation_rules.yaml` at runtime (REQ-VAL-001).

```python
class ValidationEngine:
    """Deterministic, stateless validation. Same input → same output. Always."""

    def __init__(self, rules: RuleSet, nca_overrides: dict[str, NCAOverrideProfile]):
        self.rules = rules
        self.nca_overrides = nca_overrides

    def validate(
        self,
        record: CanonicalRecord,
        nca_code: str
    ) -> ValidationReport:
        """
        Validates record against all applicable rules for the target NCA.
        Returns per-field results: PASS / CAF / CAM / DQ_WARNING.
        Records: rule_id, field_path, result, actual value, constraint, ESMA error code.
        """
        ...

class ValidationReport:
    record_id: uuid.UUID
    nca_code: str
    rule_engine_version: str
    nca_override_version: str
    results: list[RuleResult]       # Per-field, per-rule
    cross_record_results: list[CrossRecordResult]  # REQ-VAL-002
    overall_status: Literal["PASS", "CAF_FAILED", "CAM_FLAGGED"]
```

**NCA overrides:** Validation runs once per NCA registration using the appropriate override profile. Override profiles are YAML configuration files per NCA (e.g., `nca_override_cssf.yaml`, `nca_override_cbi.yaml`).

**Cross-record validation** (REQ-VAL-002): AuM sum consistency, LEI consistency, reporting period alignment, fund count, filing type. Cross-record CAF results block the entire batch.

### 5.7 L4 — DQEF Quality Layer

ESMA DQEF statistical and plausibility checks per REQ-VAL-003. Runs after L3. Three flow types:

| Flow Type | Eagle Category | Effect |
|---|---|---|
| `01_STATS` | Informational | No action required; not shown at review gate |
| `03_HARDCHECK` | CAF | Blocks submission; impossible value |
| `04_SOFTCHECK` | DQ_WARNING | Requires reviewer acknowledgement; never blocks |

Each DQ check result stores `dqef_error_code` in ESMA format (e.g., `AIFMS_DQT_4060500_WARNING1`) for direct cross-reference with ESMA feedback files.

### 5.8 L5 — Human Review and Approval Gate

**Non-bypassable.** This is the primary DORA Art.30 oversight control and the structural condition for non-high-risk EU AI Act classification.

```python
class ReviewGate:
    """
    Mandatory pre-submission gate. Cannot be bypassed by any means
    including API calls. REQ-REV-001, REQ-SCL-003.
    """

    async def submit_for_review(self, batch_id: uuid.UUID) -> ReviewSession: ...

    async def bulk_approve(
        self,
        session: ReviewSession,
        reviewer: User,  # Must be COMPLIANCE_REVIEWER or TENANT_ADMIN
    ) -> BulkApprovalResult:
        """
        Only for records with zero flags of any category.
        Audit record includes Merkle tree root hash of all approved records.
        """
        ...

    async def individual_review(
        self,
        record_id: uuid.UUID,
        reviewer: User,
        decisions: list[FlagDecision],  # Per-flag acknowledge/override
    ) -> IndividualReviewResult: ...
```

**Bulk approval** (REQ-SCL-003): Available only for records with zero flags. 1,000 clean records in under 60 seconds. Flagged records automatically split for individual review without blocking bulk approval of clean records.

**Cross-NCA grouped approval:** When NCA variants are content-identical (same canonical record, different NCA packaging), the reviewer approves once and the approval applies to all variants.

### 5.9 L6 — NCA File Packaging

XML generation from canonical records, wrapped per NCA-specific configuration (REQ-FMT-001):

```yaml
# config/packaging/cssf.yaml
packaging:
  nca_code: CSSF
  xml_structure: multi_aif_file
  compression: zip_single
  file_naming: "{aifm_national_code}_{reporting_period_type}_{reporting_period_year}_{filing_type}.zip"
  xml_variations:
    namespace_prefix: "ns1"
    encoding: "UTF-8"
  checksum_algorithm: SHA-256
```

Packaging never alters XML content. Generated XML validated against the current ESMA XSD schema. Checksum stored in audit record per file.

### 5.10 L7 — NCA Delivery

Six delivery channels per REQ-DEL-001, all producing equivalent audit trail records:

| Channel | Mechanism | Confirmation |
|---|---|---|
| `DIRECT_API` | Eagle calls NCA REST API | NCA API response |
| `ROBOT_PORTAL` | Headless browser automation | Portal confirmation number captured |
| `S3_CLIENT_BUCKET` | PutObject to client S3 | Client confirms NCA receipt |
| `S3_EAGLE_BUCKET` | Presigned URL (7-day expiry) | Client records NCA confirmation |
| `SFTP_EAGLE_SERVER` | File to outbound path | Client records NCA confirmation |
| `MANUAL` | Download from Eagle UI | Client records NCA confirmation |

**Submission sequencing** (REQ-SCL-005): AIFM record submitted and acknowledged before any AIF records. AIFM failure holds entire batch. NCA rate limits configured per NCA in override files. Robot sessions serialised per NCA portal — no parallel sessions to same portal.

**Credential resolution** (REQ-NCA-003): Before initiating delivery, the L7 worker calls `NCACredentialVault.resolve_credential(tenant_id, nca_code, aifm_profile_id)` which applies a two-step lookup: (1) AIFM-specific credential, (2) service-provider-level fallback. This supports service providers that hold a single set of NCA portal credentials for all their AIFM clients, as well as direct AIFMs that manage their own credentials. The resolved scope (`AIFM` or `SERVICE_PROVIDER`) is logged in the audit trail alongside the submission event. If no credential is found at either scope, the batch transitions to `CREDENTIAL_PENDING` status and a notification is sent to the TENANT_ADMIN.

### 5.11 L8 — Audit Trail and Lineage

Immutable, append-only event log per REQ-AUD-001. Minimum 10-year retention.

```python
@dataclass
class AuditEvent:
    event_id: uuid.UUID
    tenant_id: uuid.UUID
    timestamp: datetime  # UTC, microsecond precision
    event_type: str      # ingestion, transformation, validation, review, submission, ...
    actor_id: str        # Pseudonymous user_id or SYSTEM
    actor_role: str
    entity_type: str     # canonical_record, submission_batch, user, ...
    entity_id: uuid.UUID
    pipeline_layer: str  # L1..L11
    product_id: str      # AIFMD_ANNEX_IV — product context, not hard-coded
    payload: dict        # Event-specific structured data (JSON)

    # Immutability enforced at DB level:
    # - INSERT only (no UPDATE/DELETE grants)
    # - Table partitioned by month for performance
    # - Archived to S3 Glacier after 1 year
```

**Field-level lineage** (REQ-AUD-002): Each field in a canonical record carries a complete provenance chain — from raw input through transformation, derivation, validation, and approval. AI-assisted steps tagged distinctly.

### 5.12 L9 — Orchestration

Central control layer managing pipeline execution. The orchestrator uses a **SQS + PostgreSQL state machine** pattern — no external workflow engine (e.g., Temporal) is required. Pipeline state is persisted in PostgreSQL (`platform.pipeline_runs` table) with explicit state transitions, and SQS handles message routing between stages. This eliminates an external cluster dependency while retaining durable, auditable orchestration.

```python
class PipelineOrchestrator:
    """
    SQS-based priority queue architecture per REQ-SCL-001.
    Pipeline state persisted in PostgreSQL (platform.pipeline_runs).
    Each AIF record = independent queue item.
    """

    async def trigger_pipeline(
        self,
        batch_id: uuid.UUID,
        product_context: ProductContext,  # Resolved from product registry
    ) -> PipelineRun:
        """Creates pipeline_run record in PG, dispatches first stage to SQS."""
        ...

    async def dispatch_to_queue(
        self,
        stage: PipelineStage,
        items: list[WorkItem],
        priority: Literal["DEADLINE_CRITICAL", "STANDARD"],
    ) -> None:
        """
        Routes work items to the appropriate SQS queue with stage attribute.
        DEADLINE_CRITICAL: deadline within 2 business days.
        Per-tenant quota enforcement: max 40% of worker capacity (REQ-SCL-004).
        """
        ...

    async def advance_stage(
        self,
        pipeline_run_id: uuid.UUID,
        completed_stage: PipelineStage,
        result: StageResult,
    ) -> None:
        """
        Worker calls this after stage completion. Updates PG state,
        dispatches next stage to SQS. Retry logic: exponential backoff
        per SC-013 (max 3 retries per stage). DLQ for exhausted retries.
        """
        ...
```

**State persistence:** All pipeline state transitions are recorded in PostgreSQL with timestamps, enabling full audit trail integration (L8) and recovery after worker restarts. No in-memory workflow state — a worker crash loses only the current message, which SQS re-delivers after visibility timeout.

**Retry policy per stage (SC-013):** Each pipeline stage has an explicit retry configuration. No exceptions are silently swallowed — every failure is logged at ERROR level with correlation ID before retry or DLQ routing.

| Stage | Retryable Errors | Max Retries | Backoff (initial, multiplier, max) | Non-Retryable (fail-fast) |
|---|---|---|---|---|
| L1 Ingest | File parse error, S3 timeout | 2 | 5s, 2×, 30s | Schema violation, unsupported format |
| L2 AI Transform | `APITimeoutError`, `RateLimitError`, `APIConnectionError`, `APIStatusError` (5xx) | 3 | 2s, 2×, 60s | `APIStatusError` (4xx), `max_tokens` exceeded |
| L3 Validate | Database timeout | 2 | 1s, 2×, 10s | Validation logic error (deterministic — no retry) |
| L4 DQEF | Database timeout | 2 | 1s, 2×, 10s | Quality check logic error |
| L6 Package | S3 timeout, XML generation error | 2 | 2s, 2×, 20s | XSD validation failure |
| L7 Deliver | NCA API timeout, portal connection error | 3 | 30s, 2×, 300s | NCA rejection (4xx), authentication failure |

**Claude API constraints (L2):** `max_tokens` enforced per extraction type (field extraction: 4,096; document summary: 8,192). Response size validated before parsing — oversized responses rejected and logged as anomalies. `RateLimitError` respects `Retry-After` header. Database query timeout: 30 seconds for OLTP, 120 seconds for MOD-MANAGEMENT analytical queries.

**DLQ routing:** After max retries exhausted, the message is routed to the stage DLQ. DLQ messages trigger CloudWatch Alarm → SNS → EAGLE_ADMIN notification. Records enter `STAGE_ERROR` state in PostgreSQL. No automatic recovery from DLQ — manual investigation and re-dispatch required.

**Deadline monitoring:** The orchestrator tracks reporting deadlines per obligation (REQ-OBL-001) and auto-escalates to DEADLINE_CRITICAL priority when a deadline is within 2 business days.

### 5.13 L10 — External API

Versioned REST API per REQ-API-001 and REQ-API-002:

- **Authentication:** OAuth 2.0 (client credentials flow) for system-to-system; API keys for simple integrations.
- **Versioning:** URL-based (`/api/v1/...`). Breaking changes require new major version. Deprecation policy: 12 months notice.
- **Rate limiting:** Per-tenant, configurable. Default: 100 requests/minute, 1,000 requests/hour.
- **OpenAPI specification:** Auto-generated from FastAPI, published at `/api/docs`.
- **White-label embedding** (REQ-API-002): Iframe-embeddable views with tenant-scoped JWT tokens for service providers.

### 5.14 L11 — Identity, Access and Tenant Management

Five predefined roles per REQ-USR-001 (no custom roles):

| Role | Scope | Key Permissions |
|---|---|---|
| `EAGLE_ADMIN` | Eagle-internal | Provision tenants, manage users, system audit, reference data |
| `TENANT_ADMIN` | Tenant-wide | Manage AIFM profiles, users, delivery config, approve submissions |
| `COMPLIANCE_REVIEWER` | Per AIFM sub-entity | Review and approve submissions, manage overrides |
| `DATA_PREPARER` | Per AIFM sub-entity | Upload data, correct CAF errors, view validation results |
| `READ_ONLY` | Per AIFM sub-entity | View dashboards, audit trail, submission history |

Additional internal roles: `COO`, `CCO`, `CRO`, `CFO`, `HEAD_OF_CS`, `CCO_DELEGATE` — these are functional views within MOD-MANAGEMENT, not separate IAM roles. They are EAGLE_ADMIN accounts with additional dashboard visibility.

**Trial users:** `TRIAL_USER` role = `TENANT_ADMIN` with feature gates (no Annex IV download, no NCA submission per REQ-TRIAL-002).

---

## 6. Database Architecture

### 6.1 Schema Overview

The database schema is organised into platform schemas (product-agnostic) and product schemas (AIFMD-specific), reflecting the P15 platform–product isolation.

```
PostgreSQL Cluster
│
├── Schema: platform
│   ├── tenants
│   ├── tenant_products           # REQ-ARCH-003
│   ├── users
│   ├── user_roles
│   ├── api_keys
│   ├── audit_events              # L8 — immutable, append-only
│   ├── notifications
│   ├── product_registry          # REQ-ARCH-002 (cached from YAML)
│   ├── pipeline_runs             # L9 — orchestration state
│   ├── pipeline_states           # State machine transitions
│   ├── queue_metrics             # Real-time queue depth tracking
│   └── system_config             # Runtime configuration cache
│
├── Schema: aifmd                  # Product: AIFMD Annex IV
│   ├── aifm_profiles             # REQ-TEN-004
│   ├── aif_profiles
│   ├── nca_registrations         # REQ-MJ-001
│   ├── reporting_obligations     # REQ-OBL-001
│   ├── canonical_records         # The core data model
│   ├── canonical_fields          # Per-field provenance (REQ-POS-004)
│   ├── position_data             # REQ-POS-001
│   ├── validation_reports        # L3 results
│   ├── validation_results        # Per-field, per-rule results
│   ├── quality_results           # L4 DQEF results
│   ├── review_sessions           # L5 review gate records
│   ├── review_decisions          # Per-flag decisions
│   ├── override_records          # REQ-OVR-001
│   ├── submission_batches        # L6/L7 packaging and delivery
│   ├── submission_files          # Generated file metadata
│   ├── nca_credentials           # Encrypted vault refs (dual-scope: SP / AIFM)
│   ├── amendment_records         # REQ-AMD-001
│   ├── smart_defaults            # REQ-POS-005
│   ├── reference_data            # ECB rates, GLEIF, ESMA register
│   └── report_archive            # REQ-DAT-004
│
├── Schema: gtm                    # MOD-GTM
│   ├── prospects                 # REQ-GTM-003
│   ├── enrichment_results        # REQ-GTM-001
│   ├── legitimacy_scores         # REQ-GTM-002
│   └── outbound_status
│
├── Schema: trial                  # MOD-TRIAL
│   ├── trial_tenants            # REQ-TRIAL-001
│   ├── trial_health_scores      # REQ-TRIAL-004
│   ├── prepopulation_quality    # REQ-TRIAL-003
│   └── trial_events
│
└── Schema: management             # MOD-MANAGEMENT
    ├── ops_metrics               # REQ-OPS-001..014
    ├── capacity_calendar         # REQ-OPS-003
    ├── incident_reports          # REQ-CPL-001
    ├── dora_register             # REQ-CPL-003
    ├── isae_controls             # REQ-ISAE-001..014
    └── compliance_risk_register  # REQ-CR-001..007
```

### 6.2 Core Tables

#### tenants (platform schema)

```sql
CREATE TABLE platform.tenants (
    tenant_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_type     VARCHAR(20) NOT NULL CHECK (tenant_type IN ('DIRECT_AIFM', 'SERVICE_PROVIDER', 'TRIAL')),
    status          VARCHAR(20) NOT NULL CHECK (status IN ('ACTIVE', 'TRIAL', 'SUSPENDED', 'ARCHIVED')),
    legal_name      VARCHAR(500) NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by      UUID NOT NULL REFERENCES platform.users(user_id),
    activated_at    TIMESTAMPTZ,
    archived_at     TIMESTAMPTZ,

    -- GDPR
    dpa_confirmed   BOOLEAN NOT NULL DEFAULT FALSE,
    dpa_confirmed_at TIMESTAMPTZ,

    -- ISAE
    cuecs_acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    cuecs_acknowledged_at TIMESTAMPTZ,

    -- AI Transparency
    ai_statement_version VARCHAR(20),
    ai_statement_acknowledged_at TIMESTAMPTZ
);

ALTER TABLE platform.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE platform.tenants FORCE ROW LEVEL SECURITY;
```

#### canonical_records (aifmd schema)

The canonical record is the single source of truth for a regulatory submission (P4, P14).

```sql
CREATE TABLE aifmd.canonical_records (
    record_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES platform.tenants(tenant_id),
    aifm_profile_id UUID NOT NULL REFERENCES aifmd.aifm_profiles(aifm_profile_id),
    aif_profile_id  UUID REFERENCES aifmd.aif_profiles(aif_profile_id),  -- NULL for AIFM-level records

    record_type     VARCHAR(10) NOT NULL CHECK (record_type IN ('AIFM', 'AIF')),
    reporting_period_type VARCHAR(4) NOT NULL CHECK (reporting_period_type IN ('Q1','Q2','Q3','Q4','H1','H2','Y1')),
    reporting_period_year INTEGER NOT NULL,
    filing_type     VARCHAR(4) NOT NULL CHECK (filing_type IN ('INIT', 'AMND')),

    -- Status per pipeline state machine
    status          VARCHAR(30) NOT NULL DEFAULT 'DRAFT',

    -- The canonical data as JSONB — flexible schema per product
    data            JSONB NOT NULL DEFAULT '{}',

    -- Version tracking
    version         INTEGER NOT NULL DEFAULT 1,
    data_hash       VARCHAR(64),  -- SHA-256 of canonical data for integrity

    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    submitted_at    TIMESTAMPTZ,

    -- Product context (platform-agnostic reference)
    product_id      VARCHAR(50) NOT NULL DEFAULT 'AIFMD_ANNEX_IV'
);

-- RLS
ALTER TABLE aifmd.canonical_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE aifmd.canonical_records FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON aifmd.canonical_records
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Indexes
CREATE INDEX idx_canonical_tenant_period ON aifmd.canonical_records(tenant_id, reporting_period_year, reporting_period_type);
CREATE INDEX idx_canonical_status ON aifmd.canonical_records(status) WHERE status NOT IN ('ARCHIVED');
CREATE INDEX idx_canonical_data ON aifmd.canonical_records USING gin(data);
```

#### canonical_fields (aifmd schema) — Field Provenance

Per REQ-POS-004, every field carries provenance metadata:

```sql
CREATE TABLE aifmd.canonical_fields (
    field_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    record_id       UUID NOT NULL REFERENCES aifmd.canonical_records(record_id),
    tenant_id       UUID NOT NULL,

    field_path      VARCHAR(200) NOT NULL,  -- e.g., "AIF.NAV.Amount"
    field_value     JSONB,                  -- Current value

    -- Provenance (REQ-POS-004)
    provenance_type VARCHAR(25) NOT NULL CHECK (provenance_type IN (
        'DERIVED', 'AI_PROPOSED', 'MANUALLY_ENTERED', 'MANUALLY_OVERRIDDEN',
        'IMPORTED', 'SMART_DEFAULT', 'LOCKED'
    )),

    -- AI provenance details (when provenance_type = AI_PROPOSED)
    ai_confidence   VARCHAR(10) CHECK (ai_confidence IN ('HIGH', 'MEDIUM', 'LOW')),
    ai_model_version VARCHAR(50),
    ai_source_text  TEXT,
    ai_confirmed_by UUID,
    ai_confirmed_at TIMESTAMPTZ,

    -- Derived provenance details (when provenance_type = DERIVED)
    formula_id      VARCHAR(100),
    formula_version VARCHAR(20),
    input_fields    JSONB,  -- References to input field_ids
    reference_data_version VARCHAR(50),

    -- Override details (when provenance_type = MANUALLY_OVERRIDDEN)
    original_value  JSONB,
    override_reason TEXT,
    overridden_by   UUID,
    overridden_at   TIMESTAMPTZ,

    -- Lock indicator (P5 — deterministic core protection)
    is_locked       BOOLEAN NOT NULL DEFAULT FALSE,
    locked_at       TIMESTAMPTZ,
    locked_by       UUID,

    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE(record_id, field_path)
);

ALTER TABLE aifmd.canonical_fields ENABLE ROW LEVEL SECURITY;
ALTER TABLE aifmd.canonical_fields FORCE ROW LEVEL SECURITY;
```

#### nca_credentials (aifmd schema) — Credential Vault References

NCA portal credentials support two scopes: **service-provider-level** (one credential set used for all AIFM sub-entities) and **AIFM-level** (per-AIFM credentials when the AIFM manages its own portal access). The L7 delivery layer resolves credentials with AIFM-level taking precedence over service-provider-level (see Section 5.10).

```sql
CREATE TABLE aifmd.nca_credentials (
    credential_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL REFERENCES platform.tenants(tenant_id),
    nca_code        VARCHAR(10) NOT NULL,

    -- Scope: NULL = service-provider-level credential (applies to all AIFMs under this tenant)
    -- Non-NULL = AIFM-specific credential (overrides service-provider-level)
    aifm_profile_id UUID REFERENCES aifmd.aifm_profiles(aifm_profile_id),

    credential_scope VARCHAR(20) NOT NULL GENERATED ALWAYS AS (
        CASE WHEN aifm_profile_id IS NULL THEN 'SERVICE_PROVIDER' ELSE 'AIFM' END
    ) STORED,

    credential_type VARCHAR(20) NOT NULL CHECK (credential_type IN ('portal_login', 'api_key', 'certificate')),
    secret_arn      VARCHAR(500) NOT NULL,  -- AWS Secrets Manager ARN (actual credential never in DB)
    portal_username VARCHAR(200),           -- Non-secret portal identifier (for audit display)

    -- Lifecycle
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    rotated_at      TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ,
    created_by      UUID NOT NULL REFERENCES platform.users(user_id),

    -- Ensure one active credential per tenant+nca+scope combination
    UNIQUE NULLS NOT DISTINCT (tenant_id, nca_code, aifm_profile_id) WHERE (is_active = TRUE)
);

ALTER TABLE aifmd.nca_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE aifmd.nca_credentials FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON aifmd.nca_credentials
    USING (tenant_id = current_setting('app.current_tenant_id')::uuid);

-- Credential resolution index: AIFM-specific first, then tenant-level fallback
CREATE INDEX idx_nca_cred_resolve ON aifmd.nca_credentials(tenant_id, nca_code, aifm_profile_id)
    WHERE is_active = TRUE;
```

**Credential resolution order (L7):** When the submission worker needs NCA credentials for a given `(tenant_id, nca_code, aifm_profile_id)` triple:
1. Look for an active credential matching all three (AIFM-specific).
2. If not found, look for an active credential matching `(tenant_id, nca_code)` where `aifm_profile_id IS NULL` (service-provider-level).
3. If neither exists, the submission fails with `CREDENTIAL_NOT_FOUND` and the batch is held for TENANT_ADMIN resolution.

#### audit_events (platform schema) — Immutable

```sql
CREATE TABLE platform.audit_events (
    event_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL DEFAULT now(),
    event_type      VARCHAR(50) NOT NULL,
    actor_id        VARCHAR(100) NOT NULL,  -- Pseudonymous
    actor_role      VARCHAR(30) NOT NULL,
    entity_type     VARCHAR(50) NOT NULL,
    entity_id       UUID NOT NULL,
    pipeline_layer  VARCHAR(20),
    product_id      VARCHAR(50),
    payload         JSONB NOT NULL DEFAULT '{}',

    -- Hash chain for tamper detection
    previous_hash   VARCHAR(64),
    event_hash      VARCHAR(64) NOT NULL
) PARTITION BY RANGE (timestamp);

-- Monthly partitions (auto-created by pg_partman)
-- Partitions older than 1 year archived to S3 via pg_dump + lifecycle policy

-- CRITICAL: No UPDATE or DELETE grants on this table
REVOKE UPDATE, DELETE ON platform.audit_events FROM PUBLIC;
REVOKE UPDATE, DELETE ON platform.audit_events FROM eagle_app_role;

-- Only INSERT grant for the application
GRANT INSERT ON platform.audit_events TO eagle_app_role;
GRANT SELECT ON platform.audit_events TO eagle_app_role;
```

### 6.3 Reference Data Tables

```sql
-- ECB exchange rates (REQ-REF-001)
CREATE TABLE aifmd.ecb_rates (
    rate_date       DATE NOT NULL,
    base_currency   CHAR(3) NOT NULL DEFAULT 'EUR',
    target_currency CHAR(3) NOT NULL,
    rate            NUMERIC(18,8) NOT NULL,
    source          VARCHAR(20) NOT NULL DEFAULT 'ECB',
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (rate_date, target_currency)
);

-- GLEIF LEI register cache (REQ-REF-002)
CREATE TABLE aifmd.gleif_lei_cache (
    lei             CHAR(20) PRIMARY KEY,
    legal_name      VARCHAR(500) NOT NULL,
    entity_status   VARCHAR(20) NOT NULL,
    registration_authority VARCHAR(100),
    last_update     DATE,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at      TIMESTAMPTZ NOT NULL  -- Cache TTL
);

-- ESMA AIFM register (REQ-GTM-003)
CREATE TABLE gtm.esma_aifm_register (
    register_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aifm_name       VARCHAR(500) NOT NULL,
    lei             CHAR(20),
    national_code   VARCHAR(50),
    nca_code        VARCHAR(10) NOT NULL,
    auth_status     VARCHAR(20) NOT NULL,
    auth_date       DATE,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    register_version VARCHAR(20) NOT NULL
);
```

### 6.4 Entity Relationship Summary

```
platform.tenants ──1:N──▶ aifmd.aifm_profiles ──1:N──▶ aifmd.aif_profiles
       │                         │                            │
       │                         │                            │
       │                         ▼                            ▼
       │                   aifmd.nca_registrations     aifmd.canonical_records
       │                                                 │         │
       │   ┌─────────────────────────────────────────┐   │         │
       │   │  aifmd.nca_credentials                  │   ▼         ▼
       │   │  ┌────────────────────────────────────┐ │  aifmd.   aifmd.
       ├──▶│  │ tenant_id  ◀── platform.tenants    │ │  canonical validation
       │   │  │ aifm_id?   ◀── aifmd.aifm_profiles│ │  _fields   _reports
       │   │  │ (NULL = service-provider scope)    │ │    │          │
       │   │  └────────────────────────────────────┘ │    ▼          ▼
       │   └─────────────────────────────────────────┘  platform.  aifmd.
       │                                                audit_     validation
       ▼                                                events     _results
platform.users ──1:N──▶ platform.user_roles
```

**Credential scope:** `nca_credentials.aifm_profile_id = NULL` → service-provider-level (shared across all AIFMs). Non-NULL → AIFM-specific override. See Section 6.2 (`nca_credentials` table) for resolution logic.

---

## 7. API Layer

### 7.1 API Architecture

FastAPI application with layered routing:

```
/api/v1/
├── /auth/                    # Authentication endpoints
│   ├── POST /token           # OAuth 2.0 token exchange
│   └── POST /api-keys        # API key management
│
├── /tenants/                 # Tenant management (EAGLE_ADMIN)
│   ├── GET /                 # List tenants
│   ├── POST /                # Provision tenant
│   └── /{tenant_id}/        # Tenant detail, update, archive
│
├── /aifm/                    # AIFM profile management
│   ├── GET /                 # List AIFM profiles (tenant-scoped)
│   ├── POST /                # Create AIFM profile
│   └── /{aifm_id}/          # Profile CRUD
│       ├── /nca-registrations/  # NCA registration management
│       └── /obligations/        # Reporting obligation calendar
│
├── /data/                    # Data ingestion (L1)
│   ├── POST /upload          # File upload (REQ-ING-002)
│   ├── POST /ingest          # API data push (REQ-ING-001)
│   └── POST /extract         # AI-assisted extraction (REQ-ING-004)
│
├── /records/                 # Canonical records
│   ├── GET /                 # List records (filtered by period, status)
│   ├── GET /{record_id}     # Record detail with field provenance
│   ├── PUT /{record_id}     # Update record fields
│   └── POST /{record_id}/validate  # Trigger validation pipeline
│
├── /validation/              # Validation results (L3/L4)
│   ├── GET /{record_id}     # Validation report
│   └── GET /{record_id}/dqef  # DQEF quality results
│
├── /review/                  # Review gate (L5)
│   ├── GET /pending          # Records awaiting review
│   ├── POST /bulk-approve    # Bulk approval (zero-flag only)
│   └── POST /{record_id}/approve  # Individual review
│
├── /submissions/             # Submission management (L6/L7)
│   ├── GET /                 # Submission history
│   ├── POST /trigger         # Trigger submission for approved records
│   ├── GET /{batch_id}      # Batch status and delivery details
│   └── POST /{batch_id}/confirm  # Record NCA confirmation number
│
├── /overrides/               # CAF/CAM override management
│   ├── POST /                # Request override (with justification)
│   └── GET /{record_id}     # Override history for record
│
├── /audit/                   # Audit trail (L8)
│   ├── GET /events           # Query audit events
│   ├── GET /lineage/{record_id}  # Field-level lineage
│   └── GET /export           # Machine-readable JSON export
│
├── /reference/               # Reference data
│   ├── GET /ecb-rates        # ECB exchange rates
│   ├── GET /gleif/{lei}      # LEI lookup
│   └── GET /nca-profiles     # Active NCA configurations
│
├── /management/              # Management intelligence (EAGLE_ADMIN)
│   ├── GET /dashboard/{view} # COO, CCO, CRO, CFO views
│   ├── GET /ops/queue        # Pipeline queue status
│   └── GET /incidents        # DORA incident register
│
└── /health/                  # System health
    ├── GET /ready            # Readiness probe
    └── GET /live             # Liveness probe
```

### 7.2 Authentication and Authorisation

```python
# OAuth 2.0 + API key dual authentication
class AuthMiddleware:
    async def __call__(self, request: Request) -> AuthContext:
        # 1. Extract token or API key
        # 2. Validate and decode
        # 3. Resolve tenant_id and user_role
        # 4. Set PostgreSQL session variable for RLS
        #    SET app.current_tenant_id = '<tenant_uuid>'
        # 5. Return AuthContext with permissions
        ...

@dataclass
class AuthContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: UserRole
    aifm_scope: list[uuid.UUID]  # For sub-entity scoped roles
    product_ids: list[str]        # Active products for this tenant
```

### 7.3 Rate Limiting

Per-tenant rate limiting using a sliding window counter in Redis:

| Tier | Requests/minute | Requests/hour | Burst |
|---|---|---|---|
| Standard | 100 | 1,000 | 150 |
| Enterprise | 500 | 10,000 | 750 |
| Internal (EAGLE_ADMIN) | 1,000 | Unlimited | 1,500 |

Rate limit headers returned on every response: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.

### 7.4 Error Handling (SC-008)

All API error responses return generic messages. Internal error detail (stack traces, database query text, system paths, exception messages) never returned to external callers. Full error detail logged internally and correlated by request ID.

Response format: `{error_code, message, request_id}`. Request ID (UUID) in every response header (`X-Request-Id`) and internal log. Global exception handler catches all — no unhandled exceptions reach the ASGI layer.

---

## 8. AI Boundary Architecture

### 8.1 AI Boundary Definition

AI (Claude) operates exclusively at L2 for data extraction and transformation. The boundary is strict and architecturally enforced:

```
┌─────────────────────────────────────────────────────────┐
│                    AI PERMITTED ZONE                     │
│                                                         │
│  L2 TRANSFORMATION                                      │
│  ├── Unstructured document → canonical field mapping    │
│  ├── Per-field confidence scoring (HIGH/MEDIUM/LOW)     │
│  ├── Source text extraction and reference               │
│  └── Non-standard layout normalisation                  │
│                                                         │
│  GTM ENRICHMENT (REQ-GTM-001)                           │
│  ├── Prospect strategy inference from public sources    │
│  └── Always AI_PROPOSED_INDICATIVE — never verified     │
│                                                         │
│  TRIAL PRE-POPULATION (REQ-TRIAL-003)                   │
│  ├── Register data orientation for trial workspaces     │
│  └── Pre-population quality scoring                     │
│                                                         │
└─────────────────────────────────────────────────────────┘
                         │
                    ┌────▼────┐
                    │  GATE   │  AI output NEVER crosses this
                    │ (L3/L5) │  boundary without:
                    └────┬────┘  1. Deterministic validation (L3)
                         │       2. Human review and approval (L5)
                         ▼
┌─────────────────────────────────────────────────────────┐
│                   AI PROHIBITED ZONE                     │
│                                                         │
│  L3 VALIDATION    — All rules deterministic             │
│  L4 QUALITY       — All checks deterministic            │
│  L5 REVIEW        — Human decision only                 │
│  L6 PACKAGING     — Deterministic XML generation        │
│  L7 SUBMISSION    — Deterministic delivery              │
│  L8 AUDIT         — Append-only, no AI involvement      │
│  L11 IAM          — No AI involvement                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

### 8.2 AI Model Interface

```python
# Model-agnostic interface (REQ-MOD-002)
class AIModelAdapter(Protocol):
    """
    Abstract interface for AI model integration.
    Replacing Claude with another model = implementing this interface.
    No other pipeline layer needs to change.
    """
    model_name: str
    model_version: str

    async def extract_fields(
        self,
        document_content: bytes,
        document_type: str,
        target_schema: dict,        # Canonical field schema
        system_prompt: str,         # Version-controlled (REQ-MOD-001)
        field_allowlist: list[str], # Only these fields may be extracted
    ) -> AIExtractionResult: ...

class AIExtractionResult:
    fields: list[AIField]
    model_name: str
    model_version: str
    prompt_version: str
    tokens_used: int
    latency_ms: int

class AIField:
    field_path: str
    proposed_value: Any
    confidence: Literal["HIGH", "MEDIUM", "LOW"]
    source_text: str          # Exact text from document
    extraction_rationale: str # Why this value was proposed
```

### 8.3 AI Safety Controls

| Control | Mechanism | Requirement |
|---|---|---|
| Field allowlist | Only permitted fields can be extracted; Claude cannot write to arbitrary fields | REQ-MOD-001 |
| Confidence gating | LOW confidence fields require explicit user confirmation before pipeline proceeds | REQ-ING-004 |
| System prompt versioning | Prompt changes require compliance sign-off and regression test | REQ-MOD-001 |
| Prompt injection prevention (SC-014) | Document pre-processing strips text outside expected boundaries; Claude uses structured output mode (JSON schema only); suspicious documents with instruction-like patterns flagged for human review before L2; system/user content strictly separated — no user content interpolated into system prompt; pentest scope includes prompt injection via document upload | REQ-ING-004, REQ-AIACT-001 |
| AI classification flag | `ai_produces_regulatory_output = FALSE` — automated CI/CD check | REQ-AIACT-002 |
| Source document deletion | Unstructured documents deleted immediately after extraction | REQ-SEC-003 |
| Audit tagging | All AI-assisted steps tagged distinctly from deterministic steps | REQ-AUD-002 |
| Graceful degradation | AI failure → empty candidate mapping, all fields flagged LOW; user completes manually | REQ-RES-001 |

### 8.4 Use of AI Register

Per REQ-AUD-004, a formal register of AI usage is maintained:

```yaml
ai_register:
  model_name: "Claude (Anthropic)"
  deployment_purpose: "L2 data transformation and normalisation only"
  inputs: "Raw ingested fund data and unstructured documents"
  outputs: "Candidate field mappings with confidence scores"
  human_oversight: "Mandatory confirmation before AI output enters validation; mandatory review gate before NCA submission"
  validation_mechanism: "All AI outputs pass L3 deterministic validation before use"
  ai_classification_flag: "ai_produces_regulatory_output = FALSE"
  retention: "5 years from end of service"
```

---

## 9. Security and IAM Architecture

### 9.1 Encryption

| Layer | Standard | Implementation |
|---|---|---|
| Data in transit | TLS 1.3 (minimum 1.2) | ALB termination; internal service mesh TLS |
| Data at rest | AES-256 | Aurora encryption via AWS KMS |
| Secrets | AES-256 | AWS Secrets Manager with per-tenant keys |
| NCA credentials | AES-256 + envelope encryption | Secrets Manager; per-session retrieval; cleared from memory after use |
| S3 objects | AES-256 | SSE-KMS with bucket-level key policy |
| Backups | AES-256 | Aurora encrypted snapshots; S3 encrypted archives |

Key rotation: Automatic annual rotation for AWS KMS customer-managed keys (CMKs). Default AWS-managed keys not permitted for Eagle data stores (IS-003). NCA credential rotation on client schedule with zero-downtime key swap.

**Approved cryptographic algorithms (SC-007):**
- Hashing: SHA-256, SHA-384, SHA-512, SHA-3. MD5 and SHA-1 prohibited for any purpose.
- Symmetric: AES-256-GCM, AES-256-CBC (with authenticated encryption). DES, 3DES, RC4 prohibited.
- Asymmetric: RSA-2048 minimum (RSA-4096 preferred), ECDSA P-256, ECDSA P-384. RSA < 2048 bits prohibited.
- TLS: TLS 1.2 minimum, TLS 1.3 preferred. TLS 1.0 and 1.1 disabled. ALB security policy: `ELBSecurityPolicy-TLS13-1-2-2021-06`.
- Self-signed certificates prohibited in production. CodeQL flags `hashlib.md5()` and `hashlib.sha1()` as HIGH findings.

### 9.2 Authentication

```
┌────────────┐     ┌──────────┐     ┌──────────────┐
│  Browser   │────▶│  ALB     │────▶│  FastAPI      │
│  (JWT)     │     │          │     │  Auth MW      │
└────────────┘     └──────────┘     └──────┬───────┘
                                           │
┌────────────┐                     ┌───────▼───────┐
│  API Client│────────────────────▶│  OAuth 2.0 /  │
│  (API Key) │                     │  API Key Auth │
└────────────┘                     └───────┬───────┘
                                           │
                                   ┌───────▼───────┐
                                   │  Set RLS      │
                                   │  tenant_id    │
                                   └───────────────┘
```

- **Identity provider:** Amazon Cognito user pools with SRP protocol (SC-003). No custom authentication logic — all auth delegated to Cognito. `USER_PASSWORD_AUTH` flow prohibited.
- **MFA:** TOTP-based MFA mandatory on all accounts (RL-006). SMS MFA not permitted. Applied to: AWS IAM Identity Center, GitHub (via Google Workspace SSO), 1Password, Cognito. Cognito advanced security: lockout after 5 failed attempts.
- **Browser sessions:** JWT tokens from Cognito. Access token: 1-hour expiry. Refresh token: 30-day expiry. Server-side validation via `verify_cognito_token()` FastAPI dependency on every protected endpoint. No session state stored server-side — all claims derived from JWT per request.
- **EAGLE_ADMIN step-up:** Sensitive operations (tenant provisioning, credential vault access, user management) require step-up authentication.
- **API authentication:** OAuth 2.0 client credentials or API key in `Authorization` header.
- **EAGLE_ADMIN read-only access:** Support access to tenant data is auto-logged. Every access generates an audit event visible to the tenant.

### 9.3 Authorisation Model

```python
# Permission matrix — enforced at API layer and query layer
PERMISSIONS = {
    "EAGLE_ADMIN": {
        "tenant:create", "tenant:read", "tenant:archive",
        "user:create", "user:deactivate",
        "audit:read_system", "reference:manage",
        "incident:report", "config:view",
    },
    "TENANT_ADMIN": {
        "aifm:manage", "user:manage_tenant",
        "submission:approve", "override:approve",
        "delivery:configure", "audit:read_tenant",
    },
    "COMPLIANCE_REVIEWER": {
        "submission:review", "submission:approve",
        "override:request", "override:approve",
        "validation:view", "audit:read_aifm",
    },
    "DATA_PREPARER": {
        "data:upload", "data:edit",
        "validation:view", "record:view",
    },
    "READ_ONLY": {
        "record:view", "validation:view",
        "submission:view", "audit:read_aifm",
    },
}
```

### 9.4 Vulnerability Management (REQ-SEC-002)

**Automated scanning** is integrated into every build via CI/CD gates G4–G8 (see Section 12.2). Key tools:
- **SAST:** CodeQL (GitHub GHAS) — blocks on HIGH/CRITICAL including prohibited crypto algorithms (G4)
- **Secret scanning:** GHAS push protection — blocks any detected secret pattern in commits (G5)
- **Dependency scanning:** Dependabot + pip-audit — CRITICAL CVEs block the build (G6)
- **Container scanning:** Trivy — CRITICAL CVEs in image layers block the build; SBOM generated per image (G7)
- **IaC scanning:** Checkov — enforces encryption, port policies, container hardening, pinned actions (G8)
- **DAST:** OWASP ZAP active scan against staging mapped to OWASP Top 10:2025 — blocks production promotion (G10)

**Patching cadence (IS-005):**
- CRITICAL CVE: remediation plan within 5 business days; deployed fix within 14 days
- HIGH CVE: remediation plan within 10 business days; deployed fix within 30 days
- Container base images: rebuilt and redeployed monthly minimum
- RDS: minor version auto-upgrade enabled; major versions follow change management

**Annual penetration test (Section 18):**
- Grey-box methodology; CVSS 4.0 scoring; CREST-accredited vendor
- Mandatory scope: submission pipeline, AI boundary (prompt injection via document upload), AWS configuration, CI/CD integrity, social engineering (NCA credential phishing)
- CRITICAL findings communicated to CTO within 24 hours during exercise
- Remediation SLA: CRITICAL 30 days, HIGH 60 days; targeted retest included in scope

### 9.5 Red Lines (Non-Waivable Security Rules)

Six non-negotiable rules that cannot be waived or worked around. Violation is a disciplinary matter and may trigger a security incident:

| Rule | Summary | Enforcement |
|---|---|---|
| **RL-001** | No credentials outside 1Password or AWS Secrets Manager | GHAS secret scanning push protection (G5); quarterly 1Password audit by CTO |
| **RL-002** | No direct access to production infrastructure — SSM only | Checkov CKV_AWS_25 blocks port-22 Terraform changes; IAM denies SSH |
| **RL-003** | No real client data in non-production environments | No RDS replication from prod; S3 IAM denies cross-env access; violation = GDPR breach |
| **RL-004** | No manual changes to production infrastructure | Branch protection; OIDC deployment; IAM denies Console modification in prod |
| **RL-005** | AI must not bypass the deterministic validation gate | Pipeline enforces L2→L3 ordering; no bypass path in code; quarterly AI boundary review |
| **RL-006** | MFA mandatory on all accounts (TOTP, not SMS) | Cognito, Google Workspace, GitHub SSO, 1Password, AWS IAM Identity Center all enforce MFA |

### 9.6 NCA Credential Vault

Credentials can be stored at two scopes: **service-provider-level** (shared across all AIFM sub-entities under a SERVICE_PROVIDER tenant) and **AIFM-level** (per-AIFM override). This supports both direct AIFMs that manage their own NCA portal access and service providers that submit on behalf of multiple AIFMs using a single set of portal credentials.

```python
class NCACredentialVault:
    """
    Encrypted credential storage for NCA portal access.
    Per REQ-NCA-003: credentials stored in AWS Secrets Manager
    with per-tenant encryption keys.

    Credential scoping:
    - aifm_profile_id=None → service-provider-level (one credential for all AIFMs)
    - aifm_profile_id=<id> → AIFM-specific (overrides service-provider-level)
    """

    async def store_credential(
        self,
        tenant_id: uuid.UUID,
        nca_code: str,
        credential_type: Literal["portal_login", "api_key", "certificate"],
        credential_data: bytes,  # Encrypted before storage
        aifm_profile_id: uuid.UUID | None = None,  # None = service-provider scope
    ) -> None: ...

    async def resolve_credential(
        self,
        tenant_id: uuid.UUID,
        nca_code: str,
        aifm_profile_id: uuid.UUID,
    ) -> CredentialSession:
        """
        Two-step resolution for L7 submission:
        1. AIFM-specific: match (tenant_id, nca_code, aifm_profile_id)
        2. Fallback: match (tenant_id, nca_code, aifm_profile_id IS NULL)
        Raises CredentialNotFoundError if neither scope has an active credential.

        Returns credential for single-use session.
        Credential cleared from memory after session ends.
        Resolved scope logged in audit trail (AIFM vs SERVICE_PROVIDER).
        """
        ...
```

### 9.7 Secrets Lifecycle Management (RL-001)

All credentials used by Eagle follow a defined lifecycle. No credentials exist outside 1Password Teams or AWS Secrets Manager — this is a non-waivable red line (RL-001).

| Credential Type | Storage | Rotation | Access Audit |
|---|---|---|---|
| NCA portal credentials (per-tenant or per-AIFM) | AWS Secrets Manager (per-tenant KMS key) | Client-directed schedule; zero-downtime key swap | Every `GetSecretValue` logged in CloudTrail; IS-008 alert for off-hours access; resolved scope (AIFM / SERVICE_PROVIDER) logged in audit trail |
| SFTP keys (AWS Transfer Family) | AWS Secrets Manager | Annual rotation; automated via Terraform | CloudTrail + Transfer Family access logs |
| Claude API key | AWS Secrets Manager | On key regeneration at Anthropic; CTO performs rotation | CloudTrail; anomalous usage detected via token billing alerts |
| GitHub Actions OIDC | No stored credential — OIDC federation | N/A (short-lived session tokens) | GitHub audit log + CloudTrail AssumeRoleWithWebIdentity |
| Database connection strings | AWS Secrets Manager (injected via ECS `secretsFrom`) | Aurora password rotation (90-day cycle via Secrets Manager auto-rotation) | CloudTrail + RDS Proxy connection logs |
| Developer secrets (local dev) | 1Password Teams vault | On change; never committed to Git (RL-001, G5) | 1Password audit log; quarterly CTO review |
| Google Workspace / SSO credentials | Google Workspace (federated) | Google-managed; MFA enforced (RL-006) | Google Workspace audit log |

**Governance:** CTO performs a quarterly audit of all 1Password vault entries and AWS Secrets Manager secrets. The audit verifies: no stale credentials, rotation schedules adhered to, access restricted to minimum necessary roles. Results documented in the engineering security log.

**Break-glass procedure:** Emergency NCA credential access outside business hours requires CTO approval via 1Password emergency access flow. Access triggers a HIGH CloudWatch alert (IS-008) and is retrospectively reviewed within 24 hours.

### 9.8 HTTP Security Headers (SC-010)

All HTTP responses include mandatory security headers, enforced at FastAPI middleware and verified by OWASP ZAP (G10):

| Header | Value |
|---|---|
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains; preload` |
| `Content-Security-Policy` | `default-src 'self'; frame-ancestors 'none'` |
| `X-Content-Type-Options` | `nosniff` |
| `X-Frame-Options` | `DENY` |
| `Referrer-Policy` | `strict-origin-when-cross-origin` |
| `Permissions-Policy` | `geolocation=(), microphone=(), camera=()` |

Suppressed: `Server` header (no version disclosure), `X-Powered-By` (absent). Absence of any MUST header is a blocking finding at G10.

### 9.9 SSRF Prevention (SC-011 + IS-007)

Defence-in-depth approach with application-layer and network-layer controls:

**Application layer (SC-011):** `OutboundURLValidator` class validates all outbound URL construction — protocol (HTTPS only), hostname against allowlist (`api.anthropic.com`, NCA portal hostnames), blocks RFC 1918, 169.254.x.x (link-local), 127.x.x.x (loopback). Any URL not on allowlist raises `OutboundURLForbiddenError`. CodeQL custom query flags any `urllib`/`httpx`/`requests` call without `OutboundURLValidator` wrapping.

**Network layer (IS-007):** Security group egress rules permit only: TCP 443 to AWS VPC endpoints, TCP 443 to Anthropic API, TCP 443 to NCA portal CIDRs, TCP 22 from dedicated SFTP task role to pre-approved client IPs. Explicit DENY for 169.254.0.0/16 and non-VPC RFC 1918. VPC Flow Logs alert on disallowed egress attempts.

### 9.10 Threat Modelling (STRIDE)

Lightweight STRIDE threat modelling required for security-sensitive changes per SSDF PW.1/PW.2:

**Required for:** New external-facing API endpoints, AI boundary changes (L2/L3 interface), new data stores or data model changes, new third-party integrations with network access, IAM/VPC/security group changes.

**Not required for:** Bug fixes within already-modelled components, UI-only changes, documentation/test updates, dependency version bumps (covered by G6/G7).

Eagle-specific STRIDE controls: Spoofing → Cognito JWT verification (SC-003); Tampering → immutable S3 + cosign signing (IS-004, SRI-001); Repudiation → CloudTrail + structured logs (IS-004, SC-006); Information Disclosure → RLS + never_log list (REQ-TEN-001, SC-006); DoS → ALB WAF + SQS retry policies (SC-013); Elevation of Privilege → IAM least privilege + separation of duties (IS-001, IS-008).

### 9.11 Privileged Access Monitoring (IS-008)

Detective controls for insider threat beyond preventive IAM:

**CloudWatch alerts:** Root account login (CRITICAL, immediate CTO investigation); IAM policy with `Resource:*` attached to any role (HIGH, 5 min); Secrets Manager `GetSecretValue` for NCA credentials outside business hours (HIGH); CloudTrail `StopLogging`/`DeleteTrail` (CRITICAL, active incident); ECS Exec in production (MEDIUM, session transcript captured).

**Separation of duties:** Engineer with NCA portal credential access must not hold production deployment approval authority (G11) in the same business week. Verified via CloudTrail audit.

**Quarterly access review:** CTO audits all GitHub collaborators, AWS IAM Identity Center assignments, 1Password team vault membership, and Cognito EAGLE_ADMIN assignments. Results documented in engineering onboarding log.

### 9.12 ICT Third-Party Risk Management (DORA Art. 28–30)

| Vendor | Service | Classification | Key Controls |
|---|---|---|---|
| **Anthropic** | Claude API (L2 extraction) | Critical ICT third-party | API key in Secrets Manager (RL-001); SSRF controls (SC-011/IS-007); data minimisation via canonical allowlist (REQ-GDPR-005); L3 gate on all output (RL-005); GDPR DPA reviewed annually; BCP scenario S3 |
| **AWS** | Compute, storage, networking | Critical ICT infrastructure | Shared responsibility model documented; SSM-only access (RL-002); CloudTrail audit (IS-004); AWS Config continuous compliance; BCP scenarios S1/S2 |
| **NCA portals** | Regulatory filing destinations | Regulatory counterparty | Credentials in Secrets Manager under `nca-portal-credentials`; IS-008 separation of duties; IS-007 egress allowlist; BCP scenario S4 |

New vendor assessment requires CTO security questionnaire (data processing, certifications, incident notification, SLA, exit provisions) with Head of Compliance review for DORA/GDPR implications. Annual review for all critical vendors.

### 9.13 Security Metrics and Posture Reporting

Monthly one-page security scorecard (RAG status) to CTO and CEO:
- CI/CD gate failure rate by gate (target: G4/G7 block rate < 5% of builds)
- Mean time to remediate CRITICAL CVEs (target: < 14 days)
- Open security findings by severity (target: zero CRITICAL)
- Dependabot PR merge rate (target: patch PRs merged within 7 days)
- Security incident count by severity (target: zero MAJOR)

Quarterly: IAM access review completion (100%), security training completion (100%), vendor assessment currency (< 12 months).
Annual: Pentest completion + remediation rate, BCP test completion, SSDF practice coverage.

### 9.14 Security Training Requirements (ST-001, ST-002, ST-003)

All engineers implementing this architecture must complete mandatory security training as a precondition for code contribution:

| Requirement | Scope | Timing | Verification |
|---|---|---|---|
| **ST-001** Onboarding security training | All engineers | Before first code contribution | Completion logged in engineering onboarding checklist; CTO sign-off |
| **ST-002** Annual security refresher | All engineers | Annually (calendar year) | Tracked in quarterly security metrics (Section 9.12) |
| **ST-003** AI-specific security training | Engineers working on L2 (AI transformation), AI boundary (Section 8), or prompt engineering | Before first L2-related code contribution | Covers: prompt injection defence (SC-014), AI boundary rules (RL-005), structured output enforcement, never-log list for AI prompts (SC-006) |

Training content covers: OWASP Top 10:2025, Eagle red lines (RL-001..006), secure coding standards (SC-001..014), incident response obligations, and the Eagle-specific security architecture described in this document. Training completion is reported as part of the quarterly security scorecard.

---

## 10. Module Architecture

### 10.1 MOD-ADMIN — Eagle Administration

**Primary users:** EAGLE_ADMIN
**Scope:** Tenant provisioning, user management, reference data, system audit, NCA credential vault administration.

Key components:
- Tenant provisioning wizard with paid checklist enforcement (REQ-TEN-003)
- User CRUD with role assignment (REQ-USR-001)
- Reference data management: ECB rates (weekly auto-refresh), GLEIF LEI cache, ESMA register, NCA override file management
- System-wide audit log viewer with cross-tenant search capability
- NCA credential vault UI (store, rotate, revoke) — supports service-provider-level and per-AIFM credential scoping

### 10.2 MOD-CLIENT — Client Compliance Portal

**Primary users:** TENANT_ADMIN, COMPLIANCE_REVIEWER, DATA_PREPARER, READ_ONLY
**Scope:** Day-to-day compliance workflow from data upload through submission confirmation.

Key views:
- **Compliance dashboard** (REQ-DSH-001/002): Obligation calendar, submission status matrix, deadline alerts
- **Data upload** (REQ-ING-001/002/004): Drag-and-drop file upload, API ingestion status, AI extraction review
- **Validation results** (REQ-VAL-001): Per-field results with CAF/CAM/DQ categorisation, fix guidance
- **Review gate** (REQ-REV-001): Bulk and individual review, override management, cross-NCA grouped approval
- **Submission history** (REQ-AUD-003): Full submission timeline with status, NCA confirmation, amendment history
- **Field lineage** (REQ-LIN-001): Click-through from any field to full provenance chain
- **NCA submission preview** (REQ-FMT-001): Pre-submission view of packaged files

### 10.3 MOD-DATA — Data Ingestion and Processing

**Pipeline layers:** L1, L1B, L2
**Scope:** All data intake channels, legacy adapters, AI transformation, position calculations.

Architecture:
- Ingestion channels as pluggable implementations of `IngestionChannel` protocol
- Adapter registry as YAML configuration (REQ-LEG-001)
- Deterministic enrichment engine for legacy templates (AuM, leverage, FX)
- AI transformation service behind model-agnostic interface
- Position-level data model with seven provenance types (REQ-POS-004)
- **Dual canonical module structure** (see §10.13): generic canonical infrastructure (`canonical/model.py`, `canonical/merge.py`) plus AIFMD-specific field definitions (`canonical/aifmd_field_registry.py`, `canonical/aifmd_projection.py`, `canonical/aifmd_source_entities.py`). New products register their own field definitions without modifying the generic canonical layer.

### 10.4 MOD-COMP — Compliance Engine

**Pipeline layers:** L3, L4
**Scope:** Deterministic validation core, DQEF quality layer, override management.

Architecture:
- Rule engine loaded from YAML at runtime (REQ-VAL-001)
- NCA override profiles as configuration files
- Cross-record consistency checks (REQ-VAL-002)
- DQEF implementation with flow type classification and risk-based thresholds (REQ-VAL-003)
- Override workflow with justification, authoriser, and countersignature (REQ-OVR-001)
- ESMA error code mapping for DQEF feedback cross-reference

### 10.5 MOD-REVIEW — Review and Approval Gate

**Pipeline layer:** L5
**Scope:** Mandatory human review gate. Non-bypassable.

Single requirement (REQ-REV-001) with strict implementation:
- No API endpoint to submit directly to L6 without L5 approval
- Bulk approval only for zero-flag records with Merkle root hash in audit
- Individual review with per-flag decisions
- Cross-NCA grouped approval for content-identical variants

### 10.6 MOD-SUB — Submission and Delivery

**Pipeline layers:** L6, L7
**Scope:** XML packaging, six delivery channels, NCA portal robots, acknowledgement processing.

Architecture:
- Packaging configuration per NCA as YAML files (REQ-FMT-001)
- Six channel implementations each producing equivalent audit records
- Robot portal automation using headless browser (REQ-NCA-001)
- FIFO queue for AIFM-before-AIF sequencing (REQ-SCL-005)
- Fallback procedures per channel (REQ-RES-001)

### 10.7 MOD-AUDIT — Audit Trail, Lineage and Archive

**Pipeline layer:** L8
**Scope:** Immutable event log, field lineage, submission archive, ISAE/SOC 2 evidence.

Architecture:
- Partitioned audit_events table (monthly partitions)
- Hash chain for tamper detection (previous_hash → event_hash)
- No UPDATE/DELETE grants at database level
- Partition archival to S3 Glacier after 1 year
- Machine-readable JSON export for external auditor access

### 10.8 MOD-API — External API and Integration

**Pipeline layer:** L10
**Scope:** Versioned REST API, OAuth 2.0, rate limiting, white-label embedding.

Architecture:
- FastAPI with auto-generated OpenAPI 3.0 specification
- URL-based versioning (`/api/v1/...`)
- JWT-based white-label embedding for service providers (REQ-API-002)
- Per-tenant rate limiting via Redis sliding window

### 10.9 MOD-MANAGEMENT — Company Management Intelligence

**Primary users:** EAGLE_ADMIN, COO, CCO, CRO, CFO, HEAD_OF_CS
**Scope:** Operational dashboards, pipeline monitoring, incident management, compliance risk register, ISAE controls.

Key views:
- **COO view** (REQ-OPS-001..014): Pipeline queue, capacity calendar, exception log, DORA impact register
- **CCO/CRO view** (REQ-INT-001/002): Legitimacy review queue, prospect funnel, enrichment analytics
- **CS view** (REQ-CS-001..008): Client health scores, onboarding tracker, submission success rates
- **CFO view**: Revenue metrics, billing status, cost allocation
- All views read from the read replica to isolate from operational OLTP

### 10.10 MOD-GTM — Go-to-Market Automation

**Primary users:** EAGLE_ADMIN, CCO, CRO, CCO_DELEGATE
**Scope:** AIFM prospect database, web enrichment, legitimacy validation.

Architecture:
- Internal prospect database seeded from ESMA register (weekly refresh)
- Asynchronous AI enrichment pipeline (REQ-GTM-001) — separate from compliance pipeline
- Legitimacy scoring across four sources (REQ-GTM-002)
- CCO review queue with delegatable approval (CCO_DELEGATE)
- GDPR controls: legitimate interest basis, 30-day deletion for rejected prospects

### 10.11 MOD-TRIAL — Trial Account Lifecycle

**Primary users:** EAGLE_ADMIN, COO, CCO_DELEGATE, TRIAL_USER
**Scope:** Self-service registration, legitimacy gate, feature gating, pre-population, health monitoring, conversion trigger.

Architecture:
- Trial provisioning tied to MOD-GTM legitimacy score
- TRIAL_TENANT type with feature gates (no Annex IV download, no NCA submission)
- Register data pre-population via L1/L2 pipeline with `TRIAL_PRE_POP` flag
- 60-day configurable trial limit with health scoring (REQ-TRIAL-004)
- Conversion to paid requires CS Manager action and full paid checklist

### 10.12 MOD-BILLING — Billing and Subscriptions (Phase 1.5)

Stub module. Phase 1 billing handled operationally. Activated at ~10 clients or first external funding round. Trial-to-paid conversion trigger (REQ-TRIAL-006) is Phase 1.

### 10.13 Dual Canonical Module Structure

**Rationale:** The Eagle pipeline operates on a canonical record that must be both product-agnostic (so the platform can orchestrate, store, and audit records for any future product) and product-specific (so each regulatory regime can define its own fields, projections, and source entity mappings). The "dual canonical" pattern separates these concerns through naming convention and module boundaries.

**Naming convention:** Modules prefixed with `aifmd_` contain AIFMD-specific logic. Unprefixed modules in the same package are generic and must remain product-agnostic. This convention extends to all packages: `canonical/`, `shared/`, `derivation/`, and the top-level `aifmd_packaging/` directory.

**Module map — as implemented:**

```
canonical/                              # Canonical record infrastructure
├── model.py                            # GENERIC — CanonicalRecord, CanonicalField Pydantic models
├── merge.py                            # GENERIC — SourceMerger: multi-source field merging with priority
├── provenance.py                       # GENERIC — Provenance enum (IMPORTED, AI_PROPOSED, DERIVED, …)
├── store.py                            # GENERIC — CanonicalStore: DB read/write, version tracking
├── aifmd_field_registry.py             # AIFMD  — Field paths, types, sections for all Annex IV fields
├── aifmd_projection.py                 # AIFMD  — Canonical record → flat dict for XML builder / UI
└── aifmd_source_entities.py            # AIFMD  — AIFM / AIF entity definitions, record-type rules

shared/                                 # Shared utilities
├── constants.py                        # GENERIC — EEA country list, currency codes, region keys
├── reference_data.py                   # GENERIC — Country→region, position→turnover base mappings
├── formatting.py                       # GENERIC — String/number formatting (_str, _int_round, …)
├── aifmd_constants.py                  # AIFMD  — Strategy types, sub-asset codes, ESMA enumerations
└── aifmd_reference_data.py             # AIFMD  — AIFMD-specific lookup tables, NCA code patterns

derivation/                             # Derivation engine
├── fx_service.py                       # GENERIC — ECB rate fetching, caching, conversion
└── aifmd_period.py                     # AIFMD  — Reporting period derivation, frequency rules

aifmd_packaging/                        # AIFMD XML generation (L6) — entirely product-specific
├── orchestrator.py                     # Packaging orchestration, NCA bundling, file naming
├── aifm_builder.py                     # AIFM-level XML builder
└── aif_builder.py                      # AIF-level XML builder

validation/                             # Validation engine (L3 + L4)
└── aifmd_approved_rule_hashes.yaml     # AIFMD  — Approved rule file integrity hashes
```

**Adding a second product (e.g., EMIR):** A new product creates its own prefixed modules (`emir_field_registry.py`, `emir_constants.py`, `emir_packaging/`, etc.) alongside the existing AIFMD ones. The generic modules (`model.py`, `merge.py`, `constants.py`, `fx_service.py`) are shared across all products unchanged. The `ProductContext` (§11.2) resolves which field registry, projection, and packaging modules to load at runtime.

**Relationship to the pipeline decomposition plan:** The dual canonical structure implements the foundational layer described in the Eagle Ingestion-to-Submission Pipeline Design Plan (Phase 1: extract shared code, Phase 2: extract canonical model). The `aifmd_` prefix convention ensures that the Phase 1–2 separation is maintained as the pipeline matures through Phases 3–7 (derivation extraction, XML packaging, validation engine, DB + review loop, and new adapters).

---

## 11. Platform–Product Isolation

### 11.1 Isolation Boundary (REQ-ARCH-001)

The platform layer must not contain:
- Hard-coded references to AIFMD, Annex IV, NCA codes, or XSD schema versions
- AIFMD-specific field names in platform layer code
- Submission channel logic tied to a specific regulatory regime
- Obligation frequency logic in platform orchestration

The product layer must contain:
- All validation rule logic and NCA override profiles
- The product-specific canonical field definitions (e.g., `aifmd_field_registry.py`, `aifmd_projection.py`, `aifmd_source_entities.py`)
- Product-specific constants and reference data (e.g., `aifmd_constants.py`, `aifmd_reference_data.py`)
- Product-specific packaging logic (e.g., `aifmd_packaging/`)
- Product-specific derivation logic (e.g., `derivation/aifmd_period.py`)
- All submission channel adapters specific to that product's NCAs
- Obligation calendar generation logic
- All regime-specific error codes and DQEF equivalents

The generic canonical infrastructure (`canonical/model.py`, `canonical/merge.py`, `canonical/provenance.py`, `canonical/store.py`) and shared utilities (`shared/constants.py`, `shared/reference_data.py`, `shared/formatting.py`) remain product-agnostic. See §10.13 for the full dual canonical module map.

### 11.2 Product Context Object

The platform communicates with products through an abstract `ProductContext`:

```python
@dataclass
class ProductContext:
    """
    Product identity resolved at runtime from product registry.
    Platform orchestration triggers product pipeline via this object.
    """
    product_id: str                  # e.g., "AIFMD_ANNEX_IV"
    product_module: str              # e.g., "app.products.aifmd"
    canonical_schema: dict           # Product's canonical data model
    field_registry_module: str       # e.g., "canonical.aifmd_field_registry"
    projection_module: str           # e.g., "canonical.aifmd_projection"
    source_entities_module: str      # e.g., "canonical.aifmd_source_entities"
    constants_module: str            # e.g., "shared.aifmd_constants"
    reference_data_module: str       # e.g., "shared.aifmd_reference_data"
    packaging_module: str            # e.g., "aifmd_packaging"
    validation_rules_path: str       # Path to product's rule files
    packaging_config_path: str       # Path to product's packaging config
    submission_channels: list[str]   # Product's available channels
    obligation_calendar: Callable    # Product's obligation logic
    review_checklist: dict           # Product-specific review checklist

class ProductRegistry:
    """
    Configuration-driven product discovery (REQ-ARCH-002).
    Loaded from config/product_registry.yaml at startup.
    """
    def resolve(self, product_id: str) -> ProductContext: ...
    def list_active(self) -> list[ProductContext]: ...
```

### 11.3 Adding a New Product (Future)

To add a second regulatory reporting product (e.g., EMIR, SFDR):

1. Create a new product module under `app/products/emir/`
2. Define the canonical data model, validation rules, packaging config
3. Add an entry to `config/product_registry.yaml`
4. Assign the product to eligible tenants (REQ-ARCH-003)

No changes to platform modules required. Verified by integration tests that substitute a mock product context.

---

## 12. Deployment and CI/CD

### 12.1 Environment Strategy

| Environment | Purpose | Data | Access |
|---|---|---|---|
| `development` | Developer workstations | Synthetic only | Developers |
| `staging` | Pre-production validation | Synthetic only (REQ-ISO-007/008) | Engineering + QA |
| `production` | Live service | Client data | Restricted (four-eyes deployment) |

Production and staging are in separate AWS accounts for isolation (REQ-ISO-007). No production data in non-production environments — ever.

### 12.2 CI/CD Pipeline (REQ-REL-002)

The CI/CD pipeline enforces 11 sequential security gates (G1–G11). A build that fails any gate is blocked from progressing. Gates are hard blocks — not advisory.

| Gate | Name | Tool | Blocks On |
|---|---|---|---|
| **G1** | Lint and style | ruff (Python), eslint (TypeScript) | Any linting error |
| **G2** | Unit tests + coverage | pytest + coverage.py | < 90% coverage on L2/L3/L4/L6/L7; < 80% all other production code |
| **G3** | Integration tests | pytest + Docker Compose (ephemeral RDS/Redis) | Any test failure |
| **G4** | SAST | CodeQL (GitHub GHAS) | Any HIGH or CRITICAL finding; prohibited algorithms (SC-007) |
| **G5** | Secret scanning | GitHub GHAS push protection | Any detected secret pattern in diff (RL-001) |
| **G6** | Dependency vulnerability | Dependabot + pip-audit | Any CRITICAL CVE in pinned dependencies |
| **G7** | Container image scan + SBOM | Trivy | CRITICAL CVE in image layers; SBOM generation failure |
| **G8** | IaC security scan | Checkov | CRITICAL Terraform/Dockerfile policy violations (port-22, missing encryption, unpinned GH Actions) |
| **G9** | Container build, sign, push | GitHub Actions + ECR + cosign | Build failure; signing failure |
| **G10** | Staging deploy + DAST | Terraform apply + OWASP ZAP | HIGH/CRITICAL DAST finding; missing MUST security headers (SC-010) |
| **G11** | Production deploy (manual) | Terraform apply | No CTO/Head of Engineering approval within 24h; separation of duties check (IS-008) |

**Key enforcement rules:**
- **OIDC-based AWS deployment (RL-004):** No long-lived CI/CD credentials. GitHub Actions authenticates to AWS via OIDC federation.
- **Branch protection:** No direct push to main; PR with minimum 1 reviewer required.
- **Container image signing (SRI-001):** Every image signed with cosign (ECDSA P-256 key in Secrets Manager) at G9. Fargate validates signature before task start. Invalid signature = MAJOR incident.
- **SBOM (SRI-002):** CycloneDX SBOM generated at G7 for every production image. Archived as GitHub Actions artefact (5-year retention) and uploaded to S3 `eagle-sbom-archive` bucket.
- **SHA-pinned actions (SC-012):** All third-party GitHub Actions referenced by full commit SHA — no tag/branch references. Enforced by Checkov CKV_GHA_3 at G8.
- **No manual deployment (RL-004):** Production and staging locked — no direct SSH, console, or infrastructure-level deployment outside the pipeline. AWS IAM policies deny Console-based resource modification in production. Terraform state locked in S3/DynamoDB with daily drift detection.
- **Separation of duties (IS-008):** G11 production deploy approver must not have accessed NCA portal credentials in the same business week.
- **Emergency path:** Hotfix deployments run minimum G4, G5, G7, G8 gates. Full suite must pass within 24 hours of emergency deployment.

### 12.3 Infrastructure as Code

All infrastructure defined in Terraform:

```
infrastructure/
├── modules/
│   ├── vpc/
│   ├── ecs/
│   ├── aurora/
│   ├── sqs/
│   ├── s3/
│   ├── secrets/
│   ├── monitoring/
│   └── transfer-family/
├── environments/
│   ├── staging/
│   └── production/
└── global/
    ├── iam/
    ├── kms/
    └── route53/
```

Infrastructure changes go through the same CI/CD pipeline with Terraform plan review and four-eyes approval.

### 12.4 Secure Code Review Process (SC-009)

All pull requests undergo a tiered security review checklist before merge. PRs cannot be merged if any security finding is unresolved.

**Review checklist (applied by reviewer per change scope):**

| Category | Check | Applies To |
|---|---|---|
| Authentication | Cognito JWT verified on all new endpoints; no custom auth logic | API changes |
| Input validation | Pydantic models with explicit field constraints; no raw SQL | API / data changes |
| Secrets | No hardcoded secrets, tokens, or connection strings; `secretsFrom` only | All changes |
| Error handling | No bare `except:` or swallowed exceptions in pipeline paths (SC-013) | Pipeline changes |
| AI boundary | L2 output never bypasses L3; prompt injection defences intact (SC-014, RL-005) | L2 / AI changes |
| Dependencies | Pinned versions; no new CRITICAL/HIGH CVEs; SHA-pinned GH Actions (SC-005, SC-012) | Dependency changes |
| Data handling | No real data in tests; never-log list respected (DH-001, SC-006) | Data / logging changes |
| RLS | New tables have RLS policy; `tenant_id` column present (REQ-TEN-001) | Schema changes |

**Escalation:** Security findings detected during review that are not resolved within 24 hours are escalated to the CTO. CRITICAL findings (red line violations, credential exposure, RLS bypass) block the PR immediately — no "fix later" exceptions.

**Threat modelling gate:** Changes to security-sensitive components (new API endpoints, AI boundary, data stores, IAM/VPC, third-party integrations) require a lightweight STRIDE threat model as part of the PR description before review begins. See Section 9.9 for the STRIDE framework.

---

## 13. Observability and Operations

### 13.1 Monitoring Stack

```
┌──────────────────────────────────────────────────────┐
│                  Observability                        │
│                                                      │
│  Metrics:   CloudWatch Container Insights + Custom    │
│  Logs:      CloudWatch Logs (structured JSON)        │
│  Traces:    AWS X-Ray (distributed tracing)          │
│  Dashboards: CloudWatch Dashboards (ops)             │
│              + MOD-MANAGEMENT (business, DB-first)    │
│  Alerts:    CloudWatch Alarms → SNS → PagerDuty     │
└──────────────────────────────────────────────────────┘
```

### 13.2 Key Operational Metrics

| Metric | Target | Alert Threshold | Source |
|---|---|---|---|
| API latency (p99) | < 500ms | > 1s | ALB + FastAPI middleware |
| Validation single record | < 5s | > 10s | L3 engine instrumentation |
| Validation batch 100 AIFs | < 60s | > 120s | Orchestration layer |
| AI transformation single file | < 30s | > 60s | L2 Claude API timer |
| Queue depth (per stage) | < 100 | > 500 | SQS CloudWatch metrics |
| DLQ depth | 0 | > 0 | SQS DLQ CloudWatch alarm |
| Error rate | < 0.1% | > 1% | ALB 5xx count |
| Uptime | 99.5% | < 99.5% monthly | Synthetic monitoring |
| Database connections | < 80% pool | > 90% pool | RDS Proxy metrics |
| Worker utilisation | < 70% | > 85% | ECS task metrics |

#### 13.2.1 Security Event Alerting (IS-004 / IS-008)

CloudTrail logs are streamed to CloudWatch Logs via a multi-region trail. CloudWatch Metric Filters detect security-relevant events and trigger alarms via SNS → PagerDuty. This replaces a dedicated SIEM for Phase 1 while meeting IS-004 and IS-008 requirements.

| Security Event | CloudTrail Event / Pattern | Severity | Response SLA | SNS Target |
|---|---|---|---|---|
| Root account login | `ConsoleLogin` where `userIdentity.type = Root` | CRITICAL | Immediate CTO investigation | PagerDuty (CTO) |
| IAM policy with `Resource:*` | `PutRolePolicy` / `AttachRolePolicy` where policy contains `"Resource": "*"` | HIGH | < 5 min | PagerDuty (CTO) |
| CloudTrail tampered | `StopLogging` / `DeleteTrail` / `UpdateTrail` | CRITICAL | Immediate — active incident | PagerDuty (CTO + COO) |
| NCA credential access off-hours | `GetSecretValue` on `nca-portal-credentials/*` outside 07:00–19:00 CET weekdays | HIGH | < 15 min | PagerDuty (CTO) |
| ECS Exec in production | `ExecuteCommand` on production ECS cluster | MEDIUM | < 1 hour | SNS (CTO) |
| Security group modification | `AuthorizeSecurityGroupIngress` / `RevokeSecurityGroupIngress` in production | HIGH | < 15 min | PagerDuty (CTO) |
| Failed Cognito MFA attempts | Cognito `SignIn` failure with `TOTP_REQUIRED` > 5 within 10 min per user | MEDIUM | < 1 hour | SNS (EAGLE_ADMIN) |
| VPC Flow Logs egress anomaly | Outbound traffic to IP outside ALB/VPC-endpoint/allowlist CIDRs | HIGH | < 15 min | PagerDuty (CTO) |

**Implementation:** CloudTrail → CloudWatch Logs Log Group → Metric Filters (one per event pattern) → CloudWatch Alarms → SNS Topics (CTO-critical, ops-medium). VPC Flow Logs enabled on all subnets, streamed to CloudWatch Logs with metric filter for unexpected egress.

### 13.3 Structured Logging

All logs emitted as structured JSON:

```json
{
  "timestamp": "2026-03-31T14:23:01.123Z",
  "level": "INFO",
  "service": "eagle-api",
  "trace_id": "abc-123",
  "tenant_id": "masked-uuid",
  "user_id": "pseudonymous-id",
  "event": "validation_completed",
  "pipeline_layer": "L3",
  "record_id": "uuid",
  "duration_ms": 2340,
  "result": "CAF_FAILED",
  "caf_count": 3
}
```

Tenant IDs masked in logs; resolved only for authorised support investigations. No PII in logs. Uses `structlog` with redaction processors for known sensitive key names.

**Never-log list (SC-006):** JWT tokens (any form), passwords/credential values, NCA portal credentials, raw client AIF data/NAV figures, AIFM/AIF identifiers combined with submission content, GDPR personal data (names, emails, IDs), Claude API prompts in plain text (log SHA-256 hash only), Secrets Manager values. CloudWatch subscription filter alerts on regex patterns matching JWT format. Production log level: INFO; DEBUG permitted in staging only.

### 13.4 DORA Incident Workflow (REQ-CPL-001)

```
Incident Detected
       │
       ▼
┌──────────────┐    MAJOR: Outage near deadline / data integrity
│  Classify    │──▶ → Client notification within 4 hours
│  Severity    │    → Authority report available within 4 hours
│              │    → Post-incident review within 5 business days
│              │
│              │──▶ SIGNIFICANT: Degradation >1 hour
│              │    → Client notification within 24 hours
│              │
│              │──▶ MINOR: Isolated fault, no client impact
└──────────────┘    → Monthly service report
```

---

## 14. Resilience and Disaster Recovery

### 14.1 Availability Targets (REQ-RES-002)

| Metric | Target |
|---|---|
| Monthly uptime | 99.5% (excluding planned maintenance) |
| RTO (Recovery Time Objective) | 4 hours |
| RPO (Recovery Point Objective) | 1 hour |
| Planned maintenance notice | 48 hours minimum |
| Maintenance blackout | Not within 5 business days of any active submission deadline |

### 14.2 Failure Modes (REQ-RES-001)

| Failure | Response | Fallback |
|---|---|---|
| Ingestion failure | Return error with specific cause; no partial state | Client-initiated retry |
| AI transformation failure | Retry once after 30s; degrade to empty mapping with all fields LOW | Manual completion |
| Validation engine fault | Block with SYSTEM_ERROR; notify EAGLE_ADMIN immediately | Manual investigation |
| Direct API submission failure | Retry 3× exponential backoff (30s, 120s, 300s) | Switch to MANUAL channel |
| Robot portal failure | Per REQ-NCA-002 fallback procedure | Download for manual submission |
| Database failover | Aurora automatic failover to standby (< 60s) | Read replica promotion if needed |
| Queue failure | DLQ catches failed items; EAGLE_ADMIN alerted | Manual reprocessing |

### 14.3 Backup Strategy

| Component | Backup Method | Retention | RPO |
|---|---|---|---|
| Aurora PostgreSQL | Continuous backup + PITR | 35 days | < 5 minutes |
| Aurora snapshots | Daily automated | 90 days | 24 hours |
| S3 submissions | Cross-region replication | 10 years | Near-zero |
| Configuration files | Git (version-controlled) | Indefinite | Near-zero |
| Secrets Manager | AWS-managed replication | N/A | Near-zero |

### 14.4 Business Continuity Scenarios (DORA Art. 11)

Four named BCP scenarios with defined RTO and ownership:

| Scenario | Description | Expected Behaviour | RTO | Owner |
|---|---|---|---|---|
| **S1: AZ Failure** | Single AZ failure in eu-west-1 | ECS Fargate auto-rescheduled in remaining AZs; Aurora Multi-AZ promoted automatically; ALB continues serving. No engineer action required. | < 15 min | Head of Engineering (monitor) |
| **S2: Region Failure** | Full eu-west-1 failure | CTO declares disaster. DR runbook: restore latest RDS snapshot to eu-central-1; deploy ECS from ECR (cross-region); update Route 53 DNS. S3 cross-region replication ensures data availability. | 4 hours | CTO (decision), Head of Engineering (execution) |
| **S3: Claude API Unavailable** | Anthropic API unavailable or degraded | In-flight submissions queued in SQS with state persisted in PostgreSQL (retry per SC-013). Client notification via COO. If >4h during active submission window: CTO assesses manual L2 bypass with human review. | Anthropic-dependent; manual fallback for small volumes | CTO (assess), COO (communicate) |
| **S4: NCA Portal Unavailable** | NCA portal down on submission deadline | Eagle generates and validates complete package, retains in immutable S3 archive. COO contacts NCA via regulatory channel. Head of Compliance assesses DORA Art. 19 notification. | N/A — package archived for deferred submission | COO + Head of Compliance |

**Annual BCP test programme (DORA Art. 11(6)):**
- Q1: AZ failure simulation via AWS Fault Injection Simulator (< 30 min, automated)
- Q2: Tabletop exercise — S2 or S3 scenario (90 min, CTO + Head of Compliance + Head of CS)
- Q3: Backup restoration test — restore RDS snapshot + S3 data to isolated environment, verify integrity
- Q4: Integrated test as part of annual pentest — resilience of controls validated under disruption

Each test produces documented outcomes stored as immutable artefacts per REQ-AUD-001. Gaps logged in risk register with owner and remediation date.

---

## 15. Principle Traceability Matrix

Every architectural decision traces to one or more Blueprint principles:

| Principle | Key Architectural Decisions |
|---|---|
| **P1** Customer experience first | < 2s dashboard load; 10-min trial provisioning; clear error messages with fix guidance |
| **P2** Code-first, human-by-exception | Priority queue architecture; automated pipeline L1→L7; humans only at L5 review gate |
| **P3** Standardised product | NCA configuration-driven (not custom code); product registry pattern; fixed scope per product |
| **P4** Single source of truth | Canonical records in PostgreSQL; JSONB data model; field-level provenance tracking |
| **P5** Deterministic core, probabilistic edge | AI at L2 only; L3/L4/L6/L7 fully deterministic; non-bypassable gate between AI and submission |
| **P6** Modular and portable | Rules as YAML config; model-agnostic AI interface; pluggable adapters; platform–product isolation |
| **P7** Resilience | Defined failure modes per layer; DLQ with alerting; RTO 4h / RPO 1h; exponential backoff |
| **P8** Compliance-proof by design | Immutable audit trail; hash chain tamper detection; L5 non-bypassable; rule versioning |
| **P9** Security by design | RLS at database; TLS 1.3; AES-256 KMS; credential vault; per-tenant isolation |
| **P10** Founder-independent | All rules codified in configuration; no institutional knowledge required; automated regression suite |
| **P11** Continuous learning | AI confidence scoring; DQEF feedback loop; validation false-positive tracking |
| **P12** Ambitious growth | Auto-scaling ECS workers; per-tenant resource quotas; Fargate cost model; read replica for analytics |
| **P13** Internationally oriented | Multi-NCA architecture; configurable per jurisdiction; all communications English |
| **P14** Database-first | PostgreSQL as system of record; XML/PDF/CSV are generated views; no loose file workflows |
| **P15** Platform-first, product-second | Separate schemas; ProductContext abstraction; product registry; no AIFMD in platform code |
| **P16** Location-independent | Fully cloud-native; async-first queue architecture; no on-premise dependencies |

---

*End of document. This architecture is derived from and traceable to the Project Eagle Blueprint v1.0 (baselined 2026-03-23) and the Developer Security Guidelines v2.0 (2026-03-23). All requirement references (REQ-\*) point to the authoritative Blueprint YAML files. Security control references (RL-\*, SC-\*, IS-\*, SRI-\*, G1–G11) point to the Developer Security Guidelines.*
