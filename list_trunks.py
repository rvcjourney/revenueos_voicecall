"""
list_trunks.py — List all outbound SIP trunks in your LiveKit project.

SDK: livekit-api 1.1.0
"""
import asyncio
import aiohttp
from livekit.api import sip_service
from livekit import api
from config import LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET


async def list_trunks():
    async with aiohttp.ClientSession() as session:
        sip = sip_service.SipService(
            session,
            LIVEKIT_URL,
            LIVEKIT_API_KEY,
            LIVEKIT_API_SECRET,
        )

        response = await sip.list_sip_outbound_trunk(
            api.ListSIPOutboundTrunkRequest()
        )

        trunks = response.items
        if not trunks:
            print("\nNo outbound SIP trunks found.")
            print("Run: python create_trunk.py")
        else:
            print(f"\nFound {len(trunks)} trunk(s):\n")
            for t in trunks:
                print(f"  ID      : {t.sip_trunk_id}")
                print(f"  Name    : {t.name}")
                print(f"  Address : {t.address}")
                print(f"  Numbers : {', '.join(t.numbers) if t.numbers else 'none'}")
                print()


if __name__ == "__main__":
    asyncio.run(list_trunks())