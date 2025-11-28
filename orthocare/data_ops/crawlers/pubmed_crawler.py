"""PubMed 크롤러 모듈

NCBI E-utilities API를 사용하여 PubMed 논문 검색 및 메타데이터 추출
"""

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from datetime import datetime
import httpx

from langsmith import traceable


@dataclass
class PubMedArticle:
    """PubMed 논문 데이터"""
    pmid: str
    title: str
    abstract: str
    authors: List[str]
    journal: str
    year: int
    doi: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    mesh_terms: List[str] = field(default_factory=list)
    publication_types: List[str] = field(default_factory=list)
    url: str = ""

    def __post_init__(self):
        if not self.url:
            self.url = f"https://pubmed.ncbi.nlm.nih.gov/{self.pmid}/"


class PubMedCrawler:
    """
    PubMed 논문 크롤러

    NCBI E-utilities API 사용:
    - ESearch: 검색 쿼리로 PMID 목록 조회
    - EFetch: PMID로 논문 상세 정보 조회

    Rate limiting: 초당 3 요청 (API key 없을 시)
    """

    BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

    def __init__(
        self,
        api_key: Optional[str] = None,
        email: str = "orthocare@example.com",
        rate_limit_delay: float = 0.4,  # 초당 ~2.5 요청
    ):
        """
        Args:
            api_key: NCBI API 키 (선택, 있으면 rate limit 완화)
            email: NCBI 정책상 필수 이메일
            rate_limit_delay: API 호출 간 딜레이 (초)
        """
        self.api_key = api_key
        self.email = email
        self.rate_limit_delay = rate_limit_delay
        self.client = httpx.Client(timeout=30.0)

    def _build_params(self, **kwargs) -> Dict[str, Any]:
        """기본 파라미터 생성"""
        params = {"email": self.email, **kwargs}
        if self.api_key:
            params["api_key"] = self.api_key
        return params

    @traceable(name="pubmed_search")
    def search(
        self,
        query: str,
        max_results: int = 100,
        start: int = 0,
        sort: str = "relevance",
        min_date: Optional[str] = None,  # YYYY/MM/DD
        max_date: Optional[str] = None,
    ) -> List[str]:
        """
        PubMed 검색하여 PMID 목록 반환

        Args:
            query: 검색 쿼리 (PubMed 검색 문법 지원)
            max_results: 최대 결과 수
            start: 시작 인덱스
            sort: 정렬 방식 (relevance, pub_date)
            min_date: 최소 발행일
            max_date: 최대 발행일

        Returns:
            PMID 리스트

        Example queries:
            - "knee osteoarthritis[Title]"
            - "rotator cuff[MeSH] AND exercise[Title/Abstract]"
            - "(shoulder pain) AND (physical therapy[MeSH])"
        """
        params = self._build_params(
            db="pubmed",
            term=query,
            retmax=max_results,
            retstart=start,
            sort=sort,
            retmode="xml",
        )

        if min_date:
            params["mindate"] = min_date
            params["datetype"] = "pdat"
        if max_date:
            params["maxdate"] = max_date
            params["datetype"] = "pdat"

        response = self.client.get(f"{self.BASE_URL}/esearch.fcgi", params=params)
        response.raise_for_status()

        # XML 파싱
        root = ET.fromstring(response.text)
        pmids = [id_elem.text for id_elem in root.findall(".//Id") if id_elem.text]

        time.sleep(self.rate_limit_delay)
        return pmids

    @traceable(name="pubmed_fetch")
    def fetch_articles(
        self,
        pmids: List[str],
        batch_size: int = 50,
        show_progress: bool = True,
    ) -> List[PubMedArticle]:
        """
        PMID 목록으로 논문 상세 정보 조회

        Args:
            pmids: PMID 리스트
            batch_size: 배치 크기
            show_progress: 진행률 표시

        Returns:
            PubMedArticle 리스트
        """
        articles = []
        total = len(pmids)

        for i in range(0, total, batch_size):
            batch = pmids[i:i + batch_size]

            if show_progress:
                print(f"  Fetching {min(i + batch_size, total)}/{total} articles...")

            params = self._build_params(
                db="pubmed",
                id=",".join(batch),
                retmode="xml",
                rettype="abstract",
            )

            response = self.client.get(f"{self.BASE_URL}/efetch.fcgi", params=params)
            response.raise_for_status()

            batch_articles = self._parse_articles(response.text)
            articles.extend(batch_articles)

            if i + batch_size < total:
                time.sleep(self.rate_limit_delay)

        return articles

    def _parse_articles(self, xml_text: str) -> List[PubMedArticle]:
        """XML에서 논문 정보 파싱"""
        articles = []
        root = ET.fromstring(xml_text)

        for article_elem in root.findall(".//PubmedArticle"):
            try:
                article = self._parse_single_article(article_elem)
                if article:
                    articles.append(article)
            except Exception as e:
                # 파싱 실패 시 스킵
                continue

        return articles

    def _parse_single_article(self, elem: ET.Element) -> Optional[PubMedArticle]:
        """단일 논문 파싱"""
        medline = elem.find(".//MedlineCitation")
        if medline is None:
            return None

        # PMID
        pmid_elem = medline.find(".//PMID")
        if pmid_elem is None or not pmid_elem.text:
            return None
        pmid = pmid_elem.text

        # Article 정보
        article = medline.find(".//Article")
        if article is None:
            return None

        # 제목
        title_elem = article.find(".//ArticleTitle")
        title = title_elem.text if title_elem is not None and title_elem.text else ""

        # 초록
        abstract_parts = []
        for abs_text in article.findall(".//AbstractText"):
            label = abs_text.get("Label", "")
            text = abs_text.text or ""
            if label:
                abstract_parts.append(f"{label}: {text}")
            else:
                abstract_parts.append(text)
        abstract = " ".join(abstract_parts)

        # 저자
        authors = []
        for author in article.findall(".//Author"):
            last_name = author.find("LastName")
            fore_name = author.find("ForeName")
            if last_name is not None and last_name.text:
                name = last_name.text
                if fore_name is not None and fore_name.text:
                    name = f"{fore_name.text} {name}"
                authors.append(name)

        # 저널
        journal_elem = article.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None and journal_elem.text else ""

        # 발행년도
        year = 0
        pub_date = article.find(".//PubDate")
        if pub_date is not None:
            year_elem = pub_date.find("Year")
            if year_elem is not None and year_elem.text:
                try:
                    year = int(year_elem.text)
                except ValueError:
                    pass

        # DOI
        doi = None
        for eloc in article.findall(".//ELocationID"):
            if eloc.get("EIdType") == "doi":
                doi = eloc.text
                break

        # MeSH Terms
        mesh_terms = []
        for mesh in medline.findall(".//MeshHeading/DescriptorName"):
            if mesh.text:
                mesh_terms.append(mesh.text)

        # Keywords
        keywords = []
        for kw in medline.findall(".//KeywordList/Keyword"):
            if kw.text:
                keywords.append(kw.text)

        # Publication Types
        pub_types = []
        for pt in article.findall(".//PublicationTypeList/PublicationType"):
            if pt.text:
                pub_types.append(pt.text)

        return PubMedArticle(
            pmid=pmid,
            title=title,
            abstract=abstract,
            authors=authors,
            journal=journal,
            year=year,
            doi=doi,
            mesh_terms=mesh_terms,
            keywords=keywords,
            publication_types=pub_types,
        )

    @traceable(name="pubmed_search_and_fetch")
    def search_and_fetch(
        self,
        query: str,
        max_results: int = 100,
        **search_kwargs,
    ) -> List[PubMedArticle]:
        """
        검색 + 상세 조회 통합

        Args:
            query: 검색 쿼리
            max_results: 최대 결과 수
            **search_kwargs: search() 추가 인자

        Returns:
            PubMedArticle 리스트
        """
        pmids = self.search(query, max_results=max_results, **search_kwargs)

        if not pmids:
            return []

        return self.fetch_articles(pmids)

    def close(self):
        """HTTP 클라이언트 종료"""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 정형외과 관련 검색 쿼리 템플릿
ORTHO_SEARCH_TEMPLATES = {
    "knee": [
        "(knee osteoarthritis[Title/Abstract]) AND (exercise[Title/Abstract] OR physical therapy[MeSH])",
        "(anterior cruciate ligament[MeSH]) AND (rehabilitation[Title/Abstract])",
        "(patellofemoral pain[Title/Abstract]) AND (treatment[Title/Abstract])",
        "(meniscus tear[Title/Abstract]) AND (conservative treatment[Title/Abstract])",
    ],
    "shoulder": [
        "(rotator cuff[MeSH]) AND (exercise[Title/Abstract] OR rehabilitation[Title/Abstract])",
        "(frozen shoulder[Title/Abstract] OR adhesive capsulitis[MeSH]) AND (treatment[Title/Abstract])",
        "(shoulder impingement[Title/Abstract]) AND (physical therapy[Title/Abstract])",
    ],
    "spine": [
        "(low back pain[MeSH]) AND (exercise therapy[MeSH])",
        "(lumbar disc herniation[Title/Abstract]) AND (conservative treatment[Title/Abstract])",
        "(cervical radiculopathy[Title/Abstract]) AND (rehabilitation[Title/Abstract])",
        "(spinal stenosis[MeSH]) AND (physical therapy[Title/Abstract])",
    ],
    "hip": [
        "(hip osteoarthritis[Title/Abstract]) AND (exercise[Title/Abstract])",
        "(hip labral tear[Title/Abstract]) AND (rehabilitation[Title/Abstract])",
        "(femoroacetabular impingement[Title/Abstract]) AND (treatment[Title/Abstract])",
    ],
    "ankle": [
        "(ankle sprain[MeSH]) AND (rehabilitation[Title/Abstract])",
        "(plantar fasciitis[MeSH]) AND (treatment[Title/Abstract])",
        "(achilles tendinopathy[Title/Abstract]) AND (exercise[Title/Abstract])",
    ],
}


def get_ortho_search_queries(body_part: Optional[str] = None) -> List[str]:
    """
    정형외과 부위별 검색 쿼리 반환

    Args:
        body_part: 부위 코드 (None이면 전체)

    Returns:
        검색 쿼리 리스트
    """
    if body_part and body_part in ORTHO_SEARCH_TEMPLATES:
        return ORTHO_SEARCH_TEMPLATES[body_part]

    # 전체 쿼리 반환
    all_queries = []
    for queries in ORTHO_SEARCH_TEMPLATES.values():
        all_queries.extend(queries)
    return all_queries
