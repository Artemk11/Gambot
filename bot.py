import asyncio
import json
import os
import logging
from typing import Dict, Any, List
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup, 
    InputFile, ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove
)
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext

# ========== НАСТРОЙКИ ==========
# БЕРЕМ ТОКЕН ИЗ ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
BOT_TOKEN = os.getenv('BOT_TOKEN', '8446569923:AAGon_20FfR_w_8-WYtABwQI95QUe6rj34E')
ADMINS = ["Mister_Temich"]

# ПУТИ ДЛЯ SCALINGO
DATA_DIR = os.getenv('DATA_DIR', 'data')
DB_FILE = os.path.join(DATA_DIR, "games.json")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
BLOCKED_USERS_FILE = os.path.join(DATA_DIR, "blocked_users.json")

# Тексты
START_TEXT = """🎮 Добро пожаловать в GameBot!

Здесь вы можете найти и скачать различные игры для компьютера. Выбирайте игры из каталога и получайте их в пиратской или лицензионной версии.

Выберите действие в меню ниже:"""
# ===============================

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Создание необходимых директорий и файлов
def init_files():
    """Инициализация файлов и директорий"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        for file in [DB_FILE, USERS_FILE, BLOCKED_USERS_FILE]:
            if not os.path.exists(file):
                with open(file, "w", encoding="utf-8") as f:
                    json.dump({}, f, ensure_ascii=False, indent=2)
        logger.info("Files initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing files: {e}")

# States для FSM
class AdminStates(StatesGroup):
    waiting_for_game_name = State()
    waiting_for_game_description = State()
    waiting_for_game_photo = State()
    waiting_for_game_file = State()
    waiting_for_original_url = State()
    waiting_for_username_to_block = State()
    waiting_for_username_to_unblock = State()

def is_admin(username: str | None) -> bool:
    return username in ADMINS if username else False

def load_json(file: str) -> Dict[str, Any]:
    try:
        with open(file, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {file}: {e}")
        return {}

def save_json(data: Dict[str, Any], file: str):
    try:
        with open(file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Error saving {file}: {e}")

def save_user(user: types.User):
    users = load_json(USERS_FILE)
    user_id = str(user.id)
    
    if user_id not in users:
        users[user_id] = {
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "joined": datetime.now().isoformat()
        }
        save_json(users, USERS_FILE)

def is_user_blocked(user_id: int) -> bool:
    blocked_users = load_json(BLOCKED_USERS_FILE)
    return str(user_id) in blocked_users

def block_user(user_id: int):
    blocked_users = load_json(BLOCKED_USERS_FILE)
    blocked_users[str(user_id)] = datetime.now().isoformat()
    save_json(blocked_users, BLOCKED_USERS_FILE)

def unblock_user(user_id: int):
    blocked_users = load_json(BLOCKED_USERS_FILE)
    user_id_str = str(user_id)
    if user_id_str in blocked_users:
        del blocked_users[user_id_str]
        save_json(blocked_users, BLOCKED_USERS_FILE)

def get_user_id_by_username(username: str) -> int | None:
    users = load_json(USERS_FILE)
    for user_id, user_data in users.items():
        if user_data.get("username") == username:
            return int(user_id)
    return None

# ========== КЛАВИАТУРЫ ==========
def get_main_keyboard(user: types.User) -> ReplyKeyboardMarkup:
    buttons = [
        [KeyboardButton(text="🎮 Список игр"), KeyboardButton(text="💖 Донат")],
    ]
    if is_admin(user.username):
        buttons.append([KeyboardButton(text="⚙️ Админ-меню")])
    
    return ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )

def get_back_to_main_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]]
    )

def get_back_to_admin_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="🔙 Назад в админ-меню", callback_data="back_to_admin")]]
    )

# ========== ОСНОВНЫЕ КОМАНДЫ ==========
async def start_command(message: types.Message):
    save_user(message.from_user)
    
    if is_user_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы и не можете использовать бота.", reply_markup=ReplyKeyboardRemove())
        return
    
    await message.answer(
        START_TEXT,
        reply_markup=get_main_keyboard(message.from_user)
    )

async def handle_main_menu_buttons(message: types.Message):
    if is_user_blocked(message.from_user.id):
        await message.answer("❌ Вы заблокированы.", reply_markup=ReplyKeyboardRemove())
        return
    
    if message.text == "🎮 Список игр":
        await show_games_list(message)
    elif message.text == "💖 Донат":
        await show_donate(message)
    elif message.text == "⚙️ Админ-меню":
        await show_admin_menu(message)

# ========== ФУНКЦИОНАЛ ИГР ==========
async def show_games_list(message: types.Message):
    games = load_json(DB_FILE)
    
    if not games:
        await message.answer(
            "📭 Список игр пуст. Администратор должен добавить игры.",
            reply_markup=get_back_to_main_inline_keyboard()
        )
        return
    
    keyboard = []
    for game_name in games.keys():
        keyboard.append([InlineKeyboardButton(text=game_name, callback_data=f"game_{game_name}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await message.answer("🎯 Выберите игру:", reply_markup=markup)

async def handle_game_selection(callback: types.CallbackQuery):
    game_name = callback.data.split("_", 1)[1]
    games = load_json(DB_FILE)
    game = games.get(game_name)
    
    if not game:
        await callback.message.edit_text("❌ Игра не найдена.")
        return
    
    keyboard = []
    if game.get("file"):
        keyboard.append([InlineKeyboardButton(text="🏴‍☠️ Пиратская версия", callback_data=f"pirate_{game_name}")])
    if game.get("original_url"):
        keyboard.append([InlineKeyboardButton(text="🛒 Оригинал (лицензия)", callback_data=f"original_{game_name}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад к списку", callback_data="back_to_games_list")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    description = game.get("description", "Описание отсутствует")
    
    # Если есть фото - отправляем фото с описанием
    if game.get("photo"):
        photo_path = os.path.join(DATA_DIR, game["photo"])
        if os.path.exists(photo_path):
            try:
                with open(photo_path, 'rb') as photo_file:
                    await callback.message.answer_photo(
                        types.BufferedInputFile(photo_file.read(), filename="game_photo.jpg"),
                        caption=f"🎮 <b>{game_name}</b>\n\n{description}\n\n➡️ Выберите тип игры:",
                        reply_markup=markup,
                        parse_mode=ParseMode.HTML
                    )
                    return
            except Exception as e:
                logger.error(f"Error sending photo: {e}")
    
    # Если фото нет - отправляем просто текст
    await callback.message.edit_text(
        f"🎮 <b>{game_name}</b>\n\n{description}\n\n➡️ Выберите тип игры:",
        reply_markup=markup,
        parse_mode=ParseMode.HTML
    )

async def handle_pirate_version(callback: types.CallbackQuery):
    game_name = callback.data.split("_", 1)[1]
    games = load_json(DB_FILE)
    game = games.get(game_name)
    
    if not game or not game.get("file"):
        await callback.message.edit_text("❌ Файл недоступен.")
        return
    
    file_name = game["file"]
    file_path = os.path.join(DATA_DIR, file_name)
    
    if not os.path.exists(file_path):
        await callback.message.edit_text("❌ Файл не найден на сервере.")
        return

    # Прогресс-бар
    message = await callback.message.edit_text(f"⏬ Подготовка загрузки «{game_name}»\n[{' ' * 20}] 0%")
    
    steps = 10
    for i in range(1, steps + 1):
        percentage = i * 10
        filled = i * 2
        bar = "█" * filled + "▒" * (20 - filled)
        
        try:
            await callback.message.edit_text(f"⏬ Загрузка «{game_name}»:\n[{bar}] {percentage}%")
        except Exception:
            pass
        
        await asyncio.sleep(0.3)

    await callback.message.edit_text("✅ Готово! Отправляю файл...")
    
    try:
        original_filename = game.get("original_filename", file_name)
        with open(file_path, 'rb') as file:
            await callback.message.answer_document(
                types.BufferedInputFile(file.read(), filename=original_filename),
                caption=f"🎮 <b>{game_name}</b> - Пиратская версия\n\nУстановите файл на ваше устройство.",
                parse_mode=ParseMode.HTML
            )
    except Exception as e:
        logger.error(f"Error sending file: {e}")
        await callback.message.answer(f"❌ Ошибка при отправке файла: {e}")

async def handle_original_version(callback: types.CallbackQuery):
    game_name = callback.data.split("_", 1)[1]
    games = load_json(DB_FILE)
    game = games.get(game_name)
    
    if not game or not game.get("original_url"):
        await callback.message.edit_text("❌ Ссылка недоступна.")
        return
    
    url = game["original_url"]
    keyboard = [
        [InlineKeyboardButton(text=f"🛒 Установить «{game_name}» (лицензия)", url=url)],
        [InlineKeyboardButton(text="🔙 Назад к игре", callback_data=f"game_{game_name}")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text(
        f"🛒 <b>Оригинальная версия «{game_name}»</b>\n\nНажмите кнопку ниже для перехода к покупке:",
        reply_markup=markup,
        parse_mode=ParseMode.HTML
    )

# ========== ДОНАТ ==========
async def show_donate(message: types.Message):
    keyboard = [
        [InlineKeyboardButton(text="💳 Перейти к оплате", url="https://t.me/send?start=IV4FE5sinFii")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await message.answer(
        "💖 <b>Поддержите разработчика!</b>\n\nВаши донаты помогают развивать бота и добавлять новые игры.",
        reply_markup=markup,
        parse_mode=ParseMode.HTML
    )

# ========== АДМИН-ПАНЕЛЬ ==========
async def show_admin_menu(message: types.Message):
    if not is_admin(message.from_user.username):
        await message.answer("❌ У вас нет прав администратора.")
        return
    
    keyboard = [
        [InlineKeyboardButton(text="🎮 Добавить новую игру", callback_data="admin_add_game")],
        [InlineKeyboardButton(text="🖼 Добавить фото к игре", callback_data="admin_add_photo_existing")],
        [InlineKeyboardButton(text="📤 Добавить пиратку к игре", callback_data="admin_add_pirate_existing")],
        [InlineKeyboardButton(text="🔗 Добавить оригинал к игре", callback_data="admin_add_original_existing")],
        [InlineKeyboardButton(text="🗑 Удалить игру", callback_data="admin_delete_game")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_list_users")],
        [InlineKeyboardButton(text="🚫 Заблокировать пользователя", callback_data="admin_block_user")],
        [InlineKeyboardButton(text="✅ Разблокировать пользователя", callback_data="admin_unblock_user")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await message.answer("⚙️ <b>Админ-меню</b>\n\nВыберите действие:", reply_markup=markup, parse_mode=ParseMode.HTML)

async def handle_admin_add_game(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.username):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🎮 Введите название новой игры:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_admin")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_game_name)

async def handle_admin_add_photo_existing(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.username):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    games = load_json(DB_FILE)
    if not games:
        await callback.message.edit_text("📭 Нет игр для обновления.", reply_markup=get_back_to_admin_inline_keyboard())
        return
    
    keyboard = []
    for game_name in games.keys():
        keyboard.append([InlineKeyboardButton(text=game_name, callback_data=f"add_photo_{game_name}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")])
    await callback.message.edit_text("🖼 Выберите игру для добавления фото:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

async def handle_admin_add_pirate_existing(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.username):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    games = load_json(DB_FILE)
    if not games:
        await callback.message.edit_text("📭 Нет игр для обновления.", reply_markup=get_back_to_admin_inline_keyboard())
        return
    
    keyboard = []
    for game_name in games.keys():
        keyboard.append([InlineKeyboardButton(text=game_name, callback_data=f"add_pirate_{game_name}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")])
    await callback.message.edit_text("📤 Выберите игру для добавления пиратской версии:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

async def handle_admin_add_original_existing(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.username):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    games = load_json(DB_FILE)
    if not games:
        await callback.message.edit_text("📭 Нет игр для обновления.", reply_markup=get_back_to_admin_inline_keyboard())
        return
    
    keyboard = []
    for game_name in games.keys():
        keyboard.append([InlineKeyboardButton(text=game_name, callback_data=f"add_original_{game_name}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_admin")])
    await callback.message.edit_text("🔗 Выберите игру для добавления оригинальной версии:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

async def handle_add_photo_to_game(callback: types.CallbackQuery, state: FSMContext):
    game_name = callback.data.split("_", 2)[2]
    await state.update_data(game_name=game_name)
    await callback.message.edit_text(
        f"🖼 Добавление фото для «{game_name}». Отправьте фото:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_admin")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_game_photo)

async def handle_add_pirate_to_game(callback: types.CallbackQuery, state: FSMContext):
    game_name = callback.data.split("_", 2)[2]
    await state.update_data(game_name=game_name)
    await callback.message.edit_text(
        f"📤 Добавление пиратской версии для «{game_name}». Отправьте файл:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_admin")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_game_file)

async def handle_add_original_to_game(callback: types.CallbackQuery, state: FSMContext):
    game_name = callback.data.split("_", 2)[2]
    await state.update_data(game_name=game_name)
    await callback.message.edit_text(
        f"🔗 Добавление оригинальной версии для «{game_name}». Отправьте ссылку:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_admin")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_original_url)

async def handle_game_name_input(message: types.Message, state: FSMContext):
    await state.update_data(game_name=message.text)
    await message.answer(
        "📝 Теперь введите описание игры:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_admin")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_game_description)

async def handle_game_description_input(message: types.Message, state: FSMContext):
    await state.update_data(game_description=message.text)
    data = await state.get_data()
    game_name = data.get('game_name')
    game_description = data.get('game_description')

    # Сохраняем новую игру без файла и ссылки
    games = load_json(DB_FILE)
    games[game_name] = {
        "description": game_description,
        "added_by": message.from_user.username,
        "added_date": datetime.now().isoformat()
    }
    save_json(games, DB_FILE)

    await message.answer(
        f"✅ Игра «{game_name}» успешно добавлена! Теперь вы можете добавить фото, пиратскую или оригинальную версию.",
        reply_markup=get_back_to_admin_inline_keyboard()
    )
    await state.clear()

async def handle_game_photo_input(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("❌ Пожалуйста, отправьте фото.")
        return
    
    data = await state.get_data()
    game_name = data.get('game_name')
    
    # Сохраняем фото (берем самое большое доступное качество)
    photo = message.photo[-1]
    file_id = photo.file_id
    file = await message.bot.get_file(file_id)
    file_path = file.file_path
    
    # Создаем безопасное имя файла
    safe_file_name = f"{game_name}_photo.jpg"
    
    # Полный путь для сохранения
    full_file_path = os.path.join(DATA_DIR, safe_file_name)
    
    try:
        # Скачиваем фото
        await message.bot.download_file(file_path, full_file_path)
        
        # Проверяем, что фото скачалось
        if not os.path.exists(full_file_path):
            await message.answer("❌ Ошибка при сохранении фото.")
            return
        
        # Обновляем игру в базе
        games = load_json(DB_FILE)
        if game_name not in games:
            games[game_name] = {}
        games[game_name]["photo"] = safe_file_name
        save_json(games, DB_FILE)
        
        await message.answer(
            f"✅ Фото для игры «{game_name}» успешно добавлено!",
            reply_markup=get_back_to_admin_inline_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error saving photo: {e}")
        await message.answer(f"❌ Ошибка при сохранении фото: {e}")
    
    await state.clear()

async def handle_game_file_input(message: types.Message, state: FSMContext):
    if not message.document:
        await message.answer("❌ Пожалуйста, отправьте файл.")
        return
    
    data = await state.get_data()
    game_name = data.get('game_name')
    
    # Сохраняем файл
    file_id = message.document.file_id
    file = await message.bot.get_file(file_id)
    file_path = file.file_path
    
    # Создаем безопасное имя файла
    original_file_name = message.document.file_name
    safe_file_name = f"{game_name}_{original_file_name}".replace(" ", "_").replace("/", "_")
    
    # Полный путь для сохранения
    full_file_path = os.path.join(DATA_DIR, safe_file_name)
    
    try:
        # Скачиваем файл
        await message.bot.download_file(file_path, full_file_path)
        
        # Проверяем, что файл скачался
        if not os.path.exists(full_file_path):
            await message.answer("❌ Ошибка при сохранении файла.")
            return
        
        # Обновляем игру в базе
        games = load_json(DB_FILE)
        if game_name not in games:
            games[game_name] = {}
        games[game_name]["file"] = safe_file_name
        games[game_name]["original_filename"] = original_file_name
        save_json(games, DB_FILE)
        
        await message.answer(
            f"✅ Пиратская версия для игры «{game_name}» успешно добавлена!\n"
            f"📁 Файл: {original_file_name}",
            reply_markup=get_back_to_admin_inline_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Error saving file: {e}")
        await message.answer(f"❌ Ошибка при сохранении файла: {e}")
    
    await state.clear()

async def handle_original_url_input(message: types.Message, state: FSMContext):
    data = await state.get_data()
    game_name = data.get('game_name')
    original_url = message.text
    
    # Обновляем игру в базе
    games = load_json(DB_FILE)
    if game_name not in games:
        games[game_name] = {}
    games[game_name]["original_url"] = original_url
    save_json(games, DB_FILE)
    
    await message.answer(
        f"✅ Оригинальная версия для игры «{game_name}» успешно добавлена!",
        reply_markup=get_back_to_admin_inline_keyboard()
    )
    await state.clear()

async def handle_admin_delete_game(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.username):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    games = load_json(DB_FILE)
    if not games:
        await callback.message.edit_text("📭 Нет игр для удаления.", reply_markup=get_back_to_admin_inline_keyboard())
        return
    
    keyboard = []
    for game_name in games.keys():
        keyboard.append([InlineKeyboardButton(text=game_name, callback_data=f"delete_{game_name}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад в админ-меню", callback_data="back_to_admin")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text("🗑 <b>Выберите игру для удаления:</b>", reply_markup=markup, parse_mode=ParseMode.HTML)

async def handle_game_deletion(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.username):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    game_name = callback.data.split("_", 1)[1]
    games = load_json(DB_FILE)
    
    if game_name in games:
        # Удаляем файл, если он есть
        if games[game_name].get("file"):
            file_path = os.path.join(DATA_DIR, games[game_name]["file"])
            if os.path.exists(file_path):
                os.remove(file_path)
        
        # Удаляем фото, если оно есть
        if games[game_name].get("photo"):
            photo_path = os.path.join(DATA_DIR, games[game_name]["photo"])
            if os.path.exists(photo_path):
                os.remove(photo_path)
        
        del games[game_name]
        save_json(games, DB_FILE)
        
        await callback.message.edit_text(
            f"✅ Игра «{game_name}» успешно удалена!",
            reply_markup=get_back_to_admin_inline_keyboard()
        )
    else:
        await callback.message.edit_text("❌ Игра не найдена.", reply_markup=get_back_to_admin_inline_keyboard())

async def handle_admin_list_users(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.username):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    users = load_json(USERS_FILE)
    blocked_users = load_json(BLOCKED_USERS_FILE)
    
    if not users:
        await callback.message.edit_text("📭 Нет зарегистрированных пользователей.", reply_markup=get_back_to_admin_inline_keyboard())
        return
    
    user_list = "👥 <b>Список пользователей:</b>\n\n"
    for i, (user_id, user_data) in enumerate(list(users.items())[:20], 1):
        username = user_data.get('username', 'нет username')
        first_name = user_data.get('first_name', '')
        last_name = user_data.get('last_name', '')
        status = "🚫" if user_id in blocked_users else "✅"
        
        user_list += f"{i}. {status} {first_name} {last_name} (@{username})\n"
    
    user_list += f"\n📊 Всего пользователей: {len(users)}"
    user_list += f"\n🚫 Заблокировано: {len(blocked_users)}"
    
    if len(users) > 20:
        user_list += f"\n\n... и еще {len(users) - 20} пользователей"
    
    await callback.message.edit_text(user_list, reply_markup=get_back_to_admin_inline_keyboard(), parse_mode=ParseMode.HTML)

async def handle_admin_block_user(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.username):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🚫 Введите username пользователя для блокировки (без @):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_admin")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_username_to_block)

async def handle_admin_unblock_user(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.username):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    await callback.message.edit_text(
        "✅ Введите username пользователя для разблокировки (без @):",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 Отмена", callback_data="back_to_admin")]]
        )
    )
    await state.set_state(AdminStates.waiting_for_username_to_unblock)

async def handle_username_to_block_input(message: types.Message, state: FSMContext):
    username = message.text.strip()
    user_id = get_user_id_by_username(username)
    
    if user_id:
        block_user(user_id)
        await message.answer(
            f"✅ Пользователь @{username} заблокирован!",
            reply_markup=get_back_to_admin_inline_keyboard()
        )
    else:
        await message.answer(
            f"❌ Пользователь @{username} не найден.",
            reply_markup=get_back_to_admin_inline_keyboard()
        )
    
    await state.clear()

async def handle_username_to_unblock_input(message: types.Message, state: FSMContext):
    username = message.text.strip()
    user_id = get_user_id_by_username(username)
    
    if user_id:
        unblock_user(user_id)
        await message.answer(
            f"✅ Пользователь @{username} разблокирован!",
            reply_markup=get_back_to_admin_inline_keyboard()
        )
    else:
        await message.answer(
            f"❌ Пользователь @{username} не найден.",
            reply_markup=get_back_to_admin_inline_keyboard()
        )
    
    await state.clear()

# ========== ОБРАБОТКА ВСПОМОГАТЕЛЬНЫХ CALLBACK'ОВ ==========
async def handle_back_to_main(callback: types.CallbackQuery):
    await callback.message.edit_text("Возвращаемся в главное меню...")
    await callback.message.answer(
        "🏠 Главное меню:",
        reply_markup=get_main_keyboard(callback.from_user)
    )

async def handle_back_to_admin(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    if not is_admin(callback.from_user.username):
        await callback.answer("❌ Нет доступа", show_alert=True)
        return
    
    keyboard = [
        [InlineKeyboardButton(text="🎮 Добавить новую игру", callback_data="admin_add_game")],
        [InlineKeyboardButton(text="🖼 Добавить фото к игре", callback_data="admin_add_photo_existing")],
        [InlineKeyboardButton(text="📤 Добавить пиратку к игре", callback_data="admin_add_pirate_existing")],
        [InlineKeyboardButton(text="🔗 Добавить оригинал к игре", callback_data="admin_add_original_existing")],
        [InlineKeyboardButton(text="🗑 Удалить игру", callback_data="admin_delete_game")],
        [InlineKeyboardButton(text="👥 Список пользователей", callback_data="admin_list_users")],
        [InlineKeyboardButton(text="🚫 Заблокировать пользователя", callback_data="admin_block_user")],
        [InlineKeyboardButton(text="✅ Разблокировать пользователя", callback_data="admin_unblock_user")],
        [InlineKeyboardButton(text="🔙 Назад в меню", callback_data="back_to_main")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    
    await callback.message.edit_text("⚙️ <b>Админ-меню</b>\n\nВыберите действие:", reply_markup=markup, parse_mode=ParseMode.HTML)

async def handle_back_to_games_list(callback: types.CallbackQuery):
    await show_games_list(callback.message)

async def check_files_command(message: types.Message):
    """Команда для проверки файлов (только для админов)"""
    if not is_admin(message.from_user.username):
        return
    
    games = load_json(DB_FILE)
    if not games:
        await message.answer("📭 Нет игр в базе.")
        return
    
    files_info = "📁 Проверка файлов:\n\n"
    
    for game_name, game_data in games.items():
        if game_data.get("file"):
            file_path = os.path.join(DATA_DIR, game_data["file"])
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
                files_info += f"✅ {game_name}: ФАЙЛ - {game_data['file']} ({file_size} байт)\n"
            else:
                files_info += f"❌ {game_name}: ФАЙЛ НЕ НАЙДЕН - {game_data['file']}\n"
        if game_data.get("photo"):
            photo_path = os.path.join(DATA_DIR, game_data["photo"])
            if os.path.exists(photo_path):
                photo_size = os.path.getsize(photo_path)
                files_info += f"🖼 {game_name}: ФОТО - {game_data['photo']} ({photo_size} байт)\n"
            else:
                files_info += f"❌ {game_name}: ФОТО НЕ НАЙДЕНО - {game_data['photo']}\n"
        if not game_data.get("file") and not game_data.get("photo"):
            files_info += f"📝 {game_name}: нет файлов и фото\n"
    
    await message.answer(files_info)

# ========== ЗАПУСК БОТА ==========
async def main():
    # Инициализация файлов
    init_files()
    
    # Проверка токена
    if not BOT_TOKEN or BOT_TOKEN == '8446569923:AAGon_20FfR_w_8-WYtABwQI95QUe6rj34E':
        logger.error("BOT_TOKEN not set properly!")
        return
    
    bot = Bot(token=BOT_TOKEN, parse_mode=ParseMode.HTML)
    dp = Dispatcher()

    # Регистрация обработчиков сообщений
    dp.message.register(start_command, Command("start"))
    dp.message.register(check_files_command, Command("checkfiles"))
    dp.message.register(handle_main_menu_buttons, F.text.in_(["🎮 Список игр", "💖 Донат", "⚙️ Админ-меню"]))
    
    # Регистрация обработчиков состояний админа
    dp.message.register(handle_game_name_input, AdminStates.waiting_for_game_name)
    dp.message.register(handle_game_description_input, AdminStates.waiting_for_game_description)
    dp.message.register(handle_game_photo_input, AdminStates.waiting_for_game_photo)
    dp.message.register(handle_game_file_input, AdminStates.waiting_for_game_file)
    dp.message.register(handle_original_url_input, AdminStates.waiting_for_original_url)
    dp.message.register(handle_username_to_block_input, AdminStates.waiting_for_username_to_block)
    dp.message.register(handle_username_to_unblock_input, AdminStates.waiting_for_username_to_unblock)
    
    # Регистрация обработчиков callback'
    dp.callback_query.register(handle_back_to_main, F.data == "back_to_main")
    dp.callback_query.register(handle_back_to_admin, F.data == "back_to_admin")
    dp.callback_query.register(handle_back_to_games_list, F.data == "back_to_games_list")
    dp.callback_query.register(handle_game_selection, F.data.startswith("game_"))
    dp.callback_query.register(handle_pirate_version, F.data.startswith("pirate_"))
    dp.callback_query.register(handle_original_version, F.data.startswith("original_"))
    dp.callback_query.register(handle_admin_add_game, F.data == "admin_add_game")
    dp.callback_query.register(handle_admin_add_photo_existing, F.data == "admin_add_photo_existing")
    dp.callback_query.register(handle_admin_add_pirate_existing, F.data == "admin_add_pirate_existing")
    dp.callback_query.register(handle_admin_add_original_existing, F.data == "admin_add_original_existing")
    dp.callback_query.register(handle_add_photo_to_game, F.data.startswith("add_photo_"))
    dp.callback_query.register(handle_add_pirate_to_game, F.data.startswith("add_pirate_"))
    dp.callback_query.register(handle_add_original_to_game, F.data.startswith("add_original_"))
    dp.callback_query.register(handle_admin_delete_game, F.data == "admin_delete_game")
    dp.callback_query.register(handle_game_deletion, F.data.startswith("delete_"))
    dp.callback_query.register(handle_admin_list_users, F.data == "admin_list_users")
    dp.callback_query.register(handle_admin_block_user, F.data == "admin_block_user")
    dp.callback_query.register(handle_admin_unblock_user, F.data == "admin_unblock_user")

    logger.info("Бот запущен!")
    try:
        await dp.start_polling(bot)
    except Exception as e:
        logger.error(f"Bot error: {e}")

if __name__ == "__main__":
    asyncio.run(main())