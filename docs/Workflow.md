# AEGIS AI -- System Workflow and Implementation Process

## 1. Overview

This document describes the operational workflow, multi-agent execution
process, decision-making mechanism, and implementation phases of AEGIS
AI (AI Evidence Guard for Integrity and Security).

AEGIS AI uses a supervisor-controlled multi-agent architecture to
evaluate AI-generated responses against trusted organisational knowledge
sources and assess potential security risks before releasing responses
to end users.

## 2. System Workflow

The system follows a structured verification workflow consisting of the
following stages.

### 2.1 Request Intake

The FastAPI Gateway receives incoming requests and performs: - User
authentication. - Deterministic access control. - Input validation. -
Request processing.

### 2.2 Agent Orchestration

The LangGraph Supervisor Agent coordinates the verification workflow. It
creates and maintains a shared state, delegates tasks to specialised
agents, manages execution dependencies, and aggregates their results.

### 2.3 Multi-Agent Verification

Four specialised agents perform the core analysis.

**Claim Extraction Agent** - Extracts atomic factual claims from
AI-generated responses. - Identifies entities, dates, numerical values,
and policy-related statements. - Produces structured claim data.

**Evidence Retrieval Agent** - Retrieves relevant information from
authorised organisational documents. - Uses hybrid retrieval combining
semantic and keyword-based search. - Preserves source references,
document versions, and page information.

**Fact Verification Agent** - Evaluates extracted claims against
retrieved evidence. - Classifies claims as `SUPPORTED`, `CONTRADICTED`,
or `INSUFFICIENT EVIDENCE`. - Produces evidence-based verification
results.

**Security and Risk Assessment Agent** - Examines generated responses
and retrieved content for indirect prompt injection. - Identifies
potential sensitive information exposure. - Assigns an appropriate
security risk severity.

### 2.4 Policy-Based Decision Making

The Supervisor aggregates the agent outputs and forwards them to the
Policy Decision Engine.

The Policy Decision Engine is a deterministic, rule-based component
rather than an LLM agent. It evaluates verification results, evidence
availability, security severity, and configured policies.

It produces one of four outcomes:

-   **APPROVE:** Releases acceptable responses with supporting
    citations.
-   **CORRECT:** Sends inaccurate claims to the Correction Module for
    evidence-based correction and subsequent re-verification.
-   **BLOCK:** Withholds unsafe or prohibited responses.
-   **HUMAN REVIEW:** Escalates uncertain or high-risk cases for manual
    assessment.

Corrected responses must pass verification and policy checks again
before release.

### 2.5 Failure Handling

The Supervisor manages agent execution failures and retry operations. If
a required agent fails after the configured retries, the request is
escalated to Human Review. Unverified responses are not automatically
released.

### 2.6 Audit and Traceability

The system records relevant workflow events, verification results,
decision outcomes, source references, and execution information to
support traceability and auditing.

## 3. Knowledge Base Preparation Workflow

Trusted organisational documents are processed through a separate
ingestion pipeline before runtime verification.

The ingestion process includes:

1.  Document upload and validation.
2.  Text extraction using PyMuPDF.
3.  Text cleaning and chunking.
4.  Embedding generation using Sentence Transformers.
5.  Semantic indexing in ChromaDB.
6.  Keyword indexing using BM25.
7.  Storage of document metadata and version information.

SQLite maintains relevant metadata and audit records.

The runtime Evidence Retrieval Agent accesses this prepared knowledge
base rather than processing original documents for every request.

## 4. Implementation Process

The implementation is organised into the following development stages:

1.  **Project Setup:** Establish the repository, backend, frontend,
    dependencies, and development environment.
2.  **Knowledge Base Development:** Implement document ingestion, text
    extraction, chunking, embedding generation, and indexing.
3.  **Agent Development:** Implement the four specialised agents and
    define their structured inputs and outputs.
4.  **Workflow Orchestration:** Integrate the agents using LangGraph and
    implement shared-state management.
5.  **Decision Engine Development:** Implement deterministic response
    policies, correction handling, and failure escalation.
6.  **API Integration:** Connect the backend workflow with the React
    frontend through FastAPI endpoints.
7.  **Testing and Evaluation:** Test factual verification, security
    detection, decision consistency, and system performance.

## 5. Workflow Design Principles

The implementation follows these principles:

-   Supervisor-controlled agent coordination.
-   Evidence-based factual verification.
-   Authorised and version-aware document retrieval.
-   Deterministic access control and policy enforcement.
-   Fail-safe handling of agent execution errors.
-   Traceable decisions and audit logging.
