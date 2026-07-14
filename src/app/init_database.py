import asyncio
import os
import re

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.billing import RechargePackage
from app.models.organization_tag import OrganizationTag
from app.models.user import User


PASSWORD_PATTERN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{6,18}$")

DEFAULT_PACKAGES = (
    {
        "package_name": "体验包",
        "package_price": 990,
        "package_desc": "适合轻量问答和少量知识库上传。",
        "package_benefit": "LLM Token：50 万\nEmbedding Token：20 万\n模拟支付后立即到账",
        "llm_token": 500_000,
        "embedding_token": 200_000,
        "sort_order": 10,
    },
    {
        "package_name": "标准包",
        "package_price": 2990,
        "package_desc": "适合持续问答、资料整理和中等规模知识库构建。",
        "package_benefit": "LLM Token：200 万\nEmbedding Token：100 万\n模拟支付后立即到账",
        "llm_token": 2_000_000,
        "embedding_token": 1_000_000,
        "sort_order": 20,
    },
    {
        "package_name": "专业包",
        "package_price": 9990,
        "package_desc": "适合高频问答、团队共享资料和较大规模知识库场景。",
        "package_benefit": "LLM Token：800 万\nEmbedding Token：400 万\n模拟支付后立即到账",
        "llm_token": 8_000_000,
        "embedding_token": 4_000_000,
        "sort_order": 30,
    },
)


def initial_admin_credentials() -> tuple[str, str]:
    username = os.getenv("INITIAL_ADMIN_USERNAME", "admin").strip()
    password = os.getenv("INITIAL_ADMIN_PASSWORD", "SmartCopilot123")
    if not username:
        raise ValueError("INITIAL_ADMIN_USERNAME cannot be empty")
    if not PASSWORD_PATTERN.match(password) or len(password.encode("utf-8")) > 72:
        raise ValueError(
            "INITIAL_ADMIN_PASSWORD must be 6-18 characters and contain letters and numbers"
        )
    return username, password


async def ensure_initial_data(username: str, password: str) -> User:
    async with AsyncSessionLocal() as session:
        admin = await session.scalar(select(User).where(User.username == username))
        private_tag = f"PRIVATE_{username}"
        if admin is None:
            admin = User(
                username=username,
                password=hash_password(password),
                role="ADMIN",
                org_tags=f"DEFAULT,{private_tag}",
                primary_org=private_tag,
            )
            session.add(admin)
            await session.flush()
        else:
            admin.role = "ADMIN"
            org_tags = admin.org_tag_list
            for required_tag in ("DEFAULT", private_tag):
                if required_tag not in org_tags:
                    org_tags.append(required_tag)
            admin.org_tags = ",".join(org_tags)
            if not admin.primary_org:
                admin.primary_org = private_tag

        if await session.get(OrganizationTag, "DEFAULT") is None:
            session.add(
                OrganizationTag(
                    tag_id="DEFAULT",
                    name="默认组织",
                    description="系统默认组织标签，自动分配给所有新用户",
                    parent_tag=None,
                    upload_max_size_bytes=None,
                    created_by=admin.id,
                )
            )

        if await session.get(OrganizationTag, private_tag) is None:
            session.add(
                OrganizationTag(
                    tag_id=private_tag,
                    name=f"{username}的私人空间",
                    description="用户的私人组织标签，仅用户本人可访问",
                    parent_tag=None,
                    upload_max_size_bytes=None,
                    created_by=admin.id,
                )
            )

        for package_data in DEFAULT_PACKAGES:
            existing_package = await session.scalar(
                select(RechargePackage).where(
                    RechargePackage.package_name == package_data["package_name"]
                )
            )
            if existing_package is None:
                session.add(RechargePackage(**package_data, enabled=True, deleted=False))

        await session.commit()
        return admin


async def main() -> None:
    username, password = initial_admin_credentials()
    admin = await ensure_initial_data(username, password)
    print(f"Database seed completed; initial administrator: {admin.username}")


if __name__ == "__main__":
    asyncio.run(main())
