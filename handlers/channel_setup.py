from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ChatMember
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    ChatMemberHandler,
    MessageHandler,
    CallbackQueryHandler,
    CommandHandler,
    filters
)
from config import Config
from database import db
from tmdb import tmdb
from utils.logger import setup_logger
from utils.helpers import generate_redirect_code

logger = setup_logger(__name__)

SERIES_NAME, SERIES_SELECTION = range(2)

async def setup_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point: Triggered when the bot is added as an admin to a channel.
    """
    result = update.my_chat_member
    new_member = result.new_chat_member
    old_member = result.old_chat_member

    # Check if the bot was promoted to admin (and wasn't already one)
    if new_member.status != ChatMember.ADMINISTRATOR:
        return ConversationHandler.END

    if old_member.status == ChatMember.ADMINISTRATOR:
        # Already admin, probably just permission update
        return ConversationHandler.END

    chat = result.chat
    logger.info(f"Bot added to channel: {chat.title} ({chat.id}) by user {result.from_user.id}")

    # Only allow CEO_ID or the user who added the bot (if authorized, but for now let's assume CEO_ID or prompt says 'I click accept')
    # The prompt implies the user adding the bot is the one configuring it.
    user = result.from_user

    # Try to generate an invite link
    try:
        invite_link_obj = await context.bot.create_chat_invite_link(
            chat_id=chat.id,
            name="XTV Redirect Link"
            # member_limit omitted for unlimited
        )
        invite_link = invite_link_obj.invite_link
    except Exception as e:
        logger.error(f"Failed to create invite link for {chat.id}: {e}")
        # Try to send a message to the user about the error
        try:
            await user.send_message(f"⚠️ Error setting up redirect for <b>{chat.title}</b>: Could not create invite link. Please ensure I have 'Invite Users' permission.")
        except:
            pass
        return ConversationHandler.END

    # Store channel info in user_data
    context.user_data['setup_channel_id'] = chat.id
    context.user_data['setup_channel_title'] = chat.title
    context.user_data['setup_invite_link'] = invite_link

    # Message the user to start the setup
    try:
        await user.send_message(
            f"🚀 <b>Setup for {chat.title}</b> detected!\n\n"
            f"I've generated an invite link: {invite_link}\n\n"
            "Now, please tell me the <b>Series Name</b> for this channel (e.g., 'The Rookie').",
            parse_mode='HTML'
        )
        return SERIES_NAME
    except Exception as e:
        logger.error(f"Could not message user {user.id}: {e}")
        return ConversationHandler.END

async def receive_series_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User sends the series name. Search TMDb.
    """
    query = update.message.text
    if not query:
        await update.message.reply_text("Please enter a valid series name.")
        return SERIES_NAME

    user = update.effective_user
    await update.message.reply_text(f"🔎 Searching for '{query}'...")

    results = await tmdb.search(query)

    if not results:
        await update.message.reply_text("❌ No results found. Please try another name.")
        return SERIES_NAME # Stay in state

    # Create buttons
    keyboard = []
    for item in results:
        btn_text = f"{item['title']} ({item['media_type'].upper()})"
        keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"select_idx|{results.index(item)}")])

    keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_setup")])

    context.user_data['search_results'] = results

    await update.message.reply_text(
        "Select the correct series from the list below:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return SERIES_SELECTION

async def receive_series_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User selects a series from the buttons.
    """
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "cancel_setup":
        await query.edit_message_text("❌ Setup cancelled.")
        context.user_data.clear()
        return ConversationHandler.END

    if not data.startswith("select_idx|"):
        return SERIES_SELECTION

    try:
        idx = int(data.split("|")[1])
        selected = context.user_data['search_results'][idx]
    except (IndexError, ValueError, KeyError):
        await query.edit_message_text("⚠️ Error selecting series. Please try searching again.")
        return SERIES_NAME

    # Retrieve stored channel info
    channel_id = context.user_data.get('setup_channel_id')
    invite_link = context.user_data.get('setup_invite_link')

    if not channel_id or not invite_link:
        await query.edit_message_text("⚠️ Session expired. Please add the bot to the channel again.")
        return ConversationHandler.END

    # Generate Redirect Code
    code = generate_redirect_code()

    # Save to DB
    redirect_data = {
        "code": code,
        "series_name": selected['title'],
        "tmdb_id": selected['id'],
        "media_type": selected['media_type'],
        "private_channel_id": channel_id,
        "invite_link": invite_link
    }

    success = await db.create_redirect(redirect_data)

    if success:
        bot_username = context.bot.username
        deep_link = f"https://t.me/{bot_username}?start={code}"

        await query.edit_message_text(
            f"✅ <b>Setup Complete!</b>\n\n"
            f"📺 <b>Series:</b> {selected['title']}\n"
            f"🔗 <b>Redirect Link:</b>\n{deep_link}\n\n"
            f"This link will show the loading animation and redirect to the channel.",
            parse_mode='HTML'
        )
    else:
        await query.edit_message_text("❌ Database Error. Please try again.")

    # Clear user data
    context.user_data.clear()
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the conversation."""
    await update.message.reply_text("Setup cancelled.")
    context.user_data.clear()
    return ConversationHandler.END

# Create the ConversationHandler
setup_conversation_handler = ConversationHandler(
    entry_points=[ChatMemberHandler(setup_channel, ChatMemberHandler.MY_CHAT_MEMBER)],
    states={
        SERIES_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_series_name)],
        SERIES_SELECTION: [CallbackQueryHandler(receive_series_selection)]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_chat=False, # Important: track by user, not channel
    per_user=True
)
