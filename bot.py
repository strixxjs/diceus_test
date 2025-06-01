import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image
import pytesseract

# 🔧 Налаштування Tesseract OCR (тільки для Windows)
pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"  # змінити шлях, якщо інший

# 📁 Папка для збереження зображень і полісів
IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)

# 📊 Стани користувача
user_documents = {}   # user_id: {passport, vehicle}
user_agreement = {}   # user_id: confirmed/rejected/waiting

# 🧠 OCR: зчитування тексту з фото
def extract_text_from_image(image_path):
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang='eng+ukr')
        return text
    except Exception as e:
        return f"❌ Помилка під час розпізнавання: {e}"

def generate_insurance_policy(user_id: int, passport_text: str, vehicle_text: str) -> str:
    policy_content = (
        "===== СТРАХОВИЙ ПОЛІС =====\n\n"
        f"👤 Дані з паспорта:\n{passport_text}\n"
        f"🚗 Дані з документа на авто:\n{vehicle_text}\n\n"
        "📅 Дата оформлення: сьогодні\n"
        "💰 Сума: 1000 ГРН\n"
        "📄 Поліс видано автоматизованою системою\n"
        "============================="
    )

    policy_path = os.path.join(IMAGE_DIR, f"{user_id}_policy.txt")
    with open(policy_path, "w", encoding="utf-8") as f:
        f.write(policy_content)
    
    return policy_path

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_documents[user_id] = {"passport": None, "vehicle": None}
    user_agreement[user_id] = None

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
            "📄 *Паспорт:*\n" + passport_text + "\n\n" +
            "🚗 *Документ на авто:*\n" + vehicle_text + "\n\n" +
            "Все правильно? Відповідай: Так / Ні"
        )
        user_agreement[user_id] = "awaiting_confirmation"
        await update.message.reply_text(response)

async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip().lower()

    if user_id not in user_agreement:
        await update.message.reply_text("Спочатку надішли документи через /start.")
        return

    status = user_agreement[user_id]

    if status == "awaiting_confirmation":
        if text == "так":
            user_agreement[user_id] = "confirmed"
            await update.message.reply_text("💵 Страховка коштує 1000 ГРН. Згодні? Відповідай: Так / Ні")
            user_agreement[user_id] = "awaiting_price"
        elif text == "ні":
            user_agreement[user_id] = "rejected"
            user_documents[user_id] = {"passport": None, "vehicle": None}
            await update.message.reply_text("Будь ласка, надішліть нові фото документів.")
        else:
            await update.message.reply_text("Будь ласка, відповідай 'Так' або 'Ні'.")

    elif status == "awaiting_price":
        if text == "так":
            await update.message.reply_text("✅ Страховка оформлена! Генерую поліс...")

            passport_text = extract_text_from_image(user_documents[user_id]["passport"])
            vehicle_text = extract_text_from_image(user_documents[user_id]["vehicle"])

            policy_path = generate_insurance_policy(user_id, passport_text, vehicle_text)

            with open(policy_path, "rb") as f:
                await update.message.reply_document(f, filename="insurance_policy.txt")

            await update.message.reply_text("📄 Готово! Ваш страховий поліс надіслано.")
            user_agreement[user_id] = "done"
        elif text == "ні":
            await update.message.reply_text("❌ Вибачте, ціна фіксована.")
        else:
            await update.message.reply_text("Будь ласка, відповідай 'Так' або 'Ні'.")
    else:
        await update.message.reply_text("Не розумію. Напиши /start щоб почати спочатку.")

if __name__ == '__main__':
    app = ApplicationBuilder().token("7751870205:AAEKIglHGkeDAF7oDZaH5Udfsk9lkCy9gy8").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply))
    app.run_polling()
