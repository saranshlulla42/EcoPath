import asyncio
import logging
logging.basicConfig(level=logging.ERROR)

from config import get_settings
from services.gemini_service import generate_ecology_answers

async def run():
    print("Generating ecology answers...")
    answers = await generate_ecology_answers("Bald Eagle", "Haliaeetus leucocephalus")
    print("Answers:", answers)

if __name__ == "__main__":
    asyncio.run(run())
