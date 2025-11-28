"""운동 추천 모델"""

from typing import List, Optional, Literal
from pydantic import BaseModel, Field


class Exercise(BaseModel):
    """운동 정보"""

    exercise_id: str = Field(..., description="운동 ID (E01, E02 등)")
    name_en: str = Field(..., description="영문명")
    name_kr: str = Field(..., description="한글명")
    difficulty: Literal["low", "medium", "high"] = Field(..., description="난이도")
    diagnosis_tags: List[str] = Field(..., description="적합 진단 태그")
    function_tags: List[str] = Field(..., description="기능 태그")
    target_muscles: List[str] = Field(..., description="타겟 근육")
    sets: int = Field(..., description="세트 수")
    reps: str = Field(..., description="반복 횟수")
    rest: str = Field(..., description="휴식 시간")
    description: str = Field(..., description="설명")
    youtube: Optional[str] = Field(default=None, description="유튜브 링크")


class ExerciseRecommendation(BaseModel):
    """개별 운동 추천"""

    exercise: Exercise = Field(..., description="운동 정보")
    reason: str = Field(..., description="추천 이유 (LLM 생성)")
    priority: int = Field(..., ge=1, description="우선순위 (1이 가장 높음)")
    match_score: float = Field(..., ge=0, le=1, description="적합도 점수")


class ExcludedExercise(BaseModel):
    """제외된 운동"""

    exercise_id: str = Field(..., description="운동 ID")
    name_kr: str = Field(..., description="한글명")
    reason: str = Field(..., description="제외 사유")
    exclusion_type: Literal["contraindication", "difficulty", "nrs"] = Field(
        ..., description="제외 유형"
    )


class ExerciseSet(BaseModel):
    """운동 세트 (Phase 3 출력)"""

    body_part: str = Field(..., description="부위 코드")
    diagnosis_bucket: str = Field(..., description="진단 버킷")
    recommendations: List[ExerciseRecommendation] = Field(
        ..., min_length=1, description="추천 운동 목록"
    )
    excluded: List[ExcludedExercise] = Field(
        default_factory=list, description="제외된 운동 목록"
    )
    common_safe: List[str] = Field(
        default_factory=list, description="복합 부위 시 공통 안전 운동"
    )
    routine_order: List[str] = Field(..., description="루틴 순서 (운동 ID)")
    total_duration_min: int = Field(..., description="예상 소요 시간 (분)")
    llm_reasoning: str = Field(..., description="LLM 추천 근거")

    @property
    def exercise_count(self) -> int:
        """추천 운동 수"""
        return len(self.recommendations)

    def get_by_id(self, exercise_id: str) -> Optional[ExerciseRecommendation]:
        """ID로 운동 조회"""
        for rec in self.recommendations:
            if rec.exercise.exercise_id == exercise_id:
                return rec
        return None
