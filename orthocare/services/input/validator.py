"""입력 검증 서비스"""

from typing import List, Tuple
from pydantic import ValidationError

from orthocare.models import UserInput, BodyPartInput, Demographics, PhysicalScore
from orthocare.config.constants import SUPPORTED_BODY_PARTS


class InputValidationError(Exception):
    """입력 검증 실패"""

    def __init__(self, message: str, errors: List[str]):
        super().__init__(message)
        self.errors = errors


class InputValidator:
    """입력 데이터 검증"""

    def validate(self, data: dict) -> UserInput:
        """
        입력 데이터 검증 및 UserInput 객체 반환

        Args:
            data: 원시 입력 데이터

        Returns:
            검증된 UserInput 객체

        Raises:
            InputValidationError: 검증 실패 시
        """
        errors = []

        # 필수 필드 확인
        required_fields = ["demographics", "physical_score", "body_parts"]
        for field in required_fields:
            if field not in data:
                errors.append(f"필수 필드 누락: {field}")

        if errors:
            raise InputValidationError("입력 검증 실패", errors)

        # 부위 코드 검증
        body_parts = data.get("body_parts", [])
        for bp in body_parts:
            if bp.get("code") not in SUPPORTED_BODY_PARTS:
                errors.append(
                    f"지원하지 않는 부위: {bp.get('code')}. "
                    f"가능한 값: {SUPPORTED_BODY_PARTS}"
                )

        # 주요 부위 확인
        primary_count = sum(1 for bp in body_parts if bp.get("primary", False))
        if primary_count == 0 and body_parts:
            # 첫 번째를 주요 부위로 설정
            body_parts[0]["primary"] = True
        elif primary_count > 1:
            errors.append("주요 부위(primary=True)는 1개만 가능합니다")

        if errors:
            raise InputValidationError("입력 검증 실패", errors)

        # Pydantic 모델로 변환
        try:
            user_input = UserInput(**data)
        except ValidationError as e:
            pydantic_errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
            raise InputValidationError("데이터 형식 오류", pydantic_errors)

        return user_input

    def validate_demographics(self, data: dict) -> Tuple[Demographics, List[str]]:
        """
        인구통계 데이터 검증

        Returns:
            (Demographics 객체, 경고 메시지 리스트)
        """
        warnings = []

        try:
            demographics = Demographics(**data)
        except ValidationError as e:
            pydantic_errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
            raise InputValidationError("인구통계 데이터 오류", pydantic_errors)

        # BMI 경고
        bmi = demographics.bmi
        if bmi >= 35:
            warnings.append(f"고도 비만 (BMI {bmi}): 저강도 운동 권장")
        elif bmi < 18.5:
            warnings.append(f"저체중 (BMI {bmi})")

        # 연령 경고
        if demographics.age >= 75:
            warnings.append("고령 환자: 낙상 위험 고려 필요")

        return demographics, warnings

    def validate_body_part_input(self, data: dict) -> BodyPartInput:
        """부위별 입력 검증"""
        try:
            return BodyPartInput(**data)
        except ValidationError as e:
            pydantic_errors = [f"{err['loc']}: {err['msg']}" for err in e.errors()]
            raise InputValidationError("부위 입력 데이터 오류", pydantic_errors)
