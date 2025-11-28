"""LLM Pass #2 - 운동 추천 서비스"""

from typing import List, Optional, Dict, Any

from langsmith import traceable

from orthocare.config import settings
from orthocare.models import UserInput, PhysicalScore
from orthocare.models.diagnosis import DiagnosisResult
from orthocare.models.exercise import (
    Exercise,
    ExerciseRecommendation,
    ExcludedExercise,
    ExerciseSet,
)
from orthocare.data_ops.loaders.knee_loader import get_loader


class ExerciseRecommender:
    """
    LLM Pass #2: 운동 추천

    진단 결과, 신체 점수, NRS를 기반으로
    개인화된 운동 세트 추천
    """

    def __init__(self, llm_client=None):
        """
        Args:
            llm_client: LLM 클라이언트 (OpenAI 등)
        """
        self.llm_client = llm_client
        self.model = settings.openai_model

    @traceable(name="exercise_recommendation")
    def recommend(
        self,
        diagnosis: DiagnosisResult,
        user_input: UserInput,
    ) -> ExerciseSet:
        """
        운동 추천 생성

        Args:
            diagnosis: 진단 결과
            user_input: 사용자 입력

        Returns:
            ExerciseSet 객체
        """
        body_part_input = user_input.primary_body_part
        physical_score = user_input.physical_score

        # 후보 운동 필터링
        candidates, excluded = self._filter_exercises(
            body_part_code=body_part_input.code,
            bucket=diagnosis.final_bucket,
            physical_score=physical_score,
            nrs=body_part_input.nrs,
        )

        # LLM으로 최종 추천
        if self.llm_client is not None:
            recommendations, llm_reasoning = self._call_llm(
                candidates=candidates,
                diagnosis=diagnosis,
                user_input=user_input,
            )
        else:
            # LLM 없으면 상위 5~7개 선택
            recommendations = self._simple_recommend(candidates, physical_score)
            llm_reasoning = "LLM 없이 난이도/버킷 태그 기반 자동 선택"

        # 루틴 순서 결정
        routine_order = [r.exercise.exercise_id for r in recommendations]

        # 예상 소요 시간 계산
        total_duration = self._estimate_duration(recommendations)

        return ExerciseSet(
            body_part=body_part_input.code,
            diagnosis_bucket=diagnosis.final_bucket,
            recommendations=recommendations,
            excluded=excluded,
            common_safe=[],  # 복합 부위 시 사용
            routine_order=routine_order,
            total_duration_min=total_duration,
            llm_reasoning=llm_reasoning,
        )

    def _filter_exercises(
        self,
        body_part_code: str,
        bucket: str,
        physical_score: PhysicalScore,
        nrs: int,
    ) -> tuple:
        """
        운동 필터링

        Returns:
            (후보 운동 리스트, 제외된 운동 리스트)
        """
        loader = get_loader(body_part_code)
        allowed_difficulty = physical_score.allowed_difficulties

        # NRS 기반 난이도 제한
        if nrs > 7:
            allowed_difficulty = ["low"]
        elif nrs > 4:
            allowed_difficulty = [d for d in allowed_difficulty if d != "high"]

        # 후보 운동 조회
        all_exercises = loader.get_exercises_for_bucket(bucket, allowed_difficulty)

        candidates = []
        excluded = []

        for ex_data in all_exercises:
            exercise = Exercise(
                exercise_id=ex_data["id"],
                name_en=ex_data["name_en"],
                name_kr=ex_data["name_kr"],
                difficulty=ex_data["difficulty"],
                diagnosis_tags=ex_data["diagnosis_tags"],
                function_tags=ex_data["function_tags"],
                target_muscles=ex_data["target_muscles"],
                sets=ex_data["sets"],
                reps=ex_data["reps"],
                rest=ex_data["rest"],
                description=ex_data["description"],
                youtube=ex_data.get("youtube"),
            )
            candidates.append(exercise)

        # 난이도로 제외된 운동
        all_bucket_exercises = loader.get_exercises_for_bucket(bucket)
        for ex_data in all_bucket_exercises:
            if ex_data["difficulty"] not in allowed_difficulty:
                excluded.append(
                    ExcludedExercise(
                        exercise_id=ex_data["id"],
                        name_kr=ex_data["name_kr"],
                        reason=f"난이도 {ex_data['difficulty']}는 현재 신체 점수/통증 수준에 부적합",
                        exclusion_type="difficulty" if nrs <= 4 else "nrs",
                    )
                )

        return candidates, excluded

    def _simple_recommend(
        self,
        candidates: List[Exercise],
        physical_score: PhysicalScore,
    ) -> List[ExerciseRecommendation]:
        """LLM 없이 간단한 추천"""
        max_count = {
            "A": 7,
            "B": 6,
            "C": 5,
            "D": 4,
        }.get(physical_score.level, 5)

        # 난이도 순으로 정렬 (low -> medium -> high)
        difficulty_order = {"low": 0, "medium": 1, "high": 2}
        sorted_candidates = sorted(
            candidates, key=lambda x: difficulty_order.get(x.difficulty, 1)
        )

        recommendations = []
        for i, exercise in enumerate(sorted_candidates[:max_count]):
            recommendations.append(
                ExerciseRecommendation(
                    exercise=exercise,
                    reason=f"{exercise.name_kr}: {', '.join(exercise.function_tags)}",
                    priority=i + 1,
                    match_score=0.8 - (i * 0.05),
                )
            )

        return recommendations

    @traceable(run_type="llm", name="llm_exercise_selection")
    def _call_llm(
        self,
        candidates: List[Exercise],
        diagnosis: DiagnosisResult,
        user_input: UserInput,
    ) -> tuple:
        """LLM 호출하여 운동 추천"""
        prompt = self._build_prompt(candidates, diagnosis, user_input)

        response = self.llm_client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "당신은 재활 운동 전문가입니다. "
                        "환자의 상태에 맞는 최적의 운동 프로그램을 추천합니다. "
                        "반드시 JSON 형식으로 응답하세요."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.4,
        )

        import json

        result = json.loads(response.choices[0].message.content)

        # 추천 결과 파싱
        recommendations = []
        selected_ids = result.get("selected_exercises", [])

        for i, ex_id in enumerate(selected_ids):
            exercise = next((c for c in candidates if c.exercise_id == ex_id), None)
            if exercise:
                reason = result.get("reasons", {}).get(ex_id, "추천됨")
                recommendations.append(
                    ExerciseRecommendation(
                        exercise=exercise,
                        reason=reason,
                        priority=i + 1,
                        match_score=result.get("scores", {}).get(ex_id, 0.8),
                    )
                )

        # 전체 추론 구성
        full_reasoning = result.get("reasoning", "")

        # 조합 근거 추가
        combo = result.get("combination_rationale", {})
        if combo:
            full_reasoning += "\n\n### 운동 조합 근거:\n"
            if combo.get("why_together"):
                full_reasoning += f"- **시너지**: {combo['why_together']}\n"
            if combo.get("bucket_coverage"):
                full_reasoning += f"- **버킷 치료**: {combo['bucket_coverage']}\n"
            if combo.get("progression_logic"):
                full_reasoning += f"- **순서 논리**: {combo['progression_logic']}\n"

        # 환자 적합성 추가
        fit = result.get("patient_fit", {})
        if fit:
            full_reasoning += "\n\n### 환자 맞춤 고려사항:\n"
            if fit.get("physical_level_fit"):
                full_reasoning += f"- **신체 수준**: {fit['physical_level_fit']}\n"
            if fit.get("nrs_consideration"):
                full_reasoning += f"- **통증 고려**: {fit['nrs_consideration']}\n"
            if fit.get("precautions"):
                full_reasoning += f"- **주의사항**: {fit['precautions']}\n"

        return recommendations, full_reasoning

    def _build_prompt(
        self,
        candidates: List[Exercise],
        diagnosis: DiagnosisResult,
        user_input: UserInput,
    ) -> str:
        """LLM 프롬프트 구성"""
        demo = user_input.demographics
        physical = user_input.physical_score
        body_part = user_input.primary_body_part

        candidates_str = "\n".join(
            f"- {e.exercise_id}: {e.name_kr} "
            f"(난이도: {e.difficulty}, 기능: {', '.join(e.function_tags)})"
            for e in candidates
        )

        prompt = f"""
## 환자 정보
- 나이: {demo.age}세
- 성별: {demo.sex}
- BMI: {demo.bmi}
- 신체 점수: Lv {physical.level} ({physical.total_score}점)
- 통증 점수 (NRS): {body_part.nrs}/10

## 진단
- 버킷: {diagnosis.final_bucket}
- 신뢰도: {diagnosis.confidence:.0%}
- 근거: {diagnosis.evidence_summary}
- 진단 추론: {diagnosis.llm_reasoning}

## 후보 운동
{candidates_str}

## 요청
환자에게 적합한 운동 5~7개를 선택하고, 각 운동별 추천 이유를 작성하세요.
운동은 가동성 → 근력 → 균형 순으로 배치해주세요.

**중요**: 각 운동 추천에 대해 다음을 반드시 설명하세요:
1. **버킷 연관성**: 왜 {diagnosis.final_bucket} 버킷에 이 운동이 적합한지
2. **타겟 기능**: 이 운동이 어떤 기능(가동성/근력/균형)을 개선하는지
3. **신체 점수 적합성**: Lv {physical.level} 수준에 맞는 이유
4. **통증 고려**: NRS {body_part.nrs}점 환자에게 안전한 이유

**조합 근거**: 선택한 운동들이 왜 함께 시너지를 내는지 설명하세요.

다음 JSON 형식으로 응답하세요:
{{
    "selected_exercises": ["E01", "E02", ...],
    "reasons": {{
        "E01": "버킷 적합성 + 타겟 기능 + 신체/통증 고려 설명",
        "E02": "버킷 적합성 + 타겟 기능 + 신체/통증 고려 설명"
    }},
    "scores": {{
        "E01": 0.95,
        "E02": 0.90
    }},
    "combination_rationale": {{
        "why_together": "이 운동들이 함께 구성된 이유 (시너지)",
        "bucket_coverage": "{diagnosis.final_bucket} 버킷 치료에 이 조합이 최적인 이유",
        "progression_logic": "운동 순서가 이렇게 된 이유 (쉬운것→어려운것 등)"
    }},
    "patient_fit": {{
        "physical_level_fit": "신체 점수 Lv {physical.level}에 맞춘 이유",
        "nrs_consideration": "통증 NRS {body_part.nrs}점 고려 사항",
        "precautions": "주의사항 (있다면)"
    }},
    "reasoning": "전체 프로그램 구성 요약"
}}
"""
        return prompt

    def _estimate_duration(self, recommendations: List[ExerciseRecommendation]) -> int:
        """예상 소요 시간 계산 (분)"""
        total_seconds = 0

        for rec in recommendations:
            ex = rec.exercise
            # 세트 수 × (반복 시간 + 휴식 시간)
            reps_time = self._parse_reps_time(ex.reps)
            rest_time = self._parse_rest_time(ex.rest)
            total_seconds += ex.sets * (reps_time + rest_time)

        return max(10, total_seconds // 60)

    def _parse_reps_time(self, reps: str) -> int:
        """반복 횟수를 초 단위로 변환"""
        import re
        if "초" in reps:
            # "30초" or "30초(각 다리)" 등
            match = re.search(r"(\d+)", reps)
            return int(match.group(1)) if match else 30
        elif "회" in reps:
            # "20회" or "20회(각 다리)" 등, 1회당 3초 가정
            match = re.search(r"(\d+)", reps)
            count = int(match.group(1)) if match else 10
            return count * 3
        elif "보" in reps:
            match = re.search(r"(\d+)", reps)
            return int(match.group(1)) * 2 if match else 30
        return 30

    def _parse_rest_time(self, rest: str) -> int:
        """휴식 시간을 초 단위로 변환"""
        return int(rest.replace("초", "").strip())
