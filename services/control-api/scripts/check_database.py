""" Verify that the control API can connect to the database."""

import asyncio

from markettwin_control_api.config import get_settings
from markettwin_control_api.database import DatabaseRuntime
from markettwin_database import session_scope
from sqlalchemy import text


async def main() -> None:
    """Run a tiny postgresql connectivity check."""
    
    settings = get_settings()
    
    runtime = DatabaseRuntime(settings)

    try:
        async with session_scope(runtime.session_factory) as session:
            result = await session.execute(text("SELECT 1"))
            value = result.scalar_one()
            
            if value != 1:
                raise RuntimeError("Database connectivity check failed.")
            
        print("Markettwin postgresql connection: Ok")
        
    finally:
        await runtime.close()
        
if __name__ == "__main__":
    asyncio.run(main())
