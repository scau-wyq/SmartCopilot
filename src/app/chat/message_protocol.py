from typing import Literal

from pydantic import BaseModel, Field


class StartMessage(BaseModel):
    type: Literal["start"] = "start"
    generation_id: str = Field(serialization_alias="generationId")
    conversation_id: str = Field(serialization_alias="conversationId")
    timestamp: int


class ChunkMessage(BaseModel):
    type: Literal["chunk"] = "chunk"
    generation_id: str = Field(serialization_alias="generationId")
    conversation_id: str = Field(serialization_alias="conversationId")
    chunk: str
