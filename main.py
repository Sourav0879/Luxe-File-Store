from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient
import asyncio
import os
import random
import string
from flask import Flask

# ENV variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
STORE_CHANNEL = os.getenv("STORE_CHANNEL")
MONGO_URI = os.getenv("MONGO_URI")
CUSTOM_LINK = os.getenv("CUSTOM_LINK")

# Pyrogram Bot & MongoDB Setup
bot = Client("filestore", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URI)
db = mongo["FileStore"]
files_col = db["files"]

# Flask app for port 8080 healthcheck
app = Flask(__name__)
@app.route('/')
def home():
    return "✅ Telegram File Store Bot is running on Koyeb!"

# Random ID Generator
def generate_unique_id(length=24):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choices(chars, k=length))

# Start handler with /start or /start <ID>
@bot.on_message(filters.command("start") & filters.private)
async def start(_, message):
    if len(message.command) == 1:
        await message.reply_text("👋 Welcome! Send me any file to get a custom sharable link.")
    else:
        unique_id = message.command[1]
        data = files_col.find_one({"unique_id": unique_id})
        if data:
            try:
                await bot.copy_message(chat_id=message.chat.id, from_chat_id=STORE_CHANNEL, message_id=data["file_id"])
            except:
                await message.reply_text("❌ File not found.")
        else:
            await message.reply_text("❌ Invalid or expired ID.")

# Single file handler
@bot.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo))
async def store_file(_, message: Message):
    file_id = message.message_id
    await message.forward(STORE_CHANNEL)

    file_name = (
        message.document.file_name
        if message.document
        else message.video.file_name
        if message.video
        else "Unnamed File"
    )

    unique_id = generate_unique_id()

    files_col.insert_one({
        "file_id": file_id,
        "user_id": message.from_user.id,
        "file_name": file_name,
        "unique_id": unique_id
    })

    link = f"{CUSTOM_LINK}{unique_id}"
    await message.reply_text(f"✅ File Stored!\n🔗 Link: `{link}`", quote=True)

# Batch media group support
@bot.on_message(filters.private & filters.media_group)
async def batch_upload(_, message: Message):
    group_id = message.media_group_id
    if not hasattr(bot, "batch_cache"):
        bot.batch_cache = {}
    bot.batch_cache.setdefault(group_id, [])
    bot.batch_cache[group_id].append(message)
    await asyncio.sleep(2)

    if len(bot.batch_cache[group_id]) > 1:
        links = []
        for msg in bot.batch_cache[group_id]:
            file_id = msg.message_id
            await msg.forward(STORE_CHANNEL)
            unique_id = generate_unique_id()
            files_col.insert_one({
                "file_id": file_id,
                "user_id": msg.from_user.id,
                "unique_id": unique_id
            })
            link = f"{CUSTOM_LINK}{unique_id}"
            links.append(link)
        await message.reply_text("📦 Batch Files Stored:\n\n" + "\n".join(links))
        del bot.batch_cache[group_id]

# Run Flask + Bot
if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()
    bot.run()
