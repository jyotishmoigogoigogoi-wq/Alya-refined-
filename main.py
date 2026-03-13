import os
import asyncio
import signal
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from telegram import Update
from config import BOT_TOKEN, DATABASE_URL, logger
from database import init_db_pool, init_db, db_pool
from handlers.start import start
from handlers.plans import plans_command, giveplan_command, profile_command
from handlers.owner import (
    addapi_command, listapi_command, removeapi_command, testapi_command,
    shutdown_command, restart_command
)
from handlers.callback import on_callback
from handlers.message import chat

# Health check server
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args): pass

def run_health_check():
    port = int(os.environ.get("PORT", 5000))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    logger.info(f"Health check server on port {port}")
    server.serve_forever()

async def shutdown(app: Application):
    logger.info("Shutting down...")
    await app.updater.stop()
    await app.stop()
    await app.shutdown()
    if db_pool:
        await db_pool.close()
    logger.info("Shutdown complete")

async def main():
    if not BOT_TOKEN or not DATABASE_URL:
        raise RuntimeError("Missing BOT_TOKEN or DATABASE_URL")

    await init_db_pool()
    await init_db()

    threading.Thread(target=run_health_check, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).build()

    # Register all commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("plans", plans_command))
    app.add_handler(CommandHandler("giveplan", giveplan_command, filters=filters.COMMAND))
    app.add_handler(CommandHandler("profile", profile_command))
    app.add_handler(CommandHandler("addapi", addapi_command, filters=filters.COMMAND))
    app.add_handler(CommandHandler("listapi", listapi_command, filters=filters.COMMAND))
    app.add_handler(CommandHandler("removeapi", removeapi_command, filters=filters.COMMAND))
    app.add_handler(CommandHandler("testapi", testapi_command, filters=filters.COMMAND))
    app.add_handler(CommandHandler("shutdown", shutdown_command, filters=filters.COMMAND))
    app.add_handler(CommandHandler("restart", restart_command, filters=filters.COMMAND))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Sticker.ALL | filters.Document.IMAGE) & ~filters.COMMAND,
        chat
    ))

    shutdown_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_event.set)

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)
    logger.info("Bot started successfully!")

    await shutdown_event.wait()
    await shutdown(app)

if __name__ == "__main__":
    asyncio.run(main())