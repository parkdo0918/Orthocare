"""피드백 수집기

사용자 피드백 수집 및 처리
"""

from typing import List, Optional, Dict, Any
from datetime import datetime

from langsmith import traceable

from orthocare.models.feedback import (
    FeedbackRating,
    SearchFeedback,
    ExerciseFeedback,
    PairwisePreference,
)
from .storage import FeedbackStorage


class FeedbackCollector:
    """
    피드백 수집기

    사용 예시:
        collector = FeedbackCollector(storage)

        # 검색 결과 피드백
        collector.record_search_feedback(
            query="무릎 통증이 심해요",
            clicked=["ex_001", "ex_002"],
            useful=["ex_001"],
            irrelevant=["ex_003"],
        )

        # 운동 효과 피드백
        collector.record_exercise_feedback(
            exercise_id="knee_squat_001",
            rating="positive",
            pain_change=3,  # 통증 3점 감소
            original_query="무릎 통증 완화 운동",
        )

        # A/B 선호도
        collector.record_preference(
            query="무릎 강화 운동",
            item_a="squat_001",
            item_b="lunge_001",
            preferred="a",  # squat 선호
        )
    """

    def __init__(
        self,
        storage: FeedbackStorage,
        session_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.storage = storage
        self.session_id = session_id
        self.user_id = user_id

    @traceable(name="collect_search_feedback")
    def record_search_feedback(
        self,
        query: str,
        clicked: List[str] = None,
        useful: List[str] = None,
        irrelevant: List[str] = None,
        body_part: Optional[str] = None,
        query_embedding_id: Optional[str] = None,
    ) -> bool:
        """
        검색 결과 피드백 기록

        Args:
            query: 검색 쿼리
            clicked: 클릭한 결과 ID들
            useful: 유용했던 결과 ID들
            irrelevant: 관련없었던 결과 ID들
            body_part: 부위 코드
            query_embedding_id: 쿼리 임베딩 ID (캐싱용)

        Returns:
            저장 성공 여부
        """
        feedback = SearchFeedback(
            query_text=query,
            query_embedding_id=query_embedding_id,
            body_part=body_part,
            clicked_results=clicked or [],
            useful_results=useful or [],
            irrelevant_results=irrelevant or [],
            session_id=self.session_id,
            user_id=self.user_id,
        )

        return self.storage.save_search_feedback(feedback)

    @traceable(name="collect_exercise_feedback")
    def record_exercise_feedback(
        self,
        exercise_id: str,
        rating: str,  # very_negative, negative, neutral, positive, very_positive
        pain_change: Optional[int] = None,
        would_recommend: Optional[bool] = None,
        completion_rate: Optional[float] = None,
        comment: Optional[str] = None,
        original_query: Optional[str] = None,
        recommendation_context: Optional[Dict[str, Any]] = None,
        exercise_vector_id: Optional[str] = None,
        days_since_start: Optional[int] = None,
    ) -> bool:
        """
        운동 효과 피드백 기록

        Args:
            exercise_id: 운동 ID
            rating: 효과 평점
            pain_change: 통증 변화 (-10 ~ +10)
            would_recommend: 추천 의향
            completion_rate: 운동 완수율 (0.0 ~ 1.0)
            comment: 코멘트
            original_query: 원본 자연어 쿼리
            recommendation_context: 추천 컨텍스트
            exercise_vector_id: 벡터 DB의 운동 ID
            days_since_start: 운동 시작 후 경과 일수

        Returns:
            저장 성공 여부
        """
        feedback = ExerciseFeedback(
            exercise_id=exercise_id,
            exercise_vector_id=exercise_vector_id,
            recommendation_context=recommendation_context or {},
            original_query=original_query,
            rating=FeedbackRating(rating),
            pain_change=pain_change,
            would_recommend=would_recommend,
            completion_rate=completion_rate,
            comment=comment,
            days_since_start=days_since_start,
            session_id=self.session_id,
            user_id=self.user_id,
        )

        return self.storage.save_exercise_feedback(feedback)

    @traceable(name="collect_preference")
    def record_preference(
        self,
        query: str,
        item_a: str,
        item_b: str,
        preferred: str,  # "a", "b", or "same"
        item_a_source: str = "exercise",
        item_b_source: str = "exercise",
        confidence: Optional[float] = None,
        body_part: Optional[str] = None,
    ) -> bool:
        """
        쌍별 선호도 기록

        Args:
            query: 검색 쿼리
            item_a: 첫 번째 항목 ID
            item_b: 두 번째 항목 ID
            preferred: 선호 항목 ("a", "b", "same")
            item_a_source: A 항목 소스
            item_b_source: B 항목 소스
            confidence: 확신도 (0.0 ~ 1.0)
            body_part: 부위 코드

        Returns:
            저장 성공 여부
        """
        preference_map = {"a": -1, "same": 0, "b": 1}
        preference_value = preference_map.get(preferred.lower(), 0)

        pref = PairwisePreference(
            query_text=query,
            body_part=body_part,
            item_a_id=item_a,
            item_b_id=item_b,
            item_a_source=item_a_source,
            item_b_source=item_b_source,
            preference=preference_value,
            confidence=confidence,
            session_id=self.session_id,
            user_id=self.user_id,
        )

        return self.storage.save_pairwise_preference(pref)

    def record_batch_relevance(
        self,
        query: str,
        results: List[Dict[str, Any]],
        body_part: Optional[str] = None,
    ) -> bool:
        """
        검색 결과 일괄 관련성 피드백

        Args:
            query: 검색 쿼리
            results: 결과 리스트 [{"id": "...", "relevant": True/False}, ...]
            body_part: 부위 코드

        Returns:
            저장 성공 여부
        """
        useful = [r["id"] for r in results if r.get("relevant", False)]
        irrelevant = [r["id"] for r in results if not r.get("relevant", True)]

        return self.record_search_feedback(
            query=query,
            useful=useful,
            irrelevant=irrelevant,
            body_part=body_part,
        )

    def set_session(self, session_id: str, user_id: Optional[str] = None):
        """세션 정보 설정"""
        self.session_id = session_id
        if user_id:
            self.user_id = user_id

    def get_stats(self) -> dict:
        """수집 통계 조회"""
        return self.storage.get_stats()
