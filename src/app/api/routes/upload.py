from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, ConfigDict, Field

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.responses import ok
from app.services.file_upload_service import FileUploadService, SUPPORTED_EXTENSIONS

router = APIRouter()


class MergeRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    file_md5: str | None = Field(default=None, alias="fileMd5")
    file_name: str | None = Field(default=None, alias="fileName")


@router.post("/chunk")
async def upload_chunk(
    current_user: CurrentUserDep,
    session: SessionDep,
    file_md5: str = Form(..., alias="fileMd5"),
    chunk_index: int = Form(..., alias="chunkIndex"),
    total_size: int = Form(..., alias="totalSize"),
    file_name: str = Form(..., alias="fileName"),
    org_tag: str | None = Form(default=None, alias="orgTag"),
    is_public: bool = Form(default=False, alias="isPublic"),
    file: UploadFile = File(...),
) -> dict[str, object]:
    service = FileUploadService(session)
    data = await service.upload_chunk(
        current_user=current_user,
        file_md5=file_md5,
        chunk_index=chunk_index,
        total_size=total_size,
        file_name=file_name,
        org_tag=org_tag,
        is_public=is_public,
        file=file,
    )
    return ok("分片上传成功", data)


@router.get("/status")
async def get_upload_status(
    file_md5: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    service = FileUploadService(session)
    data = await service.get_upload_status(file_md5=file_md5, current_user=current_user)
    return ok("获取上传状态成功", data)


@router.post("/merge")
async def merge_file(
    payload: MergeRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    service = FileUploadService(session)
    data = await service.merge_file(
        current_user=current_user,
        file_md5=payload.file_md5 or "",
        file_name=payload.file_name or "",
    )
    return ok("文件合并成功", data)


@router.get("/supported-types")
async def get_supported_types() -> dict[str, object]:
    extensions = sorted(SUPPORTED_EXTENSIONS)
    return ok(
        "获取支持的文件类型成功",
        {
            "supportedTypes": [extension.upper() for extension in extensions],
            "supportedExtensions": [f".{extension}" for extension in extensions],
            "description": "系统支持的文档类型文件",
        },
    )
