from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.api.dependencies import CurrentUserDep, SessionDep
from app.api.responses import ApiError, ok
from app.chat.generation_state import generation_state_store
from app.services.conversation_service import ConversationService
from app.services.file_upload_service import FileUploadService

router = APIRouter()


@router.get("/uploads")
async def list_uploads(current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    service = FileUploadService(session)
    return ok("Get user uploads successful", await service.list_user_uploads(current_user))


@router.get("/accessible")
async def list_accessible(current_user: CurrentUserDep, session: SessionDep) -> dict[str, object]:
    service = FileUploadService(session)
    return ok("Get accessible documents successful", await service.list_accessible_uploads(current_user))


@router.get("/download-by-md5")
async def download_by_md5(
    fileMd5: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    service = FileUploadService(session)
    upload = await service.get_accessible_upload(current_user=current_user, file_md5=fileMd5)
    return ok("Get document download URL successful", service.build_download_payload(upload))


@router.get("/download")
async def download_by_name(
    fileName: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    service = FileUploadService(session)
    uploads = await service.repository.list_accessible(
        user_id=str(current_user.id),
        org_tags=current_user.org_tag_list,
        is_admin=current_user.role == "ADMIN",
    )
    upload = next((item for item in uploads if item.file_name == fileName), None)
    if upload is None:
        raise ApiError(404, "Document does not exist or is not accessible")
    return ok("Get document download URL successful", service.build_download_payload(upload))


@router.get("/preview")
async def preview_document(
    fileName: str,
    current_user: CurrentUserDep,
    session: SessionDep,
    fileMd5: str | None = None,
    pageNumber: int | None = None,
) -> dict[str, object]:
    service = FileUploadService(session)
    if fileMd5:
        upload = await service.get_accessible_upload(current_user=current_user, file_md5=fileMd5)
    else:
        uploads = await service.repository.list_accessible(
            user_id=str(current_user.id),
            org_tags=current_user.org_tag_list,
            is_admin=current_user.role == "ADMIN",
        )
        upload = next((item for item in uploads if item.file_name == fileName), None)
        if upload is None:
            raise ApiError(404, "Document does not exist or is not accessible")
    return ok("Get document preview successful", await service.build_preview_payload(upload, pageNumber))


@router.get("/page-preview")
async def page_preview(
    fileMd5: str,
    current_user: CurrentUserDep,
    session: SessionDep,
    pageNumber: int = 1,
) -> FileResponse:
    service = FileUploadService(session)
    upload = await service.get_accessible_upload(current_user=current_user, file_md5=fileMd5)
    path = await service.download_merged_file(upload.file_md5, upload.file_name)
    return FileResponse(path, filename=Path(upload.file_name).name)


@router.get("/reference-detail")
async def reference_detail(
    sessionId: str,
    referenceNumber: int,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    detail = await _find_reference_detail(
        session=session,
        user_id=int(current_user.id),
        session_id=sessionId,
        reference_number=referenceNumber,
    )
    if detail is None:
        raise ApiError(404, "Reference detail does not exist")

    file_md5 = detail.get("fileMd5")
    if not isinstance(file_md5, str) or not file_md5:
        raise ApiError(404, "Reference file does not exist")

    service = FileUploadService(session)
    await service.get_accessible_upload(current_user=current_user, file_md5=file_md5)
    return ok(
        "Get reference detail successful",
        {
            "fileMd5": detail.get("fileMd5"),
            "fileName": detail.get("fileName"),
            "referenceNumber": referenceNumber,
            "pageNumber": detail.get("pageNumber"),
            "anchorText": detail.get("anchorText"),
            "retrievalMode": detail.get("retrievalMode"),
            "retrievalLabel": detail.get("retrievalLabel"),
            "retrievalQuery": detail.get("retrievalQuery"),
            "matchedChunkText": detail.get("matchedChunkText"),
            "evidenceSnippet": detail.get("evidenceSnippet"),
            "score": detail.get("score"),
            "chunkId": detail.get("chunkId"),
        },
    )


@router.post("/{file_md5}/vectorization/retry")
async def retry_vectorization(
    file_md5: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    service = FileUploadService(session)
    upload = await service.get_accessible_upload(current_user=current_user, file_md5=file_md5)
    upload.vectorization_status = "PROCESSING"
    upload.vectorization_error_message = None
    await session.commit()
    try:
        await service.enqueue_processing_task(upload, f"merged/{upload.file_md5}")
    except Exception as exception:
        upload.vectorization_status = "FAILED"
        upload.vectorization_error_message = f"Kafka task publish failed: {exception}"[:1000]
        await session.commit()
        raise
    return ok(
        "Vectorization retry task submitted",
        {
            "fileMd5": upload.file_md5,
            "fileName": upload.file_name,
            "vectorizationStatus": upload.vectorization_status,
        },
    )


@router.delete("/{file_md5}")
async def delete_document(
    file_md5: str,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> dict[str, object]:
    service = FileUploadService(session)
    await service.delete_document(current_user=current_user, file_md5=file_md5)
    return ok("Document deleted successful")


async def _find_reference_detail(
    *,
    session,
    user_id: int,
    session_id: str,
    reference_number: int,
) -> dict[str, object] | None:
    reference_key = str(reference_number)

    snapshot = await generation_state_store.get_for_user(session_id, str(user_id))
    if snapshot is not None:
        detail = snapshot.reference_mappings.get(reference_key)
        if isinstance(detail, dict):
            return detail

    conversation_service = ConversationService(session)
    messages = await conversation_service.get_message_history(user_id=user_id, conversation_id=session_id)
    for message in reversed(messages):
        mappings = message.get("referenceMappings")
        if isinstance(mappings, dict):
            detail = mappings.get(reference_key)
            if isinstance(detail, dict):
                return detail

    return None
