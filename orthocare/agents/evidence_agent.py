"""근거 기반 에이전트

논문과 교육 자료를 검색하여 근거 기반 답변 생성
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum

from langsmith import traceable

from .tools import (
    VectorSearchTool,
    VectorSearchResult,
    PubMedSearchTool,
    PubMedSearchResult,
    OrthoBulletsSearchTool,
    OrthoBulletsSearchResult,
)


class EvidenceSource(str, Enum):
    """근거 소스 유형"""
    VECTOR_DB = "vector_db"
    PUBMED = "pubmed"
    ORTHOBULLETS = "orthobullets"


@dataclass
class EvidenceQuery:
    """근거 검색 쿼리"""
    query: str
    body_part: Optional[str] = None
    condition: Optional[str] = None
    treatment_type: Optional[str] = None
    sources: List[EvidenceSource] = field(default_factory=lambda: list(EvidenceSource))
    max_results_per_source: int = 5
    min_year: Optional[int] = None  # PubMed 필터


@dataclass
class EvidenceItem:
    """개별 근거 항목"""
    source: EvidenceSource
    title: str
    content: str
    url: Optional[str] = None
    relevance_score: float = 0.0
    year: Optional[int] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceResult:
    """근거 검색 결과"""
    query: EvidenceQuery
    evidence_items: List[EvidenceItem]
    summary: Optional[str] = None
    total_sources_searched: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def has_evidence(self) -> bool:
        return len(self.evidence_items) > 0

    def get_by_source(self, source: EvidenceSource) -> List[EvidenceItem]:
        return [e for e in self.evidence_items if e.source == source]

    def top_evidence(self, n: int = 3) -> List[EvidenceItem]:
        """상위 N개 근거 반환 (관련도순)"""
        sorted_items = sorted(
            self.evidence_items,
            key=lambda x: x.relevance_score,
            reverse=True,
        )
        return sorted_items[:n]


class EvidenceAgent:
    """
    근거 기반 에이전트

    다양한 소스에서 의학적 근거를 검색하고 종합:
    - 벡터 DB: 인덱싱된 논문, 운동 데이터
    - PubMed: 최신 연구 논문
    - OrthoBullets: 정형외과 교육 자료

    사용 예시:
        agent = EvidenceAgent(vector_tool, pubmed_tool, orthobullets_tool, llm_client)

        query = EvidenceQuery(
            query="무릎 골관절염에 효과적인 운동",
            body_part="knee",
            condition="osteoarthritis",
        )

        result = agent.search_evidence(query)
    """

    def __init__(
        self,
        vector_tool: Optional[VectorSearchTool] = None,
        pubmed_tool: Optional[PubMedSearchTool] = None,
        orthobullets_tool: Optional[OrthoBulletsSearchTool] = None,
        llm_client=None,
        model: str = "gpt-4o-mini",
    ):
        """
        Args:
            vector_tool: 벡터 검색 도구
            pubmed_tool: PubMed 검색 도구
            orthobullets_tool: OrthoBullets 검색 도구
            llm_client: OpenAI 클라이언트 (요약용)
            model: LLM 모델명
        """
        self.vector_tool = vector_tool
        self.pubmed_tool = pubmed_tool
        self.orthobullets_tool = orthobullets_tool
        self.llm_client = llm_client
        self.model = model

    @traceable(name="evidence_search")
    def search_evidence(self, query: EvidenceQuery) -> EvidenceResult:
        """
        근거 검색 실행

        Args:
            query: 검색 쿼리

        Returns:
            EvidenceResult
        """
        evidence_items = []
        errors = []
        sources_searched = 0

        # 1. 벡터 DB 검색
        if EvidenceSource.VECTOR_DB in query.sources and self.vector_tool:
            try:
                vector_results = self._search_vector_db(query)
                evidence_items.extend(vector_results)
                sources_searched += 1
            except Exception as e:
                errors.append(f"Vector DB 검색 실패: {str(e)}")

        # 2. PubMed 검색
        if EvidenceSource.PUBMED in query.sources and self.pubmed_tool:
            try:
                pubmed_results = self._search_pubmed(query)
                evidence_items.extend(pubmed_results)
                sources_searched += 1
            except Exception as e:
                errors.append(f"PubMed 검색 실패: {str(e)}")

        # 3. OrthoBullets 검색
        if EvidenceSource.ORTHOBULLETS in query.sources and self.orthobullets_tool:
            try:
                ortho_results = self._search_orthobullets(query)
                evidence_items.extend(ortho_results)
                sources_searched += 1
            except Exception as e:
                errors.append(f"OrthoBullets 검색 실패: {str(e)}")

        result = EvidenceResult(
            query=query,
            evidence_items=evidence_items,
            total_sources_searched=sources_searched,
            errors=errors,
        )

        # 4. LLM으로 요약 생성 (선택)
        if self.llm_client and evidence_items:
            try:
                result.summary = self._generate_summary(query, evidence_items)
            except Exception as e:
                errors.append(f"요약 생성 실패: {str(e)}")

        return result

    def _search_vector_db(self, query: EvidenceQuery) -> List[EvidenceItem]:
        """벡터 DB 검색"""
        results = []

        # 논문 검색
        paper_results = self.vector_tool.search_papers(
            query=query.query,
            body_part=query.body_part,
            top_k=query.max_results_per_source,
        )

        for r in paper_results:
            results.append(EvidenceItem(
                source=EvidenceSource.VECTOR_DB,
                title=r.title,
                content=r.text[:1000],  # 내용 제한
                url=r.url,
                relevance_score=r.score,
                year=r.metadata.get("year"),
                metadata={
                    "source_type": r.source,
                    "body_part": r.body_part,
                },
            ))

        return results

    def _search_pubmed(self, query: EvidenceQuery) -> List[EvidenceItem]:
        """PubMed 검색"""
        results = []

        # 쿼리 구성
        search_query = query.query
        if query.condition:
            search_query = f"({query.condition}) AND ({query.query})"
        if query.body_part:
            search_query = f"({query.body_part}) AND ({search_query})"

        pubmed_results = self.pubmed_tool.search(
            query=search_query,
            max_results=query.max_results_per_source,
            min_year=query.min_year,
        )

        for r in pubmed_results:
            results.append(EvidenceItem(
                source=EvidenceSource.PUBMED,
                title=r.title,
                content=r.abstract[:1000] if r.abstract else "",
                url=r.url,
                relevance_score=0.8,  # PubMed는 관련도 점수가 없으므로 기본값
                year=r.year,
                metadata={
                    "pmid": r.pmid,
                    "journal": r.journal,
                    "authors": r.authors[:3],
                    "mesh_terms": r.mesh_terms[:5],
                },
            ))

        return results

    def _search_orthobullets(self, query: EvidenceQuery) -> List[EvidenceItem]:
        """OrthoBullets 검색"""
        results = []

        # 부위가 지정된 경우 해당 부위 토픽에서 검색
        if query.body_part:
            ortho_results = self.orthobullets_tool.get_topics_by_body_part(
                body_part=query.body_part,
                max_topics=query.max_results_per_source,
            )
        else:
            # 일반 검색
            ortho_results = self.orthobullets_tool.search(
                query=query.query,
                max_results=query.max_results_per_source,
            )

        for r in ortho_results:
            # 내용 조합
            content_parts = []
            if r.key_points:
                content_parts.append("핵심 포인트: " + "; ".join(r.key_points[:3]))
            if r.diagnosis:
                content_parts.append(f"진단: {r.diagnosis[:200]}")
            if r.treatment:
                content_parts.append(f"치료: {r.treatment[:200]}")

            results.append(EvidenceItem(
                source=EvidenceSource.ORTHOBULLETS,
                title=r.title,
                content="\n".join(content_parts) if content_parts else "",
                url=r.url,
                relevance_score=0.7,
                metadata={
                    "body_part": r.body_part,
                    "category": r.category,
                },
            ))

        return results

    @traceable(name="evidence_summarize")
    def _generate_summary(
        self,
        query: EvidenceQuery,
        evidence_items: List[EvidenceItem],
    ) -> str:
        """근거 요약 생성"""
        # 근거 텍스트 구성
        evidence_text = ""
        for i, item in enumerate(evidence_items[:10], 1):  # 상위 10개만
            evidence_text += f"\n{i}. [{item.source.value}] {item.title}\n"
            evidence_text += f"   {item.content[:300]}...\n"

        prompt = f"""다음 의학적 근거들을 바탕으로 질문에 대한 요약을 작성하세요.

질문: {query.query}
{f'부위: {query.body_part}' if query.body_part else ''}
{f'질환: {query.condition}' if query.condition else ''}

수집된 근거:
{evidence_text}

요약 작성 지침:
1. 근거에 기반한 핵심 내용만 간결하게 요약
2. 출처를 명시하여 신뢰성 확보
3. 불확실한 내용은 "~로 보고됨", "~가 제안됨" 등으로 표현
4. 300자 이내로 작성

요약:"""

        response = self.llm_client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3,
        )

        return response.choices[0].message.content.strip()

    @traceable(name="evidence_search_for_exercise")
    def search_exercise_evidence(
        self,
        condition: str,
        body_part: str,
        max_results: int = 10,
    ) -> EvidenceResult:
        """
        운동 치료 근거 검색

        Args:
            condition: 질환명
            body_part: 부위
            max_results: 최대 결과 수

        Returns:
            EvidenceResult
        """
        query = EvidenceQuery(
            query=f"{condition} exercise therapy rehabilitation",
            body_part=body_part,
            condition=condition,
            treatment_type="exercise",
            sources=[EvidenceSource.VECTOR_DB, EvidenceSource.PUBMED],
            max_results_per_source=max_results // 2,
            min_year=2015,  # 최근 연구 위주
        )

        return self.search_evidence(query)

    @traceable(name="evidence_search_for_diagnosis")
    def search_diagnosis_evidence(
        self,
        symptoms: List[str],
        body_part: str,
    ) -> EvidenceResult:
        """
        진단 관련 근거 검색

        Args:
            symptoms: 증상 리스트
            body_part: 부위

        Returns:
            EvidenceResult
        """
        symptoms_text = " ".join(symptoms)

        query = EvidenceQuery(
            query=f"{symptoms_text} diagnosis differential",
            body_part=body_part,
            sources=[EvidenceSource.VECTOR_DB, EvidenceSource.ORTHOBULLETS],
            max_results_per_source=5,
        )

        return self.search_evidence(query)
