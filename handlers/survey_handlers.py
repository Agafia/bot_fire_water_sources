import asyncio
import datetime
import pytz
from aiogram import Router, F, Bot
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State
from aiogram.types import Message, CallbackQuery
from loguru import logger
from pyproj import Transformer

import nextgis
import pydrive
import templates
from config import Config
from keyboards import (
    get_checkout_keyboard,
    get_water_keyboard,
    get_workable_keyboard,
    get_entrance_keyboard,
    get_plate_keyboard,
)
from lexicon import bot_states
from states import BotStates

router = Router()


# --- Вспомогательные функции ---
def date_time_now():
    """Возвращает текущие дату и время."""
    try:
        current_time = datetime.datetime.now(pytz.timezone(Config.timezone))
        return {
            "year": current_time.year,
            "month": current_time.month,
            "day": current_time.day,
            "hour": current_time.hour,
            "minute": current_time.minute,
        }
    except Exception as exc:
        logger.critical(f"Ошибка при определении даты и времени: {exc}")
        return None


# --- Обработчики состояний ---
@router.message(BotStates.fid)
async def process_step_fid(message: Message, state: FSMContext):
    """Шаг 1. Обработка числового идентификатора."""
    if not message.text.isdigit():
        await message.answer("⚠ Ожидается числовой идентификатор.")
        return

    msg_fid = await message.answer("<i>Запрос к NextGIS WEB ...</i>")

    try:
        # Запускаем синхронную функцию в асинхронном контексте
        loop = asyncio.get_event_loop()
        feature = await loop.run_in_executor(
            None,
            lambda: nextgis.get_feature(
                Config.ngw_resource_wi_points, message.text, geom="no"
            ),
        )

        if feature:
            name = (
                f"{feature['fields']['name']}\n{feature['fields']['Поселение']}, "
                f"{feature['fields']['Улица']}, {feature['fields']['Дом']}"
            )
            await msg_fid.edit_text(f"<i>{name}</i>")
            await state.update_data(
                fid=int(message.text), name=name, date_time=date_time_now()
            )
            await state.set_state(BotStates.position)
            await message.answer("🌏 <b>2. Геопозиция водоисточника</b>")
        else:
            await msg_fid.edit_text(
                "<i>NextGIS не ответил или не нашёл ИД. \nПроверьте ИД или попробуйте позже</i>"
            )
            await asyncio.sleep(4)
            await msg_fid.delete()
    except Exception as e:
        logger.critical(f"Ошибка на шаге 1 (fid): {e!r}")
        await msg_fid.edit_text(
            f"<b>Произошла ошибка при запросе к NextGIS.</b>\n"
            f"<i>Пожалуйста, проверьте настройки и доступность сервиса.</i>\n"
            f"<code>Ошибка: {e}</code>"
        )
        await state.clear()


@router.message(BotStates.position, F.location)
async def process_step_position(message: Message, state: FSMContext):
    """Шаг 2. Обработка геопозиции."""
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857")

    loop = asyncio.get_event_loop()
    sm = await loop.run_in_executor(
        None, transformer.transform, message.location.latitude, message.location.longitude
    )

    await state.update_data(EPSG_3857=f"POINT({str(sm[0])} {str(sm[1])})")
    await state.set_state(BotStates.checkout)

    await message.answer(
        "✅ <b>3. Способ контроля </b>", reply_markup=get_checkout_keyboard()
    )


@router.callback_query(BotStates.checkout)
async def process_step_checkout(callback: CallbackQuery, state: FSMContext):
    """Шаг 3. Обработка способа контроля."""
    await callback.message.edit_text(f"Выбрано: {callback.data}", reply_markup=None)
    await state.update_data(checkout=callback.data)
    await state.set_state(BotStates.water)

    await callback.message.answer(
        "💦 <b>4. Наличие воды </b>", reply_markup=get_water_keyboard()
    )


@router.callback_query(BotStates.water)
async def process_step_water(callback: CallbackQuery, state: FSMContext):
    """Шаг 4. Обработка наличия воды."""
    await callback.message.edit_text(f"Выбрано: {callback.data}", reply_markup=None)
    await state.update_data(water=callback.data)
    await state.set_state(BotStates.workable)

    await callback.message.answer(
        "🛠 <b>5. Возможность установки</b>", reply_markup=get_workable_keyboard()
    )


@router.callback_query(BotStates.workable)
async def process_step_workable(callback: CallbackQuery, state: FSMContext):
    """Шаг 5. Обработка возможности установки."""
    await callback.message.edit_text(f"Выбрано: {callback.data}", reply_markup=None)
    await state.update_data(workable=callback.data)
    await state.set_state(BotStates.entrance)

    await callback.message.answer(
        "🚒 <b>6. Возможность подъезда</b>", reply_markup=get_entrance_keyboard()
    )


@router.callback_query(BotStates.entrance)
async def process_step_entrance(callback: CallbackQuery, state: FSMContext):
    """Шаг 6. Обработка возможности подъезда."""
    await callback.message.edit_text(f"Выбрано: {callback.data}", reply_markup=None)
    await state.update_data(entrance=callback.data)
    await state.set_state(BotStates.shot_medium)
    await callback.message.answer("📸 💦 <b>7. Узловой снимок</b>")


async def process_shot(
    message: Message, state: FSMContext, shot_name: str, next_state: State, next_prompt: str
):
    """Общая функция для обработки фотографий."""
    if not message.photo:
        await message.answer("⚠ Ожидается фотография.")
        return

    await state.update_data({shot_name: message.photo[-1].file_id})
    await state.set_state(next_state)
    if next_prompt:
        await message.answer(next_prompt)


@router.message(BotStates.shot_medium, F.photo)
async def process_step_shot_medium(message: Message, state: FSMContext):
    """Шаг 7. Обработка узлового снимка."""
    await process_shot(
        message, state, "shot_medium_id", BotStates.shot_full, "📸 🚒 <b>8. Обзорный снимок</b>"
    )


@router.message(BotStates.shot_full, F.photo)
async def process_step_shot_full(message: Message, state: FSMContext):
    """Шаг 8. Обработка обзорного снимка."""
    await process_shot(
        message, state, "shot_full_id", BotStates.shot_long, "📸 🏘 <b>9. Ориентирующий снимок</b>"
    )


@router.message(BotStates.shot_long, F.photo)
async def process_step_shot_long(message: Message, state: FSMContext):
    """Шаг 9. Обработка ориентирующего снимка."""
    await process_shot(message, state, "shot_long_id", BotStates.plate_exist, "")

    await message.answer(
        "🔀 <b>10. Наличие указателя</b>", reply_markup=get_plate_keyboard()
    )


@router.callback_query(BotStates.plate_exist)
async def process_step_plate_exist(callback: CallbackQuery, state: FSMContext):
    """Шаг 10. Обработка наличия указателя."""
    await callback.message.edit_text(f"Выбрано: {callback.data}", reply_markup=None)
    await state.update_data(plate_exist=callback.data)

    if callback.data == "отсутствует":
        await state.update_data(shot_plate=None)
        await state.set_state(BotStates.save)
        await callback.message.answer("💾 <b>12. Для сохранения введите /save</b>")
    else:
        await state.set_state(BotStates.shot_plate)
        await callback.message.answer("📸 🔀 <b>11. Снимок указателя</b>")


@router.message(BotStates.shot_plate, F.photo)
async def process_step_shot_plate(message: Message, state: FSMContext):
    """Шаг 11. Обработка снимка указателя."""
    await process_shot(
        message, state, "shot_plate", BotStates.save, "💾 <b>12. Для сохранения введите /save</b>"
    )


@router.message(Command("save"))
async def cmd_save(message: Message, state: FSMContext, bot: Bot):
    """Обработчик команды /save."""
    current_state = await state.get_state()
    if current_state != "BotStates:save":
        state_name = bot_states.get(current_state, "Неизвестное состояние")
        await message.answer(
            f"<i>Ввод данных ещё не завершен.\nТекущий статус: {state_name}</i>"
        )
        return

    data = await state.get_data()
    msg_text = f"<b>Передача данных...</b>\n<i>ИД: {data['fid']}</i>"
    msg = await message.answer(msg_text)

    loop = asyncio.get_event_loop()

    try:
        # 1. Запрос к NextGIS WEB
        msg_text += "\n<i>1. Запрос к NextGIS WEB...</i>"
        await msg.edit_text(msg_text)
        json_object = await loop.run_in_executor(
            None,
            lambda: nextgis.get_feature(
                Config.ngw_resource_wi_points, data["fid"], geom="no"
            ),
        )
        folder_id = json_object["fields"]["ИД_папки_Гугл_диск"]
        folder_name = f"ИД-{data['fid']} {json_object['fields']['name']} {json_object['fields']['Поселение']}, {json_object['fields']['Улица']}, {json_object['fields']['Дом']}"

        # 2. Обращение к папке Google Drive
        msg_text += "\n<i>2. Обращение к папке Google Drive...</i>"
        await msg.edit_text(msg_text)
        google_folder = await loop.run_in_executor(
            None, pydrive.create_folder, folder_id, folder_name, Config.parent_folder_id
        )

        if folder_id != google_folder:
            msg_text += "\n<i>Добавление каталога в NextGIS WEB...</i>"
            await msg.edit_text(msg_text)
            description = await loop.run_in_executor(
                None,
                templates.description_water_intake,
                data["fid"],
                json_object["fields"]["Поселение"],
                json_object["fields"]["Улица"],
                json_object["fields"]["Дом"],
                json_object["fields"]["Ориентир"],
                json_object["fields"]["Исполнение"],
                json_object["fields"]["Водоотдача_сети"],
                google_folder,
                json_object["fields"]["Ссылка_Гугл_улицы"],
                json_object["fields"]["ИД_хоз_субъекта"],
            )
            fields_values = {
                "description": description,
                "ИД_папки_Гугл_диск": google_folder,
            }
            await loop.run_in_executor(
                None,
                lambda: nextgis.ngw_put_feature(
                    Config.ngw_resource_wi_points,
                    data["fid"],
                    fields_values,
                    description=description,
                ),
            )

        date_name = (
            f"{data['date_time']['year']}-{data['date_time']['month']}-{data['date_time']['day']}"
            f"_{data['date_time']['hour']}:{data['date_time']['minute']}"
        )

        # 3-6. Передача снимков
        photo_steps = [
            ("shot_medium_id", "3. Передача узлового снимка..."),
            ("shot_full_id", "4. Передача обзорного снимка..."),
            ("shot_long_id", "5. Передача ориентирующего снимка..."),
            ("shot_plate", "6. Передача снимка указателя..."),
        ]

        for i, (shot_key, step_text) in enumerate(photo_steps):
            if data.get(shot_key):
                msg_text += f"\n<i>{step_text}</i>"
                await msg.edit_text(msg_text)
                file_info = await bot.get_file(data[shot_key])
                file_url = f"https://api.telegram.org/file/bot{Config.bot_token}/{file_info.file_path}"
                file_name = f"{i + 1}_{date_name}"
                await loop.run_in_executor(
                    None, pydrive.create_file_from_url, file_url, file_name, google_folder
                )

        # 7. Запись о проверке в NextGIS WEB
        msg_text += "\n<i>7. Запись о проверке в NextGIS WEB...</i>"
        await msg.edit_text(msg_text)
        # logger.info(data['fid'], data['checkout'], data['water'],
        #             data['workable'], data['entrance'], data['plate_exist'],
        #             data['date_time'], data['EPSG_3857'])
        await loop.run_in_executor(
            None,
            nextgis.ngw_post_wi_checkup,
            data["fid"],
            data["checkout"],
            data["water"],
            data["workable"],
            data["entrance"],
            data["plate_exist"],
            data["date_time"],
            data["EPSG_3857"],
        )

        # Отправка сообщения в канал
        msg_in_grp = f"{data['name']}\n{date_name}"
        await bot.send_message(Config.tg_canal_id, msg_in_grp)

        msg_text += "\n<i>8. Сохранение данных завершено</i>"
        await msg.edit_text(msg_text)
        await state.clear()
        await asyncio.sleep(2)
        await msg.delete()

    except Exception as e:
        logger.error(f"Ошибка при сохранении: {e}")
        await msg.edit_text(
            f"<b>Произошла ошибка при сохранении данных.</b>\n"
            f"<i>Обратитесь к администратору.</i>\n"
            f"<code>{e}</code>"
        )
        await state.clear()