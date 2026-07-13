from app.rag.schemas import ParsedSegment


class Parser:
    async def parse(self, file_path: str) -> list[ParsedSegment]:
        raise NotImplementedError
