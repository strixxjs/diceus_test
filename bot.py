import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image
import pytesseract

IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)

user_documents = {}
user_agreement = {}

pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"

def extract_text_from_image(image_path):
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang='eng+ukr') 
        return text
    except Exception as e:
        return f"❌ Помилка під час розпізнавання: {e}"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_documents[user_id] = {"passport": None, "vehicle": None}

    await update.message.reply_text(
        "Привіт! Щоб оформити автостраховку, надішли мені два фото:\n"
        "1. 📄 Паспорт\n"
        "2. 🚗 Документ на авто"
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
        await update.message.reply_text("🔍 Зчитую інформацію з документів...")

        passport_text = extract_text_from_image(user_documents[user_id]["passport"])
        vehicle_text = extract_text_from_image(user_documents[user_id]["vehicle"])

        response = (
            "📄 **Паспорт:**\n" + passport_text + "\n\n" +
            "🚗 **Документ на авто:**\n" + vehicle_text + "\n\n" +
            "Все правильно? Відповідай: Так / Ні"
        )
        user_agreement[user_id] = None   
        await update.message.reply_text(response)

async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.lower()

    if text == "так":
        user_agreement[user_id] = "confirmed"
        await show_price(update)
    elif text == "ні":
        user_agreement[user_id] = "rejected"
        await update.message.reply_text("Надішліть нові фото документів.")
    else:
        await update.message.reply_text("Будь ласка, відповідайте 'Так' або 'Ні'.")

async def show_price(update: Update):
    user_id = update.message.from_user.id
    await update.message.reply_text("💵 Страховка коштує 1000 ГРН. Чи згодні ви? Відповідайте: Так / Ні")
    user_agreement[user_id] = "waiting_for_price_response"

async def handle_price_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.lower()

    if text == "так":
        await update.message.reply_text("✅ Страховка оформлена! Надсилаю поліс...")
    elif text == "ні":
        await update.message.reply_text("❌ Вибачте, ціна фіксована.")
    else:
        await update.message.reply_text("Будь ласка, відповідайте 'Так' або 'Ні'.")

if __name__ == '__main__':
    app = ApplicationBuilder().token("7751870205:AAEKIglHGkeDAF7oDZaH5Udfsk9lkCy9gy8").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT, handle_reply))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex('^Так$'), handle_price_response))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex('^Ні$'), handle_price_response))
    app.run_polling()
