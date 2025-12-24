"""버킷 추론 파이프라인

전체 흐름:
1. 부위별 설정 로드 (BodyPartConfigLoader)
2. 가중치 계산 (WeightService)
3. 벡터 검색 (EvidenceSearchService)
4. 랭킹 통합 (RankingMerger)
5. LLM 버킷 중재 (BucketArbitrator)

v2.0: Config-Driven Architecture
- 모든 부위별 차이점은 data/medical/{body_part}/ 설정으로 관리
- 코드 수정 없이 새 부위 추가 가능
"""

from typing import Dict, List

from langsmith import traceable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config import BodyPartConfig, BodyPartConfigLoader
from bucket_inference.models import BucketInferenceInput, BucketInferenceOutput
from bucket_inference.services import (
    WeightService,
    EvidenceSearchService,
    RankingMerger,
    BucketArbitrator,
)
from bucket_inference.config import settings


class BucketInferencePipeline:
    """버킷 추론 파이프라인

    v2.0: 부위별 설정 기반 동적 처리

    사용 예시:
        pipeline = BucketInferencePipeline()
        result = pipeline.run(input_data)

        # 지원하는 부위 확인
        available = pipeline.get_available_body_parts()
    """

    def __init__(self):
        self.weight_service = WeightService()
        self.evidence_service = EvidenceSearchService()
        self.ranking_merger = RankingMerger()
        self.bucket_arbitrator = BucketArbitrator()

        # 데이터 디렉토리 설정
        BodyPartConfigLoader.set_data_dir(settings.data_dir)

    @traceable(name="bucket_inference_pipeline")
    def run(self, input_data: BucketInferenceInput) -> Dict[str, BucketInferenceOutput]:
        """
        버킷 추론 실행

        Args:
            input_data: 버킷 추론 입력

        Returns:
            {부위코드: BucketInferenceOutput} 딕셔너리
        """
        results: Dict[str, BucketInferenceOutput] = {}

        for body_part in input_data.body_parts:
            bp_code = body_part.code

            # Step 0: 부위별 설정 로드 (트리거)
            bp_config = BodyPartConfigLoader.load(bp_code)

            # Step 1: 가중치 계산 (설정 전달)
            bucket_scores, weight_ranking = self.weight_service.calculate_scores(
                body_part,
                bp_config=bp_config,
            )

            # Step 2: 벡터 검색
            query = self._build_search_query(body_part, input_data)
            evidence = self.evidence_service.search(
                query=query,
                body_part=bp_code,
            )
            search_ranking = self.evidence_service.get_search_ranking(evidence)

            # Step 3: 랭킹 통합
            merged_ranking = self.ranking_merger.merge(weight_ranking, search_ranking)

            # Step 4: LLM 버킷 중재 (설정 전달)
            result = self.bucket_arbitrator.arbitrate(
                body_part=body_part,
                bucket_scores=bucket_scores,
                weight_ranking=weight_ranking,
                search_ranking=search_ranking,
                evidence=evidence,
                user_input=input_data,
                bp_config=bp_config,
            )

            results[bp_code] = result

        return results

    def _build_search_query(
        self,
        body_part,
        user_input: BucketInferenceInput,
    ) -> str:
        """검색 쿼리 생성"""
        symptoms = body_part.symptoms[:5]  # 상위 5개

        demo = user_input.demographics
        query = (
            f"{demo.age}세 {demo.sex} 환자, "
            f"증상: {', '.join(symptoms)}"
        )

        # 자연어 입력이 있으면 추가
        if user_input.natural_language and user_input.natural_language.has_content:
            nl_text = user_input.natural_language.to_text()
            query += f"\n{nl_text}"

        return query

    def run_single(
        self,
        input_data: BucketInferenceInput,
        body_part_code: str,
    ) -> BucketInferenceOutput:
        """단일 부위 추론"""
        results = self.run(input_data)
        if body_part_code not in results:
            raise ValueError(f"부위 코드 '{body_part_code}'를 찾을 수 없습니다.")
        return results[body_part_code]

    def get_available_body_parts(self) -> List[str]:
        """지원하는 부위 목록 반환"""
        return BodyPartConfigLoader.get_available_body_parts()

    def get_body_part_config(self, body_part_code: str) -> BodyPartConfig:
        """특정 부위의 설정 반환"""
        return BodyPartConfigLoader.load(body_part_code)
