"""운동 추천 파이프라인

전체 흐름:
1. 사후 설문 처리 (AssessmentHandler)
2. 버킷 기반 필터링 (ExerciseFilter)
3. 개인화 조정 (PersonalizationService)
4. LLM 운동 추천 (ExerciseRecommender)
5. 최종 세트 구성
"""

from typing import Optional
from datetime import datetime

from langsmith import traceable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.models import PhysicalScore
from exercise_recommendation.models.input import ExerciseRecommendationInput
from exercise_recommendation.models.output import (
    ExerciseRecommendationOutput,
    RecommendedExercise,
)
from exercise_recommendation.services import (
    AssessmentHandler,
    ExerciseFilter,
    PersonalizationService,
    ExerciseRecommender,
)
from exercise_recommendation.config import settings


class ExerciseRecommendationPipeline:
    """운동 추천 파이프라인

    사용 예시:
        pipeline = ExerciseRecommendationPipeline()
        result = pipeline.run(input_data)
    """

    def __init__(self):
        self.assessment_handler = AssessmentHandler()
        self.exercise_filter = ExerciseFilter()
        self.personalization = PersonalizationService()
        self.recommender = ExerciseRecommender()

    @traceable(name="exercise_recommendation_pipeline")
    def run(self, input_data: ExerciseRecommendationInput) -> ExerciseRecommendationOutput:
        """
        운동 추천 실행

        Args:
            input_data: 운동 추천 입력

        Returns:
            ExerciseRecommendationOutput
        """
        # Step 1: 사후 설문 처리
        assessment_result = self.assessment_handler.process(
            previous_assessments=input_data.previous_assessments,
            last_assessment_date=input_data.last_assessment_date,
        )

        # Step 2: 버킷 기반 필터링 (v2.0: joint_status 추가)
        candidates, excluded = self.exercise_filter.filter_for_bucket(
            body_part=input_data.body_part,
            bucket=input_data.bucket,
            physical_score=input_data.physical_score,
            nrs=input_data.nrs,
            adjustments=assessment_result.adjustments,
            joint_status=input_data.joint_status,
        )

        # 조정 적용
        if assessment_result.adjustments:
            candidates = [
                self.exercise_filter.apply_adjustments(ex, assessment_result.adjustments)
                for ex in candidates
            ]

        # Step 3: 개인화 조정 (v2.0: joint_status 추가)
        personalized = self.personalization.apply(
            exercises=candidates,
            demographics=input_data.demographics,
            nrs=input_data.nrs,
            skipped_exercises=input_data.skipped_exercises,
            favorite_exercises=input_data.favorite_exercises,
            joint_status=input_data.joint_status,
        )

        # 운동 순서 결정
        ordered = self.personalization.get_exercise_order(personalized)

        # Step 4: LLM 운동 추천
        try:
            recommendations, llm_reasoning = self.recommender.recommend(
                candidates=ordered,
                user_input=input_data,
                adjustments=assessment_result.adjustments,
            )
        except Exception as e:
            # LLM 실패 시 간단 추천
            recommendations = self.recommender.simple_recommend(
                candidates=ordered,
                physical_level=input_data.physical_score.level,
            )
            llm_reasoning = f"LLM 없이 자동 추천 (오류: {str(e)})"

        # Step 5: 최종 세트 구성
        routine_order = [r.exercise_id for r in recommendations]
        total_duration = self._estimate_duration(recommendations)
        difficulty_level = self._determine_difficulty_level(recommendations)

        # 조정 정보
        adjustments_applied = {}
        if assessment_result.adjustments:
            adjustments_applied = {
                "difficulty_delta": assessment_result.adjustments.difficulty_delta,
                "sets_delta": assessment_result.adjustments.sets_delta,
                "reps_delta": assessment_result.adjustments.reps_delta,
            }

        return ExerciseRecommendationOutput(
            user_id=input_data.user_id,
            body_part=input_data.body_part,
            bucket=input_data.bucket,
            exercises=recommendations,
            excluded=excluded,
            routine_order=routine_order,
            total_duration_min=total_duration,
            difficulty_level=difficulty_level,
            adjustments_applied=adjustments_applied,
            assessment_status=assessment_result.status,
            assessment_message=assessment_result.message,
            llm_reasoning=llm_reasoning,
            recommended_at=datetime.utcnow(),
        )

    def _estimate_duration(self, recommendations: list) -> int:
        """예상 소요 시간 계산 (분)"""
        total_seconds = 0

        for rec in recommendations:
            # 세트 수 × (반복 시간 + 휴식 시간)
            reps_time = self._parse_reps_time(rec.reps)
            rest_time = self._parse_rest_time(rec.rest)
            total_seconds += rec.sets * (reps_time + rest_time)

        return max(10, total_seconds // 60)

    def _parse_reps_time(self, reps: str) -> int:
        """반복 횟수를 초 단위로 변환"""
        import re
        if "초" in reps:
            match = re.search(r"(\d+)", reps)
            return int(match.group(1)) if match else 30
        elif "회" in reps:
            match = re.search(r"(\d+)", reps)
            count = int(match.group(1)) if match else 10
            return count * 3  # 1회당 3초
        return 30

    def _parse_rest_time(self, rest: str) -> int:
        """휴식 시간을 초 단위로 변환"""
        import re
        match = re.search(r"(\d+)", rest)
        return int(match.group(1)) if match else 30

    def _determine_difficulty_level(self, recommendations: list) -> str:
        """전체 난이도 결정"""
        if not recommendations:
            return "medium"

        difficulties = [r.difficulty for r in recommendations]
        unique = set(difficulties)

        if len(unique) == 1:
            return difficulties[0]
        elif "high" in unique and "low" in unique:
            return "mixed"
        elif "high" in unique:
            return "high"
        elif "low" in unique and "medium" not in unique:
            return "low"
        else:
            return "medium"
