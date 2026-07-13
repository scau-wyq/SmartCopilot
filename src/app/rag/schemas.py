from pydantic import BaseModel, Field


class ParsedSegment(BaseModel):
    text: str
    page_number: int | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class TextChunk(BaseModel):
    file_md5: str
    chunk_id: int
    text_content: str
    page_number: int | None = None
    anchor_text: str | None = None
    user_id: str
    org_tag: str | None = None
    is_public: bool = False


class SearchResult(BaseModel):
    file_md5: str
    chunk_id: int
    text_content: str
    score: float
    file_name: str | None = None
    page_number: int | None = None
    anchor_text: str | None = None
    user_id: str | None = None
    org_tag: str | None = None
    is_public: bool = False
    retrieval_mode: str | None = None
