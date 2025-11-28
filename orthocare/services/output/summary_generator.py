"""출력 요약 생성 서비스"""

from typing import Dict

from orthocare.models import UserInput
from orthocare.models.diagnosis import DiagnosisResult
from orthocare.models.exercise import ExerciseSet


class SummaryGenerator:
    """환자용 요약 및 리뷰 요청 생성"""

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
