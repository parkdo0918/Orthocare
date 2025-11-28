"""평가 메트릭"""

from dataclasses import dataclass
from typing import List, Dict, Any


@dataclass
class AccuracyMetrics:
    """정확도 메트릭"""

    total: int
    passed: int
    failed: int

    @property
    def accuracy(self) -> float:
        return self.passed / self.total if self.total > 0 else 0.0

    @classmethod
    def from_results(cls, results: List[Any]) -> "AccuracyMetrics":
        total = len(results)
        passed = sum(1 for r in results if r.passed)
        failed = total - passed
        return cls(total=total, passed=passed, failed=failed)


@dataclass
class ConfusionMatrix:
    """혼동 행렬"""

    buckets: List[str]
    matrix: Dict[str, Dict[str, int]]

    @classmethod
    def from_results(
        cls,
        results: List[Any],
        buckets: List[str] = None,
    ) -> "ConfusionMatrix":
        if buckets is None:
            buckets = ["OA", "OVR", "TRM", "INF"]

        matrix = {b: {b2: 0 for b2 in buckets} for b in buckets}

        for r in results:
            if r.expected_bucket and r.actual_bucket:
                if r.expected_bucket in matrix and r.actual_bucket in buckets:
                    matrix[r.expected_bucket][r.actual_bucket] += 1

        return cls(buckets=buckets, matrix=matrix)

    def print_matrix(self) -> None:
        """혼동 행렬 출력"""
        print("\n혼동 행렬 (행: 기대, 열: 실제)")
        print("     " + "  ".join(f"{b:>4}" for b in self.buckets))
        for expected in self.buckets:
            row = [self.matrix[expected][actual] for actual in self.buckets]
            print(f"{expected:>4} " + "  ".join(f"{v:>4}" for v in row))

    def get_per_class_metrics(self) -> Dict[str, Dict[str, float]]:
        """클래스별 정밀도/재현율"""
        metrics = {}

        for bucket in self.buckets:
            # True Positives
            tp = self.matrix[bucket][bucket]

            # False Positives (다른 클래스가 이 클래스로 예측됨)
            fp = sum(
                self.matrix[other][bucket]
                for other in self.buckets
                if other != bucket
            )

            # False Negatives (이 클래스가 다른 클래스로 예측됨)
            fn = sum(
                self.matrix[bucket][other]
                for other in self.buckets
                if other != bucket
            )

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
            recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
            f1 = (
                2 * precision * recall / (precision + recall)
                if (precision + recall) > 0
                else 0.0
            )

            metrics[bucket] = {
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1": round(f1, 3),
            }

        return metrics
