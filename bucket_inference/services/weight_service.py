"""가중치 계산 서비스 (버킷 추론용)

v2.0: BodyPartConfig 통합으로 일관된 설정 관리
"""

from typing import List, Dict, Tuple, Optional

from langsmith import traceable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.models import BodyPartInput
from shared.config import BodyPartConfig, BodyPartConfigLoader
from bucket_inference.models import BucketScore
from bucket_inference.config import settings


class WeightService:
    """가중치 기반 버킷 점수 계산

    v2.0: BodyPartConfig를 통해 설정 로드
    """

    def __init__(self):
        # 캐시는 BodyPartConfigLoader에서 관리하므로 제거
        pass

    @traceable(name="weight_score_calculation")
    def calculate_scores(
        self,
        body_part: BodyPartInput,
        bp_config: Optional[BodyPartConfig] = None,
    ) -> Tuple[List[BucketScore], List[str]]:
        """
        증상 코드 기반 버킷 점수 계산

        Args:
            body_part: 부위별 입력 (증상 코드 포함)
            bp_config: 부위별 설정 (없으면 자동 로드)

        Returns:
            (버킷 점수 리스트, 순위 리스트)
        """
        # 설정 로드 (없으면 자동 로드)
        if bp_config is None:
            bp_config = BodyPartConfigLoader.load(body_part.code)

        weights = bp_config.weights
        bucket_order = bp_config.bucket_order

        # 버킷별 점수 초기화
        scores = {bucket: 0.0 for bucket in bucket_order}
        contributing = {bucket: [] for bucket in bucket_order}

        # 각 증상의 가중치 합산
        for symptom in body_part.symptoms:
            if symptom not in weights:
                continue

            weight_vector = weights[symptom]
            for i, bucket in enumerate(bucket_order):
                if i < len(weight_vector) and weight_vector[i] > 0:
                    scores[bucket] += weight_vector[i]
                    contributing[bucket].append(symptom)

        # 총점 계산
        total = sum(scores.values())
        if total == 0:
            total = 1  # 0 나눗셈 방지

        # BucketScore 리스트 생성
        bucket_scores = []
        for bucket in bucket_order:
            bucket_scores.append(
                BucketScore(
                    bucket=bucket,
                    score=round(scores[bucket], 2),
                    percentage=round((scores[bucket] / total) * 100, 1),
                    contributing_symptoms=list(set(contributing[bucket])),
                )
            )

        # 점수 순으로 정렬
        bucket_scores.sort(key=lambda x: x.score, reverse=True)

        # 순위 리스트
        ranking = [bs.bucket for bs in bucket_scores]

        return bucket_scores, ranking

    def get_score_dict(
        self,
        body_part: BodyPartInput,
        bp_config: Optional[BodyPartConfig] = None,
    ) -> Dict[str, float]:
        """버킷별 점수 딕셔너리 반환"""
        bucket_scores, _ = self.calculate_scores(body_part, bp_config)
        return {bs.bucket: bs.score for bs in bucket_scores}
