from aiogram.fsm.state import State, StatesGroup


class BotStates(StatesGroup):
    fid = State()
    position = State()
    checkout = State()
    water = State()
    workable = State()
    work_note = State()
    entrance = State()
    entr_note = State()
    plate_exist = State()
    shot_medium = State()
    shot_full = State()
    shot_long = State()
    shot_plate = State()
    save = State()
