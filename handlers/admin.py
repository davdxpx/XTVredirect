from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler, CallbackQueryHandler, MessageHandler, filters
from config import Config
from database import db
from utils.logger import setup_logger

logger = setup_logger(__name__)

# States for regenerate conversation
REGENERATE_CODE = 0

async def admin_dashboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Shows the admin dashboard.
    """
    user_id = update.effective_user.id
    if user_id != Config.CEO_ID:
        # Silently ignore or say nothing if not admin.
        return

    # Fetch stats overview
    total_links = await db.redirects.count_documents({})

    # Calculate total usage
    pipeline = [{"$group": {"_id": None, "total_usage": {"$sum": "$used_count"}}}]
    result = await db.redirects.aggregate(pipeline).to_list(length=1)
    total_usage = result[0]['total_usage'] if result else 0

    text = (
        f"<b>🤖 XTV Redirect Bot - Admin Dashboard</b>\n\n"
        f"🔗 <b>Total Redirect Links:</b> {total_links}\n"
        f"📊 <b>Total Redirects Served:</b> {total_usage}\n\n"
        "Select an action:"
    )

    keyboard = [
        [InlineKeyboardButton("📜 List Latest Links", callback_data="admin_list")],
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_stats")],
        [InlineKeyboardButton("♻️ Regenerate Invite Link", callback_data="admin_regenerate")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=reply_markup, parse_mode='HTML')
    else:
        await update.message.reply_text(text, reply_markup=reply_markup, parse_mode='HTML')

async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles admin callback queries (Dashboard navigation).
    """
    query = update.callback_query
    data = query.data
    user_id = update.effective_user.id

    if user_id != Config.CEO_ID:
        await query.answer("Unauthorized", show_alert=True)
        return

    if data == "admin_stats":
        await admin_dashboard(update, context)

    elif data == "admin_list":
        # Show last 10 links
        links = await db.redirects.find().sort("created_at", -1).limit(10).to_list(length=10)

        text = "<b>📜 Latest 10 Redirect Links:</b>\n\n"
        for link in links:
            series = link.get('series_name', 'Unknown')
            code = link.get('code', 'N/A')
            uses = link.get('used_count', 0)
            text += f"• <b>{series}</b>\n   <code>{code}</code> (Uses: {uses})\n\n"

        keyboard = [[InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_stats")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def start_regenerate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Starts the regenerate link conversation.
    """
    query = update.callback_query
    user_id = update.effective_user.id

    if user_id != Config.CEO_ID:
        await query.answer("Unauthorized", show_alert=True)
        return ConversationHandler.END

    await query.answer()
    await query.edit_message_text(
        "♻️ <b>Regenerate Invite Link</b>\n\n"
        "Please send me the <b>Redirect Code</b> of the link you want to regenerate.",
        parse_mode='HTML',
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="cancel_regenerate")]])
    )
    return REGENERATE_CODE

async def receive_regenerate_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Receives the code and regenerates the link.
    """
    code = update.message.text.strip()

    # Check if code exists
    entry = await db.get_redirect(code)
    if not entry:
        await update.message.reply_text("❌ <b>Invalid Code.</b> Please try again or /cancel.", parse_mode='HTML')
        return REGENERATE_CODE

    channel_id = entry.get('private_channel_id')
    series_name = entry.get('series_name', 'Unknown')

    if not channel_id:
        await update.message.reply_text("❌ <b>Error:</b> No channel ID found for this link.", parse_mode='HTML')
        return ConversationHandler.END

    try:
        invite_link_obj = await context.bot.create_chat_invite_link(
            chat_id=channel_id,
            name=f"Regen Link: {series_name}"
            # member_limit omitted
        )
        new_invite_link = invite_link_obj.invite_link

        # Update DB
        await db.redirects.update_one(
            {"code": code},
            {"$set": {"invite_link": new_invite_link}}
        )

        await update.message.reply_text(
            f"✅ <b>Invite Link Regenerated!</b>\n\n"
            f"📺 <b>Series:</b> {series_name}\n"
            f"🔗 <b>New Invite Link:</b> {new_invite_link}\n\n"
            f"The redirect link (<code>{code}</code>) will now point to this new invite link.",
            parse_mode='HTML'
        )
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Failed to regenerate link for {channel_id}: {e}")
        await update.message.reply_text(f"❌ <b>Error:</b> Could not create invite link.\n{e}", parse_mode='HTML')
        return ConversationHandler.END

async def cancel_regenerate(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Cancels the regenerate conversation."""
    query = update.callback_query
    if query:
        await query.answer()
        await query.edit_message_text("❌ Regeneration cancelled.")
    else:
        await update.message.reply_text("❌ Regeneration cancelled.")
    return ConversationHandler.END

regenerate_conversation_handler = ConversationHandler(
    entry_points=[CallbackQueryHandler(start_regenerate, pattern="^admin_regenerate$")],
    states={
        REGENERATE_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_regenerate_code)]
    },
    fallbacks=[
        CallbackQueryHandler(cancel_regenerate, pattern="^cancel_regenerate$"),
        MessageHandler(filters.COMMAND, cancel_regenerate)
    ],
    per_user=True
)
