#!/usr/bin/env python
"""OrthoBullets 크롤링 스크립트 (멀티 부위 지원)

사용법:
    PYTHONPATH=. python scripts/crawl_orthobullets.py --body-part knee
    PYTHONPATH=. python scripts/crawl_orthobullets.py --body-part shoulder
    PYTHONPATH=. python scripts/crawl_orthobullets.py --body-part all
"""

import argparse
import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from dataclasses import dataclass, asdict

# 프로젝트 루트
DATA_DIR = Path(__file__).parent.parent / "data"


# ============================================================
# 부위별 토픽 설정
# ============================================================

BODY_PART_TOPICS = {
    "knee": {
        "base_url": "https://www.orthobullets.com/knee-and-sports",
        "topics": {
            # OA
            "knee-osteoarthritis": {"category": "OA", "url": "/3001/knee-osteoarthritis"},
            # TRM
            "acl-injury": {"category": "TRM", "url": "/3004/acl-injury"},
            "meniscus-tear": {"category": "TRM", "url": "/3005/meniscus-tear"},
            "mcl-injury": {"category": "TRM", "url": "/3006/mcl-injury"},
            "pcl-injury": {"category": "TRM", "url": "/3007/pcl-injury"},
            # OVR
            "patellofemoral-syndrome": {"category": "OVR", "url": "/3013/patellofemoral-pain-syndrome"},
            "patellar-tendinitis": {"category": "OVR", "url": "/3014/patellar-tendinitis"},
            "iliotibial-band-syndrome": {"category": "OVR", "url": "/3015/iliotibial-band-syndrome"},
            # INF
            "septic-arthritis-knee": {"category": "INF", "url": "/3020/septic-arthritis-knee"},
            "gout": {"category": "INF", "url": "/3022/gout"},
        }
    },
    "shoulder": {
        "base_url": "https://www.orthobullets.com/shoulder-and-elbow",
        "topics": {
            # TRM
            "rotator-cuff-tear": {"category": "TRM", "url": "/3046/rotator-cuff-tear"},
            "ac-joint-separation": {"category": "TRM", "url": "/3052/ac-joint-separation"},
            "shoulder-dislocation": {"category": "TRM", "url": "/3053/shoulder-instability"},
            # OVR
            "shoulder-impingement": {"category": "OVR", "url": "/3047/shoulder-impingement"},
            "biceps-tendinopathy": {"category": "OVR", "url": "/3048/biceps-tendinopathy"},
            # OA
            "shoulder-oa": {"category": "OA", "url": "/3049/glenohumeral-osteoarthritis"},
            # STF
            "adhesive-capsulitis": {"category": "STF", "url": "/3051/adhesive-capsulitis-frozen-shoulder"},
        }
    }
}


@dataclass
class OrthoBulletsArticle:
    """크롤링된 OrthoBullets 문서"""
    source_id: str
    url: str
    title: str
    content: str
    body_part: str
    category: str  # bucket code
    key_points: List[str]
    subcategory: Optional[str] = None


class OrthoBulletsCrawler:
    """OrthoBullets 크롤러"""

    def __init__(self, rate_limit: float = 2.0):
        self.rate_limit = rate_limit
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })

    def fetch(self, url: str) -> Optional[OrthoBulletsArticle]:
        """URL에서 문서 크롤링"""
        try:
            time.sleep(self.rate_limit)
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'html.parser')

            # 제목
            title_elem = soup.find('h1')
            title = title_elem.get_text(strip=True) if title_elem else "제목 없음"

            # 본문 추출 (여러 선택자 시도)
            content_elem = (
                soup.find('div', class_='topic-content') or
                soup.find('div', class_='content') or
                soup.find('article') or
                soup.find('main')
            )

            if content_elem:
                # 스크립트, 스타일 제거
                for tag in content_elem.find_all(['script', 'style', 'nav', 'footer']):
                    tag.decompose()
                content = content_elem.get_text(separator='\n', strip=True)
            else:
                content = ""

            # Key points 추출
            key_points = []
            for li in soup.find_all('li'):
                text = li.get_text(strip=True)
                if len(text) > 20 and len(text) < 200:
                    key_points.append(text)

            return OrthoBulletsArticle(
                source_id=url.split('/')[-1],
                url=url,
                title=title,
                content=content[:5000],  # 최대 5000자
                body_part="",  # 나중에 설정
                category="",  # 나중에 설정
                key_points=key_points[:10],  # 최대 10개
            )

        except Exception as e:
            print(f"  ✗ 크롤링 실패: {e}")
            return None


def crawl_body_part(body_part: str, crawler: OrthoBulletsCrawler) -> Dict:
    """특정 부위 크롤링"""
    if body_part not in BODY_PART_TOPICS:
        print(f"지원하지 않는 부위: {body_part}")
        return {}

    config = BODY_PART_TOPICS[body_part]
    base_url = config["base_url"]
    topics = config["topics"]

    print(f"\n=== {body_part.upper()} 크롤링 ({len(topics)}개 토픽) ===")

    articles = {}
    for topic_id, topic_info in topics.items():
        url = base_url + topic_info["url"]
        print(f"\n[{topic_id}] {url}")

        article = crawler.fetch(url)
        if article:
            article.body_part = body_part
            article.category = topic_info["category"]
            article.subcategory = topic_id

            articles[topic_id] = asdict(article)
            print(f"  ✓ {article.title[:50]}...")
            print(f"    버킷: {article.category}, 내용: {len(article.content)}자")
        else:
            print(f"  ✗ 실패")

    return articles


def save_cache(body_part: str, articles: Dict) -> Path:
    """캐시 저장"""
    cache_dir = DATA_DIR / "crawled"
    cache_dir.mkdir(parents=True, exist_ok=True)

    if body_part == "knee":
        cache_path = cache_dir / "orthobullets_cache.json"
    else:
        cache_path = cache_dir / f"orthobullets_{body_part}_cache.json"

    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)

    print(f"\n저장: {cache_path} ({len(articles)}개)")
    return cache_path


def main():
    parser = argparse.ArgumentParser(description="OrthoBullets 크롤링")
    parser.add_argument("--body-part", default="all",
                       help="부위 코드 (knee, shoulder, all)")
    parser.add_argument("--rate-limit", type=float, default=2.0,
                       help="요청 간 대기 시간(초)")
    parser.add_argument("--index", action="store_true",
                       help="크롤링 후 바로 인덱싱")
    args = parser.parse_args()

    crawler = OrthoBulletsCrawler(rate_limit=args.rate_limit)

    # 크롤링할 부위 결정
    if args.body_part == "all":
        body_parts = list(BODY_PART_TOPICS.keys())
    else:
        body_parts = [args.body_part]

    # 크롤링
    all_cache_paths = []
    for bp in body_parts:
        articles = crawl_body_part(bp, crawler)
        if articles:
            cache_path = save_cache(bp, articles)
            all_cache_paths.append(cache_path)

    # 인덱싱
    if args.index and all_cache_paths:
        print("\n=== Pinecone 인덱싱 ===")
        import subprocess
        for bp in body_parts:
            cmd = f"PYTHONPATH=. python scripts/index_diagnosis_db.py --orthobullets-only --body-part {bp}"
            print(f"실행: {cmd}")
            subprocess.run(cmd, shell=True)

    print("\n=== 완료 ===")
    print(f"크롤링 부위: {', '.join(body_parts)}")
    print(f"저장된 파일: {len(all_cache_paths)}개")


if __name__ == "__main__":
    main()
