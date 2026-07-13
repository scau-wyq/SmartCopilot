from pathlib import Path

from app.rag.parsers.base import Parser
from app.rag.schemas import ParsedSegment


class PlainTextParser(Parser):
    async def parse(self, file_path: str) -> list[ParsedSegment]:
        return [ParsedSegment(text=Path(file_path).read_text(encoding="utf-8", errors="replace"))]
