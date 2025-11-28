"""무릎 데이터 로더"""

from typing import Dict, List, Any, Optional
from .base_loader import BaseLoader


class KneeLoader(BaseLoader):
    """무릎 전용 데이터 로더"""

    def __init__(self):
        super().__init__("knee")

    def get_weight_vector(self, symptom_code: str) -> List[float]:
        """
        증상 코드에 대한 가중치 벡터 반환

        Returns:
            [OA, OVR, TRM, INF] 순서의 가중치 리스트
        """
        if symptom_code not in self.weights:
            raise ValueError(
                f"알 수 없는 증상 코드: {symptom_code}"
            )
        return self.weights[symptom_code]

    def get_exercises_for_bucket(
        self,
        bucket: str,
        difficulty: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        버킷에 적합한 운동 목록 반환

        Args:
            bucket: 버킷 코드 (OA, OVR, TRM, INF)
            difficulty: 허용 난이도 리스트 (없으면 전체)

        Returns:
            운동 정보 딕셔너리 리스트
        """
        results = []
        for ex_id, ex_data in self.exercises.items():
            # 버킷 태그 확인
            if bucket not in ex_data.get("diagnosis_tags", []):
                continue
            # 난이도 필터
            if difficulty and ex_data.get("difficulty") not in difficulty:
                continue

            results.append({"id": ex_id, **ex_data})

        return results

    def get_immediate_red_flags(self) -> List[Dict[str, Any]]:
        """즉시 의뢰 필요 레드플래그 목록"""
        return self.red_flags.get("immediate_referral", [])

    def get_red_flag_survey_mapping(self) -> Dict[str, str]:
        """설문 → 레드플래그 코드 매핑"""
        return self.red_flags.get("survey_mapping", {})

    def get_symptom_codes_for_question(
        self,
        question_id: str,
        selected_option: str,
    ) -> List[str]:
        """
        설문 응답 → 증상 코드 변환

        Args:
            question_id: 질문 ID (Q1_location, Q2_onset 등)
            selected_option: 선택된 옵션

        Returns:
            증상 코드 리스트
        """
        if question_id not in self.survey_mapping:
            raise ValueError(f"알 수 없는 질문 ID: {question_id}")

        question = self.survey_mapping[question_id]
        options = question.get("options", {})

        if selected_option not in options:
            raise ValueError(
                f"알 수 없는 옵션: {selected_option} (질문: {question_id})"
            )

        option_data = options[selected_option]
        return option_data.get("symptom_codes", [])

    def get_age_based_rules(self, age: int) -> Dict[str, Any]:
        """연령대별 진단 규칙"""
        rules = self.clinical_rules.get("age_based_rules", {})

        if age < 30:
            return rules.get("under_30", {})
        elif age < 50:
            return rules.get("30_to_50", {})
        elif age < 60:
            return rules.get("over_50", {})
        else:
            return rules.get("over_60", {})

    def get_typical_case(self, bucket: str) -> Optional[Dict[str, Any]]:
        """버킷별 전형적 케이스"""
        cases = self.clinical_rules.get("typical_cases", {})
        case_key_map = {
            "OA": "OA_classic",
            "OVR": "OVR_runner",
            "TRM": "TRM_acute",
            "INF": "RA_suspect",  # INF는 RA_suspect 참조
        }
        return cases.get(case_key_map.get(bucket, ""))


def get_loader(body_part: str) -> BaseLoader:
    """부위별 로더 팩토리"""
    loaders = {
        "knee": KneeLoader,
    }

    if body_part not in loaders:
        raise ValueError(
            f"지원하지 않는 부위: {body_part}. 가능한 값: {list(loaders.keys())}"
        )

    return loaders[body_part]()
