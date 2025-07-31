from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient
import asyncio
import os
import random
import string
from flask import Flask
from threading import Thread

# ENV Variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
STORE_CHANNEL = int(os.getenv("STORE_CHANNEL"))  # e.g. -1001234567890
MONGO_URI = os.getenv("mongodb+srv://kentkouhnae1f:rCKrDhIdpLEkF0Qc@cluster0.lsxeyl3.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0")
CUSTOM_LINK = os.getenv("CUSTOM_LINK")  # e.g. https://yourblog.com/?Luxe=
OWNER_ID = int(os.getenv("OWNER_ID"))

# Pyrogram Client
bot = Client("filestore", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# MongoDB Setup
mongo = MongoClient(MONGO_URI)
db = mongo["FileStore"]
files_col = db["files"]
admin_col = db["admin_list"]

# Flask Web Server
app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Telegram File Store Bot is running!"

# Generate Unique ID for Shareable Link
def generate_unique_id(length=24):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

# Admin Check
def is_admin(user_id):
    return user_id == OWNER_ID or admin_col.find_one({"_id": user_id}) is not None

# ➕ Add Admin
@bot.on_message(filters.command("add_admin") & filters.private)
async def add_admin(_, message):
    if message.from_user.id != OWNER_ID:
        return await message.reply("🚫 Only owner can add admins.")
    if len(message.command) != 2:
        return await message.reply("❌ Usage: /add_admin <telegram_id>")
    try:
        new_admin = int(message.command[1])
        admin_col.update_one({"_id": new_admin}, {"$set": {"added_by": OWNER_ID}}, upsert=True)
        await message.reply(f"✅ Admin added: `{new_admin}`")
    except:
        await message.reply("❌ Invalid ID format.")

# ❌ Delete File Command
@bot.on_message(filters.command("delete") & filters.private)
async def delete_file(_, message):
    if not is_admin(message.from_user.id):
        return await message.reply("🚫 Only owner or admins can delete files.")
    if len(message.command) != 2:
        return await message.reply("❌ Usage: /delete <unique_id>")
    
    unique_id = message.command[1]
    file = files_col.find_one({"unique_id": unique_id})
    
    if not file:
        return await message.reply("❌ File not found.")
    
    files_col.delete_one({"unique_id": unique_id})
    await message.reply("✅ File deleted successfully.")

# /start command
@bot.on_message(filters.command("start") & filters.private)
async def start(_, message):
    if len(message.command) == 1:
        return await message.reply("👋 Send a file to get a shareable link.")
    
    unique_id = message.command[1]
    file_data = files_col.find_one({"unique_id": unique_id})
    
    if not file_data:
        return await message.reply("❌ File not found or already deleted.")
    
    try:
        sent = await bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=STORE_CHANNEL,
            message_id=file_data["forwarded_message_id"]
        )
        await message.reply("⏳ This file will auto-delete in 10 minutes.")
        asyncio.create_task(delete_after_delay(message.chat.id, sent.message_id, 600))
    except:
        await message.reply("⚠️ Unable to forward the file. It might be deleted.")

# Auto Delete Timer
async def delete_after_delay(chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id=chat_id, message_ids=message_id)
    except:
        pass

# When user sends a file
@bot.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo))
async def save_file(_, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply("🚫 Only owner or admins can upload files.")
    
    try:
        # Forward to STORE_CHANNEL anonymously
        forwarded = await bot.copy_message(
            chat_id=STORE_CHANNEL,
            from_chat_id=message.chat.id,
            message_id=message.id
        )

        file_name = (
            message.document.file_name if message.document else
            message.video.file_name if message.video else
            "Unnamed File"
        )

        unique_id = generate_unique_id()

        files_col.insert_one({
            "file_id": message.message_id,
            "user_id": message.from_user.id,
            "file_name": file_name,
            "unique_id": unique_id,
            "forwarded_message_id": forwarded.id
        })

        shareable_link = f"{CUSTOM_LINK}{unique_id}"
        await message.reply(f"✅ File stored!\n\n🔗 Shareable Link:\n{shareable_link}")
    except Exception as e:
        await message.reply(f"❌ Failed to save file.\nError: {e}")

# Start Flask + Bot
if __name__ == "__main__":
    Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()
    bot.run()
