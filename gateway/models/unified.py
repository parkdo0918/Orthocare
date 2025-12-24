"""통합 API 요청/응답 모델

앱 → 서버 한 번의 요청으로:
1. 버킷 추론
2. 운동 추천 (선택)
3. 백엔드 저장용 데이터 반환
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
import uuid

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.models import Demographics, BodyPartInput, PhysicalScore
from bucket_inference.models import (
    BucketInferenceOutput,
    RedFlagResult,
)
from bucket_inference.models.input import NaturalLanguageInput
from exercise_recommendation.models.output import ExerciseRecommendationOutput


class RequestOptions(BaseModel):
    """요청 옵션"""

    include_exercises: bool = Field(
        default=True,
        description="운동 추천 포함 여부 (False면 버킷 추론만)"
    )
    exercise_days: int = Field(
        default=3,
        ge=1, le=7,
        description="운동 커리큘럼 일수"
    )
    skip_exercise_on_red_flag: bool = Field(
        default=True,
        description="Red Flag 시 운동 추천 스킵"
    )


class DiagnosisContext(BaseModel):
    """버킷 추론 컨텍스트 (운동 추천 개인화용)

    버킷 추론의 상세 정보를 운동 추천에 전달하여
    더 정교한 개인화 수행
    """

    # 핵심 결과
    bucket: str = Field(..., description="최종 버킷 (OA/OVR/TRM/INF/STF)")
    confidence: float = Field(..., description="추론 신뢰도 (0-1)")

    # LLM 추론 정보
    llm_reasoning: str = Field(
        default="",
        description="LLM 판단 근거 (운동 개인화에 활용)"
    )
    evidence_summary: str = Field(
        default="",
        description="근거 요약"
    )

    # 점수 정보
    bucket_scores: Dict[str, float] = Field(
        default_factory=dict,
        description="버킷별 점수"
    )
    contributing_symptoms: List[str] = Field(
        default_factory=list,
        description="주요 기여 증상들 (운동 우선순위 결정에 활용)"
    )

    # 검색 결과
    weight_ranking: List[str] = Field(
        default_factory=list,
        description="가중치 기반 순위"
    )
    search_ranking: List[str] = Field(
        default_factory=list,
        description="근거 검색 기반 순위"
    )

    @classmethod
    def from_bucket_output(
        cls,
        output: BucketInferenceOutput,
        symptoms: List[str] = None,
    ) -> "DiagnosisContext":
        """BucketInferenceOutput에서 생성"""
        # 기여 증상 추출 (상위 버킷 점수에 기여한 증상)
        contributing = symptoms or []

        return cls(
            bucket=output.final_bucket,
            confidence=output.confidence,
            llm_reasoning=output.llm_reasoning,
            evidence_summary=output.evidence_summary,
            bucket_scores=output.bucket_scores,
            contributing_symptoms=contributing,
            weight_ranking=output.weight_ranking,
            search_ranking=output.search_ranking,
        )


class SurveyData(BaseModel):
    """원본 설문 데이터 (백엔드 저장용)

    앱에서 서버로 보낸 설문 데이터를 그대로 반환하여
    백엔드에서 유저 프로필에 저장할 수 있도록 함
    """

    demographics: Demographics
    body_parts: List[BodyPartInput]
    natural_language: Optional[NaturalLanguageInput] = None
    physical_score: Optional[PhysicalScore] = None
    raw_responses: Optional[Dict[str, Any]] = Field(
        default=None,
        description="앱 설문 원본 응답 (key-value)"
    )


class UnifiedRequest(BaseModel):
    """통합 API 요청

    앱에서 서버로 보내는 단일 요청으로
    버킷 추론 + 운동 추천을 한 번에 처리

    예시:
    {
        "request_id": "uuid-xxx",
        "user_id": "user_123",
        "demographics": {"age": 55, "sex": "male", ...},
        "body_parts": [{"code": "knee", "symptoms": [...], "nrs": 6}],
        "physical_score": {"total_score": 12},
        "natural_language": {"chief_complaint": "무릎이 아파요"},
        "options": {"include_exercises": true, "exercise_days": 3}
    }
    """

    # 요청 식별
    request_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="요청 고유 ID (중복 방지, 캐싱용)"
    )
    user_id: str = Field(..., description="사용자 ID")

    # 필수 입력
    demographics: Demographics = Field(..., description="인구통계학적 정보")
    body_parts: List[BodyPartInput] = Field(
        ...,
        min_length=1,
        description="부위별 증상 입력"
    )

    # 운동 추천용 (선택이지만 운동 추천 시 필요)
    physical_score: Optional[PhysicalScore] = Field(
        default=None,
        description="신체 점수 (운동 추천 시 필요)"
    )

    # 자연어 입력 (선택)
    natural_language: Optional[NaturalLanguageInput] = Field(
        default=None,
        description="자연어 입력"
    )

    # 원본 설문 (백엔드 저장용)
    raw_survey_responses: Optional[Dict[str, Any]] = Field(
        default=None,
        description="앱 설문 원본 응답"
    )

    # 옵션
    options: RequestOptions = Field(
        default_factory=RequestOptions,
        description="요청 옵션"
    )

    @property
    def primary_body_part(self) -> BodyPartInput:
        """주요 부위"""
        for bp in self.body_parts:
            if bp.primary:
                return bp
        return self.body_parts[0]

    @property
    def primary_nrs(self) -> int:
        """주요 부위 NRS"""
        return self.primary_body_part.nrs


class DiagnosisResult(BaseModel):
    """버킷 추론 결과 (응답용)"""

    body_part: str
    final_bucket: str
    confidence: float
    bucket_scores: Dict[str, float]
    weight_ranking: List[str]
    search_ranking: List[str]
    evidence_summary: str
    llm_reasoning: str
    red_flag: Optional[RedFlagResult] = None
    inferred_at: datetime

    @classmethod
    def from_bucket_output(cls, output: BucketInferenceOutput) -> "DiagnosisResult":
        """BucketInferenceOutput에서 생성"""
        return cls(
            body_part=output.body_part,
            final_bucket=output.final_bucket,
            confidence=output.confidence,
            bucket_scores=output.bucket_scores,
            weight_ranking=output.weight_ranking,
            search_ranking=output.search_ranking,
            evidence_summary=output.evidence_summary,
            llm_reasoning=output.llm_reasoning,
            red_flag=output.red_flag,
            inferred_at=output.inferred_at,
        )


class ExercisePlanResult(BaseModel):
    """운동 추천 결과 (응답용)"""

    body_part: str
    bucket: str
    exercises: List[Dict[str, Any]]  # RecommendedExercise를 dict로
    routine_order: List[str]
    total_duration_min: int
    difficulty_level: str
    llm_reasoning: str
    personalization_note: Optional[str] = None
    recommended_at: datetime

    @classmethod
    def from_exercise_output(
        cls,
        output: ExerciseRecommendationOutput,
        personalization_note: str = None,
    ) -> "ExercisePlanResult":
        """ExerciseRecommendationOutput에서 생성"""
        return cls(
            body_part=output.body_part,
            bucket=output.bucket,
            exercises=[ex.model_dump() for ex in output.exercises],
            routine_order=output.routine_order,
            total_duration_min=output.total_duration_min,
            difficulty_level=output.difficulty_level,
            llm_reasoning=output.llm_reasoning,
            personalization_note=personalization_note,
            recommended_at=output.recommended_at,
        )


class UnifiedResponse(BaseModel):
    """통합 API 응답

    앱이 이 응답 전체를 백엔드에 저장하면 됨

    구성:
    1. survey_data: 원본 설문 (유저 프로필용)
    2. diagnosis: 버킷 추론 결과
    3. exercise_plan: 운동 추천 결과 (선택)
    4. metadata: 요청/응답 메타데이터
    """

    # 요청 식별
    request_id: str = Field(..., description="요청 고유 ID")
    user_id: str = Field(..., description="사용자 ID")

    # 원본 설문 데이터 (백엔드 저장용)
    survey_data: SurveyData = Field(..., description="원본 설문 데이터")

    # 버킷 추론 결과
    diagnosis: DiagnosisResult = Field(..., description="버킷 추론 결과")

    # 운동 추천 결과 (선택)
    exercise_plan: Optional[ExercisePlanResult] = Field(
        default=None,
        description="운동 추천 결과 (red_flag 시 null)"
    )

    # 처리 상태
    status: str = Field(
        default="success",
        description="처리 상태 (success, partial, error)"
    )
    message: Optional[str] = Field(
        default=None,
        description="상태 메시지 (red_flag 경고 등)"
    )

    # 메타데이터
    processed_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="처리 완료 시간"
    )
    processing_time_ms: Optional[int] = Field(
        default=None,
        description="총 처리 시간 (밀리초)"
    )

    @property
    def has_red_flag(self) -> bool:
        """Red Flag 여부"""
        return (
            self.diagnosis.red_flag is not None
            and self.diagnosis.red_flag.triggered
        )

    @property
    def has_exercise_plan(self) -> bool:
        """운동 추천 포함 여부"""
        return self.exercise_plan is not None

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
