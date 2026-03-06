import asyncio
import random
import html
from datetime import datetime, timedelta
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

    channel_id = redirect_entry.get('private_channel_id')
    final_invite_link = redirect_entry.get('invite_link')
    user_id = update.effective_user.id

    # Check if user is already a member before fetching metadata
    is_member = False
    if channel_id:
        try:
            chat_member = await context.bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if chat_member.status in ['member', 'creator', 'administrator']:
                is_member = True
        except Exception as e:
            logger.warning(f"Failed to check member status for {user_id} in {channel_id}: {e}")

    if is_member:
        # Fast-track for existing members
        join_keyboard = [[InlineKeyboardButton("🚀 Join Channel", url=final_invite_link)]]
        await update.message.reply_text(
            "✅ <b>You are already a member!</b>\n\nClick below to go directly to the channel.",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(join_keyboard)
        )
        # Update stats in background
        await db.update_stats(code)
        return

    # Fetch TMDb details - Try to get cached details first
    details = redirect_entry.get('tmdb_details')

    if not details:
        # Fetch from TMDB if not cached
        tmdb_id = redirect_entry.get('tmdb_id')
        media_type = redirect_entry.get('media_type', 'tv') # Default to tv if missing

        details = await tmdb.get_details(media_type, tmdb_id)

        if details:
            # Cache the details for future use
            await db.update_redirect(code, {"tmdb_details": details})

    if not details:
        # Fallback if TMDb fails and not cached
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

    base_caption = (
        f"<b>{title}</b> • {details.get('year', 'N/A')}\n"
        f"⭐️ <b>{details.get('rating', 'N/A')}/10</b>  🎭 {genres}\n\n"
        f"💬 <b>Description:</b>\n"
        f"{overview}...\n\n"
    )

    initial_caption = base_caption + "Enjoy watching! 🍿"

    # Initial Button: Loading...
    loading_keyboard = [[InlineKeyboardButton("⏳ Loading...", callback_data="loading_wait")]]

    # Send Message
    if details['poster_url']:
        message = await update.message.reply_photo(
            photo=details['poster_url'],
            caption=initial_caption,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(loading_keyboard)
        )
    else:
        message = await update.message.reply_text(
            text=initial_caption,
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup(loading_keyboard)
        )

    # Dynamic Loading Animation
    loading_messages_pool = [
        "Creating Individual Invite Link... ⚙️",
        "Verifying User Access... 🔐",
        "Preparing Secure Channel... 📡",
        "Establishing Secure Connection... 📶",
        "Encrypting Data Stream... 🔑",
        "Allocating Bandwidth... ⚡️",
        "Syncing with Server... 🔄",
        "Authenticating Request... 🆔",
        "Optimizing Video Quality... 📺",
        "Checking Subscription Status... 📋",
        "Generating Access Token... 🎟️",
        "Finalizing Setup... ✅"
    ]
    # Select 3 random messages to show
    loading_messages = random.sample(loading_messages_pool, 3)

    for msg in loading_messages:
        try:
            new_text = base_caption + f"{msg}"
            if details['poster_url']:
                await message.edit_caption(
                    caption=new_text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(loading_keyboard)
                )
            else:
                await message.edit_text(
                    text=new_text,
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(loading_keyboard)
                )
        except Exception:
            pass  # Ignore errors (e.g., message not modified)
        await asyncio.sleep(1.5)

    # Determine Invite Link
    # For non-members, create one-time invite link with 10 min expiration
    expiration_notice = ""

    if channel_id:
        try:
            expire_time = datetime.now() + timedelta(minutes=10)
            invite = await context.bot.create_chat_invite_link(
                chat_id=channel_id,
                name=f"User {user_id}",
                member_limit=1,
                expire_date=expire_time
            )
            final_invite_link = invite.invite_link
            expiration_notice = "\n⚠️ <b>Link expires in 10 minutes!</b>"
        except Exception as e:
            logger.warning(f"Failed to generate dynamic link for {channel_id}: {e}")

    # Change Button to "Join Channel" and revert text
    join_keyboard = [[InlineKeyboardButton("🚀 Join Channel", url=final_invite_link)]]

    final_caption = initial_caption + expiration_notice

    try:
        if details['poster_url']:
            await message.edit_caption(
                caption=final_caption,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(join_keyboard)
            )
        else:
            await message.edit_text(
                text=final_caption,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup(join_keyboard)
            )
    except Exception as e:
        logger.warning(f"Failed to edit message for code {code}: {e}")

    # Update stats in background
    await db.update_stats(code)

async def loading_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles clicks on the 'Loading...' button.
    """
    await update.callback_query.answer("Please wait...", show_alert=False)
