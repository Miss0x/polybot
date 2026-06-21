import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from polybot.collect.polymarket_client import PolymarketClient
from polybot.settings import get_settings


async def main() -> None:
    settings = get_settings()
    client = PolymarketClient(
        gamma_base_url=settings.polymarket.gamma_base_url,
        clob_base_url=settings.polymarket.clob_base_url,
    )
    events = await client.list_events(limit=20)
    for index, event in enumerate(events[:10], start=1):
        question = event.get("question") or event.get("title")
        print(f"{index:02d}. id={event.get('id')} | question={question}")


if __name__ == "__main__":
    asyncio.run(main())
