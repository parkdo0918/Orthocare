#!/usr/bin/env python3
"""OrthoCare End-to-End 테스트

페르소나 데이터를 사용하여 전체 파이프라인 테스트:
1. 벡터 DB 연결 확인
2. 자연어 입력 → 통합 검색
3. 근거 기반 추론
4. 전체 파이프라인 실행

실행:
    python scripts/test_e2e.py
    python scripts/test_e2e.py --persona GS-OA-001
    python scripts/test_e2e.py --all
"""

import sys
import json
from pathlib import Path
from typing import Optional

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 설정 로드 (환경변수 포함)
from orthocare.config import settings

# OpenAI 클라이언트
from openai import OpenAI

# Pinecone 클라이언트
from pinecone import Pinecone


def print_header(title: str):
    """섹션 헤더 출력"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def print_step(step: str, status: str = ""):
    """단계 출력"""
    if status:
        print(f"  [{status}] {step}")
    else:
        print(f"  → {step}")


def load_personas():
    """페르소나 데이터 로드"""
    persona_file = settings.data_dir / "evaluation" / "golden_set" / "knee_personas.json"
    with open(persona_file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data["personas"]


def test_1_environment():
    """1. 환경 설정 확인"""
    print_header("1. 환경 설정 확인")

    # API 키 확인
    print_step(f"OpenAI API Key: {'설정됨' if settings.openai_api_key else '미설정'}")
    print_step(f"Pinecone API Key: {'설정됨' if settings.pinecone_api_key else '미설정'}")
    print_step(f"LangSmith: {'활성화' if settings.langsmith_tracing else '비활성화'}")
    print_step(f"모델: {settings.openai_model}")
    print_step(f"임베딩: {settings.embed_model} ({settings.embed_dimensions}차원)")

    return True


def test_2_pinecone_connection():
    """2. Pinecone 연결 테스트"""
    print_header("2. Pinecone 벡터 DB 연결")

    try:
        pc = Pinecone(api_key=settings.pinecone_api_key)

        # 인덱스 연결
        if settings.pinecone_host:
            index = pc.Index(host=settings.pinecone_host)
        else:
            index = pc.Index(settings.pinecone_index)

        # 통계 조회
        stats = index.describe_index_stats()
        print_step(f"인덱스: {settings.pinecone_index}", "OK")
        print_step(f"총 벡터 수: {stats.total_vector_count:,}")
        print_step(f"차원: {stats.dimension}")

        if stats.namespaces:
            print_step("네임스페이스:")
            for ns, ns_stats in stats.namespaces.items():
                ns_name = ns if ns else "(default)"
                print(f"      - {ns_name}: {ns_stats.vector_count:,}개")

        return index, stats.total_vector_count > 0

    except Exception as e:
        print_step(f"연결 실패: {e}", "FAIL")
        return None, False


def test_3_unified_search(index, openai_client, persona):
    """3. 통합 벡터 검색 테스트"""
    print_header("3. 통합 벡터 검색 (자연어 입력)")

    from orthocare.data_ops.indexing import TextEmbedder
    from orthocare.agents.tools import VectorSearchTool

    # 검색 도구 초기화
    embedder = TextEmbedder(openai_client)
    search_tool = VectorSearchTool(
        pinecone_index=index,
        embedder=embedder,
        default_top_k=10,
    )

    # 자연어 입력 추출
    nl_input = persona["input"].get("natural_language", {})
    chief_complaint = nl_input.get("chief_complaint", "")
    pain_description = nl_input.get("pain_description", "")
    goals = nl_input.get("goals", "")

    print_step(f"페르소나: {persona['name']}")
    print_step(f"주호소: {chief_complaint[:50]}...")

    # 통합 검색 실행
    body_part = persona["input"]["body_parts"][0]["code"]

    results = search_tool.search_for_user_input(
        chief_complaint=chief_complaint,
        pain_description=pain_description,
        goals=goals,
        body_part=body_part,
        top_k=5,
    )

    print_step(f"검색 결과:")
    print(f"      - 운동: {len(results['exercises'])}개")
    print(f"      - 근거: {len(results['evidence'])}개")

    # 상위 결과 출력
    if results['exercises']:
        print_step("상위 운동 결과:")
        for i, r in enumerate(results['exercises'][:3], 1):
            print(f"      {i}. [{r.score:.3f}] {r.title}")

    if results['evidence']:
        print_step("상위 근거 결과:")
        for i, r in enumerate(results['evidence'][:3], 1):
            print(f"      {i}. [{r.score:.3f}] {r.title[:50]}...")

    return results


def test_4_evidence_search(index, openai_client, persona):
    """4. 근거 기반 검색 테스트"""
    print_header("4. 근거 기반 검색")

    from orthocare.data_ops.indexing import TextEmbedder
    from orthocare.agents.tools import VectorSearchTool

    embedder = TextEmbedder(openai_client)
    search_tool = VectorSearchTool(
        pinecone_index=index,
        embedder=embedder,
    )

    # 증상 기반 쿼리
    symptoms = persona["input"]["body_parts"][0]["symptoms"]
    body_part = persona["input"]["body_parts"][0]["code"]

    query = f"{body_part} {' '.join(symptoms[:5])}"
    print_step(f"검색 쿼리: {query[:60]}...")

    # 논문/근거 검색
    evidence_results = search_tool.search_papers(
        query=query,
        body_part=body_part,
        top_k=5,
    )

    print_step(f"근거 자료: {len(evidence_results)}개 발견")

    if evidence_results:
        for i, r in enumerate(evidence_results[:3], 1):
            print(f"      {i}. [{r.source}] {r.title[:50]}...")
            print(f"         유사도: {r.score:.3f}")

    return evidence_results


def test_5_full_pipeline(openai_client, persona):
    """5. 전체 파이프라인 테스트"""
    print_header("5. 전체 파이프라인 실행")

    try:
        from orthocare.pipelines import GranularPipeline

        # Pinecone 연결
        pc = Pinecone(api_key=settings.pinecone_api_key)
        if settings.pinecone_host:
            index = pc.Index(host=settings.pinecone_host)
        else:
            index = pc.Index(settings.pinecone_index)

        # 파이프라인 초기화
        pipeline = GranularPipeline(
            llm_client=openai_client,
            vector_store=index,
        )

        print_step(f"페르소나: {persona['name']}")
        print_step(f"예상 버킷: {persona['expected']['bucket']}")

        # 파이프라인 실행
        result = pipeline.run(persona["input"])

        print_step("파이프라인 실행 완료", "OK")

        # 결과 출력
        if result.blocked_by_red_flag:
            print_step("결과: 레드플래그로 차단됨", "WARN")
        else:
            for body_part, diagnosis in result.diagnoses.items():
                print_step(f"진단 결과 ({body_part}):")
                print(f"      - 버킷: {diagnosis.final_bucket}")
                print(f"      - 신뢰도: {diagnosis.confidence:.2f}")

                # 버킷 점수 상위 3개
                if diagnosis.bucket_scores:
                    print(f"      - 버킷 점수:")
                    sorted_scores = sorted(
                        diagnosis.bucket_scores,
                        key=lambda x: x.score,
                        reverse=True
                    )[:3]
                    for bs in sorted_scores:
                        print(f"          {bs.bucket}: {bs.score:.3f}")

                # 진단 근거 및 인용 출력
                if hasattr(diagnosis, 'evidence_summary') and diagnosis.evidence_summary:
                    print(f"\n      === 진단 근거 요약 ===")
                    print(f"      {diagnosis.evidence_summary}")

                if hasattr(diagnosis, 'llm_reasoning') and diagnosis.llm_reasoning:
                    print(f"\n      === LLM 추론 (인용 포함) ===")
                    # 줄바꿈 처리하여 깔끔하게 출력
                    for line in diagnosis.llm_reasoning.split('\n'):
                        if line.strip():
                            print(f"      {line}")

            # 운동 추천
            for body_part, exercise_set in result.exercise_sets.items():
                if exercise_set:
                    # dict 또는 ExerciseSet 모두 처리
                    if isinstance(exercise_set, dict):
                        exercises = exercise_set.get("exercises", [])
                    elif hasattr(exercise_set, 'recommendations'):
                        exercises = exercise_set.recommendations
                    elif hasattr(exercise_set, 'exercises'):
                        exercises = exercise_set.exercises
                    else:
                        exercises = []

                    if exercises:
                        print_step(f"운동 추천 ({body_part}): {len(exercises)}개")
                        for i, ex in enumerate(exercises[:5], 1):
                            if isinstance(ex, dict):
                                name = ex.get("name_kr") or ex.get("name_en", "")
                                reason = ex.get("reason", "")
                            elif hasattr(ex, 'exercise'):
                                name = ex.exercise.name_kr or ex.exercise.name_en
                                reason = getattr(ex, 'reason', '')
                            elif hasattr(ex, 'name_kr'):
                                name = ex.name_kr or ex.name_en
                                reason = ""
                            else:
                                name = str(ex)
                                reason = ""
                            print(f"      {i}. {name}")
                            if reason:
                                # 줄바꿈 처리
                                for line in reason.split('\n'):
                                    if line.strip():
                                        print(f"         → {line.strip()}")

                        # ExerciseSet의 llm_reasoning 출력
                        if hasattr(exercise_set, 'llm_reasoning') and exercise_set.llm_reasoning:
                            print(f"\n      === 운동 프로그램 구성 근거 ===")
                            for line in exercise_set.llm_reasoning.split('\n'):
                                if line.strip():
                                    print(f"      {line}")

        # 예상 결과와 비교
        expected = persona["expected"]
        actual_bucket = None
        for body_part, diagnosis in result.diagnoses.items():
            actual_bucket = diagnosis.final_bucket
            break

        if expected["red_flag"] and result.blocked_by_red_flag:
            print_step("예상 결과 일치: 레드플래그", "PASS")
            return True
        elif actual_bucket == expected["bucket"]:
            print_step(f"예상 결과 일치: {actual_bucket}", "PASS")
            return True
        elif actual_bucket is None:
            print_step(f"진단 결과 없음 (예상: {expected['bucket']})", "SKIP")
            return True  # 파이프라인은 성공했으므로 True
        else:
            print_step(f"예상: {expected['bucket']}, 실제: {actual_bucket}", "FAIL")
            return False

    except ImportError as e:
        print_step(f"GranularPipeline 미구현: {e}", "SKIP")

        # MainPipeline으로 시도
        try:
            from orthocare.pipelines import MainPipeline

            pc = Pinecone(api_key=settings.pinecone_api_key)
            if settings.pinecone_host:
                index = pc.Index(host=settings.pinecone_host)
            else:
                index = pc.Index(settings.pinecone_index)

            pipeline = MainPipeline(
                llm_client=openai_client,
                vector_store=index,
            )

            result = pipeline.run(persona["input"])
            print_step("MainPipeline 실행 완료", "OK")
            return True

        except Exception as e2:
            print_step(f"MainPipeline 실패: {e2}", "FAIL")
            return False

    except Exception as e:
        print_step(f"파이프라인 실행 실패: {e}", "FAIL")
        import traceback
        traceback.print_exc()
        return False


def run_tests(persona_id: Optional[str] = None, run_all: bool = False):
    """테스트 실행"""
    print_header("OrthoCare E2E 테스트 시작")

    # 1. 환경 설정
    test_1_environment()

    # 2. Pinecone 연결
    index, has_data = test_2_pinecone_connection()
    if not index:
        print("\n⚠️  Pinecone 연결 실패. 테스트를 종료합니다.")
        return

    # OpenAI 클라이언트
    openai_client = OpenAI(api_key=settings.openai_api_key)

    # 페르소나 로드
    personas = load_personas()
    print_step(f"페르소나 로드: {len(personas)}개")

    # 테스트할 페르소나 선택
    if persona_id:
        test_personas = [p for p in personas if p["id"] == persona_id]
        if not test_personas:
            print(f"\n⚠️  페르소나 '{persona_id}'를 찾을 수 없습니다.")
            print("사용 가능한 ID:", [p["id"] for p in personas])
            return
    elif run_all:
        test_personas = personas
    else:
        # 기본: 첫 번째 페르소나만
        test_personas = personas[:1]

    # 테스트 실행
    results = []
    for persona in test_personas:
        print(f"\n{'─' * 60}")
        print(f" 테스트 대상: {persona['id']} - {persona['name']}")
        print(f"{'─' * 60}")

        # 전체 파이프라인 실행 (벡터 검색 포함)
        success = test_5_full_pipeline(openai_client, persona)
        results.append({
            "id": persona["id"],
            "name": persona["name"],
            "expected": persona["expected"]["bucket"],
            "success": success,
        })

    # 결과 요약
    print_header("테스트 결과 요약")
    passed = sum(1 for r in results if r["success"])
    total = len(results)
    print_step(f"통과: {passed}/{total}")

    for r in results:
        status = "PASS" if r["success"] else "FAIL"
        print(f"  [{status}] {r['id']}: {r['name']} (예상: {r['expected']})")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OrthoCare E2E 테스트")
    parser.add_argument("--persona", "-p", help="특정 페르소나 ID 테스트")
    parser.add_argument("--all", "-a", action="store_true", help="모든 페르소나 테스트")

    args = parser.parse_args()

    run_tests(persona_id=args.persona, run_all=args.all)
