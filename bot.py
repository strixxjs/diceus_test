from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привіт! Я бот, який допоможе тобі з оформленням автостраховки 🚗📄.\n"
        "Будь ласка, надішли мені фото свого паспорта та документа на авто, і я все зроблю!"
    )

if __name__ == '__main__':
    app = ApplicationBuilder().token("7751870205:AAEKIglHGkeDAF7oDZaH5Udfsk9lkCy9gy8").build()
    app.add_handler(CommandHandler("start", start))
    app.run_polling()
