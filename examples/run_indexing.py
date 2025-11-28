#!/usr/bin/env python
"""벡터 DB 인덱싱 스크립트

운동 데이터와 논문을 Pinecone에 인덱싱

Usage:
    # 전체 인덱싱
    python examples/run_indexing.py

    # 운동만 인덱싱
    python examples/run_indexing.py --exercises-only

    # 논문만 인덱싱
    python examples/run_indexing.py --papers-only

    # 특정 부위만
    python examples/run_indexing.py --body-part knee

    # 통계만 조회
    python examples/run_indexing.py --stats-only
"""

import argparse
import sys
from pathlib import Path

# 프로젝트 루트 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from openai import OpenAI
from pinecone import Pinecone

from orthocare.config import settings
from orthocare.data_ops.indexing import (
    IndexingPipeline,
    IndexingConfig,
)


def create_clients():
    """OpenAI, Pinecone 클라이언트 생성"""
    openai_client = OpenAI(api_key=settings.openai_api_key)

    pc = Pinecone(api_key=settings.pinecone_api_key)

    # 호스트 직접 연결 또는 인덱스명으로 연결
    if settings.pinecone_host:
        pinecone_index = pc.Index(host=settings.pinecone_host)
    else:
        pinecone_index = pc.Index(settings.pinecone_index)

    return openai_client, pinecone_index


def main():
    parser = argparse.ArgumentParser(description="OrthoCare 벡터 DB 인덱싱")
    parser.add_argument("--exercises-only", action="store_true", help="운동만 인덱싱")
    parser.add_argument("--papers-only", action="store_true", help="논문만 인덱싱")
    parser.add_argument("--body-part", type=str, help="특정 부위만 인덱싱")
    parser.add_argument("--stats-only", action="store_true", help="통계만 조회")
    parser.add_argument("--namespace", type=str, default="", help="Pinecone 네임스페이스")
    parser.add_argument("--dry-run", action="store_true", help="실제 인덱싱 없이 테스트")

    args = parser.parse_args()

    print("OrthoCare 인덱싱 시작...")
    print(f"  Pinecone Index: {settings.pinecone_index}")
    print(f"  Namespace: {args.namespace or '(default)'}")
    print()

    # 클라이언트 생성
    openai_client, pinecone_index = create_clients()

    # 파이프라인 초기화
    config = IndexingConfig(
        namespace=args.namespace,
        show_progress=True,
    )

    pipeline = IndexingPipeline(
        pinecone_index=pinecone_index,
        openai_client=openai_client,
        namespace=args.namespace,
        config=config,
    )

    # 통계만 조회
    if args.stats_only:
        stats = pipeline.get_stats()
        print("Pinecone 인덱스 통계:")
        print(f"  총 벡터 수: {stats.get('total_vector_count', 'N/A')}")
        print(f"  차원: {stats.get('dimension', 'N/A')}")
        if 'namespaces' in stats:
            print("  네임스페이스별:")
            for ns, ns_stats in stats['namespaces'].items():
                print(f"    {ns or '(default)'}: {ns_stats.get('vector_count', 0)} 벡터")
        return

    # Dry run
    if args.dry_run:
        print("[Dry Run] 실제 인덱싱은 수행되지 않습니다.")
        print()

        # 데이터 확인만
        from orthocare.config import settings as s
        exercise_dir = s.data_dir / "exercise"
        medical_dir = s.data_dir / "medical"

        if exercise_dir.exists():
            for bp_dir in exercise_dir.iterdir():
                if bp_dir.is_dir():
                    ex_file = bp_dir / "exercises.json"
                    if ex_file.exists():
                        import json
                        with open(ex_file) as f:
                            data = json.load(f)
                        count = len(data.get("exercises", {}))
                        print(f"  [Exercise] {bp_dir.name}: {count}개 운동")

        if medical_dir.exists():
            for bp_dir in medical_dir.iterdir():
                if bp_dir.is_dir():
                    papers_dir = bp_dir / "papers" / "processed"
                    if papers_dir.exists():
                        count = len(list(papers_dir.glob("*_chunks.json")))
                        print(f"  [Papers] {bp_dir.name}: {count}개 논문")

        return

    # 인덱싱 실행
    results = {}

    if args.exercises_only:
        print("운동 데이터 인덱싱...")
        results["exercises"] = pipeline.index_all_exercises()

    elif args.papers_only:
        print("논문 데이터 인덱싱...")
        results["papers"] = pipeline.index_all_papers()

    else:
        # 전체 인덱싱
        results = pipeline.run_full_indexing()

    # 최종 통계
    print("\n최종 인덱스 상태:")
    stats = pipeline.get_stats()
    print(f"  총 벡터 수: {stats.get('total_vector_count', 'N/A')}")


if __name__ == "__main__":
    main()
