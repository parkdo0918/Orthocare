"""LangGraph 기반 버킷 추론 파이프라인

기존 inference_pipeline.py와 동일한 기능을 LangGraph로 구현
- 상태 자동 관리
- 조건부 분기 (Red Flag, Discrepancy)
- 시각화 지원 (LangGraph Studio)
- 체크포인트/재시도 지원

v1.0: 파일럿 구현
"""

from typing import Dict, List, Optional, Annotated, TypedDict, Literal
from datetime import datetime
import operator

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langsmith import traceable

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.config import BodyPartConfig, BodyPartConfigLoader
from shared.models import BodyPartInput
from bucket_inference.models import (
    BucketInferenceInput,
    BucketInferenceOutput,
    BucketScore,
    DiscrepancyAlert,
    RedFlagResult,
)
from bucket_inference.services import (
    WeightService,
    EvidenceSearchService,
    RankingMerger,
    BucketArbitrator,
)
from bucket_inference.services.evidence_search import EvidenceResult
from bucket_inference.config import settings


# =============================================================================
# State Definition
# =============================================================================

class BucketInferenceState(TypedDict):
    """버킷 추론 파이프라인 상태

    LangGraph가 자동으로 상태를 관리하며,
    각 노드는 필요한 필드만 업데이트하면 됨
    """
    # === 입력 ===
    input_data: BucketInferenceInput
    current_body_part: BodyPartInput
    body_part_code: str

    # === 설정 ===
    bp_config: Optional[BodyPartConfig]

    # === 중간 결과 ===
    bucket_scores: Optional[List[BucketScore]]
    weight_ranking: Optional[List[str]]
    search_query: Optional[str]
    evidence: Optional[EvidenceResult]
    search_ranking: Optional[List[str]]
    merged_ranking: Optional[List[str]]

    # === 분석 결과 ===
    discrepancy: Optional[DiscrepancyAlert]
    red_flag: Optional[RedFlagResult]
    has_red_flag: bool
    has_discrepancy: bool

    # === 출력 ===
    final_result: Optional[BucketInferenceOutput]
    error: Optional[str]

    # === 메타데이터 ===
    started_at: Optional[datetime]
    completed_at: Optional[datetime]


# =============================================================================
# Node Functions
# =============================================================================

class BucketInferenceNodes:
    """버킷 추론 노드 모음

    각 노드는 State를 받아 업데이트된 부분만 반환
    """

    def __init__(self):
        self.weight_service = WeightService()
        self.evidence_service = EvidenceSearchService()
        self.ranking_merger = RankingMerger()
        self.bucket_arbitrator = BucketArbitrator()
        BodyPartConfigLoader.set_data_dir(settings.data_dir)

    @traceable(name="node_load_config")
    def load_config(self, state: BucketInferenceState) -> Dict:
        """Step 0: 부위별 설정 로드"""
        bp_code = state["body_part_code"]
        bp_config = BodyPartConfigLoader.load(bp_code)

        return {
            "bp_config": bp_config,
            "started_at": datetime.now(),
        }

    @traceable(name="node_calculate_weights")
    def calculate_weights(self, state: BucketInferenceState) -> Dict:
        """Step 1: 가중치 기반 버킷 점수 계산 (Path A)"""
        body_part = state["current_body_part"]
        bp_config = state["bp_config"]

        bucket_scores, weight_ranking = self.weight_service.calculate_scores(
            body_part,
            bp_config=bp_config,
        )

        return {
            "bucket_scores": bucket_scores,
            "weight_ranking": weight_ranking,
        }

    @traceable(name="node_build_search_query")
    def build_search_query(self, state: BucketInferenceState) -> Dict:
        """Step 2a: 검색 쿼리 구성"""
        body_part = state["current_body_part"]
        input_data = state["input_data"]
        demo = input_data.demographics

        symptoms = body_part.symptoms[:5]
        query = f"{demo.age}세 {demo.sex} 환자, 증상: {', '.join(symptoms)}"

        if input_data.natural_language and input_data.natural_language.has_content:
            nl_text = input_data.natural_language.to_text()
            query += f"\n{nl_text}"

        return {"search_query": query}

    @traceable(name="node_search_evidence")
    def search_evidence(self, state: BucketInferenceState) -> Dict:
        """Step 2b: 벡터 검색 수행 (Path B)"""
        query = state["search_query"]
        bp_code = state["body_part_code"]

        evidence = self.evidence_service.search(
            query=query,
            body_part=bp_code,
        )
        search_ranking = self.evidence_service.get_search_ranking(evidence)

        return {
            "evidence": evidence,
            "search_ranking": search_ranking,
        }

    @traceable(name="node_merge_rankings")
    def merge_rankings(self, state: BucketInferenceState) -> Dict:
        """Step 3: 랭킹 통합"""
        weight_ranking = state["weight_ranking"]
        search_ranking = state["search_ranking"]

        merged_ranking = self.ranking_merger.merge(weight_ranking, search_ranking)

        return {"merged_ranking": merged_ranking}

    @traceable(name="node_detect_discrepancy")
    def detect_discrepancy(self, state: BucketInferenceState) -> Dict:
        """Step 4a: 불일치 감지"""
        weight_ranking = state["weight_ranking"]
        search_ranking = state["search_ranking"]

        discrepancy = None
        has_discrepancy = False

        if search_ranking:
            # 상위 버킷 불일치
            if weight_ranking[0] != search_ranking[0]:
                discrepancy = DiscrepancyAlert(
                    type="top_bucket_mismatch",
                    weight_ranking=weight_ranking,
                    search_ranking=search_ranking,
                    message=(
                        f"가중치 순위({weight_ranking[0]})와 "
                        f"검색 순위({search_ranking[0]})가 불일치합니다. "
                        "LLM이 증상을 재검토하여 결정합니다."
                    ),
                    severity="warning",
                )
                has_discrepancy = True
            else:
                # 2위 이상 차이 감지
                for i, bucket in enumerate(weight_ranking):
                    if bucket in search_ranking:
                        search_idx = search_ranking.index(bucket)
                        if abs(i - search_idx) >= 2:
                            discrepancy = DiscrepancyAlert(
                                type="ranking_shift",
                                weight_ranking=weight_ranking,
                                search_ranking=search_ranking,
                                message=(
                                    f"{bucket} 버킷의 순위가 크게 다릅니다. "
                                    f"(가중치: {i+1}위, 검색: {search_idx+1}위)"
                                ),
                                severity="warning",
                            )
                            has_discrepancy = True
                            break

        return {
            "discrepancy": discrepancy,
            "has_discrepancy": has_discrepancy,
        }

    @traceable(name="node_check_red_flag")
    def check_red_flag(self, state: BucketInferenceState) -> Dict:
        """Step 4b: Red Flag 체크"""
        body_part = state["current_body_part"]
        bp_config = state["bp_config"]

        # Red Flag 체크 로직
        red_flag = None
        has_red_flag = False

        if body_part.red_flags_checked:
            # 실제 red flag 룰 적용
            red_flag_rules = bp_config.red_flags if bp_config else {}
            triggered_flags = []
            messages = []

            for flag_code in body_part.red_flags_checked:
                if flag_code in red_flag_rules:
                    triggered_flags.append(flag_code)
                    rule = red_flag_rules[flag_code]
                    messages.append(rule.get("message", f"Red Flag: {flag_code}"))

            if triggered_flags:
                red_flag = RedFlagResult(
                    triggered=True,
                    flags=triggered_flags,
                    messages=messages,
                    action="전문의 상담 권장",
                )
                has_red_flag = True

        return {
            "red_flag": red_flag,
            "has_red_flag": has_red_flag,
        }

    @traceable(name="node_llm_arbitration")
    def llm_arbitration(self, state: BucketInferenceState) -> Dict:
        """Step 5: LLM 버킷 중재"""
        result = self.bucket_arbitrator.arbitrate(
            body_part=state["current_body_part"],
            bucket_scores=state["bucket_scores"],
            weight_ranking=state["weight_ranking"],
            search_ranking=state["search_ranking"],
            evidence=state["evidence"],
            user_input=state["input_data"],
            red_flag=state["red_flag"],
            bp_config=state["bp_config"],
        )

        return {
            "final_result": result,
            "completed_at": datetime.now(),
        }

    @traceable(name="node_generate_red_flag_response")
    def generate_red_flag_response(self, state: BucketInferenceState) -> Dict:
        """Red Flag 감지 시 경고 응답 생성"""
        bucket_scores = state["bucket_scores"]
        weight_ranking = state["weight_ranking"]
        red_flag = state["red_flag"]
        bp_config = state["bp_config"]

        # Red Flag가 있어도 기본 추론 결과는 제공
        result = BucketInferenceOutput(
            body_part=state["body_part_code"],
            final_bucket=weight_ranking[0] if weight_ranking else bp_config.bucket_order[0],
            confidence=0.5,  # Red Flag로 인한 낮은 신뢰도
            bucket_scores={bs.bucket: bs.score for bs in bucket_scores} if bucket_scores else {},
            weight_ranking=weight_ranking or [],
            search_ranking=state["search_ranking"] or [],
            discrepancy=state["discrepancy"],
            evidence_summary="Red Flag 감지로 인해 전문의 상담이 필요합니다.",
            llm_reasoning=(
                f"### Red Flag 감지\n\n"
                f"다음 위험 신호가 감지되었습니다:\n"
                f"- {', '.join(red_flag.messages)}\n\n"
                f"**권장 조치**: {red_flag.action}"
            ),
            red_flag=red_flag,
        )

        return {
            "final_result": result,
            "completed_at": datetime.now(),
        }


# =============================================================================
# Graph Builder
# =============================================================================

def build_bucket_inference_graph(
    checkpointer: Optional[MemorySaver] = None,
) -> StateGraph:
    """버킷 추론 LangGraph 구성

    그래프 구조:
    ```
    [START]
        │
        ▼
    load_config
        │
        ├──────────────────────────┐
        ▼                          ▼
    calculate_weights         build_search_query
        │                          │
        │                          ▼
        │                    search_evidence
        │                          │
        └──────────┬───────────────┘
                   ▼
            merge_rankings
                   │
           ┌───────┴───────┐
           ▼               ▼
    detect_discrepancy  check_red_flag
           │               │
           └───────┬───────┘
                   ▼
            ┌──────┴──────┐
            │ has_red_flag?│
            └──────┬──────┘
                   │
        ┌──────────┼──────────┐
        ▼          │          ▼
    red_flag_resp  │   llm_arbitration
        │          │          │
        └──────────┴──────────┘
                   ▼
                 [END]
    ```
    """
    nodes = BucketInferenceNodes()

    # 그래프 생성
    graph = StateGraph(BucketInferenceState)

    # 노드 추가
    graph.add_node("load_config", nodes.load_config)
    graph.add_node("calculate_weights", nodes.calculate_weights)
    graph.add_node("build_search_query", nodes.build_search_query)
    graph.add_node("search_evidence", nodes.search_evidence)
    graph.add_node("merge_rankings", nodes.merge_rankings)
    graph.add_node("detect_discrepancy", nodes.detect_discrepancy)
    graph.add_node("check_red_flag", nodes.check_red_flag)
    graph.add_node("llm_arbitration", nodes.llm_arbitration)
    graph.add_node("red_flag_response", nodes.generate_red_flag_response)

    # 엣지 정의
    graph.set_entry_point("load_config")

    # load_config → calculate_weights (순차)
    graph.add_edge("load_config", "calculate_weights")

    # calculate_weights → build_search_query (순차)
    graph.add_edge("calculate_weights", "build_search_query")

    # build_search_query → search_evidence
    graph.add_edge("build_search_query", "search_evidence")

    # search_evidence → merge_rankings
    graph.add_edge("search_evidence", "merge_rankings")

    # merge_rankings → detect_discrepancy
    graph.add_edge("merge_rankings", "detect_discrepancy")

    # detect_discrepancy → check_red_flag
    graph.add_edge("detect_discrepancy", "check_red_flag")

    # check_red_flag → 조건부 분기
    def route_after_red_flag_check(state: BucketInferenceState) -> Literal["llm_arbitration", "red_flag_response"]:
        """Red Flag 여부에 따른 분기"""
        if state.get("has_red_flag", False):
            return "red_flag_response"
        return "llm_arbitration"

    graph.add_conditional_edges(
        "check_red_flag",
        route_after_red_flag_check,
        {
            "llm_arbitration": "llm_arbitration",
            "red_flag_response": "red_flag_response",
        },
    )

    # 종료 노드
    graph.add_edge("llm_arbitration", END)
    graph.add_edge("red_flag_response", END)

    # 컴파일
    if checkpointer:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()


# =============================================================================
# Pipeline Class (기존 인터페이스 호환)
# =============================================================================

class LangGraphBucketInferencePipeline:
    """LangGraph 기반 버킷 추론 파이프라인

    기존 BucketInferencePipeline과 동일한 인터페이스 제공
    """

    def __init__(self, use_checkpointer: bool = False):
        """
        Args:
            use_checkpointer: 체크포인트 사용 여부 (재시도/상태 저장)
        """
        self.checkpointer = MemorySaver() if use_checkpointer else None
        self.graph = build_bucket_inference_graph(self.checkpointer)
        BodyPartConfigLoader.set_data_dir(settings.data_dir)

    @traceable(name="langgraph_bucket_inference_pipeline")
    def run(self, input_data: BucketInferenceInput) -> Dict[str, BucketInferenceOutput]:
        """
        버킷 추론 실행 (기존 인터페이스와 동일)

        Args:
            input_data: 버킷 추론 입력

        Returns:
            {부위코드: BucketInferenceOutput} 딕셔너리
        """
        results: Dict[str, BucketInferenceOutput] = {}

        for body_part in input_data.body_parts:
            bp_code = body_part.code

            # 초기 상태 구성
            initial_state: BucketInferenceState = {
                "input_data": input_data,
                "current_body_part": body_part,
                "body_part_code": bp_code,
                "bp_config": None,
                "bucket_scores": None,
                "weight_ranking": None,
                "search_query": None,
                "evidence": None,
                "search_ranking": None,
                "merged_ranking": None,
                "discrepancy": None,
                "red_flag": None,
                "has_red_flag": False,
                "has_discrepancy": False,
                "final_result": None,
                "error": None,
                "started_at": None,
                "completed_at": None,
            }

            # 그래프 실행
            config = {"configurable": {"thread_id": f"{bp_code}_{datetime.now().isoformat()}"}}
            final_state = self.graph.invoke(initial_state, config)

            if final_state.get("final_result"):
                results[bp_code] = final_state["final_result"]
            elif final_state.get("error"):
                raise RuntimeError(f"버킷 추론 실패: {final_state['error']}")

        return results

    def run_single(
        self,
        input_data: BucketInferenceInput,
        body_part_code: str,
    ) -> BucketInferenceOutput:
        """단일 부위 추론"""
        results = self.run(input_data)
        if body_part_code not in results:
            raise ValueError(f"부위 코드 '{body_part_code}'를 찾을 수 없습니다.")
        return results[body_part_code]

    def get_available_body_parts(self) -> List[str]:
        """지원하는 부위 목록 반환"""
        return BodyPartConfigLoader.get_available_body_parts()

    def get_body_part_config(self, body_part_code: str) -> BodyPartConfig:
        """특정 부위의 설정 반환"""
        return BodyPartConfigLoader.load(body_part_code)

    def get_graph_visualization(self) -> str:
        """그래프 시각화 (Mermaid 형식)"""
        return self.graph.get_graph().draw_mermaid()


# =============================================================================
# Utility Functions
# =============================================================================

def compare_pipelines(
    input_data: BucketInferenceInput,
) -> Dict:
    """기존 파이프라인과 LangGraph 파이프라인 비교

    Returns:
        {
            "original": {...},
            "langgraph": {...},
            "comparison": {...},
        }
    """
    from bucket_inference.pipeline import BucketInferencePipeline
    import time

    original_pipeline = BucketInferencePipeline()
    langgraph_pipeline = LangGraphBucketInferencePipeline()

    # 기존 파이프라인 실행
    start = time.time()
    original_result = original_pipeline.run(input_data)
    original_time = time.time() - start

    # LangGraph 파이프라인 실행
    start = time.time()
    langgraph_result = langgraph_pipeline.run(input_data)
    langgraph_time = time.time() - start

    # 결과 비교
    comparison = {}
    for bp_code in original_result:
        orig = original_result[bp_code]
        lg = langgraph_result.get(bp_code)

        comparison[bp_code] = {
            "bucket_match": orig.final_bucket == lg.final_bucket if lg else False,
            "confidence_diff": abs(orig.confidence - lg.confidence) if lg else None,
            "original_bucket": orig.final_bucket,
            "langgraph_bucket": lg.final_bucket if lg else None,
        }

    return {
        "original": {
            "results": {k: v.model_dump() for k, v in original_result.items()},
            "execution_time_ms": int(original_time * 1000),
        },
        "langgraph": {
            "results": {k: v.model_dump() for k, v in langgraph_result.items()},
            "execution_time_ms": int(langgraph_time * 1000),
        },
        "comparison": comparison,
    }


if __name__ == "__main__":
    # 테스트 실행
    from shared.models import Demographics

    pipeline = LangGraphBucketInferencePipeline()

    # 그래프 시각화 출력
    print("=== LangGraph 시각화 (Mermaid) ===")
    print(pipeline.get_graph_visualization())
    print()

    # 테스트 입력
    test_input = BucketInferenceInput(
        demographics=Demographics(
            age=55,
            sex="female",
            height_cm=160,
            weight_kg=65,
        ),
        body_parts=[
            BodyPartInput(
                code="knee",
                primary=True,
                symptoms=["stiffness_morning", "crepitus", "pain_stairs", "pain_bilateral"],
                nrs=6,
            )
        ],
    )

    print("=== LangGraph 파이프라인 테스트 ===")
    try:
        results = pipeline.run(test_input)
        for bp_code, result in results.items():
            print(f"\n[{bp_code}]")
            print(f"  버킷: {result.final_bucket}")
            print(f"  신뢰도: {result.confidence}")
            print(f"  가중치 순위: {result.weight_ranking}")
            print(f"  검색 순위: {result.search_ranking}")
    except Exception as e:
        print(f"오류: {e}")
        import traceback
        traceback.print_exc()
