"""OrthoBullets 크롤러 모듈

정형외과 교육 사이트에서 질환/치료 정보 크롤링
"""

import re
import time
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from langsmith import traceable


@dataclass
class OrthoBulletsArticle:
    """OrthoBullets 문서 데이터"""
    url: str
    title: str
    content: str
    body_part: str  # knee, shoulder, spine, etc.
    category: str  # anatomy, pathology, treatment
    subcategory: Optional[str] = None
    key_points: List[str] = field(default_factory=list)
    epidemiology: Optional[str] = None
    pathoanatomy: Optional[str] = None
    classification: Optional[str] = None
    diagnosis: Optional[str] = None
    treatment: Optional[str] = None
    complications: Optional[str] = None
    references: List[str] = field(default_factory=list)

    @property
    def source_id(self) -> str:
        """URL 기반 고유 ID"""
        parsed = urlparse(self.url)
        return parsed.path.strip("/").replace("/", "_")


class OrthoBulletsCrawler:
    """
    OrthoBullets 크롤러

    정형외과 교육 자료 수집:
    - Topic pages (질환별 정보)
    - Treatment algorithms
    - Anatomy references

    주의: robots.txt 및 이용약관 준수 필요
    """

    BASE_URL = "https://www.orthobullets.com"

    # 부위별 카테고리 URL
    BODY_PART_URLS = {
        "shoulder": "/topics/shoulder",
        "knee": "/topics/knee",
        "hip": "/topics/hip",
        "spine": "/topics/spine",
        "ankle": "/topics/foot-ankle",
        "hand": "/topics/hand",
        "elbow": "/topics/elbow",
        "trauma": "/topics/trauma",
        "pediatric": "/topics/pediatric",
        "sports": "/topics/sports",
    }

    def __init__(
        self,
        rate_limit_delay: float = 2.0,  # 예의바른 크롤링
        user_agent: str = "OrthoCare Research Bot (educational purposes)",
    ):
        """
        Args:
            rate_limit_delay: 요청 간 딜레이 (초)
            user_agent: User-Agent 헤더
        """
        self.rate_limit_delay = rate_limit_delay
        self.client = httpx.Client(
            timeout=30.0,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )
        self._visited_urls = set()

    @traceable(name="orthobullets_get_topic_list")
    def get_topic_list(self, body_part: str) -> List[Dict[str, str]]:
        """
        부위별 토픽 목록 조회

        Args:
            body_part: 부위 코드 (knee, shoulder 등)

        Returns:
            토픽 정보 리스트 [{"url": ..., "title": ..., "category": ...}]
        """
        if body_part not in self.BODY_PART_URLS:
            raise ValueError(f"Unknown body part: {body_part}")

        url = urljoin(self.BASE_URL, self.BODY_PART_URLS[body_part])
        response = self.client.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        topics = []

        # 토픽 링크 찾기
        for link in soup.select("a[href*='/topics/']"):
            href = link.get("href", "")
            title = link.get_text(strip=True)

            if not title or len(title) < 3:
                continue

            # 카테고리 URL 자체는 제외
            if href in self.BODY_PART_URLS.values():
                continue

            full_url = urljoin(self.BASE_URL, href)

            # 중복 제거
            if full_url in self._visited_urls:
                continue

            topics.append({
                "url": full_url,
                "title": title,
                "body_part": body_part,
            })

        time.sleep(self.rate_limit_delay)
        return topics

    @traceable(name="orthobullets_fetch_article")
    def fetch_article(self, url: str, body_part: str = "unknown") -> Optional[OrthoBulletsArticle]:
        """
        단일 토픽 페이지 크롤링

        Args:
            url: 토픽 URL
            body_part: 부위 코드

        Returns:
            OrthoBulletsArticle 또는 None
        """
        try:
            response = self.client.get(url)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            article = self._parse_article(soup, url, body_part)

            self._visited_urls.add(url)
            time.sleep(self.rate_limit_delay)

            return article

        except Exception as e:
            print(f"  ⚠ 크롤링 실패: {url} - {e}")
            return None

    def _parse_article(
        self,
        soup: BeautifulSoup,
        url: str,
        body_part: str,
    ) -> OrthoBulletsArticle:
        """HTML에서 문서 정보 추출"""

        # 제목
        title_elem = soup.select_one("h1.topic-title, h1.title, h1")
        title = title_elem.get_text(strip=True) if title_elem else ""

        # 본문 컨텐츠
        content_parts = []

        # 메인 컨텐츠 영역
        main_content = soup.select_one(".topic-content, .content, article, main")
        if main_content:
            # 스크립트/스타일 제거
            for script in main_content.select("script, style, nav, footer"):
                script.decompose()
            content_parts.append(main_content.get_text(separator="\n", strip=True))

        content = "\n\n".join(content_parts)

        # 섹션별 내용 추출
        sections = self._extract_sections(soup)

        # 카테고리 추출
        breadcrumb = soup.select_one(".breadcrumb, nav[aria-label='breadcrumb']")
        category = "general"
        subcategory = None
        if breadcrumb:
            crumbs = [c.get_text(strip=True) for c in breadcrumb.select("a, span")]
            if len(crumbs) > 1:
                category = crumbs[1].lower() if len(crumbs) > 1 else "general"
                subcategory = crumbs[2] if len(crumbs) > 2 else None

        # Key Points
        key_points = self._extract_key_points(soup)

        # References
        references = self._extract_references(soup)

        return OrthoBulletsArticle(
            url=url,
            title=title,
            content=content,
            body_part=body_part,
            category=category,
            subcategory=subcategory,
            key_points=key_points,
            epidemiology=sections.get("epidemiology"),
            pathoanatomy=sections.get("pathoanatomy"),
            classification=sections.get("classification"),
            diagnosis=sections.get("diagnosis"),
            treatment=sections.get("treatment"),
            complications=sections.get("complications"),
            references=references,
        )

    def _extract_sections(self, soup: BeautifulSoup) -> Dict[str, str]:
        """섹션별 내용 추출"""
        sections = {}

        section_keywords = {
            "epidemiology": ["epidemiology", "incidence", "prevalence"],
            "pathoanatomy": ["pathoanatomy", "anatomy", "pathophysiology", "mechanism"],
            "classification": ["classification", "types", "stages"],
            "diagnosis": ["diagnosis", "presentation", "symptoms", "exam", "imaging"],
            "treatment": ["treatment", "management", "surgery", "nonoperative", "operative"],
            "complications": ["complications", "prognosis", "outcomes"],
        }

        for header in soup.select("h2, h3, h4"):
            header_text = header.get_text(strip=True).lower()

            for section_name, keywords in section_keywords.items():
                if any(kw in header_text for kw in keywords):
                    # 다음 형제 요소들에서 텍스트 수집
                    content_parts = []
                    for sibling in header.find_next_siblings():
                        if sibling.name in ["h2", "h3", "h4"]:
                            break
                        text = sibling.get_text(strip=True)
                        if text:
                            content_parts.append(text)

                    if content_parts:
                        sections[section_name] = " ".join(content_parts)
                    break

        return sections

    def _extract_key_points(self, soup: BeautifulSoup) -> List[str]:
        """Key Points 추출"""
        key_points = []

        # "Key Points" 또는 "Summary" 섹션 찾기
        for header in soup.select("h2, h3"):
            if "key" in header.get_text(strip=True).lower():
                ul = header.find_next("ul")
                if ul:
                    for li in ul.select("li"):
                        text = li.get_text(strip=True)
                        if text:
                            key_points.append(text)
                break

        return key_points

    def _extract_references(self, soup: BeautifulSoup) -> List[str]:
        """참고문헌 추출"""
        references = []

        # References 섹션 찾기
        for header in soup.select("h2, h3"):
            if "reference" in header.get_text(strip=True).lower():
                ref_container = header.find_next(["ol", "ul", "div"])
                if ref_container:
                    for item in ref_container.select("li, p"):
                        text = item.get_text(strip=True)
                        if text and len(text) > 10:
                            references.append(text)
                break

        return references[:20]  # 최대 20개

    @traceable(name="orthobullets_crawl_body_part")
    def crawl_body_part(
        self,
        body_part: str,
        max_articles: int = 50,
        show_progress: bool = True,
    ) -> List[OrthoBulletsArticle]:
        """
        부위별 전체 토픽 크롤링

        Args:
            body_part: 부위 코드
            max_articles: 최대 문서 수
            show_progress: 진행률 표시

        Returns:
            OrthoBulletsArticle 리스트
        """
        if show_progress:
            print(f"[OrthoBullets] {body_part} 토픽 목록 조회 중...")

        topics = self.get_topic_list(body_part)

        if show_progress:
            print(f"  {len(topics)} 토픽 발견, 최대 {max_articles}개 크롤링...")

        articles = []
        for i, topic in enumerate(topics[:max_articles]):
            if show_progress:
                print(f"  [{i+1}/{min(len(topics), max_articles)}] {topic['title'][:40]}...")

            article = self.fetch_article(topic["url"], body_part)
            if article:
                articles.append(article)

        return articles

    @traceable(name="orthobullets_search")
    def search(
        self,
        query: str,
        max_results: int = 20,
    ) -> List[Dict[str, str]]:
        """
        OrthoBullets 내부 검색

        Args:
            query: 검색어
            max_results: 최대 결과 수

        Returns:
            검색 결과 리스트
        """
        search_url = f"{self.BASE_URL}/search"
        params = {"q": query}

        try:
            response = self.client.get(search_url, params=params)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            results = []

            for item in soup.select(".search-result, .result-item")[:max_results]:
                link = item.select_one("a")
                if link:
                    results.append({
                        "url": urljoin(self.BASE_URL, link.get("href", "")),
                        "title": link.get_text(strip=True),
                    })

            time.sleep(self.rate_limit_delay)
            return results

        except Exception as e:
            print(f"  ⚠ 검색 실패: {e}")
            return []

    def close(self):
        """HTTP 클라이언트 종료"""
        self.client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# 중요 토픽 직접 URL (자주 참조되는 주제)
IMPORTANT_TOPICS = {
    "knee": [
        "/topics/12045/knee-osteoarthritis",
        "/topics/12003/acl-injury",
        "/topics/12051/meniscus-tear",
        "/topics/12061/patellofemoral-syndrome",
    ],
    "shoulder": [
        "/topics/3043/rotator-cuff-tear",
        "/topics/3008/shoulder-impingement",
        "/topics/3025/frozen-shoulder",
        "/topics/3062/shoulder-instability",
    ],
    "spine": [
        "/topics/2017/lumbar-disc-herniation",
        "/topics/2042/lumbar-spinal-stenosis",
        "/topics/2056/cervical-radiculopathy",
        "/topics/2003/low-back-pain",
    ],
    "hip": [
        "/topics/9007/hip-osteoarthritis",
        "/topics/9019/hip-labral-tear",
        "/topics/9031/femoroacetabular-impingement",
    ],
    "ankle": [
        "/topics/7008/ankle-sprain",
        "/topics/7041/plantar-fasciitis",
        "/topics/7025/achilles-tendinopathy",
    ],
}


def get_important_topic_urls(body_part: Optional[str] = None) -> List[str]:
    """
    중요 토픽 URL 반환

    Args:
        body_part: 부위 코드 (None이면 전체)

    Returns:
        URL 리스트
    """
    base = "https://www.orthobullets.com"

    if body_part and body_part in IMPORTANT_TOPICS:
        return [urljoin(base, path) for path in IMPORTANT_TOPICS[body_part]]

    all_urls = []
    for paths in IMPORTANT_TOPICS.values():
        all_urls.extend([urljoin(base, path) for path in paths])
    return all_urls
