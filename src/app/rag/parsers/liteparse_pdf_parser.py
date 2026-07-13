from app.rag.parsers.base import Parser
from app.rag.schemas import ParsedSegment


class LiteParsePdfParser(Parser):
    async def parse(self, file_path: str) -> list[ParsedSegment]:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        segments: list[ParsedSegment] = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if text.strip():
                segments.append(ParsedSegment(text=text, page_number=index))
        return segments
