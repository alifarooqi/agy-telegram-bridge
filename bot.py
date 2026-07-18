import logging
import sys
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from config import TELEGRAM_BOT_TOKEN, ALLOWED_TELEGRAM_USER_IDS
from session_manager import SessionManager

# Setup Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

# Initialize global session manager
session_manager = SessionManager()

def is_authorized(user_id: int) -> bool:
    """Checks if the Telegram user ID is authorized.
    
    If ALLOWED_TELEGRAM_USER_IDS is empty, it acts as a lock and blocks all access.
    """
    return user_id in ALLOWED_TELEGRAM_USER_IDS

def split_message(text: str, max_length: int = 4096) -> list[str]:
    """Splits a message into chunks within Telegram's max character limit."""
    if len(text) <= max_length:
        return [text]
    
    chunks = []
    while text:
        if len(text) <= max_length:
            chunks.append(text)
            break
        # Find a clean boundary (newline or space) to split
        split_idx = text.rfind("\n", 0, max_length)
        if split_idx == -1:
            split_idx = text.rfind(" ", 0, max_length)
        if split_idx == -1:
            split_idx = max_length
            
        chunks.append(text[:split_idx])
        text = text[split_idx:].lstrip()
    return chunks

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a friendly greeting when the command /start is issued."""
    user = update.effective_user
    if not user:
        return
        
    if not is_authorized(user.id):
        logger.warning(f"Unauthorized user {user.id} ({user.username}) tried to access start command.")
        await update.message.reply_text("Unauthorized. You do not have access to this Antigravity Agent.")
        return
        
    await update.message.reply_text(
        f"Hello {user.first_name}! I am your Antigravity Agent bridge.\n\n"
        "Send me any prompt to start interacting with the agent on your Mac.\n"
        "Use /reset to clear the session history and start fresh."
    )

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Resets the Antigravity conversation session for the current chat."""
    user = update.effective_user
    if not user:
        return
        
    if not is_authorized(user.id):
        await update.message.reply_text("Unauthorized.")
        return
        
    chat_id = update.effective_chat.id
    closed = await session_manager.close_session(chat_id)
    if closed:
        await update.message.reply_text("Session reset! History cleared and a new session has been initialized.")
    else:
        await update.message.reply_text("No active session found to reset. Send a message to start one.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Intercepts incoming text, forwards to Antigravity, and sends the response back."""
    user = update.effective_user
    if not user or not update.message or not update.message.text:
        return
        
    if not is_authorized(user.id):
        logger.warning(f"Unauthorized user {user.id} ({user.username}) sent a message.")
        await update.message.reply_text("Unauthorized.")
        return
        
    chat_id = update.effective_chat.id
    text = update.message.text
    
    # Indicate typing to the user
    await context.bot.send_chat_action(chat_id=chat_id, action="typing")
    
    try:
        # Get or create conversation session
        conversation = await session_manager.get_conversation(chat_id)
        
        # Forward prompt to Antigravity
        logger.info(f"Sending prompt from chat_id {chat_id} to Antigravity")
        try:
            response = await conversation.chat(text)
        except Exception as chat_err:
            err_msg = str(chat_err)
            # If it's a websocket or connection closure exception, attempt to reconnect
            if "ConnectionClosed" in err_msg or "connection" in err_msg.lower() or "websocket" in err_msg.lower():
                logger.warning(f"Connection error during chat: {chat_err}. Re-establishing session...")
                await session_manager.close_session(chat_id, clear_persistence=False)
                conversation = await session_manager.get_conversation(chat_id)
                logger.info(f"Retrying prompt from chat_id {chat_id} with new session")
                response = await conversation.chat(text)
            else:
                raise
        
        # Drain the stream and retrieve text
        response_text = await response.text()
        
        # Record conversation id if this was the first turn or if it changed
        session_manager.record_conversation_id(chat_id)
        
        # Send replies (splitting into multiple messages if needed)
        for chunk in split_message(response_text):
            await update.message.reply_text(chunk)
            
    except Exception as e:
        logger.exception(f"Error handling message from chat_id {chat_id}: {e}")
        await update.message.reply_text(f"An error occurred: {str(e)}")

async def project(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Gets or sets the project directory/workspace for the Antigravity Agent."""
    user = update.effective_user
    if not user:
        return
        
    if not is_authorized(user.id):
        await update.message.reply_text("Unauthorized.")
        return
        
    chat_id = update.effective_chat.id
    chat_key = str(chat_id)
    
    # If no arguments, return current project directory
    if not context.args:
        session_data = session_manager.saved_sessions.get(chat_key, {})
        current_project = session_data.get("project_dir")
        if current_project:
            await update.message.reply_text(f"Current project directory: `{current_project}`")
        else:
            import os
            default_project = os.getcwd()
            await update.message.reply_text(f"No specific project configured. Using default directory: `{default_project}`")
        return
        
    # Otherwise, try to update it
    new_project = " ".join(context.args).strip()
    
    import os
    if not os.path.isabs(new_project):
        await update.message.reply_text("Error: Project path must be an absolute path (e.g. `/Users/username/project`).")
        return
        
    if not os.path.isdir(new_project):
        await update.message.reply_text(f"Error: Directory `{new_project}` does not exist on your Mac.")
        return
        
    try:
        await session_manager.set_project_dir(chat_id, new_project)
        await update.message.reply_text(f"Project directory successfully updated to: `{new_project}`\nSession has been reset to apply changes.")
    except Exception as e:
        logger.exception(f"Error setting project directory for chat_id {chat_id}: {e}")
        await update.message.reply_text(f"Failed to set project directory: {str(e)}")

async def post_shutdown(application: Application) -> None:
    """Hook to clean up active agent sessions on shutdown."""
    await session_manager.close_all()

def main() -> None:
    """Starts the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN is missing in environment variables. Exiting.")
        sys.exit(1)
        
    # Build the application
    application = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .post_shutdown(post_shutdown)
        .build()
    )
    
    # Register handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("reset", reset))
    application.add_handler(CommandHandler("project", project))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    # Run the bot
    logger.info("Starting Telegram Bot...")
    application.run_polling()

if __name__ == "__main__":
    main()
