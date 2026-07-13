from docx import Document

from app.rag.parsers.base import Parser
from app.rag.schemas import ParsedSegment


class DocxParser(Parser):
    async def parse(self, file_path: str) -> list[ParsedSegment]:
        document = Document(file_path)
        text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
        return [ParsedSegment(text=text)] if text.strip() else []
