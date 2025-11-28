"""파이프라인 실행 예제"""

import json
from orthocare.pipelines import MainPipeline
from orthocare.services.output import SummaryGenerator


def main():
    # 예제 입력 데이터
    input_data = {
        "demographics": {
            "age": 55,
            "sex": "female",
            "height_cm": 160,
            "weight_kg": 65,
        },
        "physical_score": {
            "total_score": 10,  # Lv B
        },
        "body_parts": [
            {
                "code": "knee",
                "primary": True,
                "symptoms": [
                    "pain_medial",
                    "stairs_down",
                    "stiffness_morning",
                    "weather_sensitive",
                    "chronic",
                ],
                "nrs": 5,
            }
        ],
    }

    # 파이프라인 실행 (LLM/벡터DB 없이 테스트)
    pipeline = MainPipeline(llm_client=None, vector_store=None)
    result = pipeline.run(input_data)

    # 결과 출력
    print("=" * 60)
    print("파이프라인 실행 결과")
    print("=" * 60)

    if result.blocked_by_red_flag:
        print("⚠️ 레드플래그 발동 - 운동 추천 차단")
        return

    # 진단 결과
    for body_part, diagnosis in result.diagnoses.items():
        print(f"\n[{body_part}] 진단 결과:")
        print(f"  - 최종 버킷: {diagnosis.final_bucket}")
        print(f"  - 신뢰도: {diagnosis.confidence:.0%}")
        print(f"  - 근거: {diagnosis.evidence_summary}")

        print("  - 버킷 점수:")
        for bs in diagnosis.bucket_scores:
            print(f"    - {bs.bucket}: {bs.score}점 ({bs.percentage}%)")

    # 운동 추천
    for body_part, exercise_set in result.exercise_sets.items():
        print(f"\n[{body_part}] 운동 추천 ({exercise_set.exercise_count}개):")
        for rec in exercise_set.recommendations:
            ex = rec.exercise
            print(f"  - {ex.name_kr} ({ex.difficulty}): {rec.reason}")

    # 환자용 요약
    print("\n" + "=" * 60)
    print("환자용 요약")
    print("=" * 60)

    summary_gen = SummaryGenerator()
    summary = summary_gen.generate_patient_summary(
        result.user_input,
        result.diagnoses,
        result.exercise_sets,
    )
    print(summary)

    # 리뷰 요청 데이터
    print("\n" + "=" * 60)
    print("전문가 리뷰 요청 (JSON)")
    print("=" * 60)

    review_request = summary_gen.generate_review_request(
        result.user_input,
        result.diagnoses,
        result.exercise_sets,
    )
    print(json.dumps(review_request, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
