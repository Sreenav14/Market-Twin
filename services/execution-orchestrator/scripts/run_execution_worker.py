"""Run the persistent MarketTwin execution worker."""

import asyncio

from markettwin_execution_orchestrator.worker import main

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
