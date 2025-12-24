"""운동 추천 출력 모델"""

from typing import List, Optional, Dict, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class RecommendedExercise(BaseModel):
    """추천 운동"""

    exercise_id: str = Field(..., description="운동 ID")
    name_kr: str = Field(..., description="한글명")
    name_en: str = Field(..., description="영문명")
    difficulty: str = Field(..., description="난이도 (low/medium/high 또는 beginner/intermediate/advanced)")
    function_tags: List[str] = Field(..., description="기능 태그")
    target_muscles: List[str] = Field(..., description="타겟 근육")

    # 세트 정보
    sets: int = Field(..., description="세트 수")
    reps: str = Field(..., description="반복 횟수")
    rest: str = Field(..., description="휴식 시간")

    # 추천 정보
    reason: str = Field(..., description="추천 이유")
    priority: int = Field(..., ge=1, description="우선순위")
    match_score: float = Field(..., ge=0, le=1, description="적합도 점수")

    # 미디어
    youtube: Optional[str] = Field(default=None, description="유튜브 링크")
    description: Optional[str] = Field(default=None, description="운동 설명")


class ExcludedExercise(BaseModel):
    """제외된 운동"""

    exercise_id: str = Field(..., description="운동 ID")
    name_kr: str = Field(..., description="한글명")
    reason: str = Field(..., description="제외 사유")
    exclusion_type: Literal["contraindication", "difficulty", "nrs", "assessment"] = Field(
        ..., description="제외 유형"
    )


class ExerciseRecommendationOutput(BaseModel):
    """운동 추천 출력

    API 응답: POST /api/v1/recommend-exercises
    """

    # 기본 정보
    user_id: str = Field(..., description="사용자 ID")
    body_part: str = Field(..., description="부위 코드")
    bucket: str = Field(..., description="진단 버킷")

    # === 추천 결과 ===
    exercises: List[RecommendedExercise] = Field(
        ..., min_length=1, description="추천 운동 목록"
    )
    excluded: List[ExcludedExercise] = Field(
        default_factory=list, description="제외된 운동 목록"
    )
    routine_order: List[str] = Field(..., description="루틴 순서 (운동 ID)")
    total_duration_min: int = Field(..., description="예상 소요 시간 (분)")
    difficulty_level: Literal["low", "medium", "high", "mixed"] = Field(
        ..., description="전체 난이도"
    )

    # === 조정 정보 ===
    adjustments_applied: Dict[str, int] = Field(
        default_factory=dict,
        description="적용된 조정 (difficulty_delta, sets_delta, reps_delta)"
    )
    assessment_status: Literal["fresh_start", "normal", "reset"] = Field(
        ..., description="사후 설문 처리 상태"
    )
    assessment_message: str = Field(
        default="", description="사후 설문 처리 메시지"
    )

    # === LLM 추론 ===
    llm_reasoning: str = Field(..., description="LLM 추천 근거")

    # 메타데이터
    recommended_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="추천 시간"
    )

    @property
    def exercise_count(self) -> int:
        """추천 운동 수"""
        return len(self.exercises)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
