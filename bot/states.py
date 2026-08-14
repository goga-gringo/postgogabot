from aiogram.fsm.state import State, StatesGroup


class NewPost(StatesGroup):
    choosing_channels = State()
    choosing_delete_after = State()
    choosing_time = State()
    waiting_custom_time = State()


class EditPost(StatesGroup):
    waiting_text = State()
