from app.models.file_upload import FileUpload
from app.models.user import User


class PermissionService:
    default_org_tag = "DEFAULT"
    private_tag_prefix = "PRIVATE_"

    def can_access_document(self, user: User, upload: FileUpload) -> bool:
        if upload.is_public:
            return True
        if not upload.org_tag or upload.org_tag == self.default_org_tag:
            return True
        if upload.user_id == str(user.id):
            return True
        if user.role == "ADMIN":
            return True
        if upload.org_tag.startswith(self.private_tag_prefix):
            return False
        return upload.org_tag in user.org_tag_list

    def can_delete_document(self, user: User, upload: FileUpload) -> bool:
        return user.role == "ADMIN" or upload.user_id == str(user.id)

    def can_upload_to_org(self, user: User, org_tag: str | None) -> bool:
        if user.role == "ADMIN":
            return True
        if not org_tag or org_tag == self.default_org_tag:
            return True
        return org_tag in user.org_tag_list

    def can_manage_org(self, user: User) -> bool:
        return user.role == "ADMIN"
