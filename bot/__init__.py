from time import time
from logging import getLogger, FileHandler, StreamHandler, INFO, ERROR, basicConfig

try:
    from uvloop import install
    install()
except (ImportError, NotImplementedError):
    # uvloop is unavailable on Windows; asyncio's default loop works correctly.
    pass
basicConfig(format="[%(asctime)s] [%(levelname)s] - %(message)s",
            datefmt="%d-%b-%y %I:%M:%S %p",
            handlers=[FileHandler('log.txt'), StreamHandler()],
            level=INFO)

getLogger("aiohttp").setLevel(ERROR)
getLogger("pyrogram").setLevel(ERROR)
getLogger("aiohttp.web").setLevel(ERROR)

LOGGER = getLogger(__name__)
StartTime = time()

__version__ = "3.0.0"

