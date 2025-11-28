"""벡터 검색 도구

Pinecone 벡터 DB에서 관련 문서 검색
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from langsmith import traceable


@dataclass
class VectorSearchResult:
    """벡터 검색 결과"""
    id: str
    score: float
    text: str
    source: str
    title: str
    body_part: Optional[str] = None
    url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class VectorSearchTool:
    """
    벡터 검색 도구

    Pinecone에서 유사도 기반 문서 검색
    """

    def __init__(
        self,
        pinecone_index,
        embedder,
        namespace: str = "",
        default_top_k: int = 5,
    ):
        """
        Args:
            pinecone_index: Pinecone Index 객체
            embedder: TextEmbedder 인스턴스
            namespace: Pinecone 네임스페이스
            default_top_k: 기본 검색 결과 수
        """
        self.index = pinecone_index
        self.embedder = embedder
        self.namespace = namespace
        self.default_top_k = default_top_k

    @traceable(name="vector_search")
    def search(
        self,
        query: str,
        top_k: Optional[int] = None,
        filter: Optional[Dict[str, Any]] = None,
        min_score: float = 0.0,
    ) -> List[VectorSearchResult]:
        """
        벡터 유사도 검색

        Args:
            query: 검색 쿼리
            top_k: 반환할 결과 수
            filter: 메타데이터 필터 (예: {"source": {"$eq": "exercise"}})
            min_score: 최소 유사도 점수

        Returns:
            VectorSearchResult 리스트
        """
        top_k = top_k or self.default_top_k

        # 쿼리 임베딩
        query_embedding = self.embedder.embed(query)

        # Pinecone 검색
        response = self.index.query(
            vector=query_embedding.embedding,
            top_k=top_k,
            include_metadata=True,
            namespace=self.namespace,
            filter=filter,
        )

        results = []
        for match in response.matches:
            if match.score < min_score:
                continue

            metadata = match.metadata or {}
            results.append(VectorSearchResult(
                id=match.id,
                score=match.score,
                text=metadata.get("text", ""),
                source=metadata.get("source", "unknown"),
                title=metadata.get("title", ""),
                body_part=metadata.get("body_part"),
                url=metadata.get("url"),
                metadata=metadata,
            ))

        return results

    @traceable(name="vector_search_by_source")
    def search_by_source(
        self,
        query: str,
        source: str,
        top_k: Optional[int] = None,
    ) -> List[VectorSearchResult]:
        """
        특정 소스에서만 검색

        Args:
            query: 검색 쿼리
            source: 소스 타입 (exercise, paper, pubmed, orthobullets)
            top_k: 결과 수

        Returns:
            VectorSearchResult 리스트
        """
        return self.search(
            query=query,
            top_k=top_k,
            filter={"source": {"$eq": source}},
        )

    @traceable(name="vector_search_by_body_part")
    def search_by_body_part(
        self,
        query: str,
        body_part: str,
        top_k: Optional[int] = None,
    ) -> List[VectorSearchResult]:
        """
        특정 부위에서만 검색

        Args:
            query: 검색 쿼리
            body_part: 부위 코드
            top_k: 결과 수

        Returns:
            VectorSearchResult 리스트
        """
        return self.search(
            query=query,
            top_k=top_k,
            filter={"body_part": {"$eq": body_part}},
        )

    @traceable(name="vector_search_exercises")
    def search_exercises(
        self,
        query: str,
        body_part: Optional[str] = None,
        bucket: Optional[str] = None,
        top_k: int = 10,
    ) -> List[VectorSearchResult]:
        """
        운동 검색

        Args:
            query: 검색 쿼리 (증상, 근육, 기능 등)
            body_part: 부위 필터
            bucket: 진단 버킷 필터 (OA, INF, TRM 등)
            top_k: 결과 수

        Returns:
            VectorSearchResult 리스트
        """
        filter_conditions = [{"source": {"$eq": "exercise"}}]

        if body_part:
            filter_conditions.append({"body_part": {"$eq": body_part}})

        # 복합 필터 구성
        if len(filter_conditions) == 1:
            final_filter = filter_conditions[0]
        else:
            final_filter = {"$and": filter_conditions}

        results = self.search(query=query, top_k=top_k, filter=final_filter)

        # 버킷 필터링 (메타데이터에 포함된 경우)
        if bucket:
            results = [
                r for r in results
                if bucket in r.metadata.get("bucket", "").split(",")
            ]

        return results

    @traceable(name="vector_search_papers")
    def search_papers(
        self,
        query: str,
        body_part: Optional[str] = None,
        top_k: int = 5,
    ) -> List[VectorSearchResult]:
        """
        논문/연구 검색

        Args:
            query: 검색 쿼리
            body_part: 부위 필터
            top_k: 결과 수

        Returns:
            VectorSearchResult 리스트
        """
        filter_conditions = [
            {"source": {"$in": ["paper", "pubmed", "orthobullets"]}}
        ]

        if body_part:
            filter_conditions.append({"body_part": {"$eq": body_part}})

        if len(filter_conditions) == 1:
            final_filter = filter_conditions[0]
        else:
            final_filter = {"$and": filter_conditions}

        return self.search(query=query, top_k=top_k, filter=final_filter)

    @traceable(name="vector_search_unified")
    def search_unified(
        self,
        query: str,
        body_part: Optional[str] = None,
        top_k: int = 20,
        include_exercises: bool = True,
        include_papers: bool = True,
        include_crawled: bool = True,
    ) -> List[VectorSearchResult]:
        """
        통합 유사도 검색 - 모든 소스에서 검색

        사용자 자연어 입력을 임베딩하여 운동/논문/크롤링 데이터 모두에서
        유사한 콘텐츠를 찾습니다.

        Args:
            query: 사용자 자연어 쿼리 (증상 설명, 목표 등)
            body_part: 부위 필터 (선택)
            top_k: 반환할 전체 결과 수
            include_exercises: 운동 데이터 포함 여부
            include_papers: 논문 데이터 포함 여부
            include_crawled: 크롤링 데이터 포함 여부

        Returns:
            VectorSearchResult 리스트 (유사도순 정렬)
        """
        # 소스 필터 구성
        sources = []
        if include_exercises:
            sources.append("exercise")
        if include_papers:
            sources.append("paper")
        if include_crawled:
            sources.extend(["pubmed", "orthobullets"])

        if not sources:
            return []

        # 필터 조건 구성
        filter_conditions = []

        if len(sources) == 1:
            filter_conditions.append({"source": {"$eq": sources[0]}})
        else:
            filter_conditions.append({"source": {"$in": sources}})

        if body_part:
            filter_conditions.append({"body_part": {"$eq": body_part}})

        if len(filter_conditions) == 1:
            final_filter = filter_conditions[0]
        else:
            final_filter = {"$and": filter_conditions}

        return self.search(query=query, top_k=top_k, filter=final_filter)

    @traceable(name="vector_search_for_user_input")
    def search_for_user_input(
        self,
        chief_complaint: Optional[str] = None,
        pain_description: Optional[str] = None,
        goals: Optional[str] = None,
        body_part: Optional[str] = None,
        top_k: int = 15,
    ) -> Dict[str, List[VectorSearchResult]]:
        """
        사용자 자연어 입력 기반 통합 검색

        NaturalLanguageInput의 각 필드를 활용하여 관련 콘텐츠 검색.
        검색 결과를 소스별로 분리하여 반환.

        Args:
            chief_complaint: 주호소
            pain_description: 통증 설명
            goals: 목표
            body_part: 부위 코드
            top_k: 소스별 최대 결과 수

        Returns:
            {
                "exercises": [...],
                "evidence": [...],  # papers + crawled
                "all": [...]  # 전체 유사도순
            }
        """
        # 쿼리 텍스트 구성
        query_parts = []
        if chief_complaint:
            query_parts.append(chief_complaint)
        if pain_description:
            query_parts.append(pain_description)
        if goals:
            query_parts.append(goals)

        if not query_parts:
            return {"exercises": [], "evidence": [], "all": []}

        query = " ".join(query_parts)

        # 통합 검색
        all_results = self.search_unified(
            query=query,
            body_part=body_part,
            top_k=top_k * 3,  # 충분히 가져옴
        )

        # 소스별 분리
        exercises = [r for r in all_results if r.source == "exercise"]
        evidence = [r for r in all_results if r.source != "exercise"]

        return {
            "exercises": exercises[:top_k],
            "evidence": evidence[:top_k],
            "all": all_results[:top_k],
        }
