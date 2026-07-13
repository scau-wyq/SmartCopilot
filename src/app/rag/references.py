from app.rag.schemas import SearchResult

MAX_MATCHED_CHUNK_LEN = 1200
MAX_EVIDENCE_SNIPPET_LEN = 300


class ReferenceMapper:
    def build_mapping(self, results: list[SearchResult], query: str) -> dict[str, dict[str, object]]:
        mappings: dict[str, dict[str, object]] = {}
        for index, result in enumerate(results, start=1):
            file_name = result.file_name or result.file_md5
            matched_chunk_text = self._trim_to_max_length(result.text_content, MAX_MATCHED_CHUNK_LEN)
            mappings[str(index)] = {
                "fileMd5": result.file_md5,
                "fileName": file_name,
                "pageNumber": result.page_number,
                "anchorText": result.anchor_text,
                "retrievalMode": result.retrieval_mode,
                "retrievalLabel": self._retrieval_label(result.retrieval_mode),
                "retrievalQuery": self._normalize_text(query),
                "matchedChunkText": matched_chunk_text,
                "evidenceSnippet": self._build_evidence_snippet(query, result.anchor_text, matched_chunk_text),
                "score": result.score,
                "chunkId": result.chunk_id,
            }
        return mappings

    def build_context(self, results: list[SearchResult], query: str) -> str:
        if not results:
            return (
                "知识库检索未命中相关片段。请优先回答用户问题；如果问题依赖企业知识库资料，"
                "请明确说明当前未检索到可引用的知识库依据。"
            )

        sections = [
            "以下是本次从知识库检索到的参考片段。回答时必须优先基于这些片段，不要编造片段之外的事实。",
            "如果使用某个片段，请在相关句子后标注来源，格式必须是：来源#编号: 文件名 | 第N页。",
            f"用户问题：{self._normalize_text(query)}",
        ]
        for index, result in enumerate(results, start=1):
            file_name = result.file_name or result.file_md5
            page_label = f"第{result.page_number}页" if result.page_number else "页码未知"
            text = self._trim_to_max_length(result.text_content, MAX_MATCHED_CHUNK_LEN)
            sections.append(
                f"[来源#{index}] 文件：{file_name} | {page_label} | chunkId={result.chunk_id} | "
                f"score={result.score:.4f}\n{text}"
            )
        return "\n\n".join(sections)

    def _build_evidence_snippet(self, query: str, anchor_text: str | None, matched_chunk_text: str) -> str:
        normalized_anchor = self._normalize_text(anchor_text)
        if normalized_anchor:
            return self._trim_to_max_length(normalized_anchor, MAX_EVIDENCE_SNIPPET_LEN)

        normalized_chunk = self._normalize_text(matched_chunk_text)
        if not normalized_chunk:
            return self._trim_to_max_length(query, MAX_EVIDENCE_SNIPPET_LEN)

        for sentence in self._split_sentences(normalized_chunk):
            if len(sentence) >= 12:
                return self._trim_to_max_length(sentence, MAX_EVIDENCE_SNIPPET_LEN)
        return self._trim_to_max_length(normalized_chunk, MAX_EVIDENCE_SNIPPET_LEN)

    @staticmethod
    def _retrieval_label(retrieval_mode: str | None) -> str:
        if retrieval_mode == "TEXT_ONLY":
            return "关键词召回"
        if retrieval_mode == "HYBRID":
            return "混合召回（语义相关 + 关键词命中）"
        return "知识库召回"

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        sentences: list[str] = []
        start = 0
        for index, char in enumerate(text):
            if char in "。！？!?；;":
                sentence = text[start : index + 1].strip()
                if sentence:
                    sentences.append(sentence)
                start = index + 1
        tail = text[start:].strip()
        if tail:
            sentences.append(tail)
        return sentences

    def _trim_to_max_length(self, value: str | None, max_length: int) -> str:
        normalized = self._normalize_text(value)
        if len(normalized) <= max_length:
            return normalized
        return normalized[:max_length] + "..."

    @staticmethod
    def _normalize_text(value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.split())
