"""세분화된 파이프라인

각 스텝을 개별적으로 추적/관찰 가능한 파이프라인
"""

from dataclasses import dataclass
from typing import Dict, Optional, Any, List
from datetime import datetime

from langsmith import traceable

from orthocare.models import UserInput
from .steps import (
    StepContext,
    StepResult,
    StepStatus,
    # Phase 1
    InputValidationStep,
    RedFlagCheckStep,
    SymptomMappingStep,
    DemographicsEnrichmentStep,
    # Phase 2
    WeightCalculationStep,
    VectorSearchStep,
    RankingMergeStep,
    BucketArbitrationStep,
    # Phase 3
    ExerciseFilterStep,
    PersonalizationStep,
    ExerciseRecommendationStep,
    ExerciseSetAssemblyStep,
)


@dataclass
class GranularPipelineResult:
    """세분화된 파이프라인 결과"""
    context: StepContext
    success: bool
    blocked_by_red_flag: bool = False
    error: Optional[str] = None

    @property
    def summary(self) -> Dict[str, Any]:
        return self.context.get_summary()

    @property
    def diagnoses(self) -> Dict[str, Any]:
        return self.context.diagnoses

    @property
    def exercise_sets(self) -> Dict[str, Any]:
        return self.context.exercise_sets


class GranularPipeline:
    """
    세분화된 OrthoCare 파이프라인

    모든 스텝이 개별 추적 가능:
    - LangSmith에서 각 스텝 소요 시간, 입출력 확인
    - 특정 스텝만 재실행 가능
    - 스텝별 디버깅 용이

    Phase 1: 입력 처리 (4 steps)
    Phase 2: 진단 (4 steps)
    Phase 3: 운동 추천 (4 steps)
    """

    def __init__(
        self,
        llm_client=None,
        vector_store=None,
        weight_ratio: float = 0.6,
    ):
        """
        Args:
            llm_client: OpenAI 클라이언트
            vector_store: Pinecone 벡터 스토어
            weight_ratio: 가중치/검색 랭킹 비율
        """
        self.llm_client = llm_client
        self.vector_store = vector_store
        self.weight_ratio = weight_ratio

        # 서비스 초기화
        self._init_services()

        # 스텝 초기화
        self._init_steps()

    def _init_services(self):
        """서비스 초기화"""
        from orthocare.services.input import InputValidator, RedFlagChecker, SymptomMapper
        from orthocare.services.scoring import WeightService
        from orthocare.services.evidence import EvidenceSearchService
        from orthocare.services.diagnosis import BucketArbitrator
        from orthocare.services.exercise import ExerciseRecommender

        self.validator = InputValidator()
        self.red_flag_checker = RedFlagChecker()
        self.symptom_mapper = SymptomMapper()
        self.weight_service = WeightService()
        self.evidence_service = EvidenceSearchService(self.vector_store) if self.vector_store else None
        self.bucket_arbitrator = BucketArbitrator(self.llm_client) if self.llm_client else None
        self.exercise_recommender = ExerciseRecommender(self.llm_client) if self.llm_client else None

    def _init_steps(self):
        """스텝 초기화"""
        # Phase 1 스텝
        self.phase1_steps = [
            InputValidationStep(self.validator),
            RedFlagCheckStep(self.red_flag_checker),
            SymptomMappingStep(self.symptom_mapper),
            DemographicsEnrichmentStep(self.symptom_mapper),
        ]

        # Phase 2 스텝
        self.phase2_steps = [
            WeightCalculationStep(self.weight_service),
            VectorSearchStep(self.evidence_service, self.symptom_mapper),
            RankingMergeStep(self.weight_ratio),
            BucketArbitrationStep(self.bucket_arbitrator),
        ]

        # Phase 3 스텝
        self.phase3_steps = [
            ExerciseFilterStep(),
            PersonalizationStep(),
            ExerciseRecommendationStep(self.exercise_recommender),
            ExerciseSetAssemblyStep(),
        ]

    @traceable(name="granular_pipeline")
    def run(self, input_data: dict) -> GranularPipelineResult:
        """
        전체 파이프라인 실행

        Args:
            input_data: 원시 입력 데이터

        Returns:
            GranularPipelineResult
        """
        context = StepContext(
            raw_input=input_data,
            start_time=datetime.now(),
        )

        try:
            # Phase 1: 입력 처리
            phase1_success = self._run_phase1(context)

            if not phase1_success:
                return GranularPipelineResult(
                    context=context,
                    success=False,
                    error="Phase 1 failed",
                )

            # 레드플래그로 차단된 경우
            if context.blocked_by_red_flag:
                return GranularPipelineResult(
                    context=context,
                    success=True,
                    blocked_by_red_flag=True,
                )

            # Phase 2: 진단
            phase2_success = self._run_phase2(context)

            if not phase2_success:
                return GranularPipelineResult(
                    context=context,
                    success=False,
                    error="Phase 2 failed",
                )

            # Phase 3: 운동 추천
            phase3_success = self._run_phase3(context)

            return GranularPipelineResult(
                context=context,
                success=phase3_success,
                error="Phase 3 failed" if not phase3_success else None,
            )

        except Exception as e:
            return GranularPipelineResult(
                context=context,
                success=False,
                error=str(e),
            )

    @traceable(name="phase_1_input_processing")
    def _run_phase1(self, context: StepContext) -> bool:
        """Phase 1: 입력 처리"""
        for step in self.phase1_steps:
            result = step.run(context)
            if result.status == StepStatus.FAILED:
                return False
        return True

    @traceable(name="phase_2_diagnosis")
    def _run_phase2(self, context: StepContext) -> bool:
        """Phase 2: 진단"""
        for step in self.phase2_steps:
            result = step.run(context)
            if result.status == StepStatus.FAILED:
                return False
        return True

    @traceable(name="phase_3_exercise_recommendation")
    def _run_phase3(self, context: StepContext) -> bool:
        """Phase 3: 운동 추천"""
        for step in self.phase3_steps:
            result = step.run(context)
            if result.status == StepStatus.FAILED:
                return False
        return True

    def run_single_step(
        self,
        step_name: str,
        context: StepContext,
    ) -> StepResult:
        """
        단일 스텝만 실행 (디버깅/테스트용)

        Args:
            step_name: 스텝 이름
            context: 파이프라인 컨텍스트

        Returns:
            StepResult
        """
        all_steps = self.phase1_steps + self.phase2_steps + self.phase3_steps

        for step in all_steps:
            if step.name == step_name:
                return step.run(context)

        raise ValueError(f"Unknown step: {step_name}")

    def get_step_names(self) -> Dict[str, List[str]]:
        """모든 스텝 이름 반환"""
        return {
            "phase1": [s.name for s in self.phase1_steps],
            "phase2": [s.name for s in self.phase2_steps],
            "phase3": [s.name for s in self.phase3_steps],
        }

    def get_step_descriptions(self) -> Dict[str, str]:
        """스텝 설명 반환"""
        all_steps = self.phase1_steps + self.phase2_steps + self.phase3_steps
        return {s.name: s.description for s in all_steps}

    def generate_app_output(self, result: GranularPipelineResult) -> Dict[str, Any]:
        """
        앱용 출력 생성 (Phase 3-4)

        - 질환 버킷 미노출 (OA, TRM 등 명시 안함)
        - 친근한 메시지 + 운동 테이블

        Args:
            result: 파이프라인 실행 결과

        Returns:
            앱용 출력 딕셔너리
        """
        from orthocare.services.output import SummaryGenerator

        generator = SummaryGenerator()
        return generator.generate_app_output(
            user_input=result.context.user_input,
            diagnoses=result.context.diagnoses,
            exercise_sets=result.context.exercise_sets,
        )

    def generate_app_markdown(self, result: GranularPipelineResult) -> str:
        """
        앱용 마크다운 출력 생성 (Phase 3-4)

        - 질환 버킷 미노출
        - 친근한 메시지 + 운동 테이블

        Args:
            result: 파이프라인 실행 결과

        Returns:
            앱용 마크다운 문자열
        """
        from orthocare.services.output import SummaryGenerator

        generator = SummaryGenerator()
        return generator.generate_app_markdown(
            user_input=result.context.user_input,
            diagnoses=result.context.diagnoses,
            exercise_sets=result.context.exercise_sets,
        )
