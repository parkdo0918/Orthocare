"""가중치 계산 서비스"""

from typing import List, Dict, Tuple

from orthocare.models import BodyPartInput
from orthocare.models.diagnosis import BucketScore
from orthocare.data_ops.loaders.knee_loader import get_loader


class WeightService:
    """가중치 기반 버킷 점수 계산"""

    def calculate_scores(
        self,
        body_part: BodyPartInput,
    ) -> Tuple[List[BucketScore], List[str]]:
        """
        증상 코드 기반 버킷 점수 계산

        Args:
            body_part: 부위별 입력 (증상 코드 포함)

        Returns:
            (버킷 점수 리스트, 순위 리스트)
        """
        loader = get_loader(body_part.code)
        bucket_order = loader.bucket_order
        weights = loader.weights

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

    def get_score_breakdown(
        self,
        body_part: BodyPartInput,
    ) -> Dict[str, Dict[str, float]]:
        """
        증상별 버킷 기여도 상세 분석

        Returns:
            {증상: {버킷: 점수, ...}, ...}
        """
        loader = get_loader(body_part.code)
        bucket_order = loader.bucket_order
        weights = loader.weights

        breakdown = {}

        for symptom in body_part.symptoms:
            if symptom not in weights:
                continue

            weight_vector = weights[symptom]
            breakdown[symptom] = {}

            for i, bucket in enumerate(bucket_order):
                if i < len(weight_vector):
                    breakdown[symptom][bucket] = weight_vector[i]

        return breakdown

    def get_top_contributors(
        self,
        body_part: BodyPartInput,
        bucket: str,
        top_n: int = 5,
    ) -> List[Tuple[str, float]]:
        """
        특정 버킷에 가장 많이 기여한 증상 반환

        Returns:
            [(증상, 점수), ...] 리스트 (점수 내림차순)
        """
        loader = get_loader(body_part.code)
        bucket_order = loader.bucket_order
        weights = loader.weights

        if bucket not in bucket_order:
            raise ValueError(f"알 수 없는 버킷: {bucket}")

        bucket_idx = bucket_order.index(bucket)
        contributions = []

        for symptom in body_part.symptoms:
            if symptom not in weights:
                continue

            weight_vector = weights[symptom]
            if bucket_idx < len(weight_vector):
                score = weight_vector[bucket_idx]
                if score > 0:
                    contributions.append((symptom, score))

        # 점수 내림차순 정렬
        contributions.sort(key=lambda x: x[1], reverse=True)

        return contributions[:top_n]

    def compare_rankings(
        self,
        weight_ranking: List[str],
        search_ranking: List[str],
    ) -> Dict[str, any]:
        """
        가중치 순위 vs 검색 순위 비교

        Returns:
            비교 결과 딕셔너리
        """
        # 상위 버킷 일치 여부
        top_match = weight_ranking[0] == search_ranking[0] if search_ranking else True

        # 순위 변동
        changes = []
        for i, bucket in enumerate(weight_ranking):
            if bucket in search_ranking:
                search_rank = search_ranking.index(bucket)
                if search_rank != i:
                    changes.append({
                        "bucket": bucket,
                        "weight_rank": i + 1,
                        "search_rank": search_rank + 1,
                        "direction": "up" if search_rank < i else "down",
                    })

        return {
            "top_match": top_match,
            "changes": changes,
            "has_significant_discrepancy": not top_match or any(
                abs(c["weight_rank"] - c["search_rank"]) >= 2 for c in changes
            ),
        }
