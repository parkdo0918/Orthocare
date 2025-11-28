"""파이프라인 평가 모듈"""

import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

from orthocare.pipelines import MainPipeline
from .metrics import AccuracyMetrics


@dataclass
class TestCase:
    """개별 테스트 케이스"""
    id: str
    name: str
    input_data: dict
    expected: dict
    source: str = ""


@dataclass
class TestResult:
    """테스트 결과"""
    test_id: str
    test_name: str
    passed: bool
    expected_bucket: Optional[str]
    actual_bucket: Optional[str]
    expected_confidence_min: float = 0.0
    actual_confidence: float = 0.0
    expected_red_flag: bool = False
    actual_red_flag: bool = False
    error: Optional[str] = None
    details: dict = field(default_factory=dict)


class PipelineEvaluator:
    """
    파이프라인 정확도 평가

    골든셋 페르소나를 실행하고 기대값과 비교
    """

    def __init__(
        self,
        pipeline: MainPipeline,
        golden_set_path: Optional[Path] = None,
    ):
        self.pipeline = pipeline
        self.golden_set_path = golden_set_path or Path(
            "data/evaluation/golden_set/knee_personas.json"
        )
        self.results_dir = Path("data/evaluation/test_results")
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def load_golden_set(self) -> List[TestCase]:
        """골든셋 로드"""
        with open(self.golden_set_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return [
            TestCase(
                id=p["id"],
                name=p["name"],
                input_data=p["input"],
                expected=p["expected"],
                source=p.get("source", ""),
            )
            for p in data["personas"]
        ]

    def run_all(self) -> Dict[str, Any]:
        """전체 골든셋 평가 실행"""
        test_cases = self.load_golden_set()
        results = []

        print(f"\n{'='*60}")
        print(f"파이프라인 평가 시작 - {len(test_cases)}개 케이스")
        print(f"{'='*60}\n")

        for i, tc in enumerate(test_cases, 1):
            print(f"[{i}/{len(test_cases)}] {tc.name}...", end=" ")
            result = self._run_single(tc)
            results.append(result)
            print("✓ PASS" if result.passed else f"✗ FAIL ({result.error or 'Mismatch'})")

        # 메트릭 계산
        metrics = AccuracyMetrics.from_results(results)

        # 결과 저장
        report = self._generate_report(results, metrics)
        self._save_results(report)

        return report

    def _run_single(self, tc: TestCase) -> TestResult:
        """단일 테스트 케이스 실행"""
        try:
            # 파이프라인 실행
            pipeline_result = self.pipeline.run(tc.input_data)

            # 레드플래그 체크
            actual_red_flag = pipeline_result.blocked_by_red_flag
            expected_red_flag = tc.expected.get("red_flag", False)

            # 레드플래그 케이스
            if expected_red_flag:
                passed = actual_red_flag == expected_red_flag
                return TestResult(
                    test_id=tc.id,
                    test_name=tc.name,
                    passed=passed,
                    expected_bucket=tc.expected.get("bucket"),
                    actual_bucket=None,
                    expected_red_flag=expected_red_flag,
                    actual_red_flag=actual_red_flag,
                )

            # 정상 케이스 - 버킷 비교
            body_part = tc.input_data["body_parts"][0]["code"]
            diagnosis = pipeline_result.diagnoses.get(body_part)

            if diagnosis is None:
                return TestResult(
                    test_id=tc.id,
                    test_name=tc.name,
                    passed=False,
                    expected_bucket=tc.expected.get("bucket"),
                    actual_bucket=None,
                    error="No diagnosis result",
                )

            expected_bucket = tc.expected.get("bucket")
            actual_bucket = diagnosis.final_bucket
            expected_confidence = tc.expected.get("confidence_min", 0.0)
            actual_confidence = diagnosis.confidence

            # 버킷 일치 + 신뢰도 충족
            bucket_match = expected_bucket == actual_bucket
            confidence_ok = actual_confidence >= expected_confidence

            passed = bucket_match and confidence_ok

            return TestResult(
                test_id=tc.id,
                test_name=tc.name,
                passed=passed,
                expected_bucket=expected_bucket,
                actual_bucket=actual_bucket,
                expected_confidence_min=expected_confidence,
                actual_confidence=actual_confidence,
                expected_red_flag=expected_red_flag,
                actual_red_flag=actual_red_flag,
                details={
                    "bucket_scores": [
                        {"bucket": bs.bucket, "score": bs.score, "pct": bs.percentage}
                        for bs in diagnosis.bucket_scores
                    ],
                    "weight_ranking": diagnosis.weight_ranking,
                    "has_discrepancy": diagnosis.has_discrepancy,
                },
            )

        except Exception as e:
            return TestResult(
                test_id=tc.id,
                test_name=tc.name,
                passed=False,
                expected_bucket=tc.expected.get("bucket"),
                actual_bucket=None,
                error=str(e),
            )

    def _generate_report(
        self,
        results: List[TestResult],
        metrics: "AccuracyMetrics",
    ) -> Dict[str, Any]:
        """평가 리포트 생성"""
        # 버킷별 분석
        bucket_analysis = {}
        for r in results:
            if r.expected_bucket:
                if r.expected_bucket not in bucket_analysis:
                    bucket_analysis[r.expected_bucket] = {"total": 0, "correct": 0}
                bucket_analysis[r.expected_bucket]["total"] += 1
                if r.passed:
                    bucket_analysis[r.expected_bucket]["correct"] += 1

        for bucket in bucket_analysis:
            total = bucket_analysis[bucket]["total"]
            correct = bucket_analysis[bucket]["correct"]
            bucket_analysis[bucket]["accuracy"] = correct / total if total > 0 else 0

        # 실패 케이스
        failures = [
            {
                "id": r.test_id,
                "name": r.test_name,
                "expected": r.expected_bucket,
                "actual": r.actual_bucket,
                "error": r.error,
            }
            for r in results
            if not r.passed
        ]

        return {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_cases": metrics.total,
                "passed": metrics.passed,
                "failed": metrics.failed,
                "accuracy": metrics.accuracy,
                "accuracy_pct": f"{metrics.accuracy * 100:.1f}%",
            },
            "bucket_analysis": bucket_analysis,
            "failures": failures,
            "detailed_results": [
                {
                    "id": r.test_id,
                    "name": r.test_name,
                    "passed": r.passed,
                    "expected_bucket": r.expected_bucket,
                    "actual_bucket": r.actual_bucket,
                    "confidence": r.actual_confidence,
                    "details": r.details,
                }
                for r in results
            ],
        }

    def _save_results(self, report: Dict[str, Any]) -> Path:
        """결과 저장"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.results_dir / f"{timestamp}_results.json"

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        print(f"\n결과 저장: {filepath}")
        return filepath

    def print_summary(self, report: Dict[str, Any]) -> None:
        """요약 출력"""
        summary = report["summary"]

        print(f"\n{'='*60}")
        print("평가 결과 요약")
        print(f"{'='*60}")
        print(f"총 케이스: {summary['total_cases']}")
        print(f"통과: {summary['passed']}")
        print(f"실패: {summary['failed']}")
        print(f"정확도: {summary['accuracy_pct']}")

        print(f"\n{'버킷별 정확도':=^60}")
        for bucket, data in report["bucket_analysis"].items():
            acc = data["accuracy"] * 100
            print(f"  {bucket}: {data['correct']}/{data['total']} ({acc:.1f}%)")

        if report["failures"]:
            print(f"\n{'실패 케이스':=^60}")
            for f in report["failures"]:
                print(f"  - [{f['id']}] {f['name']}")
                print(f"    기대: {f['expected']} / 실제: {f['actual']}")
                if f["error"]:
                    print(f"    오류: {f['error']}")
