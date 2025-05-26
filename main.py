import asyncio
import logging
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ChatType, ContentType
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.token import TokenValidationError

logging.basicConfig(level=logging.DEBUG, filename="py_log.log", filemode="w")

API_TOKEN = ''
ADMIN_ID = None
CHANNEL_ID = None

photo_storage = {}

try:
    bot = Bot(token=API_TOKEN)
except TokenValidationError:
    logging.error("Неверный токен бота!")
    raise SystemExit("Неверный токен бота!")

dp = Dispatcher()

photo_storage = {}

@dp.message(F.content_type == ContentType.PHOTO, F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def catch_photo(message: Message, bot: Bot):
    try:
        import uuid
        photo_key = str(uuid.uuid4())[:8]
        
        photo_storage[photo_key] = {
            'file_id': message.photo[-1].file_id,
            'chat_id': message.chat.id,
            'message_id': message.message_id
        }

        await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo_storage[photo_key]['file_id'],
            caption=f"От: @{message.from_user.username or message.from_user.full_name}"
        )

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{photo_key}")],
            [InlineKeyboardButton(text="❌ Удалить", callback_data=f"reject_{photo_key}")]
        ])

        await bot.send_message(ADMIN_ID, "Действие с фото:", reply_markup=markup)
        
    except Exception as e:
        logging.error(f"Ошибка: {e}")

@dp.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def process_moderation(callback: CallbackQuery, bot: Bot):
    try:
        action, photo_key = callback.data.split('_', 1)
        photo_data = photo_storage.get(photo_key)
        
        if not photo_data:
            return await callback.answer("Фото не найдено!")
            
        if action == "reject":
            await bot.delete_message(
                chat_id=photo_data['chat_id'],
                message_id=photo_data['message_id']
            )
            await callback.answer("Фото удалено! 🗑️")
        elif action == "approve":
            await bot.send_photo(
                chat_id=CHANNEL_ID,
                photo=photo_data['file_id']
            )
            await callback.answer("Фото одобрено! ✅")
            
        del photo_storage[photo_key]
        
    except Exception as e:
        logging.error(f"Ошибка модерации: {e}")
        await callback.answer("Ошибка обработки!")

@dp.message(CommandStart())
async def start_command(message: Message):
    await message.answer(f"Ваш ID: {message.from_user.id}")

async def make_post(bot: Bot, short_file_id: str):
    try:
        await bot.send_photo(chat_id=CHANNEL_ID, photo=short_file_id)
        logging.info(f"Фото отправлено в канал: {short_file_id}")
    except Exception as e:
        logging.error(f"Ошибка при отправке фотографии в канал: {e}")
        await bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Ошибка при отправке фотографии в канал: {e}"

        )

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
