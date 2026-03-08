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
        [InlineKeyboardButton("🛠 Manage Redirect Links", callback_data="admin_manage_page_1")],
        [InlineKeyboardButton("🔄 Refresh Stats", callback_data="admin_stats")]
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

    elif data.startswith("admin_manage_page_"):
        page_num = int(data.split("_")[-1])
        await render_manage_links_page(query, page_num)

    elif data.startswith("admin_manage_link_"):
        code = data.replace("admin_manage_link_", "")
        await render_link_details(query, code)

    elif data == "ignore":
        await query.answer()

    elif data.startswith("admin_regen_"):
        code = data.replace("admin_regen_", "")
        await regenerate_invite_link_direct(update, context, code)

    elif data.startswith("admin_delete_"):
        code = data.replace("admin_delete_", "")
        await delete_redirect_channel(update, context, code)

    elif data.startswith("admin_change_"):
        code = data.replace("admin_change_", "")
        await initiate_change_channel(update, context, code)

    elif data == "admin_cancel_change":
        await cancel_change_channel(update, context)

async def render_manage_links_page(query, page_num: int):
    """
    Renders a paginated list of redirect links.
    """
    limit = 10
    skip = (page_num - 1) * limit

    total_links = await db.redirects.count_documents({})
    total_pages = max(1, (total_links + limit - 1) // limit)

    if page_num > total_pages:
        page_num = total_pages
        skip = (page_num - 1) * limit

    links = await db.redirects.find().sort("created_at", -1).skip(skip).limit(limit).to_list(length=limit)

    text = f"<b>🛠 Manage Redirect Links (Page {page_num}/{total_pages})</b>\n\nSelect a redirect to manage it:"
    keyboard = []

    for link in links:
        series = link.get('series_name', 'Unknown')
        code = link.get('code', 'N/A')
        keyboard.append([InlineKeyboardButton(f"{series} ({code})", callback_data=f"admin_manage_link_{code}")])

    # Pagination row
    nav_row = []
    if page_num > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"admin_manage_page_{page_num - 1}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="ignore"))

    nav_row.append(InlineKeyboardButton(f"Page {page_num}/{total_pages}", callback_data="ignore"))

    if page_num < total_pages:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"admin_manage_page_{page_num + 1}"))
    else:
        nav_row.append(InlineKeyboardButton(" ", callback_data="ignore"))

    keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("🔙 Back to Dashboard", callback_data="admin_stats")])

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

async def render_link_details(query, code: str):
    """
    Renders the details and management options for a specific redirect.
    """
    entry = await db.get_redirect(code)
    if not entry:
        await query.answer("Link not found in database.", show_alert=True)
        return

    series_name = entry.get('series_name', 'Unknown')
    tmdb_id = entry.get('tmdb_id', 'N/A')
    invite_link = entry.get('invite_link', 'None')
    used_count = entry.get('used_count', 0)
    created_at = entry.get('created_at')
    last_used = entry.get('last_used')

    created_str = created_at.strftime('%Y-%m-%d %H:%M') if created_at else 'N/A'
    last_used_str = last_used.strftime('%Y-%m-%d %H:%M') if last_used else 'Never'

    text = (
        f"<b>📋 Redirect Link Details</b>\n\n"
        f"📺 <b>Series Name:</b> {series_name}\n"
        f"🎬 <b>TMDb ID:</b> {tmdb_id}\n"
        f"🔑 <b>Redirect Code:</b> <code>{code}</code>\n"
        f"🔗 <b>Current Invite Link:</b> {invite_link}\n\n"
        f"📅 <b>Created At:</b> {created_str}\n"
        f"⏱ <b>Last Used:</b> {last_used_str}\n"
        f"📊 <b>Total Uses:</b> {used_count}"
    )

    keyboard = [
        [InlineKeyboardButton("♻️ Regenerate Invite Link", callback_data=f"admin_regen_{code}")],
        [InlineKeyboardButton("🔄 Change Channel", callback_data=f"admin_change_{code}")],
        [InlineKeyboardButton("🗑 Delete Redirect Channel", callback_data=f"admin_delete_{code}")],
        [InlineKeyboardButton("🔙 Back to List", callback_data="admin_manage_page_1")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def regenerate_invite_link_direct(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    """
    Directly regenerates the invite link for a given code.
    """
    query = update.callback_query

    entry = await db.get_redirect(code)
    if not entry:
        await query.answer("Invalid Code. Link not found in database.", show_alert=True)
        return

    channel_id = entry.get('private_channel_id')
    series_name = entry.get('series_name', 'Unknown')

    if not channel_id:
        await query.answer("Error: No channel ID found for this link.", show_alert=True)
        return

    try:
        invite_link_obj = await context.bot.create_chat_invite_link(
            chat_id=channel_id,
            name=f"Regen Link: {series_name}"
        )
        new_invite_link = invite_link_obj.invite_link

        # Update DB
        await db.redirects.update_one(
            {"code": code},
            {"$set": {"invite_link": new_invite_link}}
        )

        await query.answer("Invite Link Regenerated Successfully!", show_alert=True)
        # Re-render the detailed view to show updated link
        await render_link_details(query, code)

    except Exception as e:
        logger.error(f"Failed to regenerate link for {channel_id}: {e}")
        await query.answer(f"Error: Could not create invite link. Am I still admin?", show_alert=True)


async def delete_redirect_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    """
    Deletes the redirect from the database and optionally leaves the channel.
    """
    query = update.callback_query

    entry = await db.get_redirect(code)
    if not entry:
        await query.answer("Link not found in database.", show_alert=True)
        return

    channel_id = entry.get('private_channel_id')
    series_name = entry.get('series_name', 'Unknown')

    # Try to leave channel
    left_channel = False
    if channel_id:
        try:
            await context.bot.leave_chat(channel_id)
            left_channel = True
        except Exception as e:
            logger.warning(f"Could not leave channel {channel_id} while deleting redirect: {e}")

    # Delete from DB
    await db.redirects.delete_one({"code": code})

    text = f"🗑 <b>Redirect Deleted</b>\n\nSeries: {series_name}\nCode: <code>{code}</code>\n"
    if left_channel:
        text += "✅ Successfully left the channel."
    else:
        text += "⚠️ Note: Could not leave the channel automatically. You may need to remove the bot manually."

    keyboard = [[InlineKeyboardButton("🔙 Back to List", callback_data="admin_manage_page_1")]]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def initiate_change_channel(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    """
    Initiates the flow to change the channel for a specific redirect code.
    """
    query = update.callback_query

    entry = await db.get_redirect(code)
    if not entry:
        await query.answer("Link not found in database.", show_alert=True)
        return

    series_name = entry.get('series_name', 'Unknown')

    # Set the waiting state in context
    context.user_data['waiting_change_channel_code'] = code

    text = (
        f"🔄 <b>Change Channel for:</b> {series_name}\n"
        f"Code: <code>{code}</code>\n\n"
        f"<b>Instructions:</b>\n"
        f"1. Create or go to the <b>new</b> channel.\n"
        f"2. Add me as an Administrator to that channel.\n"
        f"3. I will detect it and automatically prompt you here to confirm the change.\n\n"
        f"<i>Waiting for channel addition...</i>"
    )

    keyboard = [[InlineKeyboardButton("❌ Cancel", callback_data="admin_cancel_change")]]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')


async def cancel_change_channel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Cancels the change channel flow.
    """
    query = update.callback_query

    if 'waiting_change_channel_code' in context.user_data:
        code = context.user_data.pop('waiting_change_channel_code')
        await query.answer("Change channel flow cancelled.")
        await render_link_details(query, code)
    else:
        await query.answer("No active change channel flow.")
        await render_manage_links_page(query, 1)


