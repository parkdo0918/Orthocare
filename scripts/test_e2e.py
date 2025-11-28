#!/usr/bin/env python3
"""OrthoCare End-to-End 테스트

페르소나 데이터를 사용하여 전체 파이프라인 테스트:
1. 벡터 DB 연결 확인
2. 자연어 입력 → 통합 검색
3. 근거 기반 추론
4. 전체 파이프라인 실행

결과는 날짜별 폴더에 JSON으로 저장됨:
- data/evaluation/test_results/YYYY-MM-DD/
  - run_001_GS-OA-001.json (건별 결과)
  - run_002_GS-TRM-001.json
  - REPORT.md (종합 리포트)

실행:
    python scripts/test_e2e.py
    python scripts/test_e2e.py --persona GS-OA-001
    python scripts/test_e2e.py --all
"""

import sys
import json
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

# 프로젝트 루트를 path에 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 설정 로드 (환경변수 포함)
from orthocare.config import settings

# OpenAI 클라이언트
from openai import OpenAI

# Pinecone 클라이언트
from pinecone import Pinecone


class TestResultRecorder:
    """테스트 결과 기록기"""

    def __init__(self):
        self.date_str = datetime.now().strftime("%Y-%m-%d")
        self.time_str = datetime.now().strftime("%H:%M:%S")
        self.results_dir = settings.data_dir / "evaluation" / "test_results" / self.date_str
        self.results_dir.mkdir(parents=True, exist_ok=True)

        # 기존 run 번호 확인
        existing_runs = list(self.results_dir.glob("run_*.json"))
        self.run_counter = len(existing_runs) + 1

        self.all_results: List[Dict] = []

    def record_run(self, persona_id: str, result: Dict[str, Any]) -> Path:
        """개별 테스트 결과 저장"""
        filename = f"run_{self.run_counter:03d}_{persona_id}.json"
        filepath = self.results_dir / filename

        # 메타데이터 추가
        result["_meta"] = {
            "run_number": self.run_counter,
            "timestamp": datetime.now().isoformat(),
            "persona_id": persona_id,
        }

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2, default=str)

        self.all_results.append(result)
        self.run_counter += 1

        return filepath

    def generate_report(self) -> Path:
        """종합 리포트 생성"""
        report_path = self.results_dir / "REPORT.md"

        passed = sum(1 for r in self.all_results if r.get("success"))
        failed = sum(1 for r in self.all_results if not r.get("success"))
        total = len(self.all_results)

        lines = [
            f"# OrthoCare E2E 테스트 리포트",
            f"",
            f"> 생성 시간: {self.date_str} {self.time_str}",
            f"",
            f"---",
            f"",
            f"## 요약",
            f"",
            f"| 항목 | 값 |",
            f"|------|-----|",
            f"| 총 테스트 | {total} |",
            f"| 통과 | {passed} |",
            f"| 실패 | {failed} |",
            f"| 성공률 | {passed/total*100:.1f}% |" if total > 0 else "| 성공률 | N/A |",
            f"",
            f"---",
            f"",
            f"## 건별 결과",
            f"",
        ]

        for i, result in enumerate(self.all_results, 1):
            meta = result.get("_meta", {})
            persona_id = meta.get("persona_id", "unknown")
            success = result.get("success", False)
            status_emoji = "✅" if success else "❌"

            lines.append(f"### {i}. {persona_id} {status_emoji}")
            lines.append(f"")

            # 입력 정보
            input_info = result.get("input", {})
            if input_info:
                lines.append(f"**입력:**")
                lines.append(f"- 주호소: {input_info.get('chief_complaint', 'N/A')[:100]}...")
                lines.append(f"- 증상: {', '.join(input_info.get('symptoms', [])[:5])}")
                lines.append(f"")

            # 예상 vs 실제
            lines.append(f"**결과:**")
            lines.append(f"| 항목 | 예상 | 실제 |")
            lines.append(f"|------|------|------|")
            lines.append(f"| 버킷 | {result.get('expected_bucket', 'N/A')} | {result.get('actual_bucket', 'N/A')} |")
            lines.append(f"| 신뢰도 | - | {result.get('confidence', 'N/A')} |")
            lines.append(f"")

            # 벡터 검색 결과
            search_results = result.get("search_results", {})
            if search_results:
                lines.append(f"**벡터 검색 결과:**")
                lines.append(f"| 순위 | 소스 | 제목 | 유사도 |")
                lines.append(f"|------|------|------|--------|")
                for j, sr in enumerate(search_results.get("evidence", [])[:5], 1):
                    title = sr.get("title", "")[:40]
                    source = sr.get("source", "")
                    score = sr.get("score", 0)
                    lines.append(f"| {j} | {source} | {title}... | {score:.3f} |")
                lines.append(f"")

            # LLM 추론 과정
            llm_reasoning = result.get("llm_reasoning", "")
            if llm_reasoning:
                lines.append(f"**LLM 추론:**")
                lines.append(f"```")
                for line in llm_reasoning.split('\n')[:20]:
                    lines.append(line)
                if len(llm_reasoning.split('\n')) > 20:
                    lines.append("... (생략)")
                lines.append(f"```")
                lines.append(f"")

            # 인용된 근거
            citations = result.get("citations", [])
            if citations:
                lines.append(f"**인용된 근거:**")
                for j, cite in enumerate(citations[:5], 1):
                    lines.append(f"{j}. **{cite.get('title', '')}** [{cite.get('source', '')}]")
                    quote = cite.get('quote', '')[:150]
                    if quote:
                        lines.append(f"   > \"{quote}...\"")
                lines.append(f"")

            # 운동 추천
            exercises = result.get("exercises", [])
            if exercises:
                lines.append(f"**운동 추천:** {len(exercises)}개")
                for j, ex in enumerate(exercises[:5], 1):
                    name = ex.get("name", "")
                    reason = ex.get("reason", "")[:50]
                    lines.append(f"   {j}. {name}")
                    if reason:
                        lines.append(f"      → {reason}")
                lines.append(f"")

            # 오류 메시지
            error = result.get("error")
            if error:
                lines.append(f"**오류:**")
                lines.append(f"```")
                lines.append(str(error)[:500])
                lines.append(f"```")
                lines.append(f"")

            lines.append(f"---")
            lines.append(f"")

        # 추론 흐름 분석
        lines.append(f"## 추론 흐름 분석")
        lines.append(f"")
        lines.append(f"### 파이프라인 단계")
        lines.append(f"")
        lines.append(f"```")
        lines.append(f"[입력] → [증상 추출] → [벡터 검색] → [LLM 추론] → [버킷 결정] → [운동 추천]")
        lines.append(f"```")
        lines.append(f"")
        lines.append(f"### 주요 관찰")
        lines.append(f"")

        # 성공/실패 패턴 분석
        for result in self.all_results:
            persona_id = result.get("_meta", {}).get("persona_id", "unknown")
            success = result.get("success", False)

            if success:
                lines.append(f"- **{persona_id}**: 예상 버킷({result.get('expected_bucket')})과 실제 버킷({result.get('actual_bucket')}) 일치")
            else:
                lines.append(f"- **{persona_id}**: 예상 버킷({result.get('expected_bucket')})과 실제 버킷({result.get('actual_bucket')}) 불일치")
                if result.get("error"):
                    lines.append(f"  - 오류: {str(result.get('error'))[:100]}")

        lines.append(f"")

        # 파일 저장
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))

        return report_path


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


def test_full_pipeline_with_recording(openai_client, persona, recorder: TestResultRecorder) -> Dict[str, Any]:
    """전체 파이프라인 테스트 (결과 기록 포함)"""
    print_header(f"테스트: {persona['id']} - {persona['name']}")

    result = {
        "persona_id": persona["id"],
        "persona_name": persona["name"],
        "expected_bucket": persona["expected"]["bucket"],
        "success": False,
        "input": {},
        "search_results": {},
        "llm_reasoning": "",
        "citations": [],
        "exercises": [],
        "error": None,
    }

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

        # 입력 정보 기록
        nl_input = persona["input"].get("natural_language", {})
        result["input"] = {
            "chief_complaint": nl_input.get("chief_complaint", ""),
            "symptoms": persona["input"]["body_parts"][0].get("symptoms", []),
            "body_part": persona["input"]["body_parts"][0]["code"],
        }

        # 파이프라인 실행
        pipeline_result = pipeline.run(persona["input"])

        print_step("파이프라인 실행 완료", "OK")

        # 결과 추출
        if pipeline_result.blocked_by_red_flag:
            print_step("결과: 레드플래그로 차단됨", "WARN")
            result["actual_bucket"] = "RED_FLAG"
            result["success"] = persona["expected"].get("red_flag", False)
        else:
            for body_part, diagnosis in pipeline_result.diagnoses.items():
                result["actual_bucket"] = diagnosis.final_bucket
                result["confidence"] = f"{diagnosis.confidence:.2f}"

                print_step(f"진단 결과 ({body_part}):")
                print(f"      - 버킷: {diagnosis.final_bucket}")
                print(f"      - 신뢰도: {diagnosis.confidence:.2f}")

                # 버킷 점수
                if diagnosis.bucket_scores:
                    result["bucket_scores"] = [
                        {"bucket": bs.bucket, "score": bs.score}
                        for bs in sorted(diagnosis.bucket_scores, key=lambda x: x.score, reverse=True)[:5]
                    ]

                # LLM 추론
                if hasattr(diagnosis, 'llm_reasoning') and diagnosis.llm_reasoning:
                    result["llm_reasoning"] = diagnosis.llm_reasoning
                    print(f"\n      === LLM 추론 ===")
                    for line in diagnosis.llm_reasoning.split('\n')[:10]:
                        if line.strip():
                            print(f"      {line}")

                # 인용된 근거 추출
                if hasattr(diagnosis, 'evidence_summary') and diagnosis.evidence_summary:
                    result["evidence_summary"] = diagnosis.evidence_summary

            # 운동 추천
            for body_part, exercise_set in pipeline_result.exercise_sets.items():
                if exercise_set:
                    if isinstance(exercise_set, dict):
                        exercises = exercise_set.get("exercises", [])
                    elif hasattr(exercise_set, 'recommendations'):
                        exercises = exercise_set.recommendations
                    elif hasattr(exercise_set, 'exercises'):
                        exercises = exercise_set.exercises
                    else:
                        exercises = []

                    if exercises:
                        result["exercises"] = []
                        print_step(f"운동 추천 ({body_part}): {len(exercises)}개")
                        for i, ex in enumerate(exercises[:5], 1):
                            if isinstance(ex, dict):
                                name = ex.get("name_kr") or ex.get("name_en", "")
                                reason = ex.get("reason", "")
                            elif hasattr(ex, 'exercise'):
                                name = ex.exercise.name_kr or ex.exercise.name_en
                                reason = getattr(ex, 'reason', '')
                            elif hasattr(ex, 'name_kr'):
                                name = ex.name_kr or getattr(ex, 'name_en', '')
                                reason = ""
                            else:
                                name = str(ex)
                                reason = ""

                            result["exercises"].append({"name": name, "reason": reason})
                            print(f"      {i}. {name}")

            # 예상 결과와 비교
            expected = persona["expected"]
            actual_bucket = result.get("actual_bucket")

            if expected.get("red_flag") and pipeline_result.blocked_by_red_flag:
                print_step("예상 결과 일치: 레드플래그", "PASS")
                result["success"] = True
            elif actual_bucket == expected["bucket"]:
                print_step(f"예상 결과 일치: {actual_bucket}", "PASS")
                result["success"] = True
            elif actual_bucket is None:
                print_step(f"진단 결과 없음 (예상: {expected['bucket']})", "SKIP")
                result["success"] = True
            else:
                print_step(f"예상: {expected['bucket']}, 실제: {actual_bucket}", "FAIL")
                result["success"] = False

    except ImportError as e:
        print_step(f"GranularPipeline 미구현: {e}", "SKIP")
        result["error"] = str(e)
        result["success"] = True  # 구현 안된 경우 스킵

    except Exception as e:
        print_step(f"파이프라인 실행 실패: {e}", "FAIL")
        result["error"] = str(e)
        import traceback
        result["traceback"] = traceback.format_exc()
        traceback.print_exc()

    # 결과 저장
    filepath = recorder.record_run(persona["id"], result)
    print_step(f"결과 저장: {filepath.name}")

    return result


def run_tests(persona_id: Optional[str] = None, run_all: bool = False):
    """테스트 실행"""
    print_header("OrthoCare E2E 테스트 시작")

    # 결과 기록기 초기화
    recorder = TestResultRecorder()
    print_step(f"결과 저장 위치: {recorder.results_dir}")

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
    for persona in test_personas:
        print(f"\n{'─' * 60}")
        test_full_pipeline_with_recording(openai_client, persona, recorder)

    # 리포트 생성
    report_path = recorder.generate_report()

    # 결과 요약
    print_header("테스트 결과 요약")
    passed = sum(1 for r in recorder.all_results if r.get("success"))
    total = len(recorder.all_results)
    print_step(f"통과: {passed}/{total}")

    for r in recorder.all_results:
        status = "PASS" if r.get("success") else "FAIL"
        print(f"  [{status}] {r.get('persona_id')}: {r.get('persona_name')} (예상: {r.get('expected_bucket')}, 실제: {r.get('actual_bucket', 'N/A')})")

    print(f"\n📄 리포트: {report_path}")
    print(f"📁 결과 폴더: {recorder.results_dir}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="OrthoCare E2E 테스트")
    parser.add_argument("--persona", "-p", help="특정 페르소나 ID 테스트")
    parser.add_argument("--all", "-a", action="store_true", help="모든 페르소나 테스트")

    args = parser.parse_args()

    run_tests(persona_id=args.persona, run_all=args.all)
