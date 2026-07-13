import json

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from app.core.config import settings
from app.workers.schemas import FileProcessingTask


class KafkaTaskProducer:
    async def send_file_processing_task(self, task: FileProcessingTask) -> None:
        producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
        await producer.start()
        try:
            await producer.send_and_wait(
                settings.kafka_file_processing_topic,
                task.model_dump_json(by_alias=False).encode("utf-8"),
                key=task.file_md5.encode("utf-8"),
            )
        finally:
            await producer.stop()


class KafkaTaskConsumer:
    def __init__(self) -> None:
        self.consumer = AIOKafkaConsumer(
            settings.kafka_file_processing_topic,
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id=settings.kafka_file_processing_group_id,
            enable_auto_commit=False,
        )

    async def start(self) -> None:
        await self.consumer.start()

    async def stop(self) -> None:
        await self.consumer.stop()

    async def __aiter__(self):
        async for message in self.consumer:
            payload = json.loads(message.value.decode("utf-8"))
            yield message, FileProcessingTask.model_validate(payload)
