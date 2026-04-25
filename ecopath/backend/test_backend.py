import asyncio
from config import get_settings
from services.supabase_client import get_supabase
from services.gemini_service import generate_ecology_answers
import logging

logging.basicConfig(level=logging.INFO)

async def test():
    supabase = get_supabase()
    print("Checking supabase...")
    try:
        res = supabase.table("species_cached_answers").select("*").eq("species_id", "12345").execute()
        print("Select result:", res.data)
    except Exception as e:
        print("Supabase select error:", e)

    print("Generating from Gemini...")
    try:
        ans = await generate_ecology_answers("White-bellied Heron", "Ardea insignis")
        print("Gemini result keys:", list(ans.keys()) if ans else ans)
    except Exception as e:
        print("Gemini error:", e)

if __name__ == "__main__":
    asyncio.run(test())
