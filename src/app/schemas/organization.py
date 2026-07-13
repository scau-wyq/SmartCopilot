from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OrganizationTagRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tag_id: str | None = Field(default=None, alias="tagId")
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    parent_tag: str | None = Field(default=None, alias="parentTag")
    upload_max_size_mb: int | None = Field(default=None, alias="uploadMaxSizeMb")


class OrganizationTagResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    tag_id: str = Field(alias="tagId")
    name: str
    description: str | None = None
    parent_tag: str | None = Field(default=None, alias="parentTag")
    upload_max_size_bytes: int | None = Field(default=None, alias="uploadMaxSizeBytes")
    upload_max_size_mb: int | None = Field(default=None, alias="uploadMaxSizeMb")
    created_by: int | None = Field(default=None, alias="createdBy")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    children: list["OrganizationTagResponse"] | None = None


class AssignOrgTagsRequest(BaseModel):
    org_tags: list[str] = Field(alias="orgTags")


class PrimaryOrgRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    primary_org: str = Field(alias="primaryOrg", min_length=1)
    user_id: int | None = Field(default=None, alias="userId")
