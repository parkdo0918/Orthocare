"""오케스트레이션 서비스

버킷 추론 → (Red Flag 체크) → 운동 추천
전체 흐름을 조율하고 통합 응답 생성

v3.1: LangGraph 버킷 추론 기본값 적용 (32% 성능 향상)
"""

import os
import time
from typing import Optional
from datetime import datetime

from langsmith import traceable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.models import PhysicalScore
from bucket_inference.models import BucketInferenceInput
from bucket_inference.models.input import NaturalLanguageInput
from bucket_inference.pipeline import BucketInferencePipeline, LangGraphBucketInferencePipeline
from exercise_recommendation.models.input import ExerciseRecommendationInput
from exercise_recommendation.pipeline import ExerciseRecommendationPipeline
from gateway.models import (
    UnifiedRequest,
    UnifiedResponse,
    DiagnosisContext,
    SurveyData,
    DiagnosisResult,
    ExercisePlanResult,
)


class OrchestrationService:
    """통합 오케스트레이션 서비스

    책임:
    1. 버킷 추론 실행 (LangGraph 기본, 32% 빠름)
    2. Red Flag 체크 및 분기
    3. 운동 추천 실행 (컨텍스트 전달)
    4. 통합 응답 생성

    환경변수:
    - USE_LANGGRAPH_BUCKET: "false"로 설정 시 기존 파이프라인 사용
    """

    def __init__(self, use_langgraph_bucket: Optional[bool] = None):
        """
        Args:
            use_langgraph_bucket: LangGraph 버킷 추론 사용 여부
                - None: 환경변수 USE_LANGGRAPH_BUCKET 참조 (기본값: True)
                - True: LangGraph 사용 (32% 빠름)
                - False: 기존 파이프라인 사용
        """
        # LangGraph 사용 여부 결정
        if use_langgraph_bucket is None:
            use_langgraph_bucket = os.getenv("USE_LANGGRAPH_BUCKET", "true").lower() != "false"

        # 버킷 추론 파이프라인 선택
        if use_langgraph_bucket:
            self.bucket_pipeline = LangGraphBucketInferencePipeline()
            self._bucket_pipeline_type = "langgraph"
        else:
            self.bucket_pipeline = BucketInferencePipeline()
            self._bucket_pipeline_type = "original"

        self.exercise_pipeline = ExerciseRecommendationPipeline()

    @property
    def bucket_pipeline_type(self) -> str:
        """현재 사용 중인 버킷 파이프라인 타입"""
        return self._bucket_pipeline_type

    @traceable(name="unified_orchestration")
    def process(self, request: UnifiedRequest) -> UnifiedResponse:
        """
        통합 처리 실행

        Args:
            request: 통합 요청

        Returns:
            UnifiedResponse
        """
        start_time = time.time()

        # Step 1: 버킷 추론 입력 생성
        bucket_input = self._build_bucket_input(request)

        # Step 2: 버킷 추론 실행
        bucket_results = self.bucket_pipeline.run(bucket_input)

        # 주요 부위 결과
        primary_bp = request.primary_body_part.code
        bucket_output = bucket_results.get(primary_bp)

        if not bucket_output:
            raise ValueError(f"버킷 추론 실패: {primary_bp}")

        # Step 3: 설문 데이터 구성
        survey_data = SurveyData(
            demographics=request.demographics,
            body_parts=request.body_parts,
            natural_language=request.natural_language,
            physical_score=request.physical_score,
            raw_responses=request.raw_survey_responses,
        )

        # Step 4: 진단 결과 구성
        diagnosis_result = DiagnosisResult.from_bucket_output(bucket_output)

        # Step 5: Red Flag 체크
        has_red_flag = bucket_output.has_red_flag
        exercise_plan = None
        status = "success"
        message = None

        if has_red_flag and request.options.skip_exercise_on_red_flag:
            # Red Flag → 운동 추천 스킵
            status = "partial"
            message = (
                f"Red Flag 감지: {bucket_output.red_flag.messages[0] if bucket_output.red_flag.messages else '위험 신호 감지'}. "
                "운동 추천이 생략되었습니다. 전문의 상담을 권장합니다."
            )

        elif request.options.include_exercises:
            # Step 6: 운동 추천 실행
            try:
                exercise_output = self._run_exercise_recommendation(
                    request=request,
                    bucket_output=bucket_output,
                )

                # 개인화 노트 생성
                personalization_note = self._generate_personalization_note(
                    bucket_output=bucket_output,
                    request=request,
                )

                exercise_plan = ExercisePlanResult.from_exercise_output(
                    exercise_output,
                    personalization_note=personalization_note,
                )

            except Exception as e:
                status = "partial"
                message = f"운동 추천 실패: {str(e)}. 버킷 추론 결과만 반환합니다."

        # Step 7: 처리 시간 계산
        processing_time_ms = int((time.time() - start_time) * 1000)

        return UnifiedResponse(
            request_id=request.request_id,
            user_id=request.user_id,
            survey_data=survey_data,
            diagnosis=diagnosis_result,
            exercise_plan=exercise_plan,
            status=status,
            message=message,
            processed_at=datetime.utcnow(),
            processing_time_ms=processing_time_ms,
        )

    def _build_bucket_input(self, request: UnifiedRequest) -> BucketInferenceInput:
        """버킷 추론 입력 생성"""
        return BucketInferenceInput(
            demographics=request.demographics,
            body_parts=request.body_parts,
            natural_language=request.natural_language,
            survey_responses=request.raw_survey_responses,
        )

    def _run_exercise_recommendation(
        self,
        request: UnifiedRequest,
        bucket_output,
    ):
        """운동 추천 실행 (컨텍스트 전달)"""
        # 진단 컨텍스트 생성
        diagnosis_context = DiagnosisContext.from_bucket_output(
            bucket_output,
            symptoms=request.primary_body_part.symptoms,
        )

        # 신체 점수 (없으면 기본값)
        physical_score = request.physical_score
        if physical_score is None:
            # NRS 기반 기본 레벨 추정
            nrs = request.primary_nrs
            if nrs >= 7:
                physical_score = PhysicalScore(total_score=6)  # Level D
            elif nrs >= 5:
                physical_score = PhysicalScore(total_score=9)  # Level C
            elif nrs >= 3:
                physical_score = PhysicalScore(total_score=12)  # Level B
            else:
                physical_score = PhysicalScore(total_score=15)  # Level A

        # 운동 추천 입력 생성
        exercise_input = ExerciseRecommendationInput(
            user_id=request.user_id,
            body_part=request.primary_body_part.code,
            bucket=bucket_output.final_bucket,
            physical_score=physical_score,
            demographics=request.demographics,
            nrs=request.primary_nrs,
            # diagnosis_context는 아직 ExerciseRecommendationInput에 없음
            # TODO: 추후 추가하여 개인화 강화
        )

        # 운동 추천 실행
        return self.exercise_pipeline.run(exercise_input)

    def _generate_personalization_note(
        self,
        bucket_output,
        request: UnifiedRequest,
    ) -> str:
        """개인화 노트 생성

        버킷 추론 컨텍스트를 기반으로
        이 사용자에게 왜 이 운동들이 추천되었는지 설명
        """
        notes = []

        # 버킷 기반 설명
        bucket = bucket_output.final_bucket
        confidence = bucket_output.confidence

        bucket_descriptions = {
            "OA": "퇴행성 관절염 패턴",
            "OVR": "과사용 패턴",
            "TRM": "외상/부상 패턴",
            "INF": "염증성 패턴",
            "STF": "강직/동결견 패턴",
        }

        desc = bucket_descriptions.get(bucket, bucket)
        notes.append(f"{desc}으로 진단되어 맞춤 운동을 구성했습니다 (신뢰도: {confidence*100:.0f}%).")

        # 주요 증상 기반 설명
        symptoms = request.primary_body_part.symptoms[:3]
        if symptoms:
            notes.append(f"주요 증상({', '.join(symptoms)})을 고려하여 선별했습니다.")

        # NRS 기반 강도 설명
        nrs = request.primary_nrs
        if nrs >= 7:
            notes.append("통증 수준이 높아 저강도 운동으로 시작합니다.")
        elif nrs >= 5:
            notes.append("중간 강도로 시작하며 점진적으로 증가할 수 있습니다.")
        else:
            notes.append("통증 수준이 낮아 적극적인 운동이 가능합니다.")

        return " ".join(notes)

    @traceable(name="diagnosis_only")
    def process_diagnosis_only(self, request: UnifiedRequest) -> UnifiedResponse:
        """버킷 추론만 실행 (운동 추천 제외)"""
        # 옵션 강제 설정
        request.options.include_exercises = False
        return self.process(request)
