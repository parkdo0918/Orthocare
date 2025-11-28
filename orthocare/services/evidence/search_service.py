"""3-Layer 근거 검색 서비스"""

from typing import List, Optional
from datetime import datetime

from orthocare.config import settings
from orthocare.models.evidence import Paper, SearchResult, EvidenceResult


class EvidenceSearchService:
    """
    3-Layer 근거 검색

    Layer 1: 검증된 논문 (최고 신뢰도)
    Layer 2: Orthobullets (높은 신뢰도)
    Layer 3: PubMed (중간 신뢰도, 미검증)
    """

    def __init__(self, vector_store=None):
        """
        Args:
            vector_store: 벡터 스토어 인스턴스 (Pinecone 등)
        """
        self.vector_store = vector_store
        self.similarity_threshold = settings.similarity_threshold
        self.min_relevance = settings.min_relevance_score
        self.top_k = settings.search_top_k

    def search(
        self,
        query: str,
        body_part: str,
        buckets: Optional[List[str]] = None,
    ) -> EvidenceResult:
        """
        벡터 검색 수행

        실제 데이터 구조:
        - 논문: source="paper", bucket="research" (버킷 태그 없음)
        - 운동: source="exercise", bucket="OA,OVR" 등 (쉼표 구분 문자열)

        Args:
            query: 검색 쿼리
            body_part: 부위 코드
            buckets: 필터링할 버킷 리스트 (현재 미사용 - 논문에 버킷 태그 없음)

        Returns:
            EvidenceResult 객체
        """
        if self.vector_store is None:
            return EvidenceResult(
                query=query,
                body_part=body_part,
                results=[],
                layer_breakdown={"total": 0},
                search_timestamp=datetime.now(),
            )

        # 임베딩 생성
        from orthocare.data_ops.indexing import TextEmbedder
        from openai import OpenAI

        openai_client = OpenAI()
        embedder = TextEmbedder(openai_client)
        embed_result = embedder.embed(query)

        # 필터: body_part만 (다양한 소스 타입 포함: verified_paper, pubmed, orthobullets)
        # 소스 타입: verified_paper (검증된 논문), pubmed (PubMed), orthobullets (OrthoBullets)
        filters = {"body_part": body_part}

        # 벡터 검색 수행
        raw_results = self.vector_store.query(
            vector=embed_result.embedding,
            top_k=self.top_k,
            filter=filters,
            include_metadata=True,
            namespace="",  # 기본 네임스페이스
        )

        # SearchResult로 변환
        # min_relevance: 0.35 (현재 데이터 유사도 0.4~0.5 수준)
        results = []
        min_score = 0.35

        for match in raw_results.matches:
            similarity = match.score
            if similarity < min_score:
                continue

            metadata = match.metadata or {}

            # 버킷 태그 추출 (쉼표 구분 문자열 → 리스트)
            bucket_value = metadata.get("bucket", "")
            if bucket_value and bucket_value != "research":
                bucket_tags = [b.strip() for b in bucket_value.split(",") if b.strip()]
            else:
                bucket_tags = []  # "research"는 실제 버킷이 아님

            # 실제 텍스트 내용 가져오기
            text_content = metadata.get("text", "")

            # 소스 타입에 따른 레이어 결정
            source = metadata.get("source", "paper")
            if source == "verified_paper":
                source_type = "verified_paper"
                source_layer = 1
            elif source == "orthobullets":
                source_type = "orthobullets"
                source_layer = 2
            elif source == "pubmed":
                source_type = "pubmed"
                source_layer = 3
            else:
                source_type = "verified_paper"  # 기본값
                source_layer = 1

            paper = Paper(
                doc_id=match.id,
                title=metadata.get("title", "제목 없음"),
                source_type=source_type,
                source_layer=source_layer,
                body_part=body_part,
                bucket_tags=bucket_tags,
                year=metadata.get("year"),
                url=metadata.get("url"),
                summary=text_content[:500] if text_content else None,
                content=text_content,  # 전체 텍스트
            )

            results.append(
                SearchResult(
                    paper=paper,
                    similarity_score=similarity,
                    matching_reason=f"'{metadata.get('title', '')[:30]}...' (유사도: {similarity:.2f})",
                    needs_review=False,
                    auto_embedded=True,
                )
            )

        # 유사도 기준 정렬
        results.sort(key=lambda x: x.similarity_score, reverse=True)

        return EvidenceResult(
            query=query,
            body_part=body_part,
            results=results,
            layer_breakdown={"total": len(results)},
            search_timestamp=datetime.now(),
        )

    def _search_layer(
        self,
        query: str,
        body_part: str,
        source_type: str,
        layer: int,
        buckets: Optional[List[str]] = None,
    ) -> List[SearchResult]:
        """개별 레이어 검색"""
        if self.vector_store is None:
            return []

        # 실제 메타데이터 필드명에 맞게 필터 구성
        # Pinecone 필터 형식: {"key": value} (단순 형식)
        filters = {"body_part": body_part, "source": "paper"}

        if buckets:
            filters["bucket"] = {"$in": buckets}

        # 임베딩 생성 필요 - 텍스트 쿼리를 벡터로 변환
        from orthocare.data_ops.indexing import TextEmbedder
        from openai import OpenAI

        openai_client = OpenAI()
        embedder = TextEmbedder(openai_client)
        embed_result = embedder.embed(query)
        query_embedding = embed_result.embedding  # 실제 벡터 추출

        # 벡터 검색 수행 (default 네임스페이스 사용)
        raw_results = self.vector_store.query(
            vector=query_embedding,
            top_k=self.top_k,
            filter=filters,
            include_metadata=True,
            namespace="",  # default namespace
        )

        # SearchResult로 변환
        results = []
        for match in raw_results.matches:
            similarity = match.score

            # 최소 관련성 미달 시 제외
            if similarity < self.min_relevance:
                continue

            metadata = match.metadata or {}

            # 실제 메타데이터 필드에서 값 추출
            bucket_value = metadata.get("bucket", "")
            bucket_tags = [bucket_value] if bucket_value else []

            paper = Paper(
                doc_id=match.id,
                title=metadata.get("title", "제목 없음"),
                source_type=source_type,
                source_layer=layer,
                body_part=body_part,
                bucket_tags=bucket_tags,
                year=metadata.get("year"),
                url=metadata.get("url"),
                summary=metadata.get("text", "")[:500],  # text 필드를 summary로 사용
                content=metadata.get("text", ""),  # 전체 텍스트 저장
            )

            # 자동 임베딩 판단 (Layer 2, 3만)
            needs_review = False
            auto_embedded = False

            if layer in [2, 3]:
                if similarity >= self.similarity_threshold:
                    auto_embedded = True
                else:
                    needs_review = True

            results.append(
                SearchResult(
                    paper=paper,
                    similarity_score=similarity,
                    matching_reason=self._generate_matching_reason_v2(metadata, similarity),
                    needs_review=needs_review,
                    auto_embedded=auto_embedded,
                )
            )

        return results

    def _generate_matching_reason_v2(self, metadata: dict, score: float) -> str:
        """매칭 이유 생성 (v2)"""
        bucket = metadata.get("bucket", "일반")
        title = metadata.get("title", "")[:30]
        return f"'{title}...' - 버킷: {bucket} (유사도: {score:.2f})"

    def _generate_matching_reason(self, item: dict) -> str:
        """매칭 이유 생성"""
        metadata = item.get("metadata", {})
        bucket_tags = metadata.get("bucket_tags", [])
        score = item.get("score", 0)

        tags_str = ", ".join(bucket_tags) if bucket_tags else "일반"
        return f"관련 버킷: {tags_str} (유사도: {score:.2f})"

    def get_bucket_distribution(
        self,
        evidence: EvidenceResult,
    ) -> List[tuple]:
        """
        검색 결과의 버킷 분포 반환

        Returns:
            [(버킷, 카운트), ...] 내림차순
        """
        bucket_counts = {}

        for result in evidence.results:
            for bucket in result.paper.bucket_tags:
                bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

        # 카운트 내림차순 정렬
        sorted_buckets = sorted(
            bucket_counts.items(), key=lambda x: x[1], reverse=True
        )

        return sorted_buckets

    def get_search_ranking(self, evidence: EvidenceResult) -> List[str]:
        """검색 결과 기반 버킷 순위"""
        distribution = self.get_bucket_distribution(evidence)
        return [bucket for bucket, _ in distribution]
