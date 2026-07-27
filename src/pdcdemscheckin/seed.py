import asyncio

from sqlalchemy import select

from .auth import hash_password
from .db import Database
from .models import Organizer, OrganizerRole
from .settings import get_settings


async def seed_admin() -> None:
    settings = get_settings()
    email = settings.seed_admin_email.strip().lower()
    if not email or not settings.seed_admin_password:
        return

    database = Database(settings.database_url)
    try:
        async with database.session() as db:
            organizer = await db.scalar(select(Organizer).where(Organizer.email == email))
            if not organizer:
                db.add(
                    Organizer(
                        email=email,
                        display_name=settings.seed_admin_name,
                        password_hash=hash_password(settings.seed_admin_password),
                        role=OrganizerRole.owner,
                    )
                )
    finally:
        await database.close()


if __name__ == "__main__":
    asyncio.run(seed_admin())
