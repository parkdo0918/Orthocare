"""레드플래그 체크 서비스"""

from typing import List, Dict, Any, Optional

from orthocare.models import UserInput, BodyPartInput
from orthocare.models.diagnosis import RedFlagResult
from orthocare.data_ops.loaders.knee_loader import get_loader


class RedFlagChecker:
    """레드플래그 검사"""

    def check(self, user_input: UserInput) -> Dict[str, RedFlagResult]:
        """
        모든 부위에 대해 레드플래그 검사

        Args:
            user_input: 사용자 입력

        Returns:
            부위별 RedFlagResult 딕셔너리
        """
        results = {}

        for body_part in user_input.body_parts:
            result = self._check_body_part(body_part, user_input)
            results[body_part.code] = result

        return results

    def _check_body_part(
        self,
        body_part: BodyPartInput,
        user_input: UserInput,
    ) -> RedFlagResult:
        """개별 부위 레드플래그 검사"""
        loader = get_loader(body_part.code)
        immediate_flags = loader.get_immediate_red_flags()
        survey_mapping = loader.get_red_flag_survey_mapping()

        triggered_flags = []
        messages = []

        # 증상 코드 기반 검사
        symptoms = set(body_part.symptoms)

        for flag in immediate_flags:
            flag_code = flag["code"]

            # 직접 매칭
            if flag_code in symptoms:
                triggered_flags.append(flag_code)
                messages.append(f"⚠️ {flag['label_kr']}: {flag['action']}")
                continue

            # 복합 조건 검사
            if self._check_compound_condition(flag_code, symptoms, user_input):
                triggered_flags.append(flag_code)
                messages.append(f"⚠️ {flag['label_kr']}: {flag['action']}")

        # 결과 생성
        if triggered_flags:
            severity = self._get_highest_severity(triggered_flags, immediate_flags)
            action = self._get_recommended_action(severity)

            return RedFlagResult(
                triggered=True,
                flags=triggered_flags,
                messages=messages,
                action=action,
            )

        return RedFlagResult(triggered=False)

    def _check_compound_condition(
        self,
        flag_code: str,
        symptoms: set,
        user_input: UserInput,
    ) -> bool:
        """복합 조건 검사"""
        # 발열 + 관절통
        if flag_code == "fever_with_joint_pain":
            return "fever" in symptoms or "systemic_symptoms" in symptoms

        # 심한 열감 + 부종
        if flag_code == "severe_hot_swelling":
            return "swelling_heat" in symptoms and "redness" in symptoms

        # 종아리 통증 (DVT 의심)
        if flag_code == "calf_pain_swelling":
            return "calf_pain" in symptoms

        return False

    def _get_highest_severity(
        self,
        triggered_flags: List[str],
        all_flags: List[Dict[str, Any]],
    ) -> str:
        """가장 높은 심각도 반환"""
        severity_order = {"emergency": 0, "urgent": 1, "warning": 2}

        min_severity = "warning"
        min_order = severity_order.get(min_severity, 2)

        for flag in all_flags:
            if flag["code"] in triggered_flags:
                flag_severity = flag.get("severity", "warning")
                flag_order = severity_order.get(flag_severity, 2)
                if flag_order < min_order:
                    min_severity = flag_severity
                    min_order = flag_order

        return min_severity

    def _get_recommended_action(self, severity: str) -> str:
        """심각도별 권장 조치"""
        actions = {
            "emergency": "즉시 응급실 방문을 권장합니다. 운동 추천이 제한됩니다.",
            "urgent": "가능한 빨리 정형외과 진료를 받으세요. 운동 추천이 제한됩니다.",
            "warning": "증상이 지속되면 전문의 상담을 권장합니다.",
        }
        return actions.get(severity, actions["warning"])

    def should_block_exercise(self, red_flag_results: Dict[str, RedFlagResult]) -> bool:
        """운동 추천 차단 여부"""
        for result in red_flag_results.values():
            if result.triggered:
                # emergency 또는 urgent면 차단
                if result.action and ("응급" in result.action or "정형외과" in result.action):
                    return True
        return False
