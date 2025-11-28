"""사용자 입력 모델"""

from typing import List, Optional, Literal, Any, Dict, Union
from pydantic import BaseModel, Field, field_validator


class Demographics(BaseModel):
    """인구통계학적 정보"""

    age: int = Field(..., ge=10, le=100, description="나이")
    sex: Literal["male", "female"] = Field(..., description="성별")
    height_cm: float = Field(..., ge=100, le=250, description="키 (cm)")
    weight_kg: float = Field(..., ge=30, le=200, description="몸무게 (kg)")

    @property
    def bmi(self) -> float:
        """BMI 계산"""
        height_m = self.height_cm / 100
        return round(self.weight_kg / (height_m**2), 1)

    @property
    def age_code(self) -> str:
        """연령대 코드 반환"""
        if self.age >= 60:
            return "age_gte_60"
        elif self.age >= 50:
            return "age_gte_50"
        elif self.age >= 40:
            return "age_40s"
        elif self.age >= 30:
            return "age_30s"
        elif self.age >= 20:
            return "age_20s"
        else:
            return "age_teens"

    @property
    def bmi_code(self) -> str:
        """BMI 코드 반환"""
        bmi = self.bmi
        if bmi >= 30:
            return "bmi_gte_30"
        elif bmi >= 27:
            return "bmi_gte_27"
        elif bmi >= 25:
            return "bmi_gte_25"
        else:
            return "bmi_normal"

    @property
    def sex_code(self) -> str:
        """성별 코드 반환"""
        return f"sex_{self.sex}"


class PhysicalScore(BaseModel):
    """신체 점수 (Lv A/B/C/D) - 신체 자가평가 4문항 총점"""

    total_score: int = Field(..., ge=4, le=16, description="총점 (4-16)")

    @property
    def level(self) -> Literal["A", "B", "C", "D"]:
        """
        점수에 따른 레벨 반환
        - A: 14-16점 (상위 근력)
        - B: 11-13점 (평균 이상)
        - C: 8-10점 (기본 기능)
        - D: 4-7점 (기능 저하)
        """
        if self.total_score >= 14:
            return "A"
        elif self.total_score >= 11:
            return "B"
        elif self.total_score >= 8:
            return "C"
        else:
            return "D"

    @property
    def allowed_difficulties(self) -> List[str]:
        """허용된 운동 난이도"""
        level_map = {
            "A": ["low", "medium", "high"],
            "B": ["low", "medium", "high"],
            "C": ["low", "medium"],
            "D": ["low"],
        }
        return level_map[self.level]


class BodyPartInput(BaseModel):
    """부위별 입력"""

    code: str = Field(..., description="부위 코드 (knee, shoulder 등)")
    primary: bool = Field(default=True, description="주요 부위 여부")
    side: Optional[Literal["left", "right", "both"]] = Field(default=None, description="좌우 구분")
    symptoms: List[str] = Field(default_factory=list, description="증상 코드 리스트")
    nrs: int = Field(..., ge=0, le=10, description="통증 점수 (0-10)")
    red_flags_checked: List[str] = Field(default_factory=list, description="확인된 레드플래그")

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        valid_codes = ["knee", "shoulder", "back", "neck", "ankle"]
        if v not in valid_codes:
            raise ValueError(f"지원하지 않는 부위: {v}. 가능한 값: {valid_codes}")
        return v


class SurveyResponse(BaseModel):
    """설문 응답 (raw)"""

    question_id: str
    selected_options: List[str]


class NaturalLanguageInput(BaseModel):
    """사용자 자연어 입력"""

    chief_complaint: Optional[str] = Field(
        default=None,
        description="주호소 - 사용자가 직접 입력한 증상 설명"
    )
    pain_description: Optional[str] = Field(
        default=None,
        description="통증 설명 - 언제, 어떻게, 어디가 아픈지"
    )
    history: Optional[str] = Field(
        default=None,
        description="병력 - 이전 치료, 부상 경험 등"
    )
    goals: Optional[str] = Field(
        default=None,
        description="목표 - 원하는 결과, 활동 복귀 목표 등"
    )
    additional_notes: Optional[str] = Field(
        default=None,
        description="기타 추가 정보"
    )

    @property
    def has_content(self) -> bool:
        """내용이 있는지 확인"""
        return any([
            self.chief_complaint,
            self.pain_description,
            self.history,
            self.goals,
            self.additional_notes,
        ])

    def to_text(self) -> str:
        """전체 텍스트로 변환 (LLM 컨텍스트용)"""
        parts = []
        if self.chief_complaint:
            parts.append(f"주호소: {self.chief_complaint}")
        if self.pain_description:
            parts.append(f"통증 설명: {self.pain_description}")
        if self.history:
            parts.append(f"병력: {self.history}")
        if self.goals:
            parts.append(f"목표: {self.goals}")
        if self.additional_notes:
            parts.append(f"기타: {self.additional_notes}")
        return "\n".join(parts) if parts else ""


class UserInput(BaseModel):
    """파이프라인 입력 데이터"""

    demographics: Demographics
    physical_score: PhysicalScore
    body_parts: List[BodyPartInput] = Field(..., min_length=1)
    natural_language: Optional[NaturalLanguageInput] = Field(
        default=None,
        description="사용자 자연어 입력 (주호소, 통증 설명 등)"
    )
    survey_responses: Optional[Union[List[SurveyResponse], Dict[str, Any]]] = Field(
        default=None, description="원본 설문 응답 (디버깅용) - List 또는 Dict 형식"
    )

    @property
    def primary_body_part(self) -> BodyPartInput:
        """주요 부위 반환"""
        for bp in self.body_parts:
            if bp.primary:
                return bp
        return self.body_parts[0]

    @property
    def is_multi_body_part(self) -> bool:
        """복합 부위 여부"""
        return len(self.body_parts) > 1

    def get_all_symptoms(self) -> List[str]:
        """모든 증상 코드 반환 (인구통계 포함)"""
        symptoms = [
            self.demographics.sex_code,
            self.demographics.age_code,
            self.demographics.bmi_code,
        ]
        for bp in self.body_parts:
            symptoms.extend(bp.symptoms)
        return list(set(symptoms))
