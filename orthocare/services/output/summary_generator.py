"""출력 요약 생성 서비스"""

from typing import Dict, List, Optional

from orthocare.models import UserInput
from orthocare.models.diagnosis import DiagnosisResult
from orthocare.models.exercise import ExerciseSet


# 부위별 친근한 메시지 (버킷 미노출)
FRIENDLY_MESSAGES = {
    "knee": {
        "intro": "무릎 상태를 분석한 결과, 맞춤 운동을 추천해드려요.",
        "exercise_intro": "현재 상태에 도움이 되는 운동들이에요",
    },
    "shoulder": {
        "intro": "어깨 상태를 분석한 결과, 맞춤 운동을 추천해드려요.",
        "exercise_intro": "현재 상태에 도움이 되는 운동들이에요",
    },
    "default": {
        "intro": "상태를 분석한 결과, 맞춤 운동을 추천해드려요.",
        "exercise_intro": "현재 상태에 도움이 되는 운동들이에요",
    },
}


class SummaryGenerator:
    """환자용 요약 및 리뷰 요청 생성"""

    def generate_app_output(
        self,
        user_input: UserInput,
        diagnoses: Dict[str, DiagnosisResult],
        exercise_sets: Dict[str, ExerciseSet],
    ) -> Dict:
        """
        앱용 출력 생성 (Phase 3-4)

        - 질환 버킷 미노출 (OA, TRM 등 명시 안함)
        - 친근한 메시지 + 운동 테이블
        """
        demo = user_input.demographics
        physical = user_input.physical_score

        output = {
            "user_summary": {
                "age": demo.age,
                "physical_level": physical.level,
            },
            "body_parts": [],
        }

        for bp_code, exercise_set in exercise_sets.items():
            diagnosis = diagnoses.get(bp_code)
            messages = FRIENDLY_MESSAGES.get(bp_code, FRIENDLY_MESSAGES["default"])

            # 레드플래그 체크
            red_flag_triggered = False
            red_flag_messages = []
            if diagnosis and diagnosis.red_flag and diagnosis.red_flag.triggered:
                red_flag_triggered = True
                red_flag_messages = diagnosis.red_flag.messages

            # 운동 테이블 구성
            exercise_table = self._build_exercise_table(exercise_set)

            body_part_output = {
                "code": bp_code,
                "name": {"knee": "무릎", "shoulder": "어깨"}.get(bp_code, bp_code),
                "intro_message": messages["intro"],
                "exercise_intro": messages["exercise_intro"],
                "exercises": exercise_table,
                "total_duration_min": self._get_duration(exercise_set),
                "red_flag": {
                    "triggered": red_flag_triggered,
                    "messages": red_flag_messages,
                } if red_flag_triggered else None,
            }

            output["body_parts"].append(body_part_output)

        return output

    def _build_exercise_table(self, exercise_set) -> List[Dict]:
        """운동 테이블 생성"""
        exercises = []

        # ExerciseSet 객체 또는 dict 처리
        if hasattr(exercise_set, 'recommendations'):
            for rec in exercise_set.recommendations:
                ex = rec.exercise
                exercises.append({
                    "name": ex.name_kr,
                    "difficulty": self._difficulty_to_korean(ex.difficulty),
                    "sets": ex.sets,
                    "reps": ex.reps,
                    "rest": ex.rest,
                    "reason": rec.reason,
                    "youtube": ex.youtube,
                })
        elif isinstance(exercise_set, dict):
            for ex in exercise_set.get("exercises", []):
                exercises.append({
                    "name": ex.get("name_kr", ex.get("name_en", "")),
                    "difficulty": self._difficulty_to_korean(ex.get("difficulty", "medium")),
                    "sets": ex.get("sets", 2),
                    "reps": ex.get("reps", "10회"),
                    "rest": ex.get("rest", "30초"),
                    "reason": ex.get("reason", ""),
                    "youtube": ex.get("youtube"),
                })

        return exercises

    def _difficulty_to_korean(self, difficulty: str) -> str:
        """난이도 한글 변환"""
        return {
            "low": "쉬움",
            "medium": "보통",
            "high": "어려움",
        }.get(difficulty, "보통")

    def _get_duration(self, exercise_set) -> int:
        """총 운동 시간 추출"""
        if hasattr(exercise_set, 'total_duration_min'):
            return exercise_set.total_duration_min
        elif isinstance(exercise_set, dict):
            return exercise_set.get("total_time_minutes", 0)
        return 0

    def generate_app_markdown(
        self,
        user_input: UserInput,
        diagnoses: Dict[str, DiagnosisResult],
        exercise_sets: Dict[str, ExerciseSet],
    ) -> str:
        """
        앱용 마크다운 출력 (Phase 3-4)

        - 질환 버킷 미노출
        - 친근한 메시지 + 운동 테이블
        """
        app_data = self.generate_app_output(user_input, diagnoses, exercise_sets)

        lines = []

        for bp in app_data["body_parts"]:
            # 레드플래그 경고
            if bp.get("red_flag") and bp["red_flag"]["triggered"]:
                lines.append("⚠️ **주의가 필요해요**")
                for msg in bp["red_flag"]["messages"]:
                    lines.append(f"> {msg}")
                lines.append("")
                continue

            # 친근한 인트로
            lines.append(f"### {bp['name']}")
            lines.append("")
            lines.append(bp["intro_message"])
            lines.append("")

            # 운동 추천 메시지
            lines.append(f"**{bp['exercise_intro']}** (총 {bp['total_duration_min']}분)")
            lines.append("")

            # 운동 테이블
            lines.append("| 운동 | 난이도 | 세트 | 반복 | 휴식 |")
            lines.append("|------|--------|------|------|------|")

            for ex in bp["exercises"]:
                name = ex["name"]
                if ex.get("youtube"):
                    name = f"[{ex['name']}]({ex['youtube']})"
                lines.append(
                    f"| {name} | {ex['difficulty']} | {ex['sets']} | {ex['reps']} | {ex['rest']} |"
                )

            lines.append("")

        return "\n".join(lines)

    def generate_patient_summary(
        self,
        user_input: UserInput,
        diagnoses: Dict[str, DiagnosisResult],
        exercise_sets: Dict[str, ExerciseSet],
    ) -> str:
        """환자용 요약 생성"""
        demo = user_input.demographics
        physical = user_input.physical_score

        summary_parts = [
            "## 건강 분석 결과",
            "",
            f"**환자 정보**: {demo.age}세 {'남성' if demo.sex == 'male' else '여성'}, BMI {demo.bmi}",
            f"**신체 점수**: Lv {physical.level}",
            "",
        ]

        # 부위별 진단 결과
        for body_part_code, diagnosis in diagnoses.items():
            body_part_kr = {"knee": "무릎", "shoulder": "어깨"}.get(body_part_code, body_part_code)

            summary_parts.append(f"### {body_part_kr} 분석")
            summary_parts.append("")
            summary_parts.append(f"**주요 소견**: {diagnosis.evidence_summary}")
            summary_parts.append(f"**신뢰도**: {diagnosis.confidence:.0%}")
            summary_parts.append("")

            # 경고 메시지
            if diagnosis.red_flag and diagnosis.red_flag.triggered:
                for msg in diagnosis.red_flag.messages:
                    summary_parts.append(f"> {msg}")
                summary_parts.append("")

        # 운동 추천
        summary_parts.append("### 추천 운동")
        summary_parts.append("")

        for body_part_code, exercise_set in exercise_sets.items():
            summary_parts.append(f"**예상 소요 시간**: {exercise_set.total_duration_min}분")
            summary_parts.append("")

            for rec in exercise_set.recommendations:
                ex = rec.exercise
                summary_parts.append(
                    f"- **{ex.name_kr}** ({ex.difficulty}): {rec.reason}"
                )
                if ex.youtube:
                    summary_parts.append(f"  - 영상: {ex.youtube}")

            summary_parts.append("")

        return "\n".join(summary_parts)

    def generate_review_request(
        self,
        user_input: UserInput,
        diagnoses: Dict[str, DiagnosisResult],
        exercise_sets: Dict[str, ExerciseSet],
    ) -> dict:
        """전문가 리뷰 요청 데이터 생성"""
        demo = user_input.demographics

        sections = []

        # 진단 섹션 (의사 리뷰)
        for body_part_code, diagnosis in diagnoses.items():
            sections.append({
                "section": "diagnosis",
                "body_part": body_part_code,
                "content": {
                    "bucket_scores": [
                        {
                            "bucket": bs.bucket,
                            "score": bs.score,
                            "percentage": bs.percentage,
                        }
                        for bs in diagnosis.bucket_scores
                    ],
                    "final_bucket": diagnosis.final_bucket,
                    "confidence": diagnosis.confidence,
                    "evidence_summary": diagnosis.evidence_summary,
                    "discrepancy": diagnosis.discrepancy.message if diagnosis.discrepancy else None,
                },
                "assigned_role": "doctor",
                "status": "pending",
            })

        # 운동 섹션 (트레이너 리뷰)
        for body_part_code, exercise_set in exercise_sets.items():
            sections.append({
                "section": "exercise_recommendation",
                "body_part": body_part_code,
                "content": {
                    "bucket": exercise_set.diagnosis_bucket,
                    "recommendations": [
                        {
                            "exercise_id": rec.exercise.exercise_id,
                            "name_kr": rec.exercise.name_kr,
                            "difficulty": rec.exercise.difficulty,
                            "reason": rec.reason,
                        }
                        for rec in exercise_set.recommendations
                    ],
                    "excluded": [
                        {
                            "exercise_id": ex.exercise_id,
                            "name_kr": ex.name_kr,
                            "reason": ex.reason,
                        }
                        for ex in exercise_set.excluded
                    ],
                },
                "assigned_role": "trainer",
                "status": "pending",
            })

        return {
            "patient_info": {
                "age": demo.age,
                "sex": demo.sex,
                "bmi": demo.bmi,
                "physical_level": user_input.physical_score.level,
            },
            "sections": sections,
            "status": "pending",
        }
