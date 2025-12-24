"""LLM 버킷 중재 서비스

가중치 점수와 벡터 검색 결과를 비교하여 LLM이 최종 버킷 결정

v2.0: 부위별 설정(BodyPartConfig) 기반 동적 버킷 처리
"""

from typing import List, Optional, Dict, Any
import json

from openai import OpenAI
from langsmith import traceable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.models import BodyPartInput, Demographics
from shared.config import BodyPartConfig, BodyPartConfigLoader
from bucket_inference.models import (
    BucketInferenceInput,
    BucketInferenceOutput,
    BucketScore,
    DiscrepancyAlert,
    RedFlagResult,
)
from bucket_inference.services.evidence_search import EvidenceResult
from bucket_inference.config import settings


class BucketArbitrator:
    """LLM Pass #1: 버킷 검증 및 최종 결정

    v2.0: 부위별 설정 기반으로 버킷 목록과 프롬프트를 동적으로 구성
    """

    def __init__(self, openai_client: Optional[OpenAI] = None):
        """
        Args:
            openai_client: OpenAI 클라이언트
        """
        self._openai = openai_client or OpenAI()
        self._model = settings.openai_model

    @traceable(name="bucket_arbitration")
    def arbitrate(
        self,
        body_part: BodyPartInput,
        bucket_scores: List[BucketScore],
        weight_ranking: List[str],
        search_ranking: List[str],
        evidence: Optional[EvidenceResult],
        user_input: BucketInferenceInput,
        red_flag: Optional[RedFlagResult] = None,
        bp_config: Optional[BodyPartConfig] = None,
    ) -> BucketInferenceOutput:
        """
        가중치 vs 검색 결과 비교 후 최종 버킷 결정

        Args:
            body_part: 부위별 입력
            bucket_scores: 버킷별 점수
            weight_ranking: 가중치 기반 순위
            search_ranking: 검색 기반 순위
            evidence: 검색 근거
            user_input: 사용자 입력
            red_flag: 레드플래그 결과
            bp_config: 부위별 설정 (없으면 자동 로드)

        Returns:
            BucketInferenceOutput 객체
        """
        # 설정 로드 (없으면 자동 로드)
        if bp_config is None:
            bp_config = BodyPartConfigLoader.load(body_part.code)

        # 불일치 감지
        discrepancy = self._detect_discrepancy(weight_ranking, search_ranking)

        # LLM 호출하여 최종 결정
        result = self._call_llm(
            body_part=body_part,
            bucket_scores=bucket_scores,
            weight_ranking=weight_ranking,
            search_ranking=search_ranking,
            discrepancy=discrepancy,
            evidence=evidence,
            user_input=user_input,
            bp_config=bp_config,
        )

        return BucketInferenceOutput(
            body_part=body_part.code,
            final_bucket=result["final_bucket"],
            confidence=result["confidence"],
            bucket_scores={bs.bucket: bs.score for bs in bucket_scores},
            weight_ranking=weight_ranking,
            search_ranking=search_ranking,
            discrepancy=discrepancy,
            evidence_summary=result["evidence_summary"],
            llm_reasoning=result["reasoning"],
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
        user_input: BucketInferenceInput,
        bp_config: BodyPartConfig,
    ) -> Dict[str, Any]:
        """LLM 호출하여 최종 결정"""
        prompt = self._build_prompt(
            body_part=body_part,
            bucket_scores=bucket_scores,
            weight_ranking=weight_ranking,
            search_ranking=search_ranking,
            discrepancy=discrepancy,
            evidence=evidence,
            user_input=user_input,
            bp_config=bp_config,
        )

        response = self._openai.chat.completions.create(
            model=self._model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"당신은 정형외과 {bp_config.display_name} 전문의입니다. "
                        "환자의 증상과 근거 자료를 분석하여 가장 가능성 높은 "
                        "진단 버킷을 결정합니다. 반드시 JSON 형식으로 응답하세요."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.3,
        )

        result = json.loads(response.choices[0].message.content)

        # 인용 정보 포맷팅
        citations = result.get("citations", [])
        citations_str = ""
        if citations:
            citations_str = "\n\n### 참고 문헌 인용:\n"
            for i, c in enumerate(citations, 1):
                title = c.get("title", "출처 미상")
                source_type = c.get("source_type", "paper")
                citations_str += (
                    f"{i}. **{title}** [{source_type}]\n"
                    f"   > \"{c.get('quote', '')}\"\n"
                    f"   → {c.get('relevance', '')}\n\n"
                )

        full_reasoning = result.get("reasoning", "")
        if citations_str:
            full_reasoning += citations_str

        # final_bucket 정규화 (복수 선택 방지)
        final_bucket = result.get("final_bucket", weight_ranking[0])
        if "|" in final_bucket:
            # 복수 선택된 경우 첫 번째 버킷 사용
            final_bucket = final_bucket.split("|")[0].strip()

        # 유효한 버킷인지 확인 (부위별 설정에서 가져옴)
        valid_buckets = bp_config.bucket_order
        if final_bucket not in valid_buckets:
            final_bucket = weight_ranking[0]

        return {
            "final_bucket": final_bucket,
            "confidence": result.get("confidence", 0.7),
            "evidence_summary": result.get("evidence_summary", ""),
            "reasoning": full_reasoning,
        }

    def _build_prompt(
        self,
        body_part: BodyPartInput,
        bucket_scores: List[BucketScore],
        weight_ranking: List[str],
        search_ranking: List[str],
        discrepancy: Optional[DiscrepancyAlert],
        evidence: Optional[EvidenceResult],
        user_input: BucketInferenceInput,
        bp_config: BodyPartConfig,
    ) -> str:
        """LLM 프롬프트 구성 (부위별 설정 사용)"""
        # 버킷 점수 정보
        scores_str = "\n".join(
            f"- {bs.bucket}: {bs.score}점 ({bs.percentage}%)"
            for bs in bucket_scores
        )

        # 증상 정보
        symptoms_str = ", ".join(body_part.symptoms)

        # 환자 정보
        demo = user_input.demographics
        patient_info = f"나이: {demo.age}세, 성별: {demo.sex}, BMI: {demo.bmi}"

        # 불일치 정보
        discrepancy_str = ""
        if discrepancy:
            discrepancy_str = f"\n\n## 불일치 경고\n{discrepancy.message}"

        # 근거 정보
        evidence_str = self._format_evidence(evidence)

        # 버킷 설명 (부위별 설정에서 가져옴)
        bucket_descriptions_str = self._format_bucket_descriptions(bp_config)

        # 유효 버킷 목록 (부위별 설정에서 가져옴)
        valid_buckets_str = ", ".join(bp_config.bucket_order)

        # 프롬프트 템플릿이 있으면 사용, 없으면 기본 템플릿
        if bp_config.prompt_template and "{patient_info}" in bp_config.prompt_template:
            # 템플릿 변수 치환
            prompt = bp_config.prompt_template.format(
                patient_info=patient_info,
                symptoms=symptoms_str,
                bucket_scores=scores_str,
                weight_ranking=" > ".join(weight_ranking),
                search_ranking=" > ".join(search_ranking) if search_ranking else "검색 결과 없음",
                discrepancy_info=discrepancy_str,
                evidence=evidence_str,
                bucket_descriptions=bucket_descriptions_str,
                valid_buckets=valid_buckets_str,
                default_bucket=bp_config.bucket_order[0] if bp_config.bucket_order else "OA",
            )
        else:
            # 기본 프롬프트 생성
            prompt = self._build_default_prompt(
                patient_info=patient_info,
                symptoms_str=symptoms_str,
                scores_str=scores_str,
                weight_ranking=weight_ranking,
                search_ranking=search_ranking,
                discrepancy_str=discrepancy_str,
                evidence_str=evidence_str,
                bucket_descriptions_str=bucket_descriptions_str,
                valid_buckets_str=valid_buckets_str,
                bp_config=bp_config,
            )

        return prompt

    def _format_evidence(self, evidence: Optional[EvidenceResult]) -> str:
        """근거 자료 포맷팅"""
        if not evidence or not evidence.results:
            return "검색 결과 없음"

        top_papers = evidence.get_top_results(5)
        evidence_str = ""
        for i, r in enumerate(top_papers, 1):
            content_preview = r.paper.content[:500] if r.paper.content else "내용 없음"
            evidence_str += (
                f"\n### 근거 {i}: {r.paper.title}\n"
                f"- 출처: {r.paper.source_type} (Layer {r.paper.source_layer})\n"
                f"- 유사도: {r.similarity_score:.2f}\n"
                f"- 내용:\n```\n{content_preview}...\n```\n"
            )
        return evidence_str

    def _format_bucket_descriptions(self, bp_config: BodyPartConfig) -> str:
        """버킷 설명 포맷팅"""
        lines = []
        for bucket_code in bp_config.bucket_order:
            info = bp_config.bucket_info.get(bucket_code, {})
            name_kr = info.get("name_kr", bucket_code)
            description = info.get("description", "")
            typical_profile = info.get("typical_profile", "")

            lines.append(
                f"- **{bucket_code} ({name_kr})**: {description}"
            )
            if typical_profile:
                lines.append(f"  - 전형적 프로필: {typical_profile}")

        return "\n".join(lines)

    def _build_default_prompt(
        self,
        patient_info: str,
        symptoms_str: str,
        scores_str: str,
        weight_ranking: List[str],
        search_ranking: List[str],
        discrepancy_str: str,
        evidence_str: str,
        bucket_descriptions_str: str,
        valid_buckets_str: str,
        bp_config: BodyPartConfig,
    ) -> str:
        """기본 프롬프트 생성"""
        default_bucket = bp_config.bucket_order[0] if bp_config.bucket_order else "OA"

        return f"""
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

## 검색된 근거 자료
{evidence_str}

## {bp_config.display_name} 진단 버킷 설명
{bucket_descriptions_str}

## 요청
위 정보를 종합하여 가장 가능성 높은 진단 버킷을 결정하세요.

**인용 규칙**:
1. 인용은 반드시 위 "검색된 근거 자료"에서만 해야 합니다
2. 검색 결과가 없으면 "검색된 근거 자료 없음"이라고 명시하세요

**중요**: final_bucket은 반드시 {valid_buckets_str} 중 하나만 선택하세요. 복수 선택 금지.

다음 JSON 형식으로 응답하세요:
{{
    "final_bucket": "{default_bucket}",
    "confidence": 0.75,
    "evidence_summary": "진단 근거 요약 (2-3문장)",
    "reasoning": "판단 근거 설명",
    "citations": [
        {{
            "title": "논문 제목",
            "source_type": "paper|orthobullets|pubmed",
            "quote": "인용 문장",
            "relevance": "적용 근거"
        }}
    ]
}}
"""
