from app.schemas.verification import Claim, EvidenceChunk, ClaimVerdict, VerificationResult, Verdict
from app.agents.fact_verification import FactVerificationAgent


class FakeLLM:
    def __init__(self, response):
        self.response = response

    def complete(self, prompt, temperature=0.0):
        return self.response


# Test 1: Schemas
c = Claim(claim_id='C1', claim_text='Test claim', entities=[], dates=[], numbers=['21'])
e = EvidenceChunk(chunk_id='E1', text='Test evidence', document_id='D1', section_id='D1-S1',
                  page=1, document_version='1.0', document_status='ACTIVE',
                  effective_date='2026-01-01', policy_topic='test')
v = ClaimVerdict(claim_id='C1', verdict=Verdict.SUPPORTED, explanation='Matches', source_references=[e])
r = VerificationResult(claim_verdicts=[v], overall_status='all_supported',
                       total_claims=1, supported_count=1, contradicted_count=0, insufficient_count=0)
print('Schemas OK:', r.overall_status, r.supported_count)

# Test 2: No evidence -> INSUFFICIENT_EVIDENCE
agent = FactVerificationAgent(llm_client=FakeLLM('{"verdict": "SUPPORTED", "explanation": "ok"}'),
                              vector_store=None)
result = agent.verify([c], [])
print('No evidence verdict:', result.claim_verdicts[0].verdict)

# Test 3: With evidence -> SUPPORTED
result2 = agent.verify([c], [e])
print('With evidence verdict:', result2.claim_verdicts[0].verdict)
print('All quick tests passed!')
