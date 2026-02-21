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

# Conversation States
SERIES_NAME, SERIES_SELECTION = range(2)

async def setup_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Entry point: Triggered when the bot is added as an admin to a channel.
    Messages the CEO_ID (Admin) for approval instead of the user who added the bot.
    """
    result = update.my_chat_member
    new_member = result.new_chat_member
    old_member = result.old_chat_member

    # Check if the bot was promoted to admin (and wasn't already one)
    if new_member.status != ChatMember.ADMINISTRATOR:
        return

    if old_member.status == ChatMember.ADMINISTRATOR:
        # Already admin, probably just permission update
        return

    chat = result.chat
    inviter = result.from_user
    logger.info(f"Bot added to channel: {chat.title} ({chat.id}) by user {inviter.id}")

    admin_id = Config.CEO_ID

    text = (
        f"🚨 <b>New Channel Setup Request</b>\n\n"
        f"📺 <b>Channel:</b> {chat.title}\n"
        f"🆔 <b>ID:</b> <code>{chat.id}</code>\n"
        f"👤 <b>Added by:</b> {inviter.first_name} (<code>{inviter.id}</code>)\n\n"
        "Do you want to configure a redirect link for this channel?"
    )

    keyboard = [
        [
            InlineKeyboardButton("✅ Accept", callback_data=f"setup_accept|{chat.id}"),
            InlineKeyboardButton("❌ Decline", callback_data=f"setup_decline|{chat.id}")
        ]
    ]

    try:
        await context.bot.send_message(
            chat_id=admin_id,
            text=text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='HTML'
        )
    except Exception as e:
        logger.error(f"Failed to message admin {admin_id}: {e}")

async def setup_decision(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles the Accept/Decline decision from the Admin.
    This is the ENTRY POINT for the ConversationHandler.
    """
    query = update.callback_query
    await query.answer()
    data = query.data

    action, channel_id_str = data.split("|")
    channel_id = int(channel_id_str)

    if action == "setup_decline":
        await query.edit_message_text(f"❌ Setup declined for channel ID {channel_id}.")
        # Optional: Leave channel
        try:
            await context.bot.leave_chat(channel_id)
        except:
            pass
        return ConversationHandler.END

    if action == "setup_accept":
        # Check permissions / get info
        try:
            chat = await context.bot.get_chat(channel_id)
        except Exception as e:
            await query.edit_message_text(f"⚠️ Error: Could not access channel {channel_id}. Am I still admin?\n{e}")
            return ConversationHandler.END

        # Generate Invite Link
        try:
            invite_link_obj = await context.bot.create_chat_invite_link(
                chat_id=channel_id,
                name="XTV Redirect Link"
                # member_limit omitted for unlimited
            )
            invite_link = invite_link_obj.invite_link
        except Exception as e:
            logger.error(f"Failed to create invite link for {chat.id}: {e}")
            await query.edit_message_text(
                f"⚠️ Error setting up redirect for <b>{chat.title}</b>: Could not create invite link.\n"
                f"Ensure I have 'Invite Users' permission and try again.",
                parse_mode='HTML'
            )
            return ConversationHandler.END

        # Store setup info in context.user_data (since this is per_user=True for Admin)
        context.user_data['setup_channel_id'] = channel_id
        context.user_data['setup_channel_title'] = chat.title
        context.user_data['setup_invite_link'] = invite_link

        await query.edit_message_text(
            f"🚀 <b>Setup Started for {chat.title}</b>\n\n"
            f"🔗 <b>Invite Link:</b> {invite_link}\n\n"
            "Please tell me the <b>Series Name</b> for this channel (e.g., 'The Rookie').",
            parse_mode='HTML'
        )
        return SERIES_NAME

async def receive_series_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    User (Admin) sends the series name. Search TMDb.
    """
    query = update.message.text
    if not query:
        await update.message.reply_text("Please enter a valid series name.")
        return SERIES_NAME

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
    User (Admin) selects a series from the buttons.
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
        await query.edit_message_text("⚠️ Session expired. Please restart setup.")
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

# Handler for the event trigger (not the conversation itself)
channel_event_handler = ChatMemberHandler(setup_channel, ChatMemberHandler.MY_CHAT_MEMBER)

# Conversation Handler for the Admin interaction
setup_conversation_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(setup_decision, pattern="^setup_")],
    states={
        SERIES_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_series_name)],
        SERIES_SELECTION: [CallbackQueryHandler(receive_series_selection)]
    },
    fallbacks=[CommandHandler('cancel', cancel)],
    per_user=True
)
