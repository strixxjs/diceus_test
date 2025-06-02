import os
import re
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters
from PIL import Image
from passporteye import read_mrz
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

def extract_data_from_mrz(text: str) -> dict:
    lines = [line for line in text.strip().splitlines() if line.strip()]
    if len(lines) < 2:
        return {}
    result = {}
    line1 = lines[0]
    line2 = lines[1]
    if line1.startswith("P<"):
        try:
            parts = line1.split("<<")
            last_first_name = parts[0][2:], parts[1].replace("<", " ")
            result["ПІБ"] = f"{last_first_name[1]} {last_first_name[0]}".strip()
        except:
            pass
    try:
        passport_number = line2[0:9].replace("<", "")
        birth_date = line2[13:19]
        result["Серія і номер паспорта"] = passport_number
        result["Дата народження"] = f"{birth_date[:2]}.{birth_date[2:4]}.19{birth_date[4:6]}"
    except:
        pass
    return result

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
                {"role": "system", "content": "Ти — ввічливий Telegram-бот, який допомагає користувачам оформити автострахування. Інструкції: ..."}
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

def extract_mrz_data(image_path):
    try:
        mrz = read_mrz(image_path)
        if mrz is None:
            return None
        mrz_data = mrz.to_dict()
        return {
            "ПІБ": f"{mrz_data.get('names', '')} {mrz_data.get('surname', '')}",
            "Номер паспорта": mrz_data.get("number", ""),
            "Дата народження": mrz_data.get("date_of_birth", ""),
            "Стать": mrz_data.get("sex", ""),
            "Громадянство": mrz_data.get("nationality", ""),
        }
    except Exception as e:
        return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    user_documents[user_id] = {"passport": None, "vehicle": None, "passport_raw": None, "vehicle_raw": None}
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
        user_documents[user_id] = {"passport": None, "vehicle": None, "passport_raw": None, "vehicle_raw": None}

    if user_documents[user_id]["passport"] is None:
        user_documents[user_id]["passport"] = file_path
        await update.message.reply_text("✅ Фото паспорта збережено. Надішли тепер документ на авто.")
    elif user_documents[user_id]["vehicle"] is None:
        user_documents[user_id]["vehicle"] = file_path
        await update.message.reply_text("✅ Фото авто-документа збережено. Дякую!")
        await update.message.reply_text("🔍 Зчитую інформацію з документів...")

        if not user_documents[user_id]["passport_raw"]:
            mrz_data = extract_mrz_data(user_documents[user_id]["passport"])
            raw_passport = '\n'.join([f"{key}: {value}" for key, value in mrz_data.items()]) if mrz_data else extract_text_from_image(user_documents[user_id]["passport"], lang='eng+ukr')

            extra_mrz = extract_data_from_mrz(raw_passport)
            if extra_mrz:
                mrz_text = "\n".join([f"{k}: {v}" for k, v in extra_mrz.items()])
                raw_passport += f"\n\n# Додатково розпізнано з MRZ:\n{mrz_text}"

            user_documents[user_id]["passport_raw"] = raw_passport
            user_documents[user_id]["vehicle_raw"] = extract_text_from_image(user_documents[user_id]["vehicle"], lang='eng')

            structured_info = await extract_structured_data_from_ocr(user_documents[user_id]["passport_raw"], user_documents[user_id]["vehicle_raw"], user_id)
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
            user_agreement[user_id] = None
            user_documents[user_id] = {"passport": None, "vehicle": None, "passport_raw": None, "vehicle_raw": None}
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
