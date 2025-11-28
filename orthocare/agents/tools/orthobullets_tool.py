"""OrthoBullets 검색 도구

정형외과 교육 자료 검색
"""

from dataclasses import dataclass, field
from typing import List, Optional

from langsmith import traceable

from orthocare.data_ops.crawlers import OrthoBulletsCrawler, OrthoBulletsArticle


@dataclass
class OrthoBulletsSearchResult:
    """OrthoBullets 검색 결과"""
    url: str
    title: str
    body_part: str
    category: str
    key_points: List[str] = field(default_factory=list)
    epidemiology: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None

    @classmethod
    def from_article(cls, article: OrthoBulletsArticle) -> "OrthoBulletsSearchResult":
        return cls(
            url=article.url,
            title=article.title,
            body_part=article.body_part,
            category=article.category,
            key_points=article.key_points,
            epidemiology=article.epidemiology,
            diagnosis=article.diagnosis,
            treatment=article.treatment,
        )


class OrthoBulletsSearchTool:
    """
    OrthoBullets 검색 도구

    정형외과 교육 자료 검색 및 크롤링
    """

    def __init__(self, rate_limit_delay: float = 2.0):
        """
        Args:
            rate_limit_delay: 요청 간 딜레이 (초)
        """
        self.crawler = OrthoBulletsCrawler(rate_limit_delay=rate_limit_delay)

    @traceable(name="orthobullets_search")
    def search(
        self,
        query: str,
        max_results: int = 10,
    ) -> List[OrthoBulletsSearchResult]:
        """
        OrthoBullets 내부 검색

        Args:
            query: 검색어
            max_results: 최대 결과 수

        Returns:
            OrthoBulletsSearchResult 리스트
        """
        search_results = self.crawler.search(query, max_results=max_results)

        # 검색 결과에서 상세 정보 가져오기
        results = []
        for item in search_results[:max_results]:
            article = self.crawler.fetch_article(item["url"])
            if article:
                results.append(OrthoBulletsSearchResult.from_article(article))

        return results

    @traceable(name="orthobullets_get_topics")
    def get_topics_by_body_part(
        self,
        body_part: str,
        max_topics: int = 20,
    ) -> List[OrthoBulletsSearchResult]:
        """
        부위별 토픽 목록 조회

        Args:
            body_part: 부위 코드 (knee, shoulder, spine, hip, ankle)
            max_topics: 최대 토픽 수

        Returns:
            OrthoBulletsSearchResult 리스트
        """
        articles = self.crawler.crawl_body_part(
            body_part=body_part,
            max_articles=max_topics,
            show_progress=False,
        )

        return [OrthoBulletsSearchResult.from_article(a) for a in articles]

    @traceable(name="orthobullets_get_article")
    def get_article(self, url: str) -> Optional[OrthoBulletsSearchResult]:
        """
        특정 URL의 문서 조회

        Args:
            url: OrthoBullets 문서 URL

        Returns:
            OrthoBulletsSearchResult 또는 None
        """
        article = self.crawler.fetch_article(url)
        if article:
            return OrthoBulletsSearchResult.from_article(article)
        return None

    @traceable(name="orthobullets_get_condition_info")
    def get_condition_info(
        self,
        condition: str,
    ) -> Optional[OrthoBulletsSearchResult]:
        """
        특정 질환 정보 검색

        Args:
            condition: 질환명 (예: "knee osteoarthritis", "rotator cuff tear")

        Returns:
            OrthoBulletsSearchResult 또는 None
        """
        results = self.search(condition, max_results=1)
        return results[0] if results else None

    def close(self):
        """리소스 정리"""
        self.crawler.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
