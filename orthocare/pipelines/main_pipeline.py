"""메인 파이프라인 - 전체 오케스트레이션"""

from dataclasses import dataclass
from typing import Dict, Optional, Any

from langsmith import traceable

from orthocare.models import UserInput
from orthocare.models.diagnosis import DiagnosisResult
from orthocare.models.exercise import ExerciseSet
from orthocare.models.evidence import EvidenceResult

from orthocare.services.input import InputValidator, RedFlagChecker, SymptomMapper
from orthocare.services.scoring import WeightService
from orthocare.services.evidence import EvidenceSearchService
from orthocare.services.diagnosis import BucketArbitrator
from orthocare.services.exercise import ExerciseRecommender


@dataclass
class PipelineResult:
    """파이프라인 실행 결과"""

    user_input: UserInput
    diagnoses: Dict[str, DiagnosisResult]
    exercise_sets: Dict[str, ExerciseSet]
    evidence: Dict[str, EvidenceResult]
    blocked_by_red_flag: bool = False
    error: Optional[str] = None


class MainPipeline:
    """
    OrthoCare 메인 파이프라인

    Phase 1: 입력 처리 (검증, 레드플래그, 증상 매핑)
    Phase 2: 진단 (가중치 + 벡터 검색 → LLM Pass #1)
    Phase 3: 운동 추천 (LLM Pass #2)
    Phase 4: 출력 생성
    """

    def __init__(
        self,
        llm_client=None,
        vector_store=None,
    ):
        """
        Args:
            llm_client: OpenAI 클라이언트 등
            vector_store: Pinecone 등 벡터 스토어
        """
        # 서비스 초기화
        self.validator = InputValidator()
        self.red_flag_checker = RedFlagChecker()
        self.symptom_mapper = SymptomMapper()
        self.weight_service = WeightService()
        self.evidence_service = EvidenceSearchService(vector_store)
        self.bucket_arbitrator = BucketArbitrator(llm_client)
        self.exercise_recommender = ExerciseRecommender(llm_client)

    @traceable(name="orthocare_pipeline")
    def run(self, input_data: dict) -> PipelineResult:
        """
        파이프라인 실행

        Args:
            input_data: 원시 입력 데이터

        Returns:
            PipelineResult 객체

        Raises:
            Exception: 복구 불가능한 오류 시 (Fail-fast)
        """
        # Phase 1: 입력 처리
        user_input = self._phase1_input_processing(input_data)

        # 레드플래그 체크
        red_flag_results = self.red_flag_checker.check(user_input)
        blocked = self.red_flag_checker.should_block_exercise(red_flag_results)

        if blocked:
            return PipelineResult(
                user_input=user_input,
                diagnoses={},
                exercise_sets={},
                evidence={},
                blocked_by_red_flag=True,
            )

        # Phase 2: 진단 (부위별)
        diagnoses = {}
        evidence_results = {}

        for body_part in user_input.body_parts:
            diagnosis, evidence = self._phase2_diagnosis(
                body_part=body_part,
                user_input=user_input,
                red_flag=red_flag_results.get(body_part.code),
            )
            diagnoses[body_part.code] = diagnosis
            if evidence:
                evidence_results[body_part.code] = evidence

        # Phase 3: 운동 추천 (부위별)
        exercise_sets = {}

        for body_part in user_input.body_parts:
            diagnosis = diagnoses[body_part.code]

            exercise_set = self._phase3_exercise(
                diagnosis=diagnosis,
                user_input=user_input,
            )
            exercise_sets[body_part.code] = exercise_set

        return PipelineResult(
            user_input=user_input,
            diagnoses=diagnoses,
            exercise_sets=exercise_sets,
            evidence=evidence_results,
            blocked_by_red_flag=False,
        )

    @traceable(name="phase1_input_processing")
    def _phase1_input_processing(self, input_data: dict) -> UserInput:
        """Phase 1: 입력 처리"""
        # 검증
        user_input = self.validator.validate(input_data)

        # 증상 코드 보강 (인구통계 코드 추가)
        user_input = self.symptom_mapper.enrich_user_input(user_input)

        return user_input

    @traceable(name="phase2_diagnosis")
    def _phase2_diagnosis(
        self,
        body_part,
        user_input: UserInput,
        red_flag,
    ) -> tuple:
        """Phase 2: 진단"""
        # 2-1. 경로 A: 가중치 계산
        bucket_scores, weight_ranking = self.weight_service.calculate_scores(body_part)

        # 2-2. 경로 B: 벡터 검색
        query = self._build_search_query(body_part, user_input)
        evidence = self.evidence_service.search(
            query=query,
            body_part=body_part.code,
        )
        search_ranking = self.evidence_service.get_search_ranking(evidence)

        # 2-3. LLM Pass #1: 버킷 중재
        diagnosis = self.bucket_arbitrator.arbitrate(
            body_part=body_part,
            bucket_scores=bucket_scores,
            weight_ranking=weight_ranking,
            search_ranking=search_ranking,
            evidence=evidence,
            user_input=user_input,
            red_flag=red_flag,
        )

        return diagnosis, evidence

    @traceable(name="phase3_exercise")
    def _phase3_exercise(
        self,
        diagnosis: DiagnosisResult,
        user_input: UserInput,
    ) -> ExerciseSet:
        """Phase 3: 운동 추천"""
        return self.exercise_recommender.recommend(
            diagnosis=diagnosis,
            user_input=user_input,
        )

    def _build_search_query(self, body_part, user_input: UserInput) -> str:
        """검색 쿼리 구성"""
        symptoms = body_part.symptoms
        symptom_desc = self.symptom_mapper.get_symptom_description

        descriptions = [
            symptom_desc(body_part.code, s)
            for s in symptoms[:5]  # 상위 5개
        ]

        demo = user_input.demographics
        query = (
            f"{demo.age}세 {demo.sex} 환자, "
            f"증상: {', '.join(descriptions)}"
        )

        return query
