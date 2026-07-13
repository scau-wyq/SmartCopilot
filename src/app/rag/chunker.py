from app.rag.schemas import ParsedSegment, TextChunk


class Chunker:
    def __init__(self, chunk_size: int = 1200, overlap: int = 150) -> None:
        self.chunk_size = chunk_size
        self.overlap = min(overlap, max(0, chunk_size - 1))

    def split(
        self,
        file_md5: str,
        segments: list[ParsedSegment],
        user_id: str,
        org_tag: str | None = None,
        is_public: bool = False,
    ) -> list[TextChunk]:
        chunks: list[TextChunk] = []
        chunk_id = 0
        for segment in segments:
            for text in self._split_text(segment.text):
                chunk_id += 1
                chunks.append(
                    TextChunk(
                        file_md5=file_md5,
                        chunk_id=chunk_id,
                        text_content=text,
                        page_number=segment.page_number,
                        anchor_text=self._anchor_text(text),
                        user_id=user_id,
                        org_tag=org_tag,
                        is_public=is_public,
                    )
                )
        return chunks

    def _split_text(self, text: str) -> list[str]:
        normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
        if not normalized:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + self.chunk_size, len(normalized))
            chunks.append(normalized[start:end])
            if end == len(normalized):
                break
            start = max(0, end - self.overlap)
        return chunks

    def _anchor_text(self, text: str) -> str:
        return text[:512]
