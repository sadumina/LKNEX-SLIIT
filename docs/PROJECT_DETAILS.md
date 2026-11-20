# AEGIS AI -- Project Details and Technical Specifications

## 1. Project Information

  Attribute          Description
  ------------------ --------------------------------------------------
  Project Name       AEGIS AI
  Full Name          AI Evidence Guard for Integrity and Security
  Project Category   Artificial Intelligence and Cybersecurity
  System Type        Multi-Agent AI Verification and Security Gateway

## 2. Project Overview

AEGIS AI is a multi-agent AI verification and cybersecurity framework
designed to improve the reliability and security of AI-generated
responses in organisational environments.

The system acts as an intermediate verification layer between AI
applications and end users. It evaluates generated responses against
trusted organisational documents, identifies unsupported or
contradictory factual claims, assesses potential security threats, and
applies policy-based decisions before releasing responses.

The framework uses a supervisor-controlled architecture implemented with
LangGraph, supported by specialised AI agents and a deterministic Policy
Decision Engine.

## 3. Problem Statement

Large Language Models can generate inaccurate, unsupported, or
misleading information, even when connected to external knowledge
sources through Retrieval-Augmented Generation (RAG).

Furthermore, retrieved documents and external content may contain
malicious instructions or information that introduces security risks.

Conventional AI application workflows may not provide sufficient
integrated mechanisms to verify individual factual claims, assess
retrieved evidence, detect security threats, and enforce consistent
response policies.

AEGIS AI addresses this challenge through a structured verification and
security assessment workflow.

## 4. Project Objectives

The primary objectives are:

1.  Develop a supervisor-based multi-agent architecture for AI response
    verification.
2.  Implement evidence-based factual verification using trusted
    organisational documents.
3.  Integrate hybrid information retrieval for relevant and traceable
    evidence.
4.  Identify potential prompt injection attacks and sensitive
    information exposure.
5.  Implement deterministic, risk-based response decision-making.
6.  Evaluate the proposed framework against conventional single-agent
    and unverified AI response approaches.

## 5. Core System Features

### 5.1 Multi-Agent Verification

Coordinates four specialised agents to perform claim extraction,
evidence retrieval, factual verification, and security assessment.

### 5.2 Evidence-Based Verification

Evaluates individual claims against trusted organisational documents and
provides supporting source references.

### 5.3 Hybrid Evidence Retrieval

Combines semantic search and keyword-based retrieval to identify
relevant document passages.

### 5.4 Security and Risk Assessment

Examines AI-generated responses and retrieved content for potential
prompt injection and sensitive information exposure.

### 5.5 Policy-Based Response Management

Applies deterministic rules to approve, correct, block, or escalate
generated responses.

### 5.6 Document Version Management

Maintains document metadata, source references, and version information
to support version-aware evidence retrieval.

### 5.7 Audit and Monitoring

Maintains workflow records, verification outcomes, decision information,
and relevant execution logs.

## 6. Core System Modules

  -----------------------------------------------------------------------
  Module                              Primary Responsibility
  ----------------------------------- -----------------------------------
  FastAPI Gateway                     Request handling, authentication,
                                      access control, and validation

  Supervisor Agent                    Workflow orchestration and agent
                                      coordination

  Claim Extraction Agent              Atomic factual claim identification

  Evidence Retrieval Agent            Authorised evidence retrieval

  Fact Verification Agent             Evidence-based claim evaluation

  Security and Risk Assessment Agent  Security threat identification and
                                      risk classification

  Policy Decision Engine              Deterministic response decisions

  Correction Module                   Evidence-based response correction

  Knowledge Ingestion Module          Document processing and indexing

  Audit Module                        Decision and workflow record
                                      management

  React Dashboard                     User interaction and verification
                                      reporting
  -----------------------------------------------------------------------

## 7. Technology Stack

### Frontend

-   React
-   Vite
-   Tailwind CSS

### Backend

-   Python
-   FastAPI
-   Pydantic

### AI and Agent Orchestration

-   LangGraph
-   Large Language Model API
-   Sentence Transformers

### Information Retrieval and Storage

-   ChromaDB
-   BM25
-   SQLite

### Document Processing

-   PyMuPDF

### Development and Version Control

-   Git
-   GitHub

## 8. Expected System Outputs

AEGIS AI is designed to provide:

-   Claim-level verification results.
-   Supporting evidence and document citations.
-   Security risk assessments.
-   Policy-based response decisions.
-   Corrected responses where evidence supports correction.
-   Human review escalation information.
-   Auditable workflow records.

## 9. Project Scope

The initial implementation focuses on a functional prototype that
demonstrates the proposed multi-agent verification and security workflow
using a controlled collection of trusted organisational documents.

The prototype will evaluate factual consistency, evidence retrieval,
selected security threats, policy-based decisions, and system
performance.

The framework is not intended to guarantee the elimination of all
hallucinations or the prevention of every cybersecurity attack. Its
effectiveness will be assessed through defined test scenarios and
evaluation metrics.
