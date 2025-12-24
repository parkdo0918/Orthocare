"""Bucket Inference 설정

환경 변수:
- OPENAI_API_KEY: OpenAI API 키
- PINECONE_API_KEY: Pinecone API 키
- PINECONE_INDEX: Pinecone 인덱스명 (기본값: orthocare-diagnosis)
"""

import os
from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class BucketInferenceSettings(BaseSettings):
    """버킷 추론 설정"""

    # API Keys
    openai_api_key: str = Field(default="", description="OpenAI API Key")
    pinecone_api_key: str = Field(default="", description="Pinecone API Key")

    # Pinecone
    pinecone_index_diagnosis: str = Field(
        default="orthocare-diagnosis",
        description="진단용 벡터 DB 인덱스"
    )

    @property
    def pinecone_index(self) -> str:
        """하위 호환성을 위한 프로퍼티"""
        return self.pinecone_index_diagnosis

    # OpenAI
    openai_model: str = Field(default="gpt-4o", description="LLM 모델")
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="임베딩 모델"
    )
    embedding_dimension: int = Field(default=1536, description="임베딩 차원")

    # 검색 설정
    min_search_score: float = Field(default=0.15, description="최소 유사도 점수")
    search_top_k: int = Field(default=10, description="검색 결과 수")

    # 랭킹 설정
    weight_ratio: float = Field(
        default=0.6,
        description="가중치 대비 검색 비율 (0.6 = 가중치 60%, 검색 40%)"
    )

    # 데이터 경로
    data_dir: Path = Field(
        default=Path(__file__).parent.parent.parent / "data",
        description="데이터 디렉토리"
    )

    # 서버 설정
    host: str = Field(default="0.0.0.0", description="호스트")
    port: int = Field(default=8001, description="포트")

    class Config:
        env_prefix = ""
        env_file = ".env"
        extra = "ignore"


settings = BucketInferenceSettings()
