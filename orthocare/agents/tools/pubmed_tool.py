"""PubMed 검색 도구

실시간 PubMed API 검색
"""

from dataclasses import dataclass, field
from typing import List, Optional

from langsmith import traceable

from orthocare.data_ops.crawlers import PubMedCrawler, PubMedArticle


@dataclass
class PubMedSearchResult:
    """PubMed 검색 결과"""
    pmid: str
    title: str
    abstract: str
    authors: List[str]
    journal: str
    year: int
    url: str
    doi: Optional[str] = None
    mesh_terms: List[str] = field(default_factory=list)

    @classmethod
    def from_article(cls, article: PubMedArticle) -> "PubMedSearchResult":
        return cls(
            pmid=article.pmid,
            title=article.title,
            abstract=article.abstract,
            authors=article.authors,
            journal=article.journal,
            year=article.year,
            url=article.url,
            doi=article.doi,
            mesh_terms=article.mesh_terms,
        )


class PubMedSearchTool:
    """
    PubMed 검색 도구

    NCBI E-utilities API를 통한 실시간 논문 검색
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        email: str = "orthocare@example.com",
    ):
        """
        Args:
            api_key: NCBI API 키 (선택)
            email: NCBI 정책상 필수 이메일
        """
        self.crawler = PubMedCrawler(api_key=api_key, email=email)

    @traceable(name="pubmed_search")
    def search(
        self,
        query: str,
        max_results: int = 10,
        min_year: Optional[int] = None,
    ) -> List[PubMedSearchResult]:
        """
        PubMed 검색

        Args:
            query: 검색 쿼리 (PubMed 검색 문법 지원)
            max_results: 최대 결과 수
            min_year: 최소 발행년도 (예: 2020)

        Returns:
            PubMedSearchResult 리스트

        Example queries:
            - "knee osteoarthritis exercise"
            - "rotator cuff AND rehabilitation"
            - "(shoulder pain) AND (physical therapy[MeSH])"
        """
        min_date = f"{min_year}/01/01" if min_year else None

        articles = self.crawler.search_and_fetch(
            query=query,
            max_results=max_results,
            min_date=min_date,
        )

        return [PubMedSearchResult.from_article(a) for a in articles]

    @traceable(name="pubmed_search_by_body_part")
    def search_by_body_part(
        self,
        body_part: str,
        topic: Optional[str] = None,
        max_results: int = 10,
    ) -> List[PubMedSearchResult]:
        """
        부위별 관련 논문 검색

        Args:
            body_part: 부위 (knee, shoulder, spine, hip, ankle)
            topic: 추가 토픽 (예: "exercise", "rehabilitation")
            max_results: 최대 결과 수

        Returns:
            PubMedSearchResult 리스트
        """
        # 부위별 기본 검색어
        body_part_terms = {
            "knee": "knee[Title/Abstract]",
            "shoulder": "shoulder[Title/Abstract]",
            "spine": "(spine[Title/Abstract] OR lumbar[Title/Abstract] OR cervical[Title/Abstract])",
            "hip": "hip[Title/Abstract]",
            "ankle": "(ankle[Title/Abstract] OR foot[Title/Abstract])",
        }

        base_query = body_part_terms.get(body_part, f"{body_part}[Title/Abstract]")

        if topic:
            query = f"({base_query}) AND ({topic}[Title/Abstract])"
        else:
            query = base_query

        return self.search(query, max_results=max_results)

    @traceable(name="pubmed_search_treatment")
    def search_treatment_evidence(
        self,
        condition: str,
        treatment_type: str = "exercise",
        max_results: int = 10,
        evidence_level: str = "any",
    ) -> List[PubMedSearchResult]:
        """
        치료 근거 검색

        Args:
            condition: 질환/상태 (예: "knee osteoarthritis")
            treatment_type: 치료 유형 (예: "exercise", "physical therapy")
            max_results: 최대 결과 수
            evidence_level: 근거 수준 필터
                - "any": 모든 연구
                - "rct": 무작위 대조군 연구
                - "meta": 메타분석/체계적 문헌고찰

        Returns:
            PubMedSearchResult 리스트
        """
        query_parts = [f"({condition}[Title/Abstract])"]
        query_parts.append(f"({treatment_type}[Title/Abstract])")

        # 근거 수준 필터
        if evidence_level == "rct":
            query_parts.append("(randomized controlled trial[pt])")
        elif evidence_level == "meta":
            query_parts.append("(meta-analysis[pt] OR systematic review[pt])")

        query = " AND ".join(query_parts)
        return self.search(query, max_results=max_results)

    @traceable(name="pubmed_get_article")
    def get_article(self, pmid: str) -> Optional[PubMedSearchResult]:
        """
        특정 PMID의 논문 조회

        Args:
            pmid: PubMed ID

        Returns:
            PubMedSearchResult 또는 None
        """
        articles = self.crawler.fetch_articles([pmid])
        if articles:
            return PubMedSearchResult.from_article(articles[0])
        return None

    def close(self):
        """리소스 정리"""
        self.crawler.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
