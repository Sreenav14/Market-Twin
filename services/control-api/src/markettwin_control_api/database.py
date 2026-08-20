""" Database runtime owned bt the control plane."""

from markettwin_database import (
    create_database_engine,
    create_session_factory,
)

from markettwin_control_api.config import Settings


class DatabaseRuntime:
    """Long-lived database resource for the control API."""
    
    def __init__(self, settings: Settings) -> None:
        self.engine = create_database_engine(settings.database_url)
        self.session_factory = create_session_factory(self.engine)
        
    async def close(self) -> None:
        """ Release the database resources owned by the runtime."""
        await self.engine.dispose()
        
        