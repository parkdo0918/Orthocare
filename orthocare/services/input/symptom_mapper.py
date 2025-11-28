"""설문 응답 → 증상 코드 매핑 서비스"""

from typing import List, Dict, Any

from orthocare.models import UserInput, BodyPartInput, SurveyResponse
from orthocare.data_ops.loaders.knee_loader import get_loader


class SymptomMapper:
    """설문 응답을 증상 코드로 변환"""

    def map_survey_to_symptoms(
        self,
        body_part_code: str,
        survey_responses: List[SurveyResponse],
    ) -> List[str]:
        """
        설문 응답을 증상 코드로 변환

        Args:
            body_part_code: 부위 코드
            survey_responses: 설문 응답 리스트

        Returns:
            증상 코드 리스트
        """
        loader = get_loader(body_part_code)
        symptoms = []

        for response in survey_responses:
            for option in response.selected_options:
                try:
                    codes = loader.get_symptom_codes_for_question(
                        response.question_id, option
                    )
                    symptoms.extend(codes)
                except ValueError:
                    # 알 수 없는 질문/옵션은 무시 (경고 로깅)
                    continue

        return list(set(symptoms))  # 중복 제거

    def enrich_user_input(self, user_input: UserInput) -> UserInput:
        """
        UserInput에 인구통계 기반 증상 코드 추가

        설문 응답에서 변환된 증상 코드에 연령/BMI 코드를 추가합니다.
        """
        demographics = user_input.demographics

        # 인구통계 기반 코드
        demo_codes = [
            demographics.age_code,
            demographics.bmi_code,
        ]

        # 각 부위에 인구통계 코드 추가
        enriched_body_parts = []
        for bp in user_input.body_parts:
            existing_symptoms = set(bp.symptoms)
            existing_symptoms.update(demo_codes)

            enriched_bp = BodyPartInput(
                code=bp.code,
                primary=bp.primary,
                symptoms=list(existing_symptoms),
                nrs=bp.nrs,
            )
            enriched_body_parts.append(enriched_bp)

        # 새 UserInput 생성
        return UserInput(
            demographics=user_input.demographics,
            physical_score=user_input.physical_score,
            body_parts=enriched_body_parts,
            survey_responses=user_input.survey_responses,
        )

    def get_symptom_description(
        self,
        body_part_code: str,
        symptom_code: str,
    ) -> str:
        """증상 코드에 대한 한글 설명 반환"""
        # 주요 증상 코드 설명 매핑
        descriptions = {
            # 연령
            "age_gte_60": "60세 이상",
            "age_gte_50": "50세 이상",
            "age_40s": "40대",
            "age_30s": "30대",
            "age_20s": "20대",
            "age_teens": "10대",
            # BMI
            "bmi_gte_30": "비만 (BMI 30+)",
            "bmi_gte_27": "과체중 (BMI 27+)",
            "bmi_gte_25": "과체중 (BMI 25+)",
            "bmi_normal": "정상 체중",
            # 통증 위치
            "pain_medial": "무릎 안쪽 통증",
            "pain_lateral": "무릎 바깥쪽 통증",
            "pain_anterior": "무릎 앞쪽 통증",
            "pain_bilateral": "양측 무릎 통증",
            # 악화 요인
            "stairs_down": "계단 내려갈 때 악화",
            "stairs_up": "계단 올라갈 때 악화",
            "squatting": "쪼그려 앉을 때 악화",
            "after_walking": "오래 걸은 후 악화",
            "after_exercise": "운동 후 악화",
            "weather_sensitive": "날씨에 민감",
            # 증상
            "swelling": "부종",
            "swelling_heat": "부종 + 열감",
            "stiffness_morning": "아침 뻣뻣함",
            "stiffness_30min_plus": "30분 이상 뻣뻣함",
            "locking": "무릎 잠김",
            "catching": "걸리는 느낌",
            "instability": "불안정감",
            "giving_way": "무릎 풀림",
            # 외상
            "trauma": "외상력",
            "trauma_recent": "최근 외상",
            "twisting": "비틀림 부상",
            "sudden_onset": "갑작스런 시작",
            # 경과
            "chronic": "만성 (3개월+)",
            "progressive": "점진적 악화",
            "overuse_pattern": "과사용 패턴",
        }

        return descriptions.get(symptom_code, symptom_code)
