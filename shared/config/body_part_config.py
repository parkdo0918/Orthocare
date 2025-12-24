"""부위별 설정 로더

모든 부위별 차이점(버킷, 가중치, 프롬프트 등)을
코드가 아닌 설정 파일로 관리하여 확장성 확보

사용 예시:
    config = BodyPartConfigLoader.load("shoulder")
    valid_buckets = config.bucket_order  # ["OA", "OVR", "TRM", "STF"]
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from pathlib import Path
import json


@dataclass
class BodyPartConfig:
    """부위별 설정 객체

    data/medical/{body_part}/ 폴더의 모든 설정을 담는 객체
    """

    # 기본 정보
    code: str                           # "knee" or "shoulder"
    display_name: str                   # "무릎" or "어깨"
    display_name_en: str                # "Knee" or "Shoulder"
    version: str                        # 설정 버전

    # 버킷 관련
    bucket_order: List[str]             # ["OA", "OVR", "TRM", "INF"]
    bucket_info: Dict[str, Dict]        # 버킷별 상세 정보

    # 가중치
    weights: Dict[str, List[float]]     # 증상별 가중치 벡터

    # 설문 매핑
    survey_mapping: Dict[str, Any]      # 문진 → 증상코드 매핑

    # 레드 플래그
    red_flags: Dict[str, Any]           # 위험 신호 정의

    # 프롬프트 템플릿
    prompt_template: str                # LLM 프롬프트 템플릿

    # 추가 설정
    extra_config: Dict[str, Any] = field(default_factory=dict)

    @property
    def bucket_descriptions(self) -> Dict[str, str]:
        """버킷별 설명 반환"""
        return {
            code: info.get("description", "")
            for code, info in self.bucket_info.items()
        }

    @property
    def bucket_names_kr(self) -> Dict[str, str]:
        """버킷별 한글 이름 반환"""
        return {
            code: info.get("name_kr", code)
            for code, info in self.bucket_info.items()
        }

    def get_bucket_info(self, bucket_code: str) -> Dict:
        """특정 버킷의 상세 정보 반환"""
        return self.bucket_info.get(bucket_code, {})

    def is_valid_bucket(self, bucket_code: str) -> bool:
        """유효한 버킷 코드인지 확인"""
        return bucket_code in self.bucket_order

    def get_weight(self, symptom_code: str) -> List[float]:
        """증상 코드의 가중치 벡터 반환"""
        return self.weights.get(symptom_code, [0.0] * len(self.bucket_order))


class BodyPartConfigLoader:
    """부위별 설정 로더

    Singleton 패턴 + 캐싱으로 성능 최적화
    """

    _cache: Dict[str, BodyPartConfig] = {}
    _data_dir: Optional[Path] = None

    @classmethod
    def set_data_dir(cls, data_dir: Path) -> None:
        """데이터 디렉토리 설정"""
        cls._data_dir = data_dir

    @classmethod
    def _get_data_dir(cls) -> Path:
        """데이터 디렉토리 반환"""
        if cls._data_dir is not None:
            return cls._data_dir

        # 기본값: 프로젝트 루트의 data 폴더
        return Path(__file__).parent.parent.parent / "data"

    @classmethod
    def load(cls, body_part: str) -> BodyPartConfig:
        """
        부위별 설정 로드

        Args:
            body_part: 부위 코드 (예: "knee", "shoulder")

        Returns:
            BodyPartConfig 객체

        Raises:
            FileNotFoundError: 설정 파일이 없는 경우
            ValueError: 필수 파일이 누락된 경우
        """
        # 캐시 확인
        if body_part in cls._cache:
            return cls._cache[body_part]

        base_path = cls._get_data_dir() / "medical" / body_part

        if not base_path.exists():
            raise FileNotFoundError(
                f"부위 설정 폴더를 찾을 수 없습니다: {base_path}"
            )

        # 필수 파일 로드
        config_data = cls._load_json(base_path / "config.json")
        buckets_data = cls._load_json(base_path / "buckets.json")
        weights_data = cls._load_json(base_path / "weights.json")

        # 선택 파일 로드 (없으면 빈 딕셔너리)
        survey_mapping = cls._load_json_optional(base_path / "survey_mapping.json")
        red_flags = cls._load_json_optional(base_path / "red_flags.json")

        # 프롬프트 템플릿 로드
        prompt_template = cls._load_prompt_template(base_path)

        # 가중치에서 메타데이터 제거
        weights = {
            k: v for k, v in weights_data.items()
            if not k.startswith("_")
        }

        # BodyPartConfig 생성
        config = BodyPartConfig(
            code=body_part,
            display_name=config_data.get("display_name", body_part),
            display_name_en=config_data.get("display_name_en", body_part.capitalize()),
            version=config_data.get("version", "1.0"),
            bucket_order=buckets_data.get("bucket_order", []),
            bucket_info=buckets_data.get("buckets", {}),
            weights=weights,
            survey_mapping=survey_mapping,
            red_flags=red_flags,
            prompt_template=prompt_template,
            extra_config=config_data,
        )

        # 캐시에 저장
        cls._cache[body_part] = config

        return config

    @classmethod
    def _load_json(cls, path: Path) -> Dict:
        """JSON 파일 로드 (필수)"""
        if not path.exists():
            raise FileNotFoundError(f"필수 파일을 찾을 수 없습니다: {path}")

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def _load_json_optional(cls, path: Path) -> Dict:
        """JSON 파일 로드 (선택)"""
        if not path.exists():
            return {}

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @classmethod
    def _load_prompt_template(cls, base_path: Path) -> str:
        """프롬프트 템플릿 로드"""
        # prompts/arbitrator.txt 먼저 확인
        prompt_path = base_path / "prompts" / "arbitrator.txt"

        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()

        # 없으면 기본 템플릿 반환
        return cls._get_default_prompt_template()

    @classmethod
    def _get_default_prompt_template(cls) -> str:
        """기본 프롬프트 템플릿"""
        return """
## 환자 정보
{patient_info}

## 증상
{symptoms}

## 버킷별 점수 (가중치 기반)
{bucket_scores}

## 순위 비교
- 가중치 순위: {weight_ranking}
- 검색 순위: {search_ranking}
{discrepancy_info}

## 검색된 근거 자료
{evidence}

## 버킷 설명
{bucket_descriptions}

## 요청
위 정보를 종합하여 가장 가능성 높은 진단 버킷을 결정하세요.

**중요**: final_bucket은 반드시 {valid_buckets} 중 하나만 선택하세요.

다음 JSON 형식으로 응답하세요:
{{
    "final_bucket": "{default_bucket}",
    "confidence": 0.75,
    "evidence_summary": "진단 근거 요약 (2-3문장)",
    "reasoning": "판단 근거 설명",
    "citations": [
        {{
            "title": "논문 제목",
            "source_type": "paper|orthobullets|pubmed",
            "quote": "인용 문장",
            "relevance": "적용 근거"
        }}
    ]
}}
"""

    @classmethod
    def clear_cache(cls) -> None:
        """캐시 초기화"""
        cls._cache.clear()

    @classmethod
    def get_available_body_parts(cls) -> List[str]:
        """사용 가능한 부위 목록 반환"""
        data_dir = cls._get_data_dir()
        medical_dir = data_dir / "medical"

        if not medical_dir.exists():
            return []

        return [
            d.name for d in medical_dir.iterdir()
            if d.is_dir() and (d / "config.json").exists()
        ]
