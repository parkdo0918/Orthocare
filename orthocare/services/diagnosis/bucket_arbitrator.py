"""LLM Pass #1 - 버킷 검증 및 중재"""

from typing import List, Optional

from langsmith import traceable

from orthocare.config import settings
from orthocare.models import UserInput, BodyPartInput
from orthocare.models.diagnosis import (
    DiagnosisResult,
    BucketScore,
    DiscrepancyAlert,
    RedFlagResult,
)
from orthocare.models.evidence import EvidenceResult
from orthocare.data_ops.loaders.knee_loader import get_loader


class BucketArbitrator:
    """
    LLM Pass #1: 버킷 검증 및 최종 결정

    가중치 점수와 벡터 검색 결과를 비교하여
    불일치 시 LLM이 중재하여 최종 버킷 결정
    """

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLM 클라이언트 (OpenAI 등)
        """
        self.llm_client = llm_client
        self.model = settings.openai_model

    @traceable(name="bucket_arbitration")
    def arbitrate(
        self,
        body_part: BodyPartInput,
        bucket_scores: List[BucketScore],
        weight_ranking: List[str],
        search_ranking: List[str],
        evidence: Optional[EvidenceResult],
        user_input: UserInput,
        red_flag: Optional[RedFlagResult] = None,
    ) -> DiagnosisResult:
        """
        가중치 vs 검색 결과 비교 후 최종 버킷 결정

        Args:
            body_part: 부위 입력
            bucket_scores: 가중치 기반 버킷 점수
            weight_ranking: 가중치 기반 순위
            search_ranking: 검색 기반 순위
            evidence: 근거 검색 결과
            user_input: 전체 사용자 입력
            red_flag: 레드플래그 결과

        Returns:
            DiagnosisResult 객체
        """
        # 불일치 감지
        discrepancy = self._detect_discrepancy(weight_ranking, search_ranking)

        # LLM 호출하여 최종 결정
        if self.llm_client is not None:
            result = self._call_llm(
                body_part=body_part,
                bucket_scores=bucket_scores,
                weight_ranking=weight_ranking,
                search_ranking=search_ranking,
                discrepancy=discrepancy,
                evidence=evidence,
                user_input=user_input,
            )
            final_bucket = result["final_bucket"]
            confidence = result["confidence"]
            evidence_summary = result["evidence_summary"]
            llm_reasoning = result["reasoning"]
        else:
            # LLM 없으면 가중치 순위 사용
            final_bucket = weight_ranking[0] if weight_ranking else "OA"
            confidence = bucket_scores[0].percentage / 100 if bucket_scores else 0.5
            evidence_summary = "LLM 클라이언트가 설정되지 않아 가중치 기반 결과를 사용합니다."
            llm_reasoning = "가중치 기반 자동 결정"

        return DiagnosisResult(
            body_part=body_part.code,
            bucket_scores=bucket_scores,
            weight_ranking=weight_ranking,
            search_ranking=search_ranking,
            discrepancy=discrepancy,
            final_bucket=final_bucket,
            confidence=confidence,
            evidence_summary=evidence_summary,
            llm_reasoning=llm_reasoning,
            red_flag=red_flag,
        )

    def _detect_discrepancy(
        self,
        weight_ranking: List[str],
        search_ranking: List[str],
    ) -> Optional[DiscrepancyAlert]:
        """가중치 vs 검색 불일치 감지"""
        if not search_ranking:
            return None

        # 상위 버킷 비교
        if weight_ranking[0] != search_ranking[0]:
            return DiscrepancyAlert(
                type="top_bucket_mismatch",
                weight_ranking=weight_ranking,
                search_ranking=search_ranking,
                message=(
                    f"가중치 순위({weight_ranking[0]})와 "
                    f"검색 순위({search_ranking[0]})가 불일치합니다. "
                    "LLM이 증상을 재검토하여 결정합니다."
                ),
                severity="warning",
            )

        # 2위 이상 차이 감지
        for i, bucket in enumerate(weight_ranking):
            if bucket in search_ranking:
                search_idx = search_ranking.index(bucket)
                if abs(i - search_idx) >= 2:
                    return DiscrepancyAlert(
                        type="ranking_shift",
                        weight_ranking=weight_ranking,
                        search_ranking=search_ranking,
                        message=(
                            f"{bucket} 버킷의 순위가 크게 다릅니다. "
                            f"(가중치: {i+1}위, 검색: {search_idx+1}위)"
                        ),
                        severity="warning",
                    )

        return None

    @traceable(run_type="llm", name="llm_bucket_decision")
    def _call_llm(
        self,
        body_part: BodyPartInput,
        bucket_scores: List[BucketScore],
        weight_ranking: List[str],
        search_ranking: List[str],
        discrepancy: Optional[DiscrepancyAlert],
        evidence: Optional[EvidenceResult],
        user_input: UserInput,
    ) -> dict:
        """LLM 호출하여 최종 결정"""
        loader = get_loader(body_part.code)

        # 프롬프트 구성
        prompt = self._build_prompt(
            body_part=body_part,
            bucket_scores=bucket_scores,
            weight_ranking=weight_ranking,
            search_ranking=search_ranking,
            discrepancy=discrepancy,
            evidence=evidence,
            user_input=user_input,
            buckets=loader.buckets,
        )

        # LLM 호출
        response = self.llm_client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 정형외과 진단을 보조하는 AI입니다. "
                        "환자의 증상과 근거 자료를 분석하여 가장 가능성 높은 "
                        "진단 버킷을 결정합니다. 반드시 JSON 형식으로 응답하세요."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        import json

        result = json.loads(response.choices[0].message.content)

        # 인용 정보 포맷팅 (새 구조: title, source_type, quote, relevance)
        citations = result.get("citations", [])
        citations_str = ""
        if citations:
            citations_str = "\n\n### 참고 문헌 인용:\n"
            for i, c in enumerate(citations, 1):
                title = c.get('title', c.get('source', '출처 미상'))
                source_type = c.get('source_type', 'paper')
                citations_str += (
                    f"{i}. **{title}** [{source_type}]\n"
                    f"   > \"{c.get('quote', '')}\"\n"
                    f"   → {c.get('relevance', '')}\n\n"
                )

        # 버킷별 추론 포맷팅
        bucket_reasoning = result.get("bucket_reasoning", {})
        bucket_str = ""
        if bucket_reasoning:
            bucket_str = "\n\n### 버킷별 판단 근거:\n"
            for bucket, info in bucket_reasoning.items():
                if isinstance(info, dict):
                    bucket_str += (
                        f"- **{bucket}**: {info.get('score_reason', '')}\n"
                        f"  근거: {info.get('evidence', '')}\n"
                    )

        # reasoning에 인용 및 버킷 추론 추가
        full_reasoning = result.get("reasoning", "")
        if bucket_str:
            full_reasoning += bucket_str
        if citations_str:
            full_reasoning += citations_str

        return {
            "final_bucket": result.get("final_bucket", weight_ranking[0]),
            "confidence": result.get("confidence", 0.7),
            "evidence_summary": result.get("evidence_summary", ""),
            "reasoning": full_reasoning,
            "citations": citations,
            "bucket_reasoning": bucket_reasoning,
        }

    def _build_prompt(
        self,
        body_part: BodyPartInput,
        bucket_scores: List[BucketScore],
        weight_ranking: List[str],
        search_ranking: List[str],
        discrepancy: Optional[DiscrepancyAlert],
        evidence: Optional[EvidenceResult],
        user_input: UserInput,
        buckets: dict,
    ) -> str:
        """LLM 프롬프트 구성"""
        # 버킷 점수 정보
        scores_str = "\n".join(
            f"- {bs.bucket} ({buckets.get(bs.bucket, {}).get('name_kr', bs.bucket)}): "
            f"{bs.score}점 ({bs.percentage}%)"
            for bs in bucket_scores
        )

        # 증상 정보
        symptoms_str = ", ".join(body_part.symptoms)

        # 환자 정보
        demo = user_input.demographics
        patient_info = (
            f"나이: {demo.age}세, 성별: {demo.sex}, BMI: {demo.bmi}"
        )

        # 불일치 정보
        discrepancy_str = ""
        if discrepancy:
            discrepancy_str = f"\n\n## 불일치 경고\n{discrepancy.message}"

        # 근거 정보 (상세 내용 포함)
        evidence_str = ""
        if evidence and evidence.results:
            top_papers = evidence.get_top_results(5)
            evidence_str = "\n## 검색된 근거 자료 (벡터 검색 결과)\n"
            evidence_str += f"총 {len(evidence.results)}개 문서 검색됨\n"
            for i, r in enumerate(top_papers, 1):
                # content 또는 summary 사용 (None 체크)
                content_text = r.paper.content or r.paper.summary or "내용 없음"
                content_preview = content_text[:500] if content_text else "내용 없음"
                evidence_str += (
                    f"\n### 근거 {i}: {r.paper.title}\n"
                    f"- 출처: {r.paper.source_type} (Layer {r.paper.source_layer})\n"
                    f"- 유사도: {r.similarity_score:.2f}\n"
                    f"- 버킷 태그: {', '.join(r.paper.bucket_tags) if r.paper.bucket_tags else '없음'}\n"
                    f"- 내용:\n```\n{content_preview}...\n```\n"
                )
        else:
            evidence_str = "\n## 검색된 근거 자료\n검색 결과 없음 (벡터 DB 검색 실패 또는 결과 없음)\n"

        prompt = f"""
## 환자 정보
{patient_info}

## 증상
{symptoms_str}

## 버킷별 점수 (가중치 기반)
{scores_str}

## 순위 비교
- 가중치 순위: {' > '.join(weight_ranking)}
- 검색 순위: {' > '.join(search_ranking) if search_ranking else '검색 결과 없음'}
{discrepancy_str}
{evidence_str}

## 요청
위 정보를 종합하여 가장 가능성 높은 진단 버킷을 결정하세요.
불일치가 있다면 증상을 재검토하여 판단하세요.

**매우 중요 - 인용 규칙**:
1. 인용은 반드시 위 "검색된 근거 자료"에서만 해야 합니다
2. 위에 제공되지 않은 논문/문헌은 절대 인용하지 마세요 (hallucination 금지)
3. 검색 결과가 없거나 부족하면 "검색된 근거 자료 없음"이라고 명시하세요
4. 각 인용에 정확한 출처 타입을 표시하세요 (paper/orthobullets/pubmed)

다음 JSON 형식으로 응답하세요:
{{
    "final_bucket": "OA|OVR|TRM|INF",
    "confidence": 0.0-1.0,
    "evidence_summary": "진단 근거 요약 (2-3문장)",
    "reasoning": "판단 근거 설명",
    "citations": [
        {{
            "title": "위에서 검색된 정확한 논문 제목",
            "source_type": "paper|orthobullets|pubmed",
            "quote": "해당 문헌에서 직접 인용한 문장 (위 내용에서 복사)",
            "relevance": "이 인용이 진단에 어떻게 적용되는지"
        }}
    ],
    "bucket_reasoning": {{
        "OA": {{"score_reason": "OA 점수 이유", "evidence": "관련 근거 (위 검색 결과에서)"}},
        "OVR": {{"score_reason": "OVR 점수 이유", "evidence": "관련 근거"}},
        "TRM": {{"score_reason": "TRM 점수 이유", "evidence": "관련 근거"}},
        "INF": {{"score_reason": "INF 점수 이유", "evidence": "관련 근거"}}
    }}
}}
"""
        return prompt
