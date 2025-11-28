"""Phase 2: 진단 스텝

Step 2.1: 가중치 계산
Step 2.2: 벡터 검색
Step 2.3: 랭킹 통합
Step 2.4: LLM 버킷 중재
"""

from typing import Dict, Any, List, Optional

from langsmith import traceable

from .base import PipelineStep, StepResult, StepContext, StepStatus


class WeightCalculationStep(PipelineStep):
    """
    Step 2.1: 가중치 기반 버킷 점수 계산

    - 증상별 가중치 벡터 조회
    - 버킷별 점수 합산
    - 가중치 기반 랭킹 생성
    """

    name = "step_2_1_weight_calculation"
    description = "가중치 기반 버킷 점수 계산"

    def __init__(self, weight_service=None):
        super().__init__()
        self.weight_service = weight_service

    def should_skip(self, context: StepContext) -> bool:
        return not context.validation_passed or context.blocked_by_red_flag

    @traceable(name="step_2_1_weight_calculation")
    def execute(self, context: StepContext) -> StepResult:
        """가중치 계산 실행"""
        from orthocare.services.scoring import WeightService

        service = self.weight_service or WeightService()
        user_input = context.user_input

        all_scores = {}
        all_rankings = {}

        for body_part in user_input.body_parts:
            bp_code = body_part.code
            context.current_body_part = bp_code

            try:
                bucket_scores, ranking = service.calculate_scores(body_part)

                all_scores[bp_code] = bucket_scores
                all_rankings[bp_code] = ranking

            except Exception as e:
                # 가중치 계산 실패 시 빈 결과
                all_scores[bp_code] = {}
                all_rankings[bp_code] = []

        context.bucket_scores = all_scores
        context.weight_rankings = all_rankings

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output={
                "body_parts": list(all_scores.keys()),
                "scores": all_scores,
                "rankings": all_rankings,
            },
            metadata={
                "total_body_parts": len(all_scores),
                "top_buckets": {
                    bp: rankings[0] if rankings else None
                    for bp, rankings in all_rankings.items()
                },
            },
        )


class VectorSearchStep(PipelineStep):
    """
    Step 2.2: 벡터 DB 검색

    - 증상 기반 검색 쿼리 생성
    - 유사 문서/논문 검색
    - 검색 결과 랭킹 생성
    """

    name = "step_2_2_vector_search"
    description = "벡터 DB 유사도 검색"

    def __init__(self, evidence_service=None, symptom_mapper=None):
        super().__init__()
        self.evidence_service = evidence_service
        self.symptom_mapper = symptom_mapper

    def should_skip(self, context: StepContext) -> bool:
        return not context.validation_passed or context.blocked_by_red_flag

    @traceable(name="step_2_2_vector_search")
    def execute(self, context: StepContext) -> StepResult:
        """벡터 검색 실행"""
        from orthocare.services.evidence import EvidenceSearchService
        from orthocare.services.input import SymptomMapper

        evidence_service = self.evidence_service
        mapper = self.symptom_mapper or SymptomMapper()
        user_input = context.user_input

        all_results = {}
        all_rankings = {}

        for body_part in user_input.body_parts:
            bp_code = body_part.code
            context.current_body_part = bp_code

            # 검색 쿼리 생성
            query = self._build_search_query(body_part, user_input, mapper)

            try:
                if evidence_service:
                    # 벡터 검색 실행
                    results = evidence_service.search(
                        query=query,
                        body_part=bp_code,
                    )
                    ranking = evidence_service.get_search_ranking(results)

                    all_results[bp_code] = {
                        "query": query,
                        "results_count": len(results.results) if results else 0,  # .items → .results
                        "results": results,
                    }
                    all_rankings[bp_code] = ranking
                else:
                    # 벡터 스토어 없으면 빈 결과
                    all_results[bp_code] = {"query": query, "results_count": 0}
                    all_rankings[bp_code] = []

            except Exception as e:
                all_results[bp_code] = {"query": query, "error": str(e)}
                all_rankings[bp_code] = []

        context.search_results = all_results
        context.search_rankings = all_rankings

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output={
                "body_parts": list(all_results.keys()),
                "queries": {bp: data.get("query") for bp, data in all_results.items()},
                "result_counts": {
                    bp: data.get("results_count", 0)
                    for bp, data in all_results.items()
                },
                "rankings": all_rankings,
            },
            metadata={
                "total_results": sum(
                    data.get("results_count", 0) for data in all_results.values()
                ),
            },
        )

    def _build_search_query(self, body_part, user_input, mapper) -> str:
        """검색 쿼리 생성"""
        symptoms = body_part.symptoms[:5]  # 상위 5개

        descriptions = [
            mapper.get_symptom_description(body_part.code, s)
            for s in symptoms
        ]
        descriptions = [d for d in descriptions if d]

        demo = user_input.demographics
        query = (
            f"{demo.age}세 {demo.sex} 환자, "
            f"증상: {', '.join(descriptions)}"
        )

        return query


class RankingMergeStep(PipelineStep):
    """
    Step 2.3: 랭킹 통합

    - 가중치 랭킹 + 검색 랭킹 병합
    - 앙상블 스코어 계산
    - 최종 버킷 후보 생성
    """

    name = "step_2_3_ranking_merge"
    description = "가중치/검색 랭킹 통합"

    def __init__(self, weight_ratio: float = 0.6):
        super().__init__()
        self.weight_ratio = weight_ratio  # 가중치 비율 (0.6 = 60%)

    def should_skip(self, context: StepContext) -> bool:
        return not context.validation_passed or context.blocked_by_red_flag

    @traceable(name="step_2_3_ranking_merge")
    def execute(self, context: StepContext) -> StepResult:
        """랭킹 통합 실행"""
        merged_rankings = {}

        for bp_code in context.weight_rankings.keys():
            weight_ranking = context.weight_rankings.get(bp_code, [])
            search_ranking = context.search_rankings.get(bp_code, [])

            # 앙상블 점수 계산
            merged = self._merge_rankings(
                weight_ranking,
                search_ranking,
                self.weight_ratio,
            )
            merged_rankings[bp_code] = merged

        context.merged_rankings = merged_rankings

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output={
                "body_parts": list(merged_rankings.keys()),
                "merged_rankings": merged_rankings,
                "weight_ratio": self.weight_ratio,
            },
            metadata={
                "top_candidates": {
                    bp: rankings[:3] if rankings else []
                    for bp, rankings in merged_rankings.items()
                },
            },
        )

    def _merge_rankings(
        self,
        weight_ranking: List[str],
        search_ranking: List[str],
        weight_ratio: float,
    ) -> List[str]:
        """랭킹 병합 (Reciprocal Rank Fusion 변형)"""
        scores = {}

        # 가중치 랭킹 점수
        for i, bucket in enumerate(weight_ranking):
            rank_score = 1.0 / (i + 1)  # 순위 역수
            scores[bucket] = scores.get(bucket, 0) + rank_score * weight_ratio

        # 검색 랭킹 점수
        for i, bucket in enumerate(search_ranking):
            rank_score = 1.0 / (i + 1)
            scores[bucket] = scores.get(bucket, 0) + rank_score * (1 - weight_ratio)

        # 점수순 정렬
        sorted_buckets = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
        return sorted_buckets


class BucketArbitrationStep(PipelineStep):
    """
    Step 2.4: LLM 버킷 중재 (LLM Pass #1)

    - 통합 랭킹 기반 최종 버킷 결정
    - 임상적 맥락 고려
    - 신뢰도 점수 산출
    """

    name = "step_2_4_bucket_arbitration"
    description = "LLM 기반 최종 버킷 결정"

    def __init__(self, bucket_arbitrator=None):
        super().__init__()
        self.bucket_arbitrator = bucket_arbitrator

    def should_skip(self, context: StepContext) -> bool:
        return not context.validation_passed or context.blocked_by_red_flag

    @traceable(name="step_2_4_bucket_arbitration")
    def execute(self, context: StepContext) -> StepResult:
        """버킷 중재 실행"""
        from orthocare.services.diagnosis import BucketArbitrator

        arbitrator = self.bucket_arbitrator
        user_input = context.user_input
        diagnoses = {}

        for body_part in user_input.body_parts:
            bp_code = body_part.code
            context.current_body_part = bp_code

            bucket_scores = context.bucket_scores.get(bp_code, {})
            weight_ranking = context.weight_rankings.get(bp_code, [])
            search_ranking = context.search_rankings.get(bp_code, [])
            search_results = context.search_results.get(bp_code, {})
            red_flag = context.red_flags.get(bp_code)

            try:
                if arbitrator:
                    # LLM 중재 실행
                    diagnosis = arbitrator.arbitrate(
                        body_part=body_part,
                        bucket_scores=bucket_scores,
                        weight_ranking=weight_ranking,
                        search_ranking=search_ranking,
                        evidence=search_results.get("results"),
                        user_input=user_input,
                        red_flag=red_flag,
                    )
                    diagnoses[bp_code] = diagnosis
                else:
                    # LLM 없으면 가중치 1위 사용
                    diagnoses[bp_code] = {
                        "bucket": weight_ranking[0] if weight_ranking else "OA",
                        "confidence": 0.5,
                        "reasoning": "LLM not available, using weight ranking",
                    }

            except Exception as e:
                diagnoses[bp_code] = {
                    "bucket": weight_ranking[0] if weight_ranking else "OA",
                    "confidence": 0.3,
                    "error": str(e),
                }

        context.diagnoses = diagnoses

        # 결과 추출 헬퍼 함수
        def get_bucket(d):
            if hasattr(d, 'final_bucket'):
                return d.final_bucket
            elif isinstance(d, dict):
                return d.get("bucket", "OA")
            return "OA"

        def get_confidence(d):
            if hasattr(d, 'confidence'):
                return d.confidence
            elif isinstance(d, dict):
                return d.get("confidence", 0.5)
            return 0.5

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output={
                "body_parts": list(diagnoses.keys()),
                "diagnoses": {
                    bp: {
                        "bucket": get_bucket(d),
                        "confidence": get_confidence(d),
                    }
                    for bp, d in diagnoses.items()
                },
            },
            metadata={
                "llm_used": arbitrator is not None,
                "final_buckets": {
                    bp: get_bucket(d)
                    for bp, d in diagnoses.items()
                },
            },
        )
