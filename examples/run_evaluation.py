"""평가 실행 예제"""

import argparse
from pathlib import Path

# config를 먼저 import하여 .env 로드 및 LangSmith 환경변수 설정
import orthocare.config  # noqa: F401

from orthocare.pipelines import MainPipeline
from orthocare.evaluation import PipelineEvaluator
from orthocare.evaluation.metrics import ConfusionMatrix


def create_llm_client():
    """OpenAI 클라이언트 생성"""
    from openai import OpenAI
    return OpenAI()


def create_vector_store():
    """Pinecone 벡터 스토어 생성"""
    from pinecone import Pinecone
    from orthocare.config import settings

    pc = Pinecone(api_key=settings.pinecone_api_key)

    # 호스트가 설정되어 있으면 직접 연결, 아니면 인덱스명으로 조회
    if settings.pinecone_host:
        return pc.Index(host=settings.pinecone_host)
    else:
        return pc.Index(settings.pinecone_index)


def main():
    parser = argparse.ArgumentParser(description="OrthoCare 파이프라인 평가")
    parser.add_argument(
        "--full",
        action="store_true",
        help="전체 파이프라인 실행 (LLM + 벡터검색 포함)"
    )
    parser.add_argument(
        "--llm-only",
        action="store_true",
        help="LLM만 사용 (벡터검색 없음)"
    )
    args = parser.parse_args()

    llm_client = None
    vector_store = None

    if args.full:
        print("전체 파이프라인 모드 (LLM + 벡터검색)")
        llm_client = create_llm_client()
        try:
            vector_store = create_vector_store()
        except Exception as e:
            print(f"벡터스토어 연결 실패: {e}")
            print("LLM만 사용하여 진행합니다.")
    elif args.llm_only:
        print("LLM 모드 (벡터검색 없음)")
        llm_client = create_llm_client()
    else:
        print("가중치 기반 테스트 모드 (LLM 없음)")

    pipeline = MainPipeline(llm_client=llm_client, vector_store=vector_store)

    # 평가기 초기화
    golden_set_path = Path("data/evaluation/golden_set/knee_personas.json")
    evaluator = PipelineEvaluator(pipeline, golden_set_path)

    # 평가 실행
    report = evaluator.run_all()

    # 요약 출력
    evaluator.print_summary(report)

    # 혼동 행렬
    results = [
        type("R", (), {
            "expected_bucket": r["expected_bucket"],
            "actual_bucket": r["actual_bucket"],
            "passed": r["passed"],
        })()
        for r in report["detailed_results"]
    ]

    cm = ConfusionMatrix.from_results(results)
    cm.print_matrix()

    # 클래스별 메트릭
    print("\n클래스별 메트릭:")
    per_class = cm.get_per_class_metrics()
    for bucket, m in per_class.items():
        print(f"  {bucket}: P={m['precision']:.2f} R={m['recall']:.2f} F1={m['f1']:.2f}")


if __name__ == "__main__":
    main()
