"""Google Sheets 클라이언트 모듈

논문/자료 검토 워크플로우를 위한 Google Sheets 연동
"""

import os
from enum import Enum
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

from langsmith import traceable

# Optional: gspread 사용
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False


class ReviewStatus(str, Enum):
    """검토 상태"""
    PENDING = "pending"       # 검토 대기
    APPROVED = "approved"     # 승인
    REJECTED = "rejected"     # 거절
    MODIFIED = "modified"     # 수정 필요
    INDEXED = "indexed"       # 인덱싱 완료


@dataclass
class ReviewItem:
    """검토 대상 항목"""
    source: str           # pubmed, orthobullets, exercise
    source_id: str        # PMID, URL, ID 등
    title: str
    content: str
    body_part: str
    category: str
    url: str
    status: ReviewStatus = ReviewStatus.PENDING
    reviewer: Optional[str] = None
    review_note: Optional[str] = None
    created_at: Optional[str] = None
    reviewed_at: Optional[str] = None
    extra: Optional[Dict[str, Any]] = None

    def to_row(self) -> List[str]:
        """시트 행 데이터로 변환"""
        return [
            self.source,
            self.source_id,
            self.title[:100],  # 제목 길이 제한
            self.content[:500] if self.content else "",  # 내용 미리보기
            self.body_part,
            self.category,
            self.url,
            self.status.value,
            self.reviewer or "",
            self.review_note or "",
            self.created_at or datetime.now().isoformat(),
            self.reviewed_at or "",
        ]

    @classmethod
    def from_row(cls, row: List[str]) -> "ReviewItem":
        """시트 행에서 객체 생성"""
        return cls(
            source=row[0] if len(row) > 0 else "",
            source_id=row[1] if len(row) > 1 else "",
            title=row[2] if len(row) > 2 else "",
            content=row[3] if len(row) > 3 else "",
            body_part=row[4] if len(row) > 4 else "",
            category=row[5] if len(row) > 5 else "",
            url=row[6] if len(row) > 6 else "",
            status=ReviewStatus(row[7]) if len(row) > 7 and row[7] else ReviewStatus.PENDING,
            reviewer=row[8] if len(row) > 8 else None,
            review_note=row[9] if len(row) > 9 else None,
            created_at=row[10] if len(row) > 10 else None,
            reviewed_at=row[11] if len(row) > 11 else None,
        )


# 시트 헤더
SHEET_HEADERS = [
    "Source",
    "Source ID",
    "Title",
    "Content Preview",
    "Body Part",
    "Category",
    "URL",
    "Status",
    "Reviewer",
    "Review Note",
    "Created At",
    "Reviewed At",
]


class SheetsClient:
    """
    Google Sheets 클라이언트

    검토 워크플로우 지원:
    1. 크롤링된 자료를 시트에 업로드
    2. 검토자가 시트에서 승인/거절/수정 마킹
    3. 승인된 항목만 벡터 DB에 인덱싱
    """

    def __init__(
        self,
        spreadsheet_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ):
        """
        Args:
            spreadsheet_id: Google Sheets 스프레드시트 ID
            credentials_path: 서비스 계정 JSON 경로
            scopes: API 스코프
        """
        if not GSPREAD_AVAILABLE:
            raise ImportError("gspread 및 google-auth 패키지가 필요합니다: pip install gspread google-auth")

        self.spreadsheet_id = spreadsheet_id or os.getenv("GOOGLE_SHEETS_ID")
        self.credentials_path = credentials_path or os.getenv("GOOGLE_CREDENTIALS_PATH")

        if not self.credentials_path:
            raise ValueError("Google 서비스 계정 인증 정보가 필요합니다.")

        self.scopes = scopes or [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]

        self._client: Optional[gspread.Client] = None
        self._spreadsheet: Optional[gspread.Spreadsheet] = None

    def connect(self) -> "SheetsClient":
        """Sheets API 연결"""
        creds = Credentials.from_service_account_file(
            self.credentials_path,
            scopes=self.scopes,
        )
        self._client = gspread.authorize(creds)

        if self.spreadsheet_id:
            self._spreadsheet = self._client.open_by_key(self.spreadsheet_id)

        return self

    def create_spreadsheet(self, title: str) -> str:
        """
        새 스프레드시트 생성

        Args:
            title: 스프레드시트 제목

        Returns:
            스프레드시트 ID
        """
        if not self._client:
            self.connect()

        spreadsheet = self._client.create(title)
        self._spreadsheet = spreadsheet
        self.spreadsheet_id = spreadsheet.id

        # 기본 시트에 헤더 추가
        sheet = spreadsheet.sheet1
        sheet.update_title("Review Queue")
        sheet.update("A1", [SHEET_HEADERS])

        # 헤더 스타일 (첫 행 고정)
        sheet.freeze(rows=1)

        return spreadsheet.id

    def get_or_create_worksheet(self, name: str) -> "gspread.Worksheet":
        """워크시트 가져오거나 생성"""
        try:
            return self._spreadsheet.worksheet(name)
        except gspread.WorksheetNotFound:
            worksheet = self._spreadsheet.add_worksheet(title=name, rows=1000, cols=20)
            worksheet.update("A1", [SHEET_HEADERS])
            worksheet.freeze(rows=1)
            return worksheet

    @traceable(name="sheets_upload_items")
    def upload_items(
        self,
        items: List[ReviewItem],
        worksheet_name: str = "Review Queue",
        append: bool = True,
    ) -> int:
        """
        검토 항목 업로드

        Args:
            items: 업로드할 항목 리스트
            worksheet_name: 워크시트 이름
            append: True면 추가, False면 덮어쓰기

        Returns:
            업로드된 행 수
        """
        if not self._spreadsheet:
            self.connect()

        worksheet = self.get_or_create_worksheet(worksheet_name)

        rows = [item.to_row() for item in items]

        if append:
            # 기존 데이터에 추가
            existing = worksheet.get_all_values()
            start_row = len(existing) + 1
            worksheet.update(f"A{start_row}", rows)
        else:
            # 헤더 유지하고 덮어쓰기
            worksheet.update("A2", rows)

        return len(rows)

    @traceable(name="sheets_get_items_by_status")
    def get_items_by_status(
        self,
        status: ReviewStatus,
        worksheet_name: str = "Review Queue",
    ) -> List[ReviewItem]:
        """
        상태별 항목 조회

        Args:
            status: 검토 상태
            worksheet_name: 워크시트 이름

        Returns:
            ReviewItem 리스트
        """
        if not self._spreadsheet:
            self.connect()

        worksheet = self.get_or_create_worksheet(worksheet_name)
        all_rows = worksheet.get_all_values()[1:]  # 헤더 제외

        items = []
        for row in all_rows:
            if len(row) > 7 and row[7] == status.value:
                items.append(ReviewItem.from_row(row))

        return items

    @traceable(name="sheets_update_status")
    def update_status(
        self,
        source_id: str,
        new_status: ReviewStatus,
        reviewer: Optional[str] = None,
        note: Optional[str] = None,
        worksheet_name: str = "Review Queue",
    ) -> bool:
        """
        항목 상태 업데이트

        Args:
            source_id: 소스 ID
            new_status: 새 상태
            reviewer: 검토자
            note: 검토 메모
            worksheet_name: 워크시트 이름

        Returns:
            성공 여부
        """
        if not self._spreadsheet:
            self.connect()

        worksheet = self.get_or_create_worksheet(worksheet_name)
        all_rows = worksheet.get_all_values()

        for i, row in enumerate(all_rows[1:], start=2):  # 헤더 다음부터
            if len(row) > 1 and row[1] == source_id:
                # 상태 업데이트
                worksheet.update_cell(i, 8, new_status.value)  # Status column (H)

                if reviewer:
                    worksheet.update_cell(i, 9, reviewer)  # Reviewer column (I)

                if note:
                    worksheet.update_cell(i, 10, note)  # Note column (J)

                # 검토 시간 기록
                worksheet.update_cell(i, 12, datetime.now().isoformat())  # Reviewed At (L)

                return True

        return False

    def get_approved_items(
        self,
        worksheet_name: str = "Review Queue",
    ) -> List[ReviewItem]:
        """승인된 항목 조회"""
        return self.get_items_by_status(ReviewStatus.APPROVED, worksheet_name)

    def get_pending_items(
        self,
        worksheet_name: str = "Review Queue",
    ) -> List[ReviewItem]:
        """대기 중인 항목 조회"""
        return self.get_items_by_status(ReviewStatus.PENDING, worksheet_name)

    def mark_as_indexed(
        self,
        source_ids: List[str],
        worksheet_name: str = "Review Queue",
    ) -> int:
        """
        항목들을 인덱싱 완료로 마킹

        Args:
            source_ids: 마킹할 소스 ID 리스트
            worksheet_name: 워크시트 이름

        Returns:
            업데이트된 행 수
        """
        count = 0
        for source_id in source_ids:
            if self.update_status(source_id, ReviewStatus.INDEXED, worksheet_name=worksheet_name):
                count += 1
        return count


class ReviewWorkflow:
    """
    검토 워크플로우 관리자

    전체 프로세스:
    1. 크롤러로 수집 → 시트 업로드 (pending)
    2. 전문가 검토 → 시트에서 approved/rejected 마킹
    3. approved 항목 → 벡터 DB 인덱싱
    4. 인덱싱 완료 → indexed로 상태 변경
    """

    def __init__(
        self,
        sheets_client: SheetsClient,
        indexer=None,  # PineconeIndexer
    ):
        self.sheets = sheets_client
        self.indexer = indexer

    @traceable(name="workflow_upload_crawl_results")
    def upload_crawl_results(
        self,
        articles: List[Any],  # PubMedArticle 또는 OrthoBulletsArticle
        source_type: str,
        worksheet_name: str = "Review Queue",
    ) -> int:
        """
        크롤링 결과를 검토 시트에 업로드

        Args:
            articles: 크롤링된 문서 리스트
            source_type: 소스 타입 (pubmed, orthobullets)
            worksheet_name: 워크시트 이름

        Returns:
            업로드된 항목 수
        """
        items = []

        for article in articles:
            if source_type == "pubmed":
                item = ReviewItem(
                    source="pubmed",
                    source_id=article.pmid,
                    title=article.title,
                    content=article.abstract,
                    body_part=self._infer_body_part(article.title, article.abstract),
                    category="research",
                    url=article.url,
                )
            elif source_type == "orthobullets":
                item = ReviewItem(
                    source="orthobullets",
                    source_id=article.source_id,
                    title=article.title,
                    content=article.content[:500],
                    body_part=article.body_part,
                    category=article.category,
                    url=article.url,
                )
            else:
                continue

            items.append(item)

        return self.sheets.upload_items(items, worksheet_name)

    def _infer_body_part(self, title: str, abstract: str) -> str:
        """제목/초록에서 부위 추론"""
        text = (title + " " + abstract).lower()

        body_part_keywords = {
            "knee": ["knee", "patella", "meniscus", "acl", "pcl", "mcl"],
            "shoulder": ["shoulder", "rotator cuff", "glenohumeral", "scapula"],
            "spine": ["spine", "lumbar", "cervical", "thoracic", "vertebra", "disc"],
            "hip": ["hip", "femoral", "acetabulum", "labrum"],
            "ankle": ["ankle", "achilles", "plantar", "calcaneus"],
            "elbow": ["elbow", "ulnar", "radial head"],
            "wrist": ["wrist", "carpal", "scaphoid"],
        }

        for part, keywords in body_part_keywords.items():
            if any(kw in text for kw in keywords):
                return part

        return "general"

    @traceable(name="workflow_process_approved")
    def process_approved_items(
        self,
        worksheet_name: str = "Review Queue",
    ) -> Dict[str, int]:
        """
        승인된 항목들을 인덱싱

        Returns:
            {"processed": N, "success": M, "failed": K}
        """
        if not self.indexer:
            raise ValueError("Indexer가 설정되지 않았습니다.")

        from ..indexing.indexer import IndexDocument, generate_document_id

        approved = self.sheets.get_approved_items(worksheet_name)

        results = {"processed": len(approved), "success": 0, "failed": 0}
        indexed_ids = []

        for item in approved:
            try:
                # IndexDocument 생성
                doc = IndexDocument(
                    id=generate_document_id(item.source, item.source_id),
                    text=item.content,
                    source=item.source,
                    source_id=item.source_id,
                    title=item.title,
                    body_part=item.body_part,
                    bucket=item.category,
                    url=item.url,
                )

                # 인덱싱
                result = self.indexer.index_document(doc)

                if result.success:
                    results["success"] += 1
                    indexed_ids.append(item.source_id)
                else:
                    results["failed"] += 1

            except Exception as e:
                print(f"  ⚠ 인덱싱 실패 ({item.source_id}): {e}")
                results["failed"] += 1

        # 인덱싱 완료 마킹
        if indexed_ids:
            self.sheets.mark_as_indexed(indexed_ids, worksheet_name)

        return results

    def get_review_stats(
        self,
        worksheet_name: str = "Review Queue",
    ) -> Dict[str, int]:
        """검토 통계 조회"""
        stats = {status.value: 0 for status in ReviewStatus}

        if not self.sheets._spreadsheet:
            self.sheets.connect()

        worksheet = self.sheets.get_or_create_worksheet(worksheet_name)
        all_rows = worksheet.get_all_values()[1:]

        for row in all_rows:
            if len(row) > 7:
                status = row[7]
                if status in stats:
                    stats[status] += 1

        return stats
