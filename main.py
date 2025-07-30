from pyrogram import Client, filters
from pyrogram.types import Message
from pymongo import MongoClient
import asyncio
import os
import random
import string
from flask import Flask
from threading import Thread

# ENV variables
API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))
STORE_CHANNEL = os.getenv("STORE_CHANNEL")
MONGO_URI = os.getenv("MONGO_URI")
CUSTOM_LINK = os.getenv("CUSTOM_LINK")

bot = Client("FileStoreBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
mongo = MongoClient(MONGO_URI)
db = mongo["FileStore"]
files_col = db["files"]
admin_col = db["admins"]

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Bot is alive!"

def generate_unique_id(length=24):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

def is_admin(user_id):
    return user_id == OWNER_ID or admin_col.find_one({"_id": user_id})

@bot.on_message(filters.command("add_admin") & filters.private)
async def add_admin(_, message):
    if message.from_user.id != OWNER_ID:
        return await message.reply("🚫 Only owner can add admins.")
    if len(message.command) != 2:
        return await message.reply("Usage: /add_admin <telegram_id>")
    try:
        admin_id = int(message.command[1])
        admin_col.update_one({"_id": admin_id}, {"$set": {}}, upsert=True)
        await message.reply(f"✅ Admin added: `{admin_id}`")
    except:
        await message.reply("❌ Invalid Telegram ID.")

@bot.on_message(filters.command("delete") & filters.private)
async def delete_file(_, message):
    if not is_admin(message.from_user.id):
        return await message.reply("🚫 Only owner/admin can delete files.")
    if len(message.command) != 2:
        return await message.reply("Usage: /delete <unique_id>")
    file_id = message.command[1]
    result = files_col.delete_one({"unique_id": file_id})
    if result.deleted_count:
        await message.reply("✅ File removed from database.")
    else:
        await message.reply("❌ File not found.")

@bot.on_message(filters.command("start") & filters.private)
async def get_file(_, message):
    if len(message.command) == 1:
        return await message.reply("👋 Send a file to get a shareable link.")
    
    unique_id = message.command[1]
    file_data = files_col.find_one({"unique_id": unique_id})
    if not file_data:
        return await message.reply("❌ File not found or deleted.")

    try:
        sent = await bot.copy_message(
            chat_id=message.chat.id,
            from_chat_id=STORE_CHANNEL,
            message_id=file_data["forwarded_message_id"]
        )
        await message.reply("⏳ This message will auto-delete in 10 minutes.")
        asyncio.create_task(delete_after(message.chat.id, sent.id, 600))
    except Exception as e:
        await message.reply("⚠️ Unable to forward file.")

async def delete_after(chat_id, msg_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_messages(chat_id, msg_id)
    except: pass

@bot.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo))
async def save_file(_, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply("🚫 Only admins or owner can upload files.")
    
    forwarded = await message.forward(STORE_CHANNEL)
    unique_id = generate_unique_id()
    file_name = (
        message.document.file_name if message.document else
        message.video.file_name if message.video else
        "Unnamed File"
    )

    files_col.insert_one({
        "file_id": message.id,
        "user_id": message.from_user.id,
        "file_name": file_name,
        "unique_id": unique_id,
        "forwarded_message_id": forwarded.id
    })

    link = f"{CUSTOM_LINK}{unique_id}"
    await message.reply(f"✅ File saved!\n🔗 Shareable Link:\n`{link}`")

@bot.on_message(filters.private & filters.media_group)
async def batch_handler(_, message: Message):
    if not is_admin(message.from_user.id):
        return
    group_id = message.media_group_id
    if not hasattr(bot, "batch_cache"):
        bot.batch_cache = {}
    bot.batch_cache.setdefault(group_id, []).append(message)

    await asyncio.sleep(2)
    if len(bot.batch_cache[group_id]) > 1:
        links = []
        for msg in bot.batch_cache[group_id]:
            forwarded = await msg.forward(STORE_CHANNEL)
            unique_id = generate_unique_id()
            files_col.insert_one({
                "file_id": msg.id,
                "user_id": msg.from_user.id,
                "unique_id": unique_id,
                "forwarded_message_id": forwarded.id
            })
            links.append(f"{CUSTOM_LINK}{unique_id}")
        await message.reply("📦 Batch Links:\n\n" + "\n".join(links))
        del bot.batch_cache[group_id]

if __name__ == "__main__":
    Thread(target=lambda: app.run(host="0.0.0.0", port=8080)).start()
    bot.run()
