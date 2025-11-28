"""Phase 1: 입력 처리 스텝

Step 1.1: 입력 검증
Step 1.2: 레드플래그 체크
Step 1.3: 증상 매핑
Step 1.4: 인구통계 보강
"""

from typing import Dict, Any, List

from langsmith import traceable

from .base import PipelineStep, StepResult, StepContext, StepStatus


class InputValidationStep(PipelineStep):
    """
    Step 1.1: 입력 데이터 검증

    - Pydantic 스키마 검증
    - 필수 필드 확인
    - 데이터 타입 변환
    """

    name = "step_1_1_input_validation"
    description = "입력 데이터 검증 및 파싱"

    def __init__(self, validator=None):
        super().__init__()
        self.validator = validator

    @traceable(name="step_1_1_input_validation")
    def execute(self, context: StepContext) -> StepResult:
        """입력 검증 실행"""
        from orthocare.services.input import InputValidator

        validator = self.validator or InputValidator()

        try:
            user_input = validator.validate(context.raw_input)
            context.user_input = user_input
            context.validation_passed = True

            return StepResult(
                step_name=self.name,
                status=StepStatus.COMPLETED,
                output={
                    "demographics": {
                        "age": user_input.demographics.age,
                        "sex": user_input.demographics.sex,
                    },
                    "body_parts_count": len(user_input.body_parts),
                    "body_parts": [bp.code for bp in user_input.body_parts],
                },
                metadata={
                    "validation_passed": True,
                    "has_survey_responses": user_input.survey_responses is not None,
                },
            )

        except Exception as e:
            context.validation_passed = False
            raise


class RedFlagCheckStep(PipelineStep):
    """
    Step 1.2: 레드플래그 체크

    - 즉시 의료 조치 필요한 증상 확인
    - 운동 권장 가능 여부 결정
    """

    name = "step_1_2_red_flag_check"
    description = "레드플래그 증상 확인"

    def __init__(self, red_flag_checker=None):
        super().__init__()
        self.red_flag_checker = red_flag_checker

    def should_skip(self, context: StepContext) -> bool:
        return not context.validation_passed

    @traceable(name="step_1_2_red_flag_check")
    def execute(self, context: StepContext) -> StepResult:
        """레드플래그 체크 실행"""
        from orthocare.services.input import RedFlagChecker

        checker = self.red_flag_checker or RedFlagChecker()

        user_input = context.user_input
        red_flag_results = checker.check(user_input)
        should_block = checker.should_block_exercise(red_flag_results)

        context.red_flags = red_flag_results
        context.blocked_by_red_flag = should_block

        # 감지된 레드플래그 목록
        detected_flags = []
        for bp_code, result in red_flag_results.items():
            if hasattr(result, 'detected_flags') and result.detected_flags:
                detected_flags.extend([
                    {"body_part": bp_code, "flag": f}
                    for f in result.detected_flags
                ])

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output={
                "detected_count": len(detected_flags),
                "detected_flags": detected_flags,
                "blocked": should_block,
            },
            metadata={
                "body_parts_checked": list(red_flag_results.keys()),
                "should_block_exercise": should_block,
            },
        )


class SymptomMappingStep(PipelineStep):
    """
    Step 1.3: 증상 코드 매핑

    - 설문 응답을 증상 코드로 변환
    - 증상 설명 추출
    """

    name = "step_1_3_symptom_mapping"
    description = "설문 응답을 증상 코드로 매핑"

    def __init__(self, symptom_mapper=None):
        super().__init__()
        self.symptom_mapper = symptom_mapper

    def should_skip(self, context: StepContext) -> bool:
        return not context.validation_passed or context.blocked_by_red_flag

    @traceable(name="step_1_3_symptom_mapping")
    def execute(self, context: StepContext) -> StepResult:
        """증상 매핑 실행"""
        from orthocare.services.input import SymptomMapper

        mapper = self.symptom_mapper or SymptomMapper()

        user_input = context.user_input
        symptom_codes = {}

        for body_part in user_input.body_parts:
            bp_code = body_part.code
            symptoms = body_part.symptoms

            # 증상 설명 추출
            descriptions = []
            for s in symptoms:
                desc = mapper.get_symptom_description(bp_code, s)
                if desc:
                    descriptions.append(desc)

            symptom_codes[bp_code] = {
                "codes": symptoms,
                "descriptions": descriptions,
            }

        context.symptom_codes = symptom_codes

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output={
                "body_parts": list(symptom_codes.keys()),
                "symptom_counts": {
                    bp: len(data["codes"])
                    for bp, data in symptom_codes.items()
                },
            },
            metadata={
                "total_symptoms": sum(
                    len(data["codes"]) for data in symptom_codes.values()
                ),
            },
        )


class DemographicsEnrichmentStep(PipelineStep):
    """
    Step 1.4: 인구통계 정보 보강

    - 나이 그룹 분류
    - BMI 카테고리
    - 활동 수준 추정
    """

    name = "step_1_4_demographics_enrichment"
    description = "인구통계 정보 보강"

    def __init__(self, symptom_mapper=None):
        super().__init__()
        self.symptom_mapper = symptom_mapper

    def should_skip(self, context: StepContext) -> bool:
        return not context.validation_passed or context.blocked_by_red_flag

    @traceable(name="step_1_4_demographics_enrichment")
    def execute(self, context: StepContext) -> StepResult:
        """인구통계 보강 실행"""
        from orthocare.services.input import SymptomMapper

        mapper = self.symptom_mapper or SymptomMapper()

        user_input = context.user_input
        enriched_input = mapper.enrich_user_input(user_input)

        # 보강된 인구통계 코드 추출
        enriched_codes = []
        for body_part in enriched_input.body_parts:
            for symptom in body_part.symptoms:
                # D로 시작하면 인구통계 코드
                if symptom.startswith("D"):
                    enriched_codes.append({
                        "body_part": body_part.code,
                        "code": symptom,
                    })

        context.user_input = enriched_input
        context.enriched_demographics = {
            "added_codes": enriched_codes,
            "age_group": self._get_age_group(user_input.demographics.age),
        }

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output={
                "enriched_codes_count": len(enriched_codes),
                "enriched_codes": enriched_codes,
            },
            metadata={
                "age_group": context.enriched_demographics["age_group"],
            },
        )

    def _get_age_group(self, age: int) -> str:
        """나이 그룹 분류"""
        if age < 30:
            return "young"
        elif age < 50:
            return "middle"
        elif age < 65:
            return "senior"
        else:
            return "elderly"
