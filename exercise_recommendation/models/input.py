"""운동 추천 입력 모델

사후 설문 데이터 포함 - 앱에서 전달받음
"""

from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.models import Demographics, PhysicalScore


class JointStatus(BaseModel):
    """관절 상태 정보 (v2.0 개인화용)

    새로운 운동 DB 칼럼(joint_load, kinetic_chain, required_rom)을
    활용한 개인화를 위한 입력 모델
    """

    # 관절 상태
    joint_condition: Literal["normal", "limited", "unstable"] = Field(
        default="normal",
        description="관절 상태 (normal: 정상, limited: 가동범위 제한, unstable: 불안정)"
    )

    # 가동범위 상태
    rom_status: Literal["normal", "restricted"] = Field(
        default="normal",
        description="가동범위 상태 (normal: 정상, restricted: 제한됨)"
    )

    # 재활 단계
    rehabilitation_phase: Literal["acute", "subacute", "chronic", "maintenance"] = Field(
        default="maintenance",
        description="재활 단계 (acute: 급성기, subacute: 아급성기, chronic: 만성기, maintenance: 유지기)"
    )

    # 체중부하 가능 여부
    weight_bearing_tolerance: Literal["none", "partial", "full"] = Field(
        default="full",
        description="체중부하 허용 수준 (none: 불가, partial: 부분, full: 전체)"
    )

    @property
    def preferred_joint_load(self) -> List[str]:
        """선호하는 관절 부하 수준"""
        if self.joint_condition == "unstable" or self.weight_bearing_tolerance == "none":
            return ["very_low"]
        elif self.joint_condition == "limited" or self.weight_bearing_tolerance == "partial":
            return ["very_low", "low"]
        else:
            return ["very_low", "low", "medium"]

    @property
    def preferred_kinetic_chain(self) -> List[str]:
        """선호하는 운동 사슬 타입"""
        if self.rehabilitation_phase == "acute":
            return ["OKC"]  # 급성기: 열린 사슬만
        elif self.rehabilitation_phase == "subacute":
            return ["OKC", "CKC"]  # 아급성기: 둘 다 가능
        else:
            return ["OKC", "CKC"]  # 만성기/유지기: 둘 다 가능

    @property
    def preferred_rom(self) -> List[str]:
        """선호하는 가동범위"""
        if self.rom_status == "restricted":
            return ["small"]
        else:
            return ["small", "medium"]


class PostAssessmentResult(BaseModel):
    """사후 설문 결과 (앱에서 수집)

    RPE 기반 3문항:
    1. 운동 난이도 체감 (1-5)
    2. 근육 자극 정도 (1-5)
    3. 땀 배출량 (1-5)
    """

    session_date: datetime = Field(..., description="세션 날짜")

    # RPE 기반 3문항
    difficulty_felt: int = Field(
        ..., ge=1, le=5,
        description="운동 난이도 체감 (1: 매우 쉬움 ~ 5: 매우 힘듦)"
    )
    muscle_stimulus: int = Field(
        ..., ge=1, le=5,
        description="근육 자극 정도 (1: 전혀 없음 ~ 5: 매우 강함)"
    )
    sweat_level: int = Field(
        ..., ge=1, le=5,
        description="땀 배출량 (1: 전혀 없음 ~ 5: 매우 많음)"
    )

    # 선택 항목
    pain_during_exercise: Optional[int] = Field(
        default=None, ge=0, le=10,
        description="운동 중 통증 (NRS 0-10)"
    )
    skipped_exercises: List[str] = Field(
        default_factory=list,
        description="건너뛴 운동 ID 목록"
    )
    completed_sets: Optional[int] = Field(
        default=None,
        description="완료한 세트 수"
    )
    total_sets: Optional[int] = Field(
        default=None,
        description="총 세트 수"
    )

    @property
    def total_rpe_score(self) -> int:
        """RPE 총점 (3-15)"""
        return self.difficulty_felt + self.muscle_stimulus + self.sweat_level

    @property
    def completion_rate(self) -> Optional[float]:
        """완수율 (0.0-1.0)"""
        if self.total_sets and self.completed_sets is not None:
            return self.completed_sets / self.total_sets
        return None


class ExerciseRecommendationInput(BaseModel):
    """운동 추천 입력

    API 엔드포인트: POST /api/v1/recommend-exercises
    사용 빈도: 매일

    예시:
    {
        "user_id": "user_123",
        "body_part": "knee",
        "bucket": "OA",
        "physical_score": {"total_score": 12},
        "demographics": {"age": 55, "sex": "male", ...},
        "nrs": 5,
        "previous_assessments": [...],
        "last_assessment_date": "2025-11-29T10:00:00"
    }
    """

    # === 필수 ===
    user_id: str = Field(..., description="사용자 ID")
    body_part: str = Field(..., description="부위 코드 (knee, shoulder 등)")
    bucket: str = Field(..., description="버킷 추론 결과 (OA/OVR/TRM/INF)")

    # === 사전 평가 결과 ===
    physical_score: PhysicalScore = Field(..., description="신체 점수 (Lv A/B/C/D)")
    demographics: Demographics = Field(..., description="인구통계학적 정보")
    nrs: int = Field(..., ge=0, le=10, description="통증 점수 (0-10)")

    # === v2.0: 관절 상태 (개인화 강화) ===
    joint_status: Optional[JointStatus] = Field(
        default=None,
        description="관절 상태 정보 (v2.0 개인화용, 없으면 기본값 사용)"
    )

    # === 사후 설문 데이터 (Optional) ===
    previous_assessments: Optional[List[PostAssessmentResult]] = Field(
        default=None,
        description="최근 사후 설문 기록 (최대 3세션)"
    )
    last_assessment_date: Optional[datetime] = Field(
        default=None,
        description="마지막 사후 설문 날짜"
    )

    # === 운동 중 데이터 (Optional) ===
    exercise_duration_history: Optional[List[int]] = Field(
        default=None,
        description="운동 시간 기록 (분)"
    )
    skipped_exercises: Optional[List[str]] = Field(
        default=None,
        description="자주 건너뛴 운동 ID"
    )
    favorite_exercises: Optional[List[str]] = Field(
        default=None,
        description="즐겨찾기 운동 ID"
    )

    @property
    def is_first_session(self) -> bool:
        """최초 운동 여부"""
        return self.previous_assessments is None or len(self.previous_assessments) == 0

    @property
    def has_valid_assessments(self) -> bool:
        """유효한 사후 설문 존재 여부"""
        return (
            self.previous_assessments is not None
            and len(self.previous_assessments) > 0
        )

    class Config:
        json_schema_extra = {
            "example": {
                "user_id": "user_ex_001",
                "body_part": "knee",
                "bucket": "OA",
                "physical_score": {"total_score": 12},
                "demographics": {
                    "age": 55,
                    "sex": "male",
                    "height_cm": 175,
                    "weight_kg": 80
                },
                "nrs": 5,
                "joint_status": {
                    "joint_condition": "normal",
                    "rom_status": "normal",
                    "rehabilitation_phase": "maintenance",
                    "weight_bearing_tolerance": "full"
                },
                "previous_assessments": [
                    {
                        "session_date": "2026-01-06T10:00:00",
                        "difficulty_felt": 3,
                        "muscle_stimulus": 3,
                        "sweat_level": 2,
                        "pain_during_exercise": 4,
                        "skipped_exercises": [],
                        "completed_sets": 10,
                        "total_sets": 12
                    }
                ],
                "last_assessment_date": "2026-01-06T10:00:00",
                "skipped_exercises": ["E05"],
                "favorite_exercises": ["E01", "E02"]
            }
        }
