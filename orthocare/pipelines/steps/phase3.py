"""Phase 3: 운동 추천 스텝

Step 3.1: 버킷 기반 운동 필터링
Step 3.2: 개인화 조정
Step 3.3: LLM 운동 추천
Step 3.4: 최종 세트 구성
"""

from typing import Dict, Any, List, Optional

from langsmith import traceable

from .base import PipelineStep, StepResult, StepContext, StepStatus


class ExerciseFilterStep(PipelineStep):
    """
    Step 3.1: 버킷 기반 운동 필터링

    - 진단 버킷에 맞는 운동 필터링
    - 기능별 운동 분류
    - 초기 후보 목록 생성
    """

    name = "step_3_1_exercise_filter"
    description = "버킷 기반 운동 필터링"

    def __init__(self, data_loader=None):
        super().__init__()
        self.data_loader = data_loader

    def should_skip(self, context: StepContext) -> bool:
        return not context.validation_passed or context.blocked_by_red_flag

    @traceable(name="step_3_1_exercise_filter")
    def execute(self, context: StepContext) -> StepResult:
        """운동 필터링 실행"""
        filtered = {}

        for bp_code, diagnosis in context.diagnoses.items():
            context.current_body_part = bp_code

            # DiagnosisResult 객체 또는 딕셔너리 모두 처리
            if hasattr(diagnosis, 'final_bucket'):
                bucket = diagnosis.final_bucket
            elif isinstance(diagnosis, dict):
                bucket = diagnosis.get("bucket", "OA")
            else:
                bucket = "OA"

            try:
                # 데이터 로더로 운동 로드
                if self.data_loader:
                    exercises = self.data_loader.get_exercises_for_bucket(bucket)
                else:
                    # 기본 로더 사용
                    from orthocare.data_ops.loaders import KneeLoader
                    if bp_code == "knee":
                        loader = KneeLoader()
                        exercises = loader.get_exercises_for_bucket(bucket)
                    else:
                        exercises = []

                # 운동 정보 구조화
                filtered[bp_code] = {
                    "bucket": bucket,
                    "exercises": exercises,
                    "count": len(exercises),
                    "by_function": self._group_by_function(exercises),
                }

            except Exception as e:
                filtered[bp_code] = {
                    "bucket": bucket,
                    "exercises": [],
                    "count": 0,
                    "error": str(e),
                }

        context.filtered_exercises = filtered

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output={
                "body_parts": list(filtered.keys()),
                "exercise_counts": {
                    bp: data["count"]
                    for bp, data in filtered.items()
                },
                "buckets": {
                    bp: data["bucket"]
                    for bp, data in filtered.items()
                },
            },
            metadata={
                "total_exercises": sum(
                    data["count"] for data in filtered.values()
                ),
            },
        )

    def _group_by_function(self, exercises: List[Dict]) -> Dict[str, List]:
        """기능별 그룹화"""
        groups = {}
        for ex in exercises:
            for func in ex.get("function_tags", []):
                if func not in groups:
                    groups[func] = []
                groups[func].append(ex.get("name_kr", ex.get("name_en", "")))
        return groups


class PersonalizationStep(PipelineStep):
    """
    Step 3.2: 개인화 조정

    - 연령대별 난이도 조정
    - 활동 수준 고려
    - 통증 강도 반영
    """

    name = "step_3_2_personalization"
    description = "개인 맞춤 운동 조정"

    def should_skip(self, context: StepContext) -> bool:
        return not context.validation_passed or context.blocked_by_red_flag

    @traceable(name="step_3_2_personalization")
    def execute(self, context: StepContext) -> StepResult:
        """개인화 실행"""
        user_input = context.user_input
        demo = user_input.demographics
        personalized = {}

        for bp_code, data in context.filtered_exercises.items():
            body_part = next(
                (bp for bp in user_input.body_parts if bp.code == bp_code),
                None,
            )

            if not body_part:
                personalized[bp_code] = data
                continue

            exercises = data.get("exercises", [])

            # 개인화 필터/조정
            adjusted = self._apply_personalization(
                exercises=exercises,
                age=demo.age,
                nrs=body_part.nrs,
                activity_level=getattr(demo, 'activity_level', None),
            )

            personalized[bp_code] = {
                **data,
                "exercises": adjusted["exercises"],
                "adjustments": adjusted["adjustments"],
            }

        context.personalized_exercises = personalized

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output={
                "body_parts": list(personalized.keys()),
                "adjustments": {
                    bp: data.get("adjustments", {})
                    for bp, data in personalized.items()
                },
            },
            metadata={
                "age": demo.age,
                "applied_rules": [
                    bp_data.get("adjustments", {}).get("rule", "none")
                    for bp_data in personalized.values()
                ],
            },
        )

    def _apply_personalization(
        self,
        exercises: List[Dict],
        age: int,
        nrs: int,
        activity_level: Optional[str] = None,
    ) -> Dict:
        """개인화 규칙 적용"""
        adjustments = {}

        # 1. 연령 기반 난이도 필터
        if age >= 65:
            # 고령자: low/medium 난이도만
            exercises = [
                e for e in exercises
                if e.get("difficulty", "medium") in ["low", "medium"]
            ]
            adjustments["age_filter"] = "elderly_safe"
        elif age < 30:
            # 젊은층: 제한 없음
            adjustments["age_filter"] = "none"
        else:
            # 중년: medium 우선
            adjustments["age_filter"] = "moderate"

        # 2. 통증 강도 기반 조정
        if nrs >= 7:
            # 심한 통증: low 난이도만, 세트 수 감소
            exercises = [
                e for e in exercises
                if e.get("difficulty", "medium") == "low"
            ]
            adjustments["pain_adjustment"] = "reduced_intensity"
        elif nrs >= 4:
            # 중등도 통증: high 제외
            exercises = [
                e for e in exercises
                if e.get("difficulty", "medium") != "high"
            ]
            adjustments["pain_adjustment"] = "moderate_intensity"
        else:
            adjustments["pain_adjustment"] = "full_intensity"

        return {
            "exercises": exercises,
            "adjustments": adjustments,
        }


class ExerciseRecommendationStep(PipelineStep):
    """
    Step 3.3: LLM 운동 추천 (LLM Pass #2)

    - 최종 운동 선택
    - 추천 이유 생성
    - 주의사항 추가
    """

    name = "step_3_3_exercise_recommendation"
    description = "LLM 기반 최종 운동 추천"

    def __init__(self, exercise_recommender=None):
        super().__init__()
        self.exercise_recommender = exercise_recommender

    def should_skip(self, context: StepContext) -> bool:
        return not context.validation_passed or context.blocked_by_red_flag

    @traceable(name="step_3_3_exercise_recommendation")
    def execute(self, context: StepContext) -> StepResult:
        """운동 추천 실행"""
        from orthocare.services.exercise import ExerciseRecommender

        recommender = self.exercise_recommender
        user_input = context.user_input
        recommendations = {}

        for bp_code, data in context.personalized_exercises.items():
            diagnosis = context.diagnoses.get(bp_code)
            context.current_body_part = bp_code

            try:
                if recommender and diagnosis:
                    # LLM 추천 실행 (ExerciseRecommender는 diagnosis, user_input만 받음)
                    rec = recommender.recommend(
                        diagnosis=diagnosis,
                        user_input=user_input,
                    )
                    recommendations[bp_code] = rec
                else:
                    # LLM 없거나 진단 없으면 상위 8개 선택
                    exercises = data.get("exercises", [])[:8]
                    recommendations[bp_code] = {
                        "exercises": exercises,
                        "reasoning": "Selected top exercises without LLM",
                    }

            except Exception as e:
                recommendations[bp_code] = {
                    "exercises": data.get("exercises", [])[:8],
                    "error": str(e),
                }

        context.recommended_exercises = recommendations

        # 결과 추출 헬퍼
        def get_exercise_count(rec):
            if hasattr(rec, 'recommendations'):
                return len(rec.recommendations)
            elif hasattr(rec, 'exercises'):
                return len(rec.exercises)
            elif isinstance(rec, dict):
                return len(rec.get("exercises", []))
            return 0

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output={
                "body_parts": list(recommendations.keys()),
                "recommendation_counts": {
                    bp: get_exercise_count(rec)
                    for bp, rec in recommendations.items()
                },
            },
            metadata={
                "llm_used": recommender is not None,
            },
        )


class ExerciseSetAssemblyStep(PipelineStep):
    """
    Step 3.4: 최종 운동 세트 구성

    - 운동 순서 결정
    - 세트/반복 확정
    - 총 운동 시간 계산
    """

    name = "step_3_4_exercise_set_assembly"
    description = "최종 운동 세트 구성"

    def should_skip(self, context: StepContext) -> bool:
        return not context.validation_passed or context.blocked_by_red_flag

    @traceable(name="step_3_4_exercise_set_assembly")
    def execute(self, context: StepContext) -> StepResult:
        """세트 구성 실행"""
        exercise_sets = {}

        for bp_code, rec in context.recommended_exercises.items():
            # ExerciseSet 객체가 있으면 그대로 사용 (reason, llm_reasoning 보존)
            if hasattr(rec, 'recommendations') and hasattr(rec, 'llm_reasoning'):
                # ExerciseSet 객체를 그대로 저장
                exercise_sets[bp_code] = rec
            else:
                # 딕셔너리인 경우 기존 로직
                if hasattr(rec, 'recommendations'):
                    exercises = [r.exercise.__dict__ if hasattr(r, 'exercise') else r for r in rec.recommendations]
                elif hasattr(rec, 'exercises'):
                    exercises = rec.exercises
                elif isinstance(rec, dict):
                    exercises = rec.get("exercises", [])
                else:
                    exercises = []

                # 운동 순서 정렬 (난이도순)
                sorted_exercises = self._sort_exercises(exercises)

                # 총 시간 계산
                total_time = self._calculate_total_time(sorted_exercises)

                # 진단 버킷 추출
                diagnosis = context.diagnoses.get(bp_code)
                if hasattr(diagnosis, 'final_bucket'):
                    diagnosis_bucket = diagnosis.final_bucket
                elif isinstance(diagnosis, dict):
                    diagnosis_bucket = diagnosis.get("bucket", "")
                else:
                    diagnosis_bucket = ""

                # 세트 구성
                exercise_set = {
                    "body_part": bp_code,
                    "diagnosis_bucket": diagnosis_bucket,
                    "exercises": sorted_exercises,
                    "exercise_count": len(sorted_exercises),
                    "total_time_minutes": total_time,
                    "warm_up": self._get_warm_up(sorted_exercises),
                    "cool_down": self._get_cool_down(sorted_exercises),
                }

                exercise_sets[bp_code] = exercise_set

        context.exercise_sets = exercise_sets

        # 헬퍼 함수: ExerciseSet 또는 dict에서 값 추출
        def get_count(es):
            if hasattr(es, 'recommendations'):
                return len(es.recommendations)
            return es.get("exercise_count", 0)

        def get_time(es):
            if hasattr(es, 'total_duration_min'):
                return es.total_duration_min
            return es.get("total_time_minutes", 0)

        def get_bucket(es):
            if hasattr(es, 'diagnosis_bucket'):
                return es.diagnosis_bucket
            return es.get("diagnosis_bucket", "")

        return StepResult(
            step_name=self.name,
            status=StepStatus.COMPLETED,
            output={
                "body_parts": list(exercise_sets.keys()),
                "exercise_sets": {
                    bp: {
                        "count": get_count(es),
                        "total_time": get_time(es),
                        "bucket": get_bucket(es),
                    }
                    for bp, es in exercise_sets.items()
                },
            },
            metadata={
                "total_exercises": sum(
                    get_count(es) for es in exercise_sets.values()
                ),
                "total_time_all": sum(
                    get_time(es) for es in exercise_sets.values()
                ),
            },
        )

    def _sort_exercises(self, exercises: List[Dict]) -> List[Dict]:
        """난이도순 정렬 (low → medium → high)"""
        difficulty_order = {"low": 0, "medium": 1, "high": 2}
        return sorted(
            exercises,
            key=lambda x: difficulty_order.get(x.get("difficulty", "medium"), 1),
        )

    def _calculate_total_time(self, exercises: List[Dict]) -> int:
        """총 운동 시간 계산 (분)"""
        total_seconds = 0

        for ex in exercises:
            sets = ex.get("sets", 2)
            reps = ex.get("reps", "10회")
            rest = ex.get("rest", "30초")

            # 반복 시간 추정 (1회 = 3초)
            rep_count = self._parse_number(reps, 10)
            set_time = rep_count * 3  # 초

            # 휴식 시간
            rest_seconds = self._parse_number(rest, 30)

            # 운동당 총 시간
            exercise_time = sets * (set_time + rest_seconds)
            total_seconds += exercise_time

        return round(total_seconds / 60)

    def _parse_number(self, text: str, default: int) -> int:
        """숫자 추출"""
        import re
        match = re.search(r"(\d+)", str(text))
        return int(match.group(1)) if match else default

    def _get_warm_up(self, exercises: List[Dict]) -> List[str]:
        """워밍업 운동 추출"""
        return [
            ex.get("name_kr", ex.get("name_en", ""))
            for ex in exercises[:2]
            if ex.get("difficulty") == "low"
        ]

    def _get_cool_down(self, exercises: List[Dict]) -> List[str]:
        """쿨다운 운동 추출"""
        low_exercises = [ex for ex in exercises if ex.get("difficulty") == "low"]
        return [
            ex.get("name_kr", ex.get("name_en", ""))
            for ex in low_exercises[-2:]
        ] if len(low_exercises) >= 2 else []
