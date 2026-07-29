"""写入系统初始化所需的超管账户、资料、角色和绑定关系。"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


def bootstrap_project() -> Path:
    project_root = Path(__file__).resolve().parents[2]
    os.chdir(project_root)
    sys.path.insert(0, str(project_root))
    return project_root


bootstrap_project()

from app.core.config.enums import (  # noqa: E402
    AccountStatusEnum,
    AccountType,
    StatusEnum,
    SysBizCategory,
)
from app.core.security.password import hash_password  # noqa: E402
from app.modules.iam.account.model import (  # noqa: E402
    SysAccount,
    SysAccountIdentity,
)
from app.modules.iam.enums import (  # noqa: E402
    AccountIdentityBindStatus,
    AccountIdentityType,
    IamRelationSubjectType,
    IamRelationTargetType,
    IamRelationType,
    RoleScopeType,
)
from app.modules.iam.relation.model import SysIamRelation  # noqa: E402
from app.modules.iam.role.constants import SUPER_ADMIN_ROLE_CODE  # noqa: E402
from app.modules.iam.role.model import SysRole  # noqa: E402
from app.modules.user.admin.model import AdminUserProfile  # noqa: E402
from app.platform.db.session import close_engine, get_session_factory  # noqa: E402

SUPER_ADMIN_ACCOUNT_ID = "1"
SUPER_ADMIN_ROLE_ID = "1"
SUPER_ADMIN_IDENTITY_ID = "1"
SUPER_ADMIN_ACCOUNT_ROLE_REL_ID = "1"


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed super admin account and role data.")
    parser.add_argument(
        "--account",
        default=os.getenv("SEED_SUPER_ADMIN_ACCOUNT", "superadmin"),
        help="超管登录账号，默认读取 SEED_SUPER_ADMIN_ACCOUNT 或 superadmin。",
    )
    parser.add_argument(
        "--password",
        default=os.getenv("SEED_SUPER_ADMIN_PASSWORD", "123456"),
        help="超管初始密码，默认读取 SEED_SUPER_ADMIN_PASSWORD 或 123456。",
    )
    parser.add_argument(
        "--reset-password",
        action="store_true",
        default=env_bool("SEED_SUPER_ADMIN_RESET_PASSWORD"),
        help="已存在超管账号时也重置密码；也可设置 SEED_SUPER_ADMIN_RESET_PASSWORD=true。",
    )
    parser.add_argument(
        "--name",
        default=os.getenv("SEED_SUPER_ADMIN_NAME", "超级管理员"),
        help="超管资料姓名，默认读取 SEED_SUPER_ADMIN_NAME 或 超级管理员。",
    )
    parser.add_argument(
        "--nickname",
        default=os.getenv("SEED_SUPER_ADMIN_NICKNAME", "超管"),
        help="超管资料昵称，默认读取 SEED_SUPER_ADMIN_NICKNAME 或 超管。",
    )
    parser.add_argument(
        "--email",
        default=os.getenv("SEED_SUPER_ADMIN_EMAIL"),
        help="超管资料邮箱，默认读取 SEED_SUPER_ADMIN_EMAIL。",
    )
    parser.add_argument(
        "--phone",
        default=os.getenv("SEED_SUPER_ADMIN_PHONE"),
        help="超管资料手机号，默认读取 SEED_SUPER_ADMIN_PHONE。",
    )
    return parser


async def ensure_unique_account_identity(
    db: AsyncSession,
    *,
    identifier: str,
) -> None:
    stmt = select(SysAccountIdentity).where(
        SysAccountIdentity.identity_type == AccountIdentityType.ACCOUNT.value,
        SysAccountIdentity.identifier == identifier,
        SysAccountIdentity.account_id != SUPER_ADMIN_ACCOUNT_ID,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise RuntimeError(
            f"登录账号 {identifier!r} 已被账户 {existing.account_id!r} 使用，无法作为超管账号。"
        )


async def ensure_account(
    db: AsyncSession,
    *,
    account: str,
    password: str,
    reset_password: bool,
) -> str:
    entity = await db.get(SysAccount, SUPER_ADMIN_ACCOUNT_ID)
    if entity is None:
        db.add(
            SysAccount(
                id=SUPER_ADMIN_ACCOUNT_ID,
                password_hash=hash_password(password),
                account_type=AccountType.ADMIN.value,
                account_status=AccountStatusEnum.ENABLED.value,
                cancelled_at=None,
                cancelled_by=None,
                cancel_reason=None,
            )
        )
        await db.flush()
        return "created"

    entity.account_type = AccountType.ADMIN.value
    entity.account_status = AccountStatusEnum.ENABLED.value
    entity.cancelled_at = None
    entity.cancelled_by = None
    entity.cancel_reason = None
    if reset_password:
        entity.password_hash = hash_password(password)
    await db.flush()
    return "updated"


async def ensure_account_identity(
    db: AsyncSession,
    *,
    account: str,
) -> str:
    await ensure_unique_account_identity(db, identifier=account)

    stmt = select(SysAccountIdentity).where(
        SysAccountIdentity.account_id == SUPER_ADMIN_ACCOUNT_ID,
        SysAccountIdentity.identity_type == AccountIdentityType.ACCOUNT.value,
    )
    entity = (await db.execute(stmt)).scalar_one_or_none()
    if entity is None:
        identity_by_id = await db.get(SysAccountIdentity, SUPER_ADMIN_IDENTITY_ID)
        if identity_by_id is not None and identity_by_id.account_id != SUPER_ADMIN_ACCOUNT_ID:
            raise RuntimeError(
                f"登录标识种子 ID {SUPER_ADMIN_IDENTITY_ID!r} 已被账户 "
                f"{identity_by_id.account_id!r} 使用。"
            )
        entity = identity_by_id or SysAccountIdentity(id=SUPER_ADMIN_IDENTITY_ID)
        db.add(entity)
        action = "created"
    else:
        action = "updated"

    entity.account_id = SUPER_ADMIN_ACCOUNT_ID
    entity.identity_type = AccountIdentityType.ACCOUNT.value
    entity.identifier = account
    entity.verified = True
    entity.is_primary = True
    entity.bind_status = AccountIdentityBindStatus.BOUND.value
    await db.flush()
    return action


async def ensure_admin_profile(
    db: AsyncSession,
    *,
    name: str,
    nickname: str,
    email: str | None,
    phone: str | None,
) -> str:
    entity = await db.get(AdminUserProfile, SUPER_ADMIN_ACCOUNT_ID)
    if entity is None:
        entity = AdminUserProfile(account_id=SUPER_ADMIN_ACCOUNT_ID)
        db.add(entity)
        action = "created"
    else:
        action = "updated"

    entity.name = name
    entity.nickname = nickname
    entity.email = email
    entity.phone = phone
    entity.title = "Super Admin"
    entity.employee_no = "SA-0001"
    entity.remark = "系统内置超管账户"
    await db.flush()
    return action


async def ensure_role(db: AsyncSession) -> str:
    stmt = select(SysRole).where(
        SysRole.code == SUPER_ADMIN_ROLE_CODE,
        SysRole.id != SUPER_ADMIN_ROLE_ID,
    )
    existing = (await db.execute(stmt)).scalar_one_or_none()
    if existing is not None:
        raise RuntimeError(
            f"超管角色编码 {SUPER_ADMIN_ROLE_CODE!r} 已被角色 {existing.id!r} 使用。"
        )

    entity = await db.get(SysRole, SUPER_ADMIN_ROLE_ID)
    if entity is None:
        entity = SysRole(id=SUPER_ADMIN_ROLE_ID)
        db.add(entity)
        action = "created"
    else:
        action = "updated"

    entity.code = SUPER_ADMIN_ROLE_CODE
    entity.name = "超级管理员"
    entity.category = SysBizCategory.SYS.value
    entity.scope_type = RoleScopeType.PLATFORM.value
    entity.owner_dept_id = None
    entity.sort = 1
    entity.status = StatusEnum.ENABLED.value
    entity.is_builtin = True
    entity.description = "系统内置超级管理员角色"
    entity.extra = {}
    await db.flush()
    return action


async def ensure_account_role_rel(db: AsyncSession) -> str:
    stmt = select(SysIamRelation).where(
        SysIamRelation.subject_type == IamRelationSubjectType.ACCOUNT.value,
        SysIamRelation.subject_id == SUPER_ADMIN_ACCOUNT_ID,
        SysIamRelation.relation_type == IamRelationType.ACCOUNT_ROLE.value,
        SysIamRelation.target_type == IamRelationTargetType.ROLE.value,
        SysIamRelation.target_id == SUPER_ADMIN_ROLE_ID,
    )
    entity = (await db.execute(stmt)).scalar_one_or_none()
    if entity is not None:
        return "exists"

    rel_by_id = await db.get(SysIamRelation, SUPER_ADMIN_ACCOUNT_ROLE_REL_ID)
    if rel_by_id is None:
        db.add(
            SysIamRelation(
                id=SUPER_ADMIN_ACCOUNT_ROLE_REL_ID,
                subject_type=IamRelationSubjectType.ACCOUNT.value,
                subject_id=SUPER_ADMIN_ACCOUNT_ID,
                relation_type=IamRelationType.ACCOUNT_ROLE.value,
                target_type=IamRelationTargetType.ROLE.value,
                target_id=SUPER_ADMIN_ROLE_ID,
            )
        )
    else:
        db.add(
            SysIamRelation(
                subject_type=IamRelationSubjectType.ACCOUNT.value,
                subject_id=SUPER_ADMIN_ACCOUNT_ID,
                relation_type=IamRelationType.ACCOUNT_ROLE.value,
                target_type=IamRelationTargetType.ROLE.value,
                target_id=SUPER_ADMIN_ROLE_ID,
            )
        )
    await db.flush()
    return "created"


async def seed(args: argparse.Namespace) -> dict[str, str]:
    account = str(args.account).strip()
    password = str(args.password)
    if not account:
        raise ValueError("超管登录账号不能为空。")
    if len(password) < 6:
        raise ValueError("超管初始密码长度不能小于 6。")

    session_factory = get_session_factory()
    async with session_factory() as db:
        async with db.begin():
            result = {
                "account": await ensure_account(
                    db,
                    account=account,
                    password=password,
                    reset_password=bool(args.reset_password),
                ),
                "identity": await ensure_account_identity(db, account=account),
                "profile": await ensure_admin_profile(
                    db,
                    name=str(args.name).strip() or "超级管理员",
                    nickname=str(args.nickname).strip() or "超管",
                    email=args.email,
                    phone=args.phone,
                ),
                "role": await ensure_role(db),
                "account_role_rel": await ensure_account_role_rel(db),
            }
    return result


async def async_main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        result = await seed(args)
    finally:
        await close_engine()

    print("Super admin seed completed:")
    for name, action in result.items():
        print(f"- {name}: {action}")
    print(f"- account_id: {SUPER_ADMIN_ACCOUNT_ID}")
    print(f"- role_id: {SUPER_ADMIN_ROLE_ID}")


def main() -> None:
    asyncio.run(async_main())


if __name__ == "__main__":
    main()
