#!/usr/bin/env python3
"""벡터 DB 인덱싱 실행

운동 데이터를 Pinecone에 인덱싱합니다.

실행:
    python scripts/run_indexing.py
    python scripts/run_indexing.py --exercises-only
"""

import sys
from pathlib import Path

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orthocare.config import settings
from openai import OpenAI
from pinecone import Pinecone


def main():
    print("=" * 50)
    print("OrthoCare 벡터 DB 인덱싱")
    print("=" * 50)

    # 클라이언트 초기화
    print("\n[1] 클라이언트 연결...")
    openai_client = OpenAI(api_key=settings.openai_api_key)
    pc = Pinecone(api_key=settings.pinecone_api_key)

    # Pinecone 인덱스 연결
    if settings.pinecone_host:
        index = pc.Index(host=settings.pinecone_host)
    else:
        index = pc.Index(settings.pinecone_index)

    # 현재 상태 확인
    stats = index.describe_index_stats()
    print(f"  현재 벡터 수: {stats.total_vector_count:,}")
    print(f"  차원: {stats.dimension}")

    # 인덱싱 파이프라인 초기화
    print("\n[2] 인덱싱 파이프라인 초기화...")
    from orthocare.data_ops.indexing import IndexingPipeline, IndexingConfig

    config = IndexingConfig(
        namespace="",  # 기본 네임스페이스
        chunk_max_tokens=512,
        chunk_overlap_tokens=100,
        batch_size=50,
        show_progress=True,
    )

    pipeline = IndexingPipeline(
        pinecone_index=index,
        openai_client=openai_client,
        config=config,
    )

    # 전체 인덱싱 실행
    print("\n[3] 인덱싱 실행...")
    results = pipeline.run_full_indexing()

    # 결과 확인
    print("\n[4] 결과 확인...")
    final_stats = index.describe_index_stats()
    print(f"  최종 벡터 수: {final_stats.total_vector_count:,}")

    return results


if __name__ == "__main__":
    main()
