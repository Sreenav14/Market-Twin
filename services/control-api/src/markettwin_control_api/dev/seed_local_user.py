"""Provision an approved local user."""

import argparse
import asyncio

from sqlalchemy import select

from markettwin_control_api.auth.providers.local import LOCAL_AUTH_ISSUER
from markettwin_control_api.config import get_settings
from markettwin_control_api.database import DatabaseRuntime
from markettwin_control_api.persistence.models import (
    User,
    UserIdentity,
    Workspace,
    WorkspaceMember,
)


async def seed_local_user(
    *,
    email: str,
    display_name: str | None = None,
) -> None:
    """Provision an approved local user."""
    settings = get_settings()

    if settings.app_env != "local":
        raise RuntimeError("Local user seeding is only available in the local environment.")

    cleaned_email = email.strip()
    normalized_email = cleaned_email.casefold()
    cleaned_display_name = display_name.strip() if display_name is not None else ""

    if not cleaned_email:
        raise ValueError("Email is required.")

    if not cleaned_display_name:
        raise ValueError("Display name is required.")

    database = DatabaseRuntime(settings)
    identity_already_existed = False

    try:
        async with database.session_factory() as session:
            async with session.begin():
                identity_result = await session.execute(
                    select(UserIdentity).where(
                        UserIdentity.issuer == LOCAL_AUTH_ISSUER,
                        UserIdentity.subject == normalized_email,
                    )
                )

                existing_identity = identity_result.scalar_one_or_none()

                if existing_identity is not None:
                    identity_already_existed = True
                    user_result = await session.execute(
                        select(User).where(User.id == existing_identity.user_id)
                    )
                    user = user_result.scalar_one()
                else:
                    user_result = await session.execute(
                        select(User).where(User.normalized_email == normalized_email)
                    )

                    user = user_result.scalar_one_or_none()

                    if user is None:
                        user = User(
                            email=cleaned_email,
                            normalized_email=normalized_email,
                            display_name=cleaned_display_name,
                            status="active",
                        )

                        session.add(user)
                        await session.flush()

                    identity = UserIdentity(
                        user_id=user.id,
                        issuer=LOCAL_AUTH_ISSUER,
                        subject=normalized_email,
                    )

                    session.add(identity)
                    await session.flush()

                if user.status != "active" or user.deleted_at is not None:
                    raise RuntimeError(
                        "A matching MarketTwin user exists but is inactive or deleted."
                    )

                membership_result = await session.execute(
                    select(WorkspaceMember).where(
                        WorkspaceMember.user_id == user.id,
                    )
                )

                existing_membership = membership_result.scalars().first()

                if existing_membership is None:
                    workspace = Workspace(
                        name=f"{cleaned_display_name}'s Workspace",
                        status="active",
                        created_by_user_id=user.id,
                    )

                    session.add(workspace)
                    await session.flush()

                    membership = WorkspaceMember(
                        workspace_id=workspace.id,
                        user_id=user.id,
                        role="owner",
                    )

                    session.add(membership)

        if identity_already_existed:
            print(f"Local identity is already approved: {normalized_email}")
        else:
            print(f"Provisioned local user: {normalized_email}")

    finally:
        await database.close()


def main() -> None:
    """Run local user provisioning from command line."""

    parser = argparse.ArgumentParser(description="Provision a local user for development.")

    parser.add_argument(
        "--email",
        required=True,
        help="The email address of the user to provision.",
    )

    parser.add_argument(
        "--display-name",
        required=True,
        help="The display name of the user to provision.",
    )

    arguments = parser.parse_args()

    asyncio.run(
        seed_local_user(
            email=arguments.email,
            display_name=arguments.display_name,
        )
    )


if __name__ == "__main__":
    main()
