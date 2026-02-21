import asyncio
import random
import html
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import Config
from database import db
from tmdb import tmdb
from utils.logger import setup_logger

logger = setup_logger(__name__)

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles /start command.
    If args provided, treats as redirect code.
    If no args, just welcomes the user (or admin).
    """
    args = context.args
    if not args:
        user_id = update.effective_user.id
        if user_id == Config.CEO_ID:
            await update.message.reply_text(
                "👋 <b>Welcome, Admin!</b>\n\n"
                "Use /admin to access the dashboard.\n"
                "To set up a redirect, simply add me as an Admin to a channel.",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text(
                "👋 <b>Welcome to XTV Redirect Bot!</b>\n\n"
                "I am the gatekeeper for XTV Franchise channels.\n"
                "Please use the link provided in our public channels.",
                parse_mode='HTML'
            )
        return

    code = args[0]
    redirect_entry = await db.get_redirect(code)

    if not redirect_entry:
        await update.message.reply_text("❌ <b>Invalid or expired link.</b>", parse_mode='HTML')
        return

    # Fetch TMDb details
    tmdb_id = redirect_entry.get('tmdb_id')
    media_type = redirect_entry.get('media_type', 'tv') # Default to tv if missing

    details = await tmdb.get_details(media_type, tmdb_id)

    if not details:
        # Fallback if TMDb fails
        details = {
            "title": redirect_entry.get('series_name'),
            "year": "N/A",
            "rating": "N/A",
            "genres": "Unknown",
            "overview": "No description available.",
            "poster_url": None
        }

    # Construct Caption (Escape HTML characters)
    title = html.escape(str(details.get('title', 'Unknown')))
    genres = html.escape(str(details.get('genres', 'Unknown')))
    overview = html.escape(str(details.get('overview', 'No description available.'))[:300])

    caption = (
        f"<b>{title}</b> • {details.get('year', 'N/A')}\n"
        f"⭐️ <b>{details.get('rating', 'N/A')}/10</b>  🎭 {genres}\n\n"
        f"💬 <b>Description:</b>\n"
        f"{overview}...\n\n"
        f"Enjoy watching! 🍿"
    )

    # Initial Button: Loading...
    loading_keyboard = [[InlineKeyboardButton("⏳ Loading...", callback_data="loading_wait")]]

    # Send Message
    if details['poster_url']:
        message = await update.message.reply_photo(
            photo=details['poster_url'],
            caption=caption,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(loading_keyboard)
        )
    else:
        message = await update.message.reply_text(
            text=caption,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(loading_keyboard)
        )

    # Wait 3-8 seconds
    delay = random.uniform(3, 8)
    await asyncio.sleep(delay)

    # Change Button to "Join Channel"
    invite_link = redirect_entry.get('invite_link')
    join_keyboard = [[InlineKeyboardButton("🚀 Join Channel", url=invite_link)]]

    try:
        await message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(join_keyboard))
    except Exception as e:
        logger.warning(f"Failed to edit message for code {code}: {e}")

    # Update stats in background
    await db.update_stats(code)

async def loading_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles clicks on the 'Loading...' button.
    """
    await update.callback_query.answer("Please wait...", show_alert=False)
