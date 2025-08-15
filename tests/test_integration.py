import asyncio
import pytest
from aiogram import Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, User, Chat, CallbackQuery, PhotoSize

from handlers import survey_handlers, common_handlers
from states import BotStates


def test_full_survey_flow(mocker):
    """Тестирование полного цикла опроса."""
    async def run_test():
        # Мокируем внешние зависимости
        mocker.patch('nextgis.get_feature', return_value={'fields': {'name': 'Test', 'Поселение': 'Test', 'Улица': 'Test', 'Дом': 'Test', 'ИД_папки_Гугл_диск': 'test_id'}})
        mocker.patch('pydrive.create_folder', return_value='new_folder_id')
        mocker.patch('nextgis.ngw_post_wi_checkup', return_value=True)
        mock_answer = mocker.async_stub()
        mocker.patch.object(Message, 'answer', mock_answer)
        mock_edit_text = mocker.async_stub()
        mocker.patch.object(Message, 'edit_text', mock_edit_text)

        # Инициализация FSM
        storage = MemoryStorage()
        bot_id = 123456789
        user_id = 123
        chat_id = 123
        storage_key = StorageKey(bot_id=bot_id, user_id=user_id, chat_id=chat_id)
        state = FSMContext(storage=storage, key=storage_key)

        # Создаем "фейковые" объекты для тестирования
        bot = Bot(token="123456789:AABBCCDDEEFFaabbccddeeff-123456789")
        user = User(id=user_id, is_bot=False, first_name="Test")
        chat = Chat(id=chat_id, type="private")

        # 1. /start
        start_message = Message(message_id=1, date=123, chat=chat, from_user=user, text="/start", bot=bot)
        await common_handlers.cmd_start(start_message, state)
        current_state = await state.get_state()
        assert current_state == BotStates.fid

        # 2. fid
        fid_message = Message(message_id=2, date=124, chat=chat, from_user=user, text="123", bot=bot)
        await survey_handlers.process_step_fid(fid_message, state)
        current_state = await state.get_state()
        assert current_state == BotStates.position

        # 3. position
        position_message = Message(message_id=3, date=125, chat=chat, from_user=user, location={'latitude': 55.7558, 'longitude': 37.6173}, bot=bot)
        await survey_handlers.process_step_position(position_message, state)
        current_state = await state.get_state()
        assert current_state == BotStates.checkout

        # 4. checkout
        checkout_callback = CallbackQuery(id="1", from_user=user, chat_instance="1", data="установка с пуском воды", message=position_message)
        await survey_handlers.process_step_checkout(checkout_callback, state)
        current_state = await state.get_state()
        assert current_state == BotStates.water

        # 5. water
        water_callback = CallbackQuery(id="2", from_user=user, chat_instance="1", data="имеется", message=position_message)
        await survey_handlers.process_step_water(water_callback, state)
        current_state = await state.get_state()
        assert current_state == BotStates.workable

        # 6. workable
        workable_callback = CallbackQuery(id="3", from_user=user, chat_instance="1", data="возможна", message=position_message)
        await survey_handlers.process_step_workable(workable_callback, state)
        current_state = await state.get_state()
        assert current_state == BotStates.entrance

        # 7. entrance
        entrance_callback = CallbackQuery(id="4", from_user=user, chat_instance="1", data="возможен", message=position_message)
        await survey_handlers.process_step_entrance(entrance_callback, state)
        current_state = await state.get_state()
        assert current_state == BotStates.shot_medium

        # 8. shot_medium
        photo_message = Message(message_id=4, date=126, chat=chat, from_user=user, photo=[PhotoSize(file_id="test_file_id", file_unique_id="test_unique_id", width=100, height=100)], bot=bot)
        await survey_handlers.process_step_shot_medium(photo_message, state)
        current_state = await state.get_state()
        assert current_state == BotStates.shot_full

        # 9. shot_full
        await survey_handlers.process_step_shot_full(photo_message, state)
        current_state = await state.get_state()
        assert current_state == BotStates.shot_long

        # 10. shot_long
        await survey_handlers.process_step_shot_long(photo_message, state)
        current_state = await state.get_state()
        assert current_state == BotStates.plate_exist

        # 11. plate_exist
        plate_exist_callback = CallbackQuery(id="5", from_user=user, chat_instance="1", data="есть (по ГОСТ)", message=position_message)
        await survey_handlers.process_step_plate_exist(plate_exist_callback, state)
        current_state = await state.get_state()
        assert current_state == BotStates.shot_plate

        # 12. shot_plate
        await survey_handlers.process_step_shot_plate(photo_message, state)
        current_state = await state.get_state()
        assert current_state == BotStates.save

        # 13. save
        save_message = Message(message_id=5, date=127, chat=chat, from_user=user, text="/save", bot=bot)
        await survey_handlers.cmd_save(save_message, state, bot)
        current_state = await state.get_state()
        assert current_state is None

    asyncio.run(run_test())
