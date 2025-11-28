"""기본 데이터 로더"""

import json
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Any, Optional

from orthocare.config import settings


class BaseLoader(ABC):
    """부위별 데이터 로더 추상 클래스"""

    def __init__(self, body_part: str):
        self.body_part = body_part
        # 새 폴더 구조: medical/{body_part}, exercise/{body_part}
        self.medical_dir = settings.data_dir / "medical" / body_part
        self.exercise_dir = settings.data_dir / "exercise" / body_part
        self._validate_data_dirs()

        # 캐시
        self._weights: Optional[Dict[str, List[float]]] = None
        self._exercises: Optional[Dict[str, Any]] = None
        self._survey_mapping: Optional[Dict[str, Any]] = None
        self._red_flags: Optional[Dict[str, Any]] = None
        self._clinical_rules: Optional[Dict[str, Any]] = None
        self._buckets: Optional[Dict[str, Any]] = None

    def _validate_data_dirs(self) -> None:
        """데이터 디렉토리 존재 확인 - Fail-fast"""
        if not self.medical_dir.exists():
            raise FileNotFoundError(
                f"의료 데이터 디렉토리를 찾을 수 없습니다: {self.medical_dir}"
            )
        if not self.exercise_dir.exists():
            raise FileNotFoundError(
                f"운동 데이터 디렉토리를 찾을 수 없습니다: {self.exercise_dir}"
            )

    def _load_json(self, filename: str, data_type: str = "medical") -> Dict[str, Any]:
        """
        JSON 파일 로드 - Fail-fast

        Args:
            filename: 파일명
            data_type: "medical" 또는 "exercise"
        """
        base_dir = self.medical_dir if data_type == "medical" else self.exercise_dir
        filepath = base_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(
                f"필수 파일을 찾을 수 없습니다: {filepath}"
            )
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)

    @property
    def weights(self) -> Dict[str, List[float]]:
        """가중치 데이터 (캐시됨)"""
        if self._weights is None:
            data = self._load_json("weights.json")
            # _metadata 제외
            self._weights = {k: v for k, v in data.items() if not k.startswith("_")}
        return self._weights

    @property
    def exercises(self) -> Dict[str, Any]:
        """운동 데이터 (캐시됨) - exercise 폴더에서 로드"""
        if self._exercises is None:
            data = self._load_json("exercises.json", data_type="exercise")
            self._exercises = data.get("exercises", {})
        return self._exercises

    @property
    def survey_mapping(self) -> Dict[str, Any]:
        """설문 매핑 데이터 (캐시됨)"""
        if self._survey_mapping is None:
            data = self._load_json("survey_mapping.json")
            self._survey_mapping = data.get("questions", {})
        return self._survey_mapping

    @property
    def demographics_mapping(self) -> Dict[str, Any]:
        """인구통계 매핑 데이터"""
        data = self._load_json("survey_mapping.json")
        return data.get("demographics_mapping", {})

    @property
    def red_flags(self) -> Dict[str, Any]:
        """레드플래그 데이터 (캐시됨)"""
        if self._red_flags is None:
            self._red_flags = self._load_json("red_flags.json")
        return self._red_flags

    @property
    def clinical_rules(self) -> Dict[str, Any]:
        """임상 규칙 데이터 (캐시됨)"""
        if self._clinical_rules is None:
            self._clinical_rules = self._load_json("clinical_rules.json")
        return self._clinical_rules

    @property
    def buckets(self) -> Dict[str, Any]:
        """버킷 정의 (캐시됨)"""
        if self._buckets is None:
            data = self._load_json("buckets.json")
            self._buckets = data.get("buckets", {})
        return self._buckets

    @property
    def bucket_order(self) -> List[str]:
        """버킷 순서"""
        data = self._load_json("buckets.json")
        return data.get("bucket_order", [])

    @abstractmethod
    def get_weight_vector(self, symptom_code: str) -> List[float]:
        """증상 코드에 대한 가중치 벡터 반환"""
        pass

    @abstractmethod
    def get_exercises_for_bucket(self, bucket: str) -> List[Dict[str, Any]]:
        """버킷에 적합한 운동 목록 반환"""
        pass

    def clear_cache(self) -> None:
        """캐시 초기화"""
        self._weights = None
        self._exercises = None
        self._survey_mapping = None
        self._red_flags = None
        self._clinical_rules = None
        self._buckets = None
