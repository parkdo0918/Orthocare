"""텍스트 임베딩 모듈"""

from typing import List, Optional
from dataclasses import dataclass
import time

from langsmith import traceable


@dataclass
class EmbeddingResult:
    """임베딩 결과"""
    text: str
    embedding: List[float]
    model: str
    tokens_used: int


class TextEmbedder:
    """
    텍스트 임베딩 생성기

    OpenAI text-embedding-3-large 사용
    - 3072 차원
    - 최대 8191 토큰
    """

    def __init__(
        self,
        openai_client=None,
        model: str = "text-embedding-3-large",
        dimensions: int = 3072,
        batch_size: int = 100,
        rate_limit_delay: float = 0.1,
    ):
        """
        Args:
            openai_client: OpenAI 클라이언트
            model: 임베딩 모델명
            dimensions: 임베딩 차원
            batch_size: 배치 크기
            rate_limit_delay: API 호출 간 딜레이 (초)
        """
        self.client = openai_client
        self.model = model
        self.dimensions = dimensions
        self.batch_size = batch_size
        self.rate_limit_delay = rate_limit_delay

    @traceable(name="embed_text")
    def embed(self, text: str) -> EmbeddingResult:
        """단일 텍스트 임베딩"""
        if not self.client:
            raise ValueError("OpenAI 클라이언트가 설정되지 않았습니다.")

        response = self.client.embeddings.create(
            model=self.model,
            input=text,
            dimensions=self.dimensions,
        )

        return EmbeddingResult(
            text=text,
            embedding=response.data[0].embedding,
            model=self.model,
            tokens_used=response.usage.total_tokens,
        )

    @traceable(name="embed_batch")
    def embed_batch(
        self,
        texts: List[str],
        show_progress: bool = True,
    ) -> List[EmbeddingResult]:
        """
        배치 임베딩

        Args:
            texts: 텍스트 리스트
            show_progress: 진행률 표시 여부

        Returns:
            EmbeddingResult 리스트
        """
        if not self.client:
            raise ValueError("OpenAI 클라이언트가 설정되지 않았습니다.")

        results = []
        total = len(texts)

        for i in range(0, total, self.batch_size):
            batch = texts[i:i + self.batch_size]

            if show_progress:
                print(f"  임베딩 중... {min(i + self.batch_size, total)}/{total}")

            response = self.client.embeddings.create(
                model=self.model,
                input=batch,
                dimensions=self.dimensions,
            )

            for j, data in enumerate(response.data):
                results.append(
                    EmbeddingResult(
                        text=batch[j],
                        embedding=data.embedding,
                        model=self.model,
                        tokens_used=response.usage.total_tokens // len(batch),
                    )
                )

            # Rate limiting
            if i + self.batch_size < total:
                time.sleep(self.rate_limit_delay)

        return results

    def get_dimensions(self) -> int:
        """임베딩 차원 반환"""
        return self.dimensions
