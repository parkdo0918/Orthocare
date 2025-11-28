#!/usr/bin/env python
"""OrthoBullets 데이터 크롤링 및 인덱싱 스크립트

중요 무릎 토픽을 크롤링하고 벡터 DB에 인덱싱
"""

import json
import sys
from pathlib import Path
from dataclasses import asdict

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from orthocare.config import settings
from orthocare.data_ops.crawlers import (
    OrthoBulletsCrawler,
    OrthoBulletsArticle,
    get_important_topic_urls,
    IMPORTANT_TOPICS,
)


# 토픽 URL → 버킷 매핑
TOPIC_BUCKET_MAP = {
    # OA (Osteoarthritis)
    "knee-osteoarthritis": ["OA"],
    "hip-osteoarthritis": ["OA"],
    "rheumatoid-arthritis": ["INF", "OA"],

    # TRM (Trauma)
    "acl-injury": ["TRM"],
    "meniscus-tear": ["TRM"],
    "mcl-injury": ["TRM"],
    "pcl-injury": ["TRM"],
    "patellar-fracture": ["TRM"],
    "tibial-plateau-fracture": ["TRM"],

    # OVR (Overuse)
    "patellofemoral-syndrome": ["OVR"],
    "patellar-tendinitis": ["OVR"],
    "iliotibial-band-syndrome": ["OVR"],
    "runners-knee": ["OVR"],

    # INF (Inflammatory)
    "septic-arthritis": ["INF"],
    "gout": ["INF"],
    "knee-effusion": ["INF", "TRM"],
}


def get_bucket_for_topic(url: str) -> list:
    """URL에서 버킷 태그 추출"""
    for keyword, buckets in TOPIC_BUCKET_MAP.items():
        if keyword in url.lower():
            return buckets
    # 기본값: 일반 정형외과 (OA가 가장 흔함)
    return ["OA"]


def main():
    print("=" * 60)
    print(" OrthoBullets 크롤링 시작")
    print("=" * 60)

    # 캐시 파일 경로
    cache_path = settings.data_dir / "crawled" / "orthobullets_cache.json"

    # 이미 캐시가 있으면 로드
    if cache_path.exists():
        print(f"\n[캐시 발견] {cache_path}")
        with open(cache_path, 'r', encoding='utf-8') as f:
            cached = json.load(f)
        print(f"  → 캐시된 문서: {len(cached)}개")

        # 사용자에게 재크롤링 여부 확인 (자동화를 위해 스킵)
        # 여기서는 캐시가 있으면 인덱싱만 진행
        return index_cached_data(cache_path)

    # OrthoBullets 크롤링
    print("\n[1] OrthoBullets 중요 토픽 크롤링...")

    # 중요 토픽 URL 가져오기 (무릎만)
    important_urls = get_important_topic_urls("knee")
    print(f"  → 대상 토픽: {len(important_urls)}개")

    articles = {}

    with OrthoBulletsCrawler(rate_limit_delay=2.0) as crawler:
        for i, url in enumerate(important_urls, 1):
            print(f"\n[{i}/{len(important_urls)}] {url}")

            article = crawler.fetch_article(url, body_part="knee")
            if article:
                # 버킷 태그 추가
                buckets = get_bucket_for_topic(url)
                article.category = ",".join(buckets)  # 버킷을 category에 저장

                articles[article.source_id] = asdict(article)
                print(f"  ✓ {article.title[:50]}...")
                print(f"    버킷: {buckets}")
                print(f"    Key Points: {len(article.key_points)}개")
            else:
                print(f"  ✗ 크롤링 실패")

    # 캐시 저장
    print(f"\n[2] 캐시 저장: {cache_path}")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(articles, f, ensure_ascii=False, indent=2)
    print(f"  → {len(articles)}개 문서 저장됨")

    # 인덱싱
    return index_cached_data(cache_path)


def index_cached_data(cache_path: Path) -> int:
    """캐시된 OrthoBullets 데이터 인덱싱"""
    from pinecone import Pinecone
    from openai import OpenAI

    from orthocare.data_ops.indexing import IndexingPipeline, IndexingConfig

    print("\n[3] 벡터 DB 인덱싱...")

    # 캐시 로드
    with open(cache_path, 'r', encoding='utf-8') as f:
        cached = json.load(f)

    if not cached:
        print("  ⚠ 인덱싱할 데이터 없음")
        return 0

    # OrthoBulletsArticle 객체 복원
    from orthocare.data_ops.crawlers import OrthoBulletsArticle

    articles = []
    for source_id, data in cached.items():
        try:
            article = OrthoBulletsArticle(**data)
            articles.append(article)
        except Exception as e:
            print(f"  ⚠ 복원 실패 ({source_id}): {e}")

    print(f"  → 복원된 문서: {len(articles)}개")

    # Pinecone 연결
    pc = Pinecone(api_key=settings.pinecone_api_key)
    index = pc.Index(settings.pinecone_index)
    openai_client = OpenAI()

    # 인덱싱 파이프라인
    pipeline = IndexingPipeline(
        pinecone_index=index,
        openai_client=openai_client,
        namespace="",
        config=IndexingConfig(show_progress=True),
    )

    # OrthoBullets 인덱싱
    results = pipeline.crawled_indexer.index_orthobullets_articles(articles)

    success = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)

    print(f"\n[완료] 인덱싱 결과")
    print(f"  → 성공: {success}개")
    print(f"  → 실패: {failed}개")

    # 최종 벡터 수 확인
    stats = index.describe_index_stats()
    print(f"  → 총 벡터 수: {stats.total_vector_count}")

    return success


if __name__ == "__main__":
    count = main()
    sys.exit(0 if count > 0 else 1)
