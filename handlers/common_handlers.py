from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery
from loguru import logger

from keyboards import get_help_keyboard
from lexicon import bot_states
from states import BotStates
from handlers import survey_handlers

router = Router()


@router.message(Command('stop'))
async def cmd_stop(message: Message, state: FSMContext):
    """Обработчик команды /stop."""
    current_state = await state.get_state()
    if current_state is not None:
        await state.clear()
        await message.answer("Диалог прерван. Все данные удалены.")
    else:
        await message.answer("Нет активного диалога для остановки.")
    await message.delete()


@router.message(Command('help'))
async def cmd_help(message: Message):
    """Обработчик команды /help."""
    await message.answer('📖 <b>Помощь</b>', reply_markup=get_help_keyboard())


@router.callback_query(F.data == 'delete_message')
async def delete_message_callback(callback: CallbackQuery):
    """Удаляет сообщение, к которому привязана кнопка."""
    await callback.message.delete()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Обработчик команды /start."""
    logger.debug(f'Старт пользователя: username - {message.from_user.username}, '
                 f'first_name - {message.from_user.first_name}, last_name - {message.from_user.last_name}, '
                 f'id - {message.from_user.id}')

    current_state = await state.get_state()
    if current_state is not None:
        state_name = bot_states.get(current_state, "Неизвестное состояние")
        await message.answer(f'<i>Диалог ввода данных уже запущен.\n'
                             f'Текущий статус: {state_name}</i>')
        return

    # Проверяем, есть ли аргументы в команде /start
    args = message.text.split()
    if len(args) > 1 and args[1].isdigit():
        fid = args[1]
        await message.answer(f'🆔 <b>1. Числовой идентификатор:</b> {fid}')
        await state.set_state(BotStates.fid)
        # Создаем "фейковое" сообщение, чтобы передать его в следующий шаг
        fake_message = message
        fake_message.text = fid
        await survey_handlers.process_step_fid(fake_message, state)
    else:
        await state.set_state(BotStates.fid)
        await message.answer('🆔 <b>1. Числовой идентификатор </b>')


@router.message()
async def process_unknown_messages(message: Message, state: FSMContext):
    """Обработчик для любых других сообщений."""
    current_state = await state.get_state()
    if current_state is None:
        await message.answer('<i>Для запуска введите команду /start</i>')
    else:
        state_name = bot_states.get(current_state, "Неизвестное состояние")
        await message.answer(f'<i>Неверный ввод для текущего шага: {state_name}</i>\n'
                             f'<i>Для отмены введите /stop</i>')