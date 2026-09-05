import asyncio
from traceback import format_exc

# Pyrofork captures the current event loop when a Client is constructed.  Create
# the application loop before importing modules that construct Telegram clients.
loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

from aiohttp import web
from pyrogram import idle

from bot import LOGGER, __version__
from bot.config import Telegram
from bot.server import web_server
from bot.telegram import StreamBot, UserBot, multi_clients
from bot.telegram.clients import initialize_clients


async def stop_clients():
    """Stop only clients that actually reached the connected state."""
    clients = list({id(client): client for client in [*multi_clients.values(), UserBot, StreamBot]}.values())
    connected = [client for client in clients if getattr(client, "is_connected", False)]
    if connected:
        results = await asyncio.gather(*(client.stop() for client in connected), return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                LOGGER.warning("Client shutdown failed: %s", result)


async def start_services():
    Telegram.validate()
    if StreamBot.loop is not asyncio.get_running_loop():
        raise RuntimeError("Telegram client was initialized on a different event loop")
    runner = None
    try:
        LOGGER.info("Initializing %s v-%s", Telegram.SITE_NAME, __version__)

        await StreamBot.start()
        StreamBot.username = StreamBot.me.username
        LOGGER.info("Bot Client: [@%s]", StreamBot.username)
        handler_count = sum(len(handlers) for handlers in StreamBot.dispatcher.groups.values())
        LOGGER.info("Telegram dispatcher ready with %s handlers", handler_count)

        if Telegram.SESSION_STRING:
            await UserBot.start()
            UserBot.username = UserBot.me.username or UserBot.me.first_name or UserBot.me.id
            LOGGER.info("User Client: %s", UserBot.username)

        LOGGER.info("Initializing additional streaming clients")
        await initialize_clients()

        LOGGER.info("Starting %s web server on port %s", Telegram.SITE_NAME, Telegram.PORT)
        runner = web.AppRunner(await web_server())
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", Telegram.PORT).start()

        LOGGER.info("%s is ready at %s", Telegram.SITE_NAME, Telegram.BASE_URL or f"http://127.0.0.1:{Telegram.PORT}")
        await idle()
    finally:
        if runner is not None:
            await runner.cleanup()
        await stop_clients()


def main():
    try:
        loop.run_until_complete(start_services())
    except KeyboardInterrupt:
        LOGGER.info("%s stopped", Telegram.SITE_NAME)
    except Exception:
        LOGGER.error(format_exc())
        raise SystemExit(1)
    finally:
        asyncio.set_event_loop(None)
        loop.close()


if __name__ == "__main__":
    main()
