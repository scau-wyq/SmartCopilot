from pydantic import BaseModel


class FileProcessingTask(BaseModel):
    file_md5: str
    file_path: str | None = None
    file_name: str | None = None
    user_id: str
    org_tag: str | None = None
    is_public: bool = False
    task_type: str = "UPLOAD_PROCESS"
    requester_id: str | None = None
