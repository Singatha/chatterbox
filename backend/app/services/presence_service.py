from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database import AsyncSessionLocal
from app.repositories.conversation_repository import ConversationRepository
from app.repositories.user_repository import UserRepository
from app.websocket.events import PresenceOfflineData, PresenceOfflineEvent
from app.websocket.manager import ConnectionManager


async def mark_user_offline(
    user_id: UUID,
    manager: ConnectionManager,
    session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal,
) -> None:
    last_seen = datetime.now(timezone.utc)
    async with session_factory() as session:
        await UserRepository(session).set_last_seen(user_id, last_seen)
        peer_ids = await ConversationRepository(session).peer_ids(user_id)
        await session.commit()
    await manager.send_to_users(
        peer_ids,
        PresenceOfflineEvent(
            data=PresenceOfflineData(
                user_id=user_id,
                last_seen=last_seen.isoformat(),
            )
        ).model_dump(mode="json"),
        exclude_user_id=user_id,
    )
