import asyncio
import tempfile
from pathlib import Path

from app.core.database import AsyncSessionLocal
from app.integrations.kafka_client import KafkaTaskConsumer
from app.integrations.minio_storage import MinioStorage
from app.rag.pipeline import RagIngestionPipeline
from app.repositories.file_upload_repository import FileUploadRepository
from app.workers.schemas import FileProcessingTask


class FileProcessingWorker:
    def __init__(self) -> None:
        self.storage = MinioStorage()

    async def process_task(self, task: FileProcessingTask) -> None:
        async with AsyncSessionLocal() as session:
            repository = FileUploadRepository(session)
            await repository.mark_vectorization_processing(task.file_md5, reset_actual_usage=True)
            await session.commit()

            pipeline = RagIngestionPipeline(session)
            try:
                local_path = await asyncio.to_thread(self._download_task_file, task)
                result = await pipeline.ingest_file(
                    file_md5=task.file_md5,
                    file_path=str(local_path),
                    user_id=task.user_id,
                    org_tag=task.org_tag,
                    is_public=task.is_public,
                )
                await repository.mark_vectorization_completed(
                    task.file_md5,
                    result.actual_embedding_tokens,
                    result.actual_chunk_count,
                )
                await session.commit()
            except Exception as exception:
                await repository.mark_vectorization_failed(task.file_md5, str(exception))
                await session.commit()
                raise
            finally:
                await pipeline.close()

    def _download_task_file(self, task: FileProcessingTask) -> Path:
        suffix = Path(task.file_name or task.file_md5).suffix
        target = Path(tempfile.gettempdir()) / "smartcopilot-file-processing" / f"{task.file_md5}{suffix}"
        object_name = task.file_path or f"merged/{task.file_md5}"
        return self.storage.download_file(object_name, target)


async def consume_forever() -> None:
    consumer = KafkaTaskConsumer()
    worker = FileProcessingWorker()
    await consumer.start()
    try:
        async for message, task in consumer:
            await worker.process_task(task)
            await consumer.consumer.commit()
    finally:
        await consumer.stop()


if __name__ == "__main__":
    asyncio.run(consume_forever())
