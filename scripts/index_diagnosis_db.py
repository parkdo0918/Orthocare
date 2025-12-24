"""진단용 벡터 DB 인덱싱 스크립트

벡터 DB: orthocare-diagnosis
소스: verified_paper, orthobullets, pubmed

사용법:
    PYTHONPATH=. python scripts/index_diagnosis_db.py
    PYTHONPATH=. python scripts/index_diagnosis_db.py --papers-only
    PYTHONPATH=. python scripts/index_diagnosis_db.py --clear-first
"""

import argparse
import json
import os
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(override=True)  # .env 파일 우선

from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI

# 설정 (환경변수 무시, 하드코딩)
PINECONE_INDEX = "orthocare-diagnosis"
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536
DATA_DIR = Path(__file__).parent.parent / "data"


def get_clients():
    """Pinecone, OpenAI 클라이언트 반환"""
    pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
    openai = OpenAI()
    return pc, openai


def ensure_index_exists(pc: Pinecone, recreate: bool = False):
    """인덱스 존재 확인 및 생성"""
    if PINECONE_INDEX in pc.list_indexes().names():
        if recreate:
            print(f"인덱스 '{PINECONE_INDEX}' 삭제 중...")
            pc.delete_index(PINECONE_INDEX)
            print(f"인덱스 '{PINECONE_INDEX}' 삭제 완료")
            import time
            time.sleep(5)  # 삭제 완료 대기
        else:
            print(f"인덱스 '{PINECONE_INDEX}' 이미 존재")
            return

    print(f"인덱스 '{PINECONE_INDEX}' 생성 중... (차원: {EMBEDDING_DIM})")
    pc.create_index(
        name=PINECONE_INDEX,
        dimension=EMBEDDING_DIM,
        metric="cosine",
        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
    )
    print(f"인덱스 '{PINECONE_INDEX}' 생성 완료")


def embed_text(openai: OpenAI, text: str) -> List[float]:
    """텍스트 임베딩"""
    response = openai.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def load_paper_metadata(body_part: str) -> Dict:
    """논문 메타데이터 로드"""
    metadata_path = DATA_DIR / "medical" / body_part / "papers" / "paper_metadata.json"
    if metadata_path.exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f).get("papers", {})
    return {}


def index_papers(pc: Pinecone, openai: OpenAI, body_part: str = "knee"):
    """논문 인덱싱"""
    print(f"\n=== 논문 인덱싱 ({body_part}) ===")

    index = pc.Index(PINECONE_INDEX)
    paper_metadata = load_paper_metadata(body_part)

    processed_dir = DATA_DIR / "medical" / body_part / "papers" / "processed"
    if not processed_dir.exists():
        print(f"처리된 논문 디렉토리 없음: {processed_dir}")
        return 0

    vectors = []
    for chunk_file in processed_dir.glob("*.json"):
        with open(chunk_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)

        for chunk in chunks:
            paper_id = chunk.get("paper_id", chunk_file.stem)
            paper_info = paper_metadata.get(paper_id, {})

            # 임베딩
            text = chunk.get("text", "")
            if not text:
                continue

            embedding = embed_text(openai, text)

            # 메타데이터
            bucket_tags = paper_info.get("buckets", [])
            source_type = paper_info.get("source_type", "verified_paper")

            metadata = {
                "body_part": body_part,
                "source": source_type,
                "bucket": ",".join(bucket_tags),
                "title": paper_info.get("title", chunk.get("title", "")),
                "text": text[:1000],  # Pinecone 메타데이터 제한
            }
            # year가 있을 때만 추가 (null 불허)
            if paper_info.get("year"):
                metadata["year"] = paper_info["year"]

            vec_id = f"paper_{paper_id}_{chunk.get('chunk_id', 0)}"
            vectors.append({
                "id": vec_id,
                "values": embedding,
                "metadata": metadata,
            })

    # 배치 업서트
    if vectors:
        batch_size = 100
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            index.upsert(vectors=batch)
            print(f"  업서트: {i + len(batch)}/{len(vectors)}")

    print(f"논문 인덱싱 완료: {len(vectors)}개")
    return len(vectors)


def index_orthobullets(pc: Pinecone, openai: OpenAI, body_part: str = None):
    """OrthoBullets 인덱싱

    Args:
        body_part: 특정 부위만 인덱싱 (None이면 모든 파일)
    """
    print("\n=== OrthoBullets 인덱싱 ===")

    index = pc.Index(PINECONE_INDEX)

    # OrthoBullets 캐시 파일들 찾기
    crawled_dir = DATA_DIR / "crawled"
    cache_files = []

    if body_part:
        # 특정 부위만
        if body_part == "knee":
            cache_files = [crawled_dir / "orthobullets_cache.json"]
        else:
            cache_files = [crawled_dir / f"orthobullets_{body_part}_cache.json"]
    else:
        # 모든 OrthoBullets 파일
        cache_files = list(crawled_dir.glob("orthobullets*.json"))

    total_vectors = []
    for cache_path in cache_files:
        if not cache_path.exists():
            print(f"OrthoBullets 캐시 없음: {cache_path}")
            continue

        print(f"  파일: {cache_path.name}")

        with open(cache_path, "r", encoding="utf-8") as f:
            articles = json.load(f)

        vectors = []
        for article_id, article in articles.items():
            content = article.get("content", "")
            if not content:
                continue

            embedding = embed_text(openai, content)

            metadata = {
                "body_part": article.get("body_part", "knee"),
                "source": "orthobullets",
                "bucket": article.get("category", ""),
                "title": article.get("title", ""),
                "text": content[:1000],
                "url": article.get("url", ""),
            }

            vectors.append({
                "id": f"orthobullets_{article_id}",
                "values": embedding,
                "metadata": metadata,
            })

        # 배치 업서트
        if vectors:
            index.upsert(vectors=vectors)
            print(f"    -> {len(vectors)}개 인덱싱")

        total_vectors.extend(vectors)

    print(f"OrthoBullets 인덱싱 완료: 총 {len(total_vectors)}개")
    return len(total_vectors)


def main():
    parser = argparse.ArgumentParser(description="진단용 벡터 DB 인덱싱")
    parser.add_argument("--papers-only", action="store_true", help="논문만 인덱싱")
    parser.add_argument("--orthobullets-only", action="store_true", help="OrthoBullets만 인덱싱")
    parser.add_argument("--clear-first", action="store_true", help="기존 데이터 삭제 후 인덱싱")
    parser.add_argument("--recreate-index", action="store_true", help="인덱스 삭제 후 재생성")
    parser.add_argument("--body-part", default="knee", help="부위 코드")
    args = parser.parse_args()

    print(f"=== 진단용 벡터 DB 인덱싱 시작 ({datetime.now()}) ===")
    print(f"인덱스: {PINECONE_INDEX}")
    print(f"임베딩 모델: {EMBEDDING_MODEL} (차원: {EMBEDDING_DIM})")

    pc, openai = get_clients()
    ensure_index_exists(pc, recreate=args.recreate_index)

    if args.clear_first:
        print("\n기존 데이터 삭제 중...")
        index = pc.Index(PINECONE_INDEX)
        index.delete(delete_all=True)
        print("삭제 완료")

    total = 0

    if not args.orthobullets_only:
        total += index_papers(pc, openai, args.body_part)

    if not args.papers_only:
        # body_part 인자가 없거나 특정 부위면 해당 부위만, all이면 모든 부위
        ob_body_part = None if args.body_part == "all" else args.body_part
        total += index_orthobullets(pc, openai, body_part=ob_body_part)

    print(f"\n=== 인덱싱 완료: 총 {total}개 벡터 ===")


if __name__ == "__main__":
    main()
