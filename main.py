import asyncio
import logging
import imagehash

from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ChatType, ContentType
from aiogram.filters import CommandStart
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.token import TokenValidationError
from PIL import Image
import os

logging.basicConfig(level=logging.DEBUG, filename="py_log.log", filemode="w")

API_TOKEN = ''
ADMIN_ID = None
CHANNEL_ID = None

photo_storage = {}
hash_storage = {}

try:
    bot = Bot(token=API_TOKEN)
except TokenValidationError:
    logging.error("Неверный токен бота!")
    raise SystemExit("Неверный токен бота!")

dp = Dispatcher()


@dp.message(F.content_type == ContentType.PHOTO, F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def catch_photo(message: Message, bot: Bot):
    try:
        import uuid

        photo = message.photo[-1]
        photo_key = str(uuid.uuid4())[:8]

        file_info = await bot.get_file(photo.file_id)
        file_path = file_info.file_path
        downloaded_file = await bot.download_file(file_path)

        temp_filename = f"temp_{photo_key}.jpg"
        with open(temp_filename, 'wb') as f:
            f.write(downloaded_file.read())

        with Image.open(temp_filename) as img:
            img_hash = str(imagehash.average_hash(img))

        for h_key, h_val in hash_storage.items():
            if imagehash.hex_to_hash(h_val) - imagehash.hex_to_hash(img_hash) <= 5:
                markup = InlineKeyboardMarkup(inline_keyboard=[
                         [InlineKeyboardButton(text="✅ Всё равно одобрить", callback_data=f"approve_{photo_key}")],
                         [InlineKeyboardButton(text="❌ Удалить как дубликат", callback_data=f"reject_{photo_key}")]
                       ])
                
                photo_msg = await bot.send_photo(
                 chat_id=ADMIN_ID,
                 photo=photo.file_id,
                 caption=f"⚠️ Возможный дубликат от @{message.from_user.username or message.from_user.full_name}"
                )

                btns_msg = await bot.send_message(
                 chat_id=ADMIN_ID,
                 text="Действие с фото-дубликатом:",
                 reply_markup=markup
                )

                photo_storage[photo_key] = {
                 'file_id': photo.file_id,
                 'chat_id': message.chat.id,
                 'message_id': message.message_id,
                 'admin_photo_msg_id': photo_msg.message_id,
                 'admin_btns_msg_id': btns_msg.message_id
                }

                hash_storage[photo_key] = img_hash
                os.remove(temp_filename)
            
        photo_msg = await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo.file_id,
            caption=f"От: @{message.from_user.username or message.from_user.full_name}"
        )

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Одобрить", callback_data=f"approve_{photo_key}")],
            [InlineKeyboardButton(text="❌ Удалить", callback_data=f"reject_{photo_key}")]
        ])

        btns_msg = await bot.send_message(
            chat_id=ADMIN_ID,
            text="Действие с фото:",
            reply_markup=markup
        )

        photo_storage[photo_key] = {
            'file_id': photo.file_id,
            'chat_id': message.chat.id,
            'message_id': message.message_id,
            'admin_photo_msg_id': photo_msg.message_id,
            'admin_btns_msg_id': btns_msg.message_id
        }

        hash_storage[photo_key] = img_hash

        os.remove(temp_filename)

    except Exception as e:
        logging.error(f"Ошибка в catch_photo: {e}")

@dp.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def process_moderation(callback: CallbackQuery, bot: Bot):
    try:
        action, photo_key = callback.data.split('_', 1)
        photo_data = photo_storage.get(photo_key)
        
        if not photo_data:
            return await callback.answer("Фото не найдено!")
            
        if action == "reject":
           
           await bot.delete_message(
           chat_id=callback.from_user.id,
           message_id=photo_data['admin_photo_msg_id']
           )

           await bot.delete_message(
          chat_id=callback.from_user.id,
          message_id=photo_data['admin_btns_msg_id']
          )
           
           await callback.answer("Фото удалено из ЛС! 🗑️")
        
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
