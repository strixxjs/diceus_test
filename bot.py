import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)

user_documents = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_documents[user_id] = {"passport": None, "vehicle": None}

    await update.message.reply_text(
        "Привіт! Щоб оформити автостраховку, надішли мені два фото:\n"
        "1. 📄 Паспорт\n"
        "2. 🚗 Тех паспорт на авто"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    photos = update.message.photo

    if not photos:
        await update.message.reply_text("Будь ласка, надішли фото документа.")
        return


    photo_file = await photos[-1].get_file()
    file_path = os.path.join(IMAGE_DIR, f"{user_id}_{len(os.listdir(IMAGE_DIR))}.jpg")
    await photo_file.download_to_drive(file_path)

    if user_documents.get(user_id) is None:
        user_documents[user_id] = {"passport": None, "vehicle": None}

    if user_documents[user_id]["passport"] is None:
        user_documents[user_id]["passport"] = file_path
        await update.message.reply_text("✅ Фото паспорта збережено. Надішли тепер документ на авто.")
    elif user_documents[user_id]["vehicle"] is None:
        user_documents[user_id]["vehicle"] = file_path
        await update.message.reply_text("✅ Фото авто-документа збережено. Дякую!")
        await update.message.reply_text("🔍 Тепер я зчитую інформацію з документів...")
    else:
        await update.message.reply_text("У мене вже є два фото. Якщо хочеш надіслати нові — напиши /start заново.")


if __name__ == '__main__':
    app = ApplicationBuilder().token("7751870205:AAEKIglHGkeDAF7oDZaH5Udfsk9lkCy9gy8").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.run_polling()

