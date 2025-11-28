"""파이프라인 스텝 기본 클래스"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum

from langsmith import traceable


class StepStatus(str, Enum):
    """스텝 실행 상태"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    """스텝 실행 결과"""
    step_name: str
    status: StepStatus
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == StepStatus.COMPLETED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_name": self.step_name,
            "status": self.status.value,
            "output_type": type(self.output).__name__ if self.output else None,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


@dataclass
class StepContext:
    """파이프라인 컨텍스트 (스텝 간 공유 데이터)"""

    # 입력 데이터
    raw_input: Dict[str, Any] = field(default_factory=dict)
    user_input: Any = None  # UserInput

    # Phase 1 결과
    validation_passed: bool = False
    red_flags: Dict[str, Any] = field(default_factory=dict)
    blocked_by_red_flag: bool = False
    symptom_codes: Dict[str, List[str]] = field(default_factory=dict)
    enriched_demographics: Dict[str, Any] = field(default_factory=dict)

    # Phase 2 결과 (부위별)
    bucket_scores: Dict[str, Dict[str, float]] = field(default_factory=dict)
    weight_rankings: Dict[str, List[str]] = field(default_factory=dict)
    search_results: Dict[str, Any] = field(default_factory=dict)
    search_rankings: Dict[str, List[str]] = field(default_factory=dict)
    merged_rankings: Dict[str, List[str]] = field(default_factory=dict)
    diagnoses: Dict[str, Any] = field(default_factory=dict)

    # Phase 3 결과 (부위별)
    filtered_exercises: Dict[str, List[Any]] = field(default_factory=dict)
    personalized_exercises: Dict[str, List[Any]] = field(default_factory=dict)
    recommended_exercises: Dict[str, List[Any]] = field(default_factory=dict)
    exercise_sets: Dict[str, Any] = field(default_factory=dict)

    # 메타 정보
    current_body_part: Optional[str] = None
    step_results: List[StepResult] = field(default_factory=list)
    start_time: Optional[datetime] = None

    def add_step_result(self, result: StepResult):
        self.step_results.append(result)

    def get_step_result(self, step_name: str) -> Optional[StepResult]:
        for r in self.step_results:
            if r.step_name == step_name:
                return r
        return None

    def get_summary(self) -> Dict[str, Any]:
        """파이프라인 실행 요약"""
        return {
            "total_steps": len(self.step_results),
            "completed": sum(1 for r in self.step_results if r.status == StepStatus.COMPLETED),
            "failed": sum(1 for r in self.step_results if r.status == StepStatus.FAILED),
            "skipped": sum(1 for r in self.step_results if r.status == StepStatus.SKIPPED),
            "total_duration_ms": sum(r.duration_ms for r in self.step_results),
            "steps": [r.to_dict() for r in self.step_results],
        }


class PipelineStep(ABC):
    """
    파이프라인 스텝 추상 클래스

    각 스텝은:
    1. 명확한 입력/출력
    2. 단일 책임
    3. LangSmith 추적 가능
    4. 실패 시 명확한 에러 메시지
    """

    name: str = "base_step"
    description: str = ""

    def __init__(self):
        self._start_time: Optional[float] = None

    @abstractmethod
    def execute(self, context: StepContext) -> StepResult:
        """
        스텝 실행

        Args:
            context: 파이프라인 컨텍스트

        Returns:
            StepResult 객체
        """
        pass

    def should_skip(self, context: StepContext) -> bool:
        """스텝 스킵 여부 결정"""
        return False

    def run(self, context: StepContext) -> StepResult:
        """
        스텝 실행 래퍼 (타이밍, 에러 핸들링)
        """
        import time

        # 스킵 체크
        if self.should_skip(context):
            result = StepResult(
                step_name=self.name,
                status=StepStatus.SKIPPED,
                metadata={"reason": "Skipped by should_skip()"},
            )
            context.add_step_result(result)
            return result

        start = time.time()

        try:
            result = self.execute(context)
            result.duration_ms = (time.time() - start) * 1000

        except Exception as e:
            result = StepResult(
                step_name=self.name,
                status=StepStatus.FAILED,
                error=str(e),
                duration_ms=(time.time() - start) * 1000,
            )

        context.add_step_result(result)
        return result
