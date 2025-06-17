import asyncio
import logging
import imagehash
import json
import uuid
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.enums import ChatType, ContentType
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.token import TokenValidationError
from PIL import Image
import os

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot_errors.log"),
        logging.StreamHandler()
    ]
)

API_TOKEN = ''
ADMIN_ID = None
CHANNEL_ID = None

HASH_STORAGE_FILE = "hash_storage.json"
SCHEDULED_POSTS_FILE = "scheduled_posts.json"
USER_PLANNING_FILE = "user_planning.json"
MODERATION_STORAGE_FILE = "moderation_storage.json"

class BotData:
    def __init__(self):
        self.hash_storage = {}
        self.scheduled_posts = []
        self.user_planning = {}
        self.photo_storage = {}
        self.load_data()

    def load_data(self):
        try:
            if os.path.exists(HASH_STORAGE_FILE):
                with open(HASH_STORAGE_FILE, "r", encoding="utf-8") as f:
                    self.hash_storage = json.load(f)
            if os.path.exists(SCHEDULED_POSTS_FILE):
                with open(SCHEDULED_POSTS_FILE, "r", encoding="utf-8") as f:
                    self.scheduled_posts = json.load(f)
            if os.path.exists(USER_PLANNING_FILE):
                with open(USER_PLANNING_FILE, "r", encoding="utf-8") as f:
                    self.user_planning = {int(k): v for k, v in json.load(f).items()}
            if os.path.exists(MODERATION_STORAGE_FILE):
                with open(MODERATION_STORAGE_FILE, "r", encoding="utf-8") as f:
                    self.photo_storage = json.load(f)
        except Exception as e:
            logging.error(f"Load error: {e}")

    def save_data(self):
        try:
            with open(HASH_STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.hash_storage, f, indent=2)
            with open(SCHEDULED_POSTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.scheduled_posts, f, indent=2)
            with open(USER_PLANNING_FILE, "w", encoding="utf-8") as f:
                json.dump(self.user_planning, f, indent=2)
            with open(MODERATION_STORAGE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.photo_storage, f, indent=2)
        except Exception as e:
            logging.error(f"Save error: {e}")

bot_data = BotData()

try:
    bot = Bot(token=API_TOKEN)
except TokenValidationError:
    raise SystemExit("Invalid bot token!")

dp = Dispatcher()

async def error_handler(update: types.Update, exception: Exception):
    logging.error(f"Unhandled exception: {exception}")
    return True

dp.errors.register(error_handler)

@dp.message(CommandStart())
async def start_command(message: Message):
    await message.answer(f"Ваш ID: {message.from_user.id}")

@dp.message(Command("plan"))
async def plan_command(message: Message):
    user_id = message.from_user.id
    plan = bot_data.user_planning.get(user_id, {'photos': [], 'times': [], 'active': True})
    
    schedule_text = ""
    if plan.get('times'):
        times_str = ", ".join(f"{t['hour']:02}:{t['minute']:02}" for t in plan['times'])
        schedule_text = f"\nТекущий график: {times_str}"
    
    bot_data.user_planning[user_id] = {
        'photos': plan['photos'],
        'times': plan['times'],
        'active': True
    }
    bot_data.save_data()
    
    await message.answer(f"Режим планирования активирован.{schedule_text}\nОтправь время публикации (например: 8 9 10:30 14) и фото. Потом нажми 'Стоп'.")

@dp.message(F.text & (F.chat.type == ChatType.PRIVATE))
async def receive_schedule(message: Message):
    user_id = message.from_user.id
    if user_id in bot_data.user_planning and bot_data.user_planning[user_id]['active']:
        times = []
        for part in message.text.split():
            try:
                if ':' in part:
                    hour, minute = map(int, part.split(':'))
                else:
                    hour, minute = int(part), 0
                if 0 <= hour < 24 and 0 <= minute < 60:
                    times.append({'hour': hour, 'minute': minute})
            except:
                continue
        
        if times:
            bot_data.user_planning[user_id]['times'] = times
            bot_data.save_data()
            time_strs = ", ".join(f"{t['hour']:02}:{t['minute']:02}" for t in times)
            await message.answer(f"График обновлен: {time_strs}")

@dp.message(F.content_type == ContentType.PHOTO, F.chat.type == ChatType.PRIVATE)
async def receive_planned_photo(message: Message):
    user_id = message.from_user.id
    if user_id in bot_data.user_planning and bot_data.user_planning[user_id]['active']:
        photo = message.photo[-1]
        
        file_info = await bot.get_file(photo.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        temp_filename = f"temp_{uuid.uuid4().hex}.jpg"
        
        with open(temp_filename, 'wb') as f:
            f.write(downloaded_file.read())

        with Image.open(temp_filename) as img:
            img_hash = str(imagehash.phash(img))

        os.remove(temp_filename)

        is_copy = any(
            imagehash.hex_to_hash(old_hash) - imagehash.hex_to_hash(img_hash) <= 5
            for old_hash in bot_data.hash_storage.values()
        )

        bot_data.user_planning[user_id]['photos'].append({
            'file_id': photo.file_id,
            'hash': img_hash
        })

        bot_data.hash_storage[str(uuid.uuid4())] = img_hash
        bot_data.save_data()

        post_time = ""
        if bot_data.user_planning[user_id]['times']:
            now = datetime.now()
            idx = len(bot_data.user_planning[user_id]['photos']) - 1
            times_count = len(bot_data.user_planning[user_id]['times'])
            day_offset = idx // times_count
            time_idx = idx % times_count
            time = bot_data.user_planning[user_id]['times'][time_idx]
            post_time = (now + timedelta(days=day_offset)).replace(
                hour=time['hour'],
                minute=time['minute'],
                second=0,
                microsecond=0
            )
            post_time = f"\nБудет опубликовано: {post_time.strftime('%d.%m.%Y в %H:%M')}"

        markup = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🛑 Стоп", callback_data=f"stop_planning_{user_id}"),
                InlineKeyboardButton(text="🗑️ Удалить", callback_data=f"delete_photo_{user_id}_{len(bot_data.user_planning[user_id]['photos'])-1}")
            ]
        ])

        caption = f"Фото добавлено в график ({'копия!' if is_copy else 'уникальное'}){post_time}"
        await message.answer_photo(photo.file_id, caption=caption, reply_markup=markup)

@dp.callback_query(F.data.startswith("stop_planning_"))
async def stop_planning_callback(callback: CallbackQuery):
    user_id = int(callback.data.split("_")[2])
    if callback.from_user.id != user_id:
        return await callback.answer("Это не ваши данные!")
    
    await process_planning(user_id)
    await callback.message.answer("✅ Планирование завершено. Все фото добавлены в график публикаций.")
    await callback.answer()

@dp.callback_query(F.data.startswith("delete_photo_"))
async def delete_photo_callback(callback: CallbackQuery):
    parts = callback.data.split("_")
    user_id = int(parts[2])
    photo_idx = int(parts[3])
    
    if callback.from_user.id != user_id:
        return await callback.answer("Это не ваши данные!")

    plan = bot_data.user_planning.get(user_id)
    if not plan or photo_idx >= len(plan['photos']):
        return await callback.answer("Фото не найдено!")

    removed_photo = plan['photos'].pop(photo_idx)
    for key, val in list(bot_data.hash_storage.items()):
        if val == removed_photo['hash']:
            del bot_data.hash_storage[key]
            break

    bot_data.save_data()
    await callback.message.delete()
    await callback.answer(f"🗑️ Фото {photo_idx + 1} удалено из графика")

@dp.message(F.text.lower() == "стоп")
async def stop_planning(message: Message):
    user_id = message.from_user.id
    plan = bot_data.user_planning.get(user_id)
    if not plan or not plan['photos'] or not plan['times']:
        return await message.answer("Нет данных для планирования.")

    now = datetime.now()
    day_offset = 0
    idx = 0
    scheduled_count = 0
    
    while idx < len(plan['photos']):
        for t in plan['times']:
            if idx >= len(plan['photos']):
                break
            dt = (now + timedelta(days=day_offset)).replace(hour=t['hour'], minute=t['minute'], second=0, microsecond=0)
            bot_data.scheduled_posts.append({
                'file_id': plan['photos'][idx]['file_id'],
                'timestamp': dt.isoformat(),
                'user_id': user_id
            })
            idx += 1
            scheduled_count += 1
        day_offset += 1

    bot_data.save_data()
    del bot_data.user_planning[user_id]
    await message.answer(f"Фото запланированы. Всего: {scheduled_count}")

@dp.message(F.content_type == ContentType.PHOTO, F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def catch_group_photo(message: Message):
    try:
        photo = message.photo[-1]
        photo_key = str(uuid.uuid4())[:8]

        file_info = await bot.get_file(photo.file_id)
        downloaded_file = await bot.download_file(file_info.file_path)
        temp_filename = f"temp_{photo_key}.jpg"
        
        with open(temp_filename, 'wb') as f:
            f.write(downloaded_file.read())

        with Image.open(temp_filename) as img:
            img_hash = str(imagehash.phash(img))

        duplicate_found = any(
            imagehash.hex_to_hash(old_hash) - imagehash.hex_to_hash(img_hash) <= 5
            for old_hash in bot_data.hash_storage.values()
        )

        photo_msg = await bot.send_photo(
            chat_id=ADMIN_ID,
            photo=photo.file_id,
            caption=f"От: @{message.from_user.username or message.from_user.full_name}\n{'⚠️ Возможный дубликат!' if duplicate_found else ''}"
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

        bot_data.photo_storage[photo_key] = {
            'file_id': photo.file_id,
            'chat_id': message.chat.id,
            'message_id': message.message_id,
            'admin_photo_msg_id': photo_msg.message_id,
            'admin_btns_msg_id': btns_msg.message_id,
            'hash': img_hash
        }

        os.remove(temp_filename)
        bot_data.save_data()

    except Exception as e:
        logging.error(f"Ошибка обработки фото из группы: {e}")
        if os.path.exists(temp_filename):
            os.remove(temp_filename)

@dp.callback_query(F.data.startswith("approve_") | F.data.startswith("reject_"))
async def process_moderation(callback: CallbackQuery):
    try:
        action, photo_key = callback.data.split('_', 1)
        photo_data = bot_data.photo_storage.get(photo_key)

        if not photo_data:
            return await callback.answer("Фото не найдено!")

        if action == "reject":
            try:
                await bot.delete_message(chat_id=ADMIN_ID, message_id=photo_data['admin_photo_msg_id'])
                await bot.delete_message(chat_id=ADMIN_ID, message_id=photo_data['admin_btns_msg_id'])
            except Exception as e:
                logging.error(f"Ошибка при удалении сообщений: {e}")

            bot_data.hash_storage[photo_key] = photo_data['hash']
            await callback.answer("Фото отклонено! 🗑️")

        elif action == "approve":
            await bot.send_photo(chat_id=CHANNEL_ID, photo=photo_data['file_id'])
            bot_data.hash_storage[photo_key] = photo_data['hash']
            await callback.answer("Фото одобрено! ✅")

        del bot_data.photo_storage[photo_key]
        bot_data.save_data()

    except Exception as e:
        logging.error(f"Ошибка модерации: {e}")
        await callback.answer("Ошибка обработки!")

async def process_planning(user_id: int):
    if user_id not in bot_data.user_planning:
        return False

    plan = bot_data.user_planning[user_id]
    if not plan['photos'] or not plan['times']:
        return False

    now = datetime.now()
    day_offset = 0
    idx = 0
    
    while idx < len(plan['photos']):
        for t in plan['times']:
            if idx >= len(plan['photos']):
                break
            dt = (now + timedelta(days=day_offset)).replace(hour=t['hour'], minute=t['minute'], second=0, microsecond=0)
            bot_data.scheduled_posts.append({
                'file_id': plan['photos'][idx]['file_id'],
                'timestamp': dt.isoformat(),
                'user_id': user_id
            })
            idx += 1
        day_offset += 1

    bot_data.save_data()
    return True

async def scheduler():
    while True:
        now = datetime.now()
        to_remove = []
        
        for i, post in enumerate(bot_data.scheduled_posts):
            post_time = datetime.fromisoformat(post['timestamp'])
            if post_time <= now:
                try:
                    await bot.send_photo(chat_id=CHANNEL_ID, photo=post['file_id'])
                    to_remove.append(i)
                except Exception as e:
                    logging.error(f"Ошибка отправки фото: {e}")

        for i in sorted(to_remove, reverse=True):
            if i < len(bot_data.scheduled_posts):
                bot_data.scheduled_posts.pop(i)
        
        if to_remove:
            bot_data.save_data()
        
        await asyncio.sleep(60)

async def main():
    asyncio.create_task(scheduler())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
