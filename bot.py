import os
import re
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image
import pytesseract
from rapidfuzz import fuzz, process
import openai

load_dotenv()

TOKEN = os.getenv("TELEGRAM_TOKEN")
openai.api_key = os.getenv("OPENAI_API_KEY")

IMAGE_DIR = "images"
os.makedirs(IMAGE_DIR, exist_ok=True)

user_documents = {}
user_agreement = {}
user_openaichat = {}

known_brands = ["Toyota", "Ford", "Honda", "BMW", "Mercedes", "Nissan", "Audi", "Kia", "Hyundai", "Chevrolet", "Volkswagen", "Mazda", "Subaru", "Tesla", "Jeep"]
known_states = ["California", "Massachusetts", "New York", "Florida", "Texas", "Illinois", "Ohio", "Pennsylvania", "Georgia", "Nevada", "Arizona", "Colorado"]

def extract_text_from_image(image_path, lang='eng+ukr'):
    try:
        img = Image.open(image_path)
        text = pytesseract.image_to_string(img, lang=lang)
        return text
    except Exception as e:
        return f"❌ Помилка під час розпізнавання: {e}"

def clean_text(text):
    lines = text.splitlines()
    cleaned = [re.sub(r'[^А-Яа-яA-Za-z0-9 .,/-]', '', line.strip()) for line in lines if line.strip()]
    return '\n'.join(cleaned)

def normalize_text_line(line):
    words = line.split()
    normalized = []
    for word in words:
        brand_match = process.extractOne(word, known_brands, scorer=fuzz.ratio)
        state_match = process.extractOne(word, known_states, scorer=fuzz.ratio)
        if brand_match and brand_match[1] >= 80:
            normalized.append(brand_match[0])
        elif state_match and state_match[1] >= 80:
            normalized.append(state_match[0])
        else:
            normalized.append(word)
    return ' '.join(normalized)

def generate_insurance_policy(user_id: int, passport_text: str, vehicle_text: str) -> str:
    passport_text = clean_text(passport_text)
    vehicle_text_lines = clean_text(vehicle_text).splitlines()
    vehicle_text = '\n'.join([normalize_text_line(line) for line in vehicle_text_lines])
    policy_content = (
        "========== СТРАХОВИЙ ПОЛІС ==========\n\n"
        "👤 ПАСПОРТНІ ДАНІ:\n"
        f"{passport_text}\n\n"
        "🚗 ДАНІ АВТОМОБІЛЯ:\n"
        f"{vehicle_text}\n\n"
        "📅 Дата оформлення: сьогодні\n"
        "💰 Сума: 100 USD\n"
        "📄 Поліс видано автоматизованою системою\n\n"
        "======================================"
    )
    policy_path = os.path.join(IMAGE_DIR, f"{user_id}_policy.txt")
    with open(policy_path, "w", encoding="utf-8") as f:
        f.write(policy_content)
    return policy_path

from openai import OpenAI
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def ai_completion(prompt: str, user_id: int) -> str:
    try:
        if user_id not in user_openaichat:
            user_openaichat[user_id] = [
                {"role": "system", "content": "Ти — ввічливий Telegram-бот, який допомагає користувачам оформити автострахування. Інструкції: \n1. Попроси користувача надіслати фото паспорта та документа на авто.\n2. Після отримання фото, зчитай текст з документів і запитай підтвердження.\n3. Якщо користувач погоджується, повідом про вартість страховки та запитай згоду.\n4. Якщо користувач погоджується, згенеруй страховий поліс і надішли його. Проси лише фото документів! І не пиши щоб люди надавали тобі данні з документів в текстовому вигляді."}
            ]
        user_openaichat[user_id].append({"role": "user", "content": prompt})
        response = client.chat.completions.create(
            model="gpt-4.1-nano",
            messages=user_openaichat[user_id],
            temperature=0.7,
            max_tokens=300,
        )
        reply = response.choices[0].message.content.strip()
        user_openaichat[user_id].append({"role": "assistant", "content": reply})
        return reply
    except Exception as e:
        return "⚠️ Виникла помилка з AI. Спробуй пізніше."

async def extract_structured_data_from_ocr(passport_text_raw: str, vehicle_text_raw: str, user_id: int) -> str:
    prompt = f"""
Ось текст з двох документів. Текст має помилки, це результат OCR з фото.
Проаналізуй і виправ помилки. Створи структуровану відповідь, яка містить такі поля:

👤 ПАСПОРТНІ ДАНІ:
- ПІБ
- Серія і номер паспорта (якщо є)
- Дата народження або інші ідентифікаційні дані (якщо є)

🚗 ДАНІ АВТО:
- Марка та модель авто
- Рік випуску
- VIN або держномер (якщо є)
- Штат реєстрації (наприклад, Massachusetts)

Поверни лише зрозумілий звіт для користувача. Не додавай пояснень.  
Ось дані:

=== ПАСПОРТ ===
{passport_text_raw}

=== АВТО ===
{vehicle_text_raw}
"""
    return await ai_completion(prompt, user_id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_documents[user_id] = {"passport": None, "vehicle": None}
    user_agreement[user_id] = None
    await update.message.reply_text("Привіт! Щоб оформити автостраховку, надішли мені два фото:\n1. 📄 Паспорт\n2. 🚗 Документ на авто")

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
        raw_passport = extract_text_from_image(user_documents[user_id]["passport"], lang='ukr')
        raw_vehicle = extract_text_from_image(user_documents[user_id]["vehicle"], lang='eng')
        user_documents[user_id]["passport_raw"] = raw_passport
        user_documents[user_id]["vehicle_raw"] = raw_vehicle
        structured_info = await extract_structured_data_from_ocr(raw_passport, raw_vehicle, user_id)
        user_agreement[user_id] = "awaiting_confirmation"
        await update.message.reply_text("🔍 Ось що я зміг зчитати з ваших документів:\n\n" + structured_info + "\n\nВсе правильно? Відповідай: Так / Ні")

async def handle_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text.strip().lower()
    if user_id not in user_agreement:
        await update.message.reply_text("Спочатку надішли документи через /start.")
        return
    status = user_agreement[user_id]
    if status == "awaiting_confirmation":
        if text == "так":
            user_agreement[user_id] = "awaiting_price"
            await update.message.reply_text("💵 Страховка коштує 100 usd. Згодні? Відповідай: Так / Ні")
        elif text == "ні":
            user_agreement[user_id] = "rejected"
            user_documents[user_id] = {"passport": None, "vehicle": None}
            await update.message.reply_text("Будь ласка, надішліть нові фото документів.")
        else:
            reply = await ai_completion(text, user_id)
            await update.message.reply_text(reply)
    elif status == "awaiting_price":
        if text == "так":
            await update.message.reply_text("✅ Страховка оформлена! Генерую поліс...")
            passport_text = user_documents[user_id].get("passport_raw", "")
            vehicle_text = user_documents[user_id].get("vehicle_raw", "")
            policy_path = generate_insurance_policy(user_id, passport_text, vehicle_text)
            with open(policy_path, "rb") as f:
                await update.message.reply_document(f, filename="insurance_policy.txt")
            await update.message.reply_text("📄 Готово! Ваш страховий поліс надіслано.")
            user_agreement[user_id] = "done"
        elif text == "ні":
            await update.message.reply_text("❌ Вибачте, ціна фіксована.")
        else:
            reply = await ai_completion(text, user_id)
            await update.message.reply_text(reply)
    else:
        reply = await ai_completion(text, user_id)
        await update.message.reply_text(reply)

async def handle_invalid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Я приймаю лише фото паспорта та авто-документа. Надішліть, будь ласка, зображення.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply))
    app.add_handler(MessageHandler(~filters.PHOTO & ~filters.TEXT & ~filters.COMMAND, handle_invalid))
    app.run_polling()
