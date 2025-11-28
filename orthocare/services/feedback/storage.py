"""피드백 저장소

피드백 데이터 영구 저장 및 조회
"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional
from datetime import datetime
import threading

from orthocare.models.feedback import (
    SearchFeedback,
    ExerciseFeedback,
    PairwisePreference,
    FeedbackBatch,
)


class FeedbackStorage(ABC):
    """피드백 저장소 추상 클래스"""

    @abstractmethod
    def save_search_feedback(self, feedback: SearchFeedback) -> bool:
        pass

    @abstractmethod
    def save_exercise_feedback(self, feedback: ExerciseFeedback) -> bool:
        pass

    @abstractmethod
    def save_pairwise_preference(self, preference: PairwisePreference) -> bool:
        pass

    @abstractmethod
    def get_feedback_batch(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_rating: Optional[int] = None,
    ) -> FeedbackBatch:
        pass

    @abstractmethod
    def get_stats(self) -> dict:
        pass


class JSONFeedbackStorage(FeedbackStorage):
    """JSON 파일 기반 피드백 저장소

    개발/테스트용. 프로덕션에서는 DB 기반 저장소 사용 권장.
    """

    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self.search_file = self.storage_dir / "search_feedbacks.jsonl"
        self.exercise_file = self.storage_dir / "exercise_feedbacks.jsonl"
        self.pairwise_file = self.storage_dir / "pairwise_preferences.jsonl"

        self._lock = threading.Lock()

    def _append_jsonl(self, file_path: Path, data: dict) -> bool:
        """JSONL 형식으로 append"""
        try:
            with self._lock:
                with open(file_path, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(data, ensure_ascii=False, default=str) + '\n')
            return True
        except Exception as e:
            print(f"피드백 저장 실패: {e}")
            return False

    def _read_jsonl(self, file_path: Path) -> List[dict]:
        """JSONL 파일 읽기"""
        if not file_path.exists():
            return []

        items = []
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        items.append(json.loads(line))
        except Exception as e:
            print(f"피드백 읽기 실패: {e}")

        return items

    def save_search_feedback(self, feedback: SearchFeedback) -> bool:
        return self._append_jsonl(self.search_file, feedback.model_dump())

    def save_exercise_feedback(self, feedback: ExerciseFeedback) -> bool:
        return self._append_jsonl(self.exercise_file, feedback.model_dump())

    def save_pairwise_preference(self, preference: PairwisePreference) -> bool:
        return self._append_jsonl(self.pairwise_file, preference.model_dump())

    def get_feedback_batch(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        min_rating: Optional[int] = None,
    ) -> FeedbackBatch:
        """피드백 배치 조회"""
        batch = FeedbackBatch()

        # 검색 피드백
        for item in self._read_jsonl(self.search_file):
            try:
                fb = SearchFeedback(**item)
                if start_date and fb.timestamp < start_date:
                    continue
                if end_date and fb.timestamp > end_date:
                    continue
                batch.search_feedbacks.append(fb)
            except Exception:
                continue

        # 운동 피드백
        for item in self._read_jsonl(self.exercise_file):
            try:
                fb = ExerciseFeedback(**item)
                if start_date and fb.timestamp < start_date:
                    continue
                if end_date and fb.timestamp > end_date:
                    continue
                if min_rating is not None and fb.rating.score < min_rating:
                    continue
                batch.exercise_feedbacks.append(fb)
            except Exception:
                continue

        # 쌍별 선호도
        for item in self._read_jsonl(self.pairwise_file):
            try:
                pref = PairwisePreference(**item)
                if start_date and pref.timestamp < start_date:
                    continue
                if end_date and pref.timestamp > end_date:
                    continue
                batch.pairwise_preferences.append(pref)
            except Exception:
                continue

        return batch

    def get_stats(self) -> dict:
        """저장소 통계"""
        return {
            "search_feedbacks": len(self._read_jsonl(self.search_file)),
            "exercise_feedbacks": len(self._read_jsonl(self.exercise_file)),
            "pairwise_preferences": len(self._read_jsonl(self.pairwise_file)),
            "storage_dir": str(self.storage_dir),
        }

    def export_for_training(self, output_path: Path) -> dict:
        """
        강화학습 학습용 데이터 내보내기

        Returns:
            {
                "positive_pairs": [(query, result_id), ...],
                "negative_pairs": [(query, result_id), ...],
                "triplets": [(anchor, positive, negative), ...],
            }
        """
        batch = self.get_feedback_batch()

        export_data = {
            "positive_pairs": batch.get_positive_pairs(),
            "negative_pairs": batch.get_negative_pairs(),
            "triplets": batch.get_triplets(),
            "export_time": datetime.utcnow().isoformat(),
            "total_feedbacks": batch.total_count,
        }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)

        return export_data
