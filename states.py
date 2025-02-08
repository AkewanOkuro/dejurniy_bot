from aiogram.dispatcher.filters.state import State, StatesGroup

class CalendarFSM(StatesGroup):
    waiting_password = State()
    registration = State()
    choosing_year = State()
    choosing_week = State()
    choosing_day = State()
    assigning_user = State()

class SwapFSM(StatesGroup):
    select_user = State()
    enter_message = State()