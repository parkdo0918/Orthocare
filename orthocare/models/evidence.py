"""근거 문서 모델"""

from typing import List, Optional, Literal
from datetime import datetime
from pydantic import BaseModel, Field


class Paper(BaseModel):
    """논문/가이드라인 정보"""

    doc_id: str = Field(..., description="문서 ID")
    title: str = Field(..., description="제목")
    source_type: Literal["verified_paper", "orthobullets", "pubmed"] = Field(
        ..., description="소스 타입"
    )
    source_layer: Literal[1, 2, 3] = Field(..., description="검색 레이어")
    body_part: str = Field(..., description="관련 부위")
    bucket_tags: List[str] = Field(..., description="관련 버킷 태그")
    year: Optional[int] = Field(default=None, description="출판 연도")
    url: Optional[str] = Field(default=None, description="원문 URL")
    summary: Optional[str] = Field(default=None, description="요약")
    content: Optional[str] = Field(default=None, description="전체 내용")


class SearchResult(BaseModel):
    """검색 결과"""

    paper: Paper = Field(..., description="문서 정보")
    similarity_score: float = Field(..., ge=0, le=1, description="유사도 점수")
    matching_reason: str = Field(..., description="매칭 이유")
    needs_review: bool = Field(default=False, description="의사 검토 필요 여부")
    auto_embedded: bool = Field(default=False, description="자동 임베딩 여부")


class EvidenceResult(BaseModel):
    """근거 검색 결과 (Phase 2 중간 출력)"""

    query: str = Field(..., description="검색 쿼리")
    body_part: str = Field(..., description="부위")
    results: List[SearchResult] = Field(..., description="검색 결과 목록")
    layer_breakdown: dict = Field(
        default_factory=dict, description="레이어별 결과 수"
    )
    search_timestamp: datetime = Field(
        default_factory=datetime.now, description="검색 시점"
    )

    @property
    def total_count(self) -> int:
        """총 결과 수"""
        return len(self.results)

    @property
    def verified_count(self) -> int:
        """검증된 문서 수 (Layer 1)"""
        return sum(1 for r in self.results if r.paper.source_layer == 1)

    @property
    def needs_review_count(self) -> int:
        """검토 필요 문서 수"""
        return sum(1 for r in self.results if r.needs_review)

    def get_by_bucket(self, bucket: str) -> List[SearchResult]:
        """버킷별 결과 필터링"""
        return [r for r in self.results if bucket in r.paper.bucket_tags]

    def get_top_results(self, n: int = 5) -> List[SearchResult]:
        """상위 n개 결과"""
        sorted_results = sorted(
            self.results, key=lambda x: x.similarity_score, reverse=True
        )
        return sorted_results[:n]
