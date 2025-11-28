"""사용자 피드백 모델

강화학습 기반 벡터 DB 개선을 위한 피드백 저장 스키마.

사용 시나리오:
1. 사용자가 운동 추천을 받음
2. 운동 수행 후 만족도/효과 피드백
3. 피드백 데이터 축적
4. 유사한 케이스끼리 클러스터링 강화

향후 활용:
- Contrastive Learning: 긍정 피드백 → 쿼리-결과 유사도 강화
- Triplet Loss: (쿼리, 긍정결과, 부정결과) 학습
- 피드백 기반 재랭킹 모델 학습
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field
import uuid


class FeedbackType(str, Enum):
    """피드백 유형"""
    RELEVANCE = "relevance"  # 검색 결과 관련성
    EFFECTIVENESS = "effectiveness"  # 운동 효과
    SATISFACTION = "satisfaction"  # 전반적 만족도
    PREFERENCE = "preference"  # 선호도 (A vs B)


class FeedbackRating(str, Enum):
    """피드백 등급"""
    VERY_NEGATIVE = "very_negative"  # -2
    NEGATIVE = "negative"  # -1
    NEUTRAL = "neutral"  # 0
    POSITIVE = "positive"  # +1
    VERY_POSITIVE = "very_positive"  # +2

    @property
    def score(self) -> int:
        scores = {
            "very_negative": -2,
            "negative": -1,
            "neutral": 0,
            "positive": 1,
            "very_positive": 2,
        }
        return scores[self.value]


class SearchFeedback(BaseModel):
    """검색 결과 피드백

    사용자가 검색 결과 중 실제로 유용했던 것과
    그렇지 않았던 것을 표시
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # 원본 쿼리 정보
    query_text: str = Field(..., description="검색에 사용된 텍스트")
    query_embedding_id: Optional[str] = Field(default=None, description="쿼리 임베딩 ID (재사용용)")
    body_part: Optional[str] = None

    # 결과 피드백
    clicked_results: List[str] = Field(default_factory=list, description="클릭한 결과 ID들")
    useful_results: List[str] = Field(default_factory=list, description="유용했던 결과 ID들")
    irrelevant_results: List[str] = Field(default_factory=list, description="관련없었던 결과 ID들")

    # 세션 정보
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class ExerciseFeedback(BaseModel):
    """운동 효과 피드백

    추천된 운동의 실제 효과에 대한 피드백.
    강화학습에서 가장 중요한 신호.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # 운동 정보
    exercise_id: str = Field(..., description="운동 ID")
    exercise_vector_id: Optional[str] = Field(default=None, description="벡터 DB의 운동 ID")

    # 추천 컨텍스트
    recommendation_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="추천 시 컨텍스트 (증상, 진단, 쿼리 등)"
    )
    original_query: Optional[str] = Field(default=None, description="원본 자연어 쿼리")

    # 피드백
    rating: FeedbackRating = Field(..., description="효과 평점")
    pain_change: Optional[int] = Field(
        default=None,
        ge=-10, le=10,
        description="통증 변화 (-10: 악화, 0: 변화없음, +10: 완전호전)"
    )
    would_recommend: Optional[bool] = Field(default=None, description="다른 사람에게 추천하겠는가")
    completion_rate: Optional[float] = Field(
        default=None,
        ge=0.0, le=1.0,
        description="운동 완수율 (0.0-1.0)"
    )

    # 자유 텍스트
    comment: Optional[str] = Field(default=None, max_length=500)

    # 메타
    days_since_start: Optional[int] = Field(default=None, description="운동 시작 후 경과 일수")
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class PairwisePreference(BaseModel):
    """쌍별 선호도 피드백

    두 운동/결과 중 어느 것이 더 유용했는지.
    Bradley-Terry 모델이나 ELO 방식으로 활용 가능.
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    # 쿼리 컨텍스트
    query_text: str
    body_part: Optional[str] = None

    # 비교 대상
    item_a_id: str
    item_b_id: str
    item_a_source: str  # exercise, paper, etc.
    item_b_source: str

    # 선호도 (-1: A 선호, 0: 동일, 1: B 선호)
    preference: int = Field(..., ge=-1, le=1)
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="확신도")

    # 메타
    session_id: Optional[str] = None
    user_id: Optional[str] = None


class FeedbackBatch(BaseModel):
    """피드백 배치

    강화학습 학습에 사용할 피드백 배치
    """
    search_feedbacks: List[SearchFeedback] = Field(default_factory=list)
    exercise_feedbacks: List[ExerciseFeedback] = Field(default_factory=list)
    pairwise_preferences: List[PairwisePreference] = Field(default_factory=list)

    @property
    def total_count(self) -> int:
        return (
            len(self.search_feedbacks) +
            len(self.exercise_feedbacks) +
            len(self.pairwise_preferences)
        )

    def get_positive_pairs(self) -> List[tuple]:
        """
        긍정 피드백에서 (쿼리, 결과) 쌍 추출

        Contrastive Learning 학습용
        """
        pairs = []

        # 검색 피드백에서 추출
        for sf in self.search_feedbacks:
            for useful_id in sf.useful_results:
                pairs.append((sf.query_text, useful_id))

        # 운동 피드백에서 추출
        for ef in self.exercise_feedbacks:
            if ef.rating.score >= 1 and ef.original_query:
                pairs.append((ef.original_query, ef.exercise_id))

        return pairs

    def get_negative_pairs(self) -> List[tuple]:
        """
        부정 피드백에서 (쿼리, 결과) 쌍 추출
        """
        pairs = []

        for sf in self.search_feedbacks:
            for irrelevant_id in sf.irrelevant_results:
                pairs.append((sf.query_text, irrelevant_id))

        for ef in self.exercise_feedbacks:
            if ef.rating.score <= -1 and ef.original_query:
                pairs.append((ef.original_query, ef.exercise_id))

        return pairs

    def get_triplets(self) -> List[tuple]:
        """
        Triplet 학습용 (anchor, positive, negative) 추출
        """
        triplets = []

        for pref in self.pairwise_preferences:
            if pref.preference == -1:  # A 선호
                triplets.append((pref.query_text, pref.item_a_id, pref.item_b_id))
            elif pref.preference == 1:  # B 선호
                triplets.append((pref.query_text, pref.item_b_id, pref.item_a_id))

        return triplets
