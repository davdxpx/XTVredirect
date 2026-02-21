import logging
import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ChatMemberHandler, ContextTypes
from config import Config
from utils.logger import setup_logger
from handlers.admin import admin_dashboard, admin_callback_handler, regenerate_conversation_handler
from handlers.start import start_handler, loading_callback
from handlers.channel_setup import setup_conversation_handler, channel_event_handler

# Set up logging
logger = setup_logger(__name__)

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a telegram message to notify the developer."""
    logger.error(f"Exception while handling an update: {context.error}")

def main():
    """Start the bot."""
    # Validate configuration
    try:
        Config.validate()
    except ValueError as e:
        logger.critical(f"Configuration Error: {e}")
        return

    application = ApplicationBuilder().token(Config.BOT_TOKEN).build()

    # Handlers

    # 1. Conversation Handlers (Stateful)
    # Channel Setup (High Priority)
    application.add_handler(setup_conversation_handler)

    # Channel Event Handler (Triggers the setup message to Admin)
    application.add_handler(channel_event_handler)

    # Admin Regenerate Conversation (Specific Pattern)
    application.add_handler(regenerate_conversation_handler)

    # 2. Command Handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("admin", admin_dashboard))

    # 3. Callback Query Handlers (Specific patterns)
    # Note: regenerate_conversation_handler handles 'admin_regenerate', so admin_callback_handler won't see it if conversation starts.
    # But admin_callback_handler matches '^admin_', so we need to be careful.
    # Actually, Application checks handlers in order. If regenerate_conversation_handler matches, it handles it?
    # Wait, ConversationHandler only handles if it's in a state OR if it matches an entry point.
    # If it matches entry point, it returns the first state.
    # So yes, adding it before admin_callback_handler is correct.

    application.add_handler(CallbackQueryHandler(admin_callback_handler, pattern="^admin_"))
    application.add_handler(CallbackQueryHandler(loading_callback, pattern="^loading_wait$"))

    # Error handler
    application.add_error_handler(error_handler)

    logger.info("Bot is starting...")
    application.run_polling()

if __name__ == '__main__':
    main()
