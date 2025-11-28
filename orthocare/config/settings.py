"""환경변수 및 설정 관리 - Pydantic Settings 기반"""

import os
from pathlib import Path
from functools import lru_cache
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator


class Settings(BaseSettings):
    """전역 설정 - .env 파일에서 로드"""

    # 프로젝트 경로
    project_root: Path = Field(
        default_factory=lambda: Path(__file__).parent.parent.parent
    )

    # OpenAI
    openai_api_key: str = Field(..., description="OpenAI API 키 (필수)")
    openai_model: str = Field(default="gpt-4o", description="사용할 모델")

    # Pinecone (벡터DB)
    pinecone_api_key: str = Field(..., description="Pinecone API 키 (필수)")
    pinecone_environment: str = Field(..., description="Pinecone 환경")
    pinecone_index: str = Field(default="orthocare", description="Pinecone 인덱스명")
    pinecone_host: str = Field(default="", description="Pinecone 호스트 URL")

    # LangSmith (트레이싱)
    langsmith_tracing: bool = Field(default=True, description="LangSmith 추적 활성화")
    langsmith_endpoint: str = Field(
        default="https://api.smith.langchain.com",
        description="LangSmith API 엔드포인트"
    )
    langsmith_api_key: str = Field(default="", description="LangSmith API 키")
    langsmith_project: str = Field(default="orthocare", description="LangSmith 프로젝트명")

    @model_validator(mode="after")
    def setup_langsmith_env(self) -> "Settings":
        """LangSmith 환경변수를 os.environ에 설정 (langsmith 라이브러리 호환)"""
        if self.langsmith_tracing and self.langsmith_api_key:
            os.environ["LANGSMITH_TRACING"] = "true"
            os.environ["LANGSMITH_ENDPOINT"] = self.langsmith_endpoint
            os.environ["LANGSMITH_API_KEY"] = self.langsmith_api_key
            os.environ["LANGSMITH_PROJECT"] = self.langsmith_project
        return self

    # 임베딩
    embed_model: str = Field(
        default="text-embedding-3-large", description="임베딩 모델"
    )
    embed_dimensions: int = Field(default=3072, description="임베딩 차원")

    # 검색 설정
    search_top_k: int = Field(default=10, description="검색 결과 수")
    similarity_threshold: float = Field(
        default=0.85, description="자동 임베딩 임계값"
    )
    min_relevance_score: float = Field(
        default=0.6, description="최소 관련성 점수 (미만 시 제외)"
    )

    # 경로 설정
    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    @property
    def knee_data_dir(self) -> Path:
        return self.data_dir / "knee"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # 알 수 없는 환경변수 무시


@lru_cache()
def get_settings() -> Settings:
    """싱글톤 설정 객체 반환"""
    return Settings()


# 전역 settings 인스턴스
settings = get_settings()
