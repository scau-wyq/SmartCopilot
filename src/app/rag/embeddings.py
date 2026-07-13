import httpx

from app.core.config import settings


class EmbeddingConfigurationError(RuntimeError):
    pass


class EmbeddingService:
    def __init__(self) -> None:
        self.base_url = settings.embedding_base_url.rstrip("/")
        self.api_key = settings.embedding_api_key
        self.model = settings.embedding_model
        self.timeout = settings.embedding_request_timeout_seconds

    @property
    def model_version(self) -> str:
        return self.model

    async def embed_texts(self, texts: list[str], user_id: str, usage_type: str) -> list[list[float]]:
        if not texts:
            return []
        if not self.api_key:
            raise EmbeddingConfigurationError("EMBEDDING_API_KEY is not configured")

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "input": texts,
                    "encoding_format": "float",
                },
            )
        response.raise_for_status()
        payload = response.json()
        data = sorted(payload.get("data", []), key=lambda item: item.get("index", 0))
        vectors = [item["embedding"] for item in data]
        if len(vectors) != len(texts):
            raise RuntimeError("Embedding response count does not match request count")
        return vectors
