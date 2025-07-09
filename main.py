import asyncio
from bot import run_skymovies
from filmy import start_filmyfly

async def main():
    await asyncio.gather(
        run_skymovies(),
        start_filmyfly()
    )

if __name__ == "__main__":
    asyncio.run(main())
