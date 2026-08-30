from aiogram.fsm.state import State, StatesGroup


class NewPost(StatesGroup):
    choosing_channels = State()
    waiting_content = State()
    choosing_delete_after = State()
    choosing_time = State()
    waiting_custom_time = State()
    waiting_buttons = State()
    editing_text = State()
    editing_media = State()


class EditPost(StatesGroup):
    waiting_text = State()
    waiting_buttons = State()
    waiting_media = State()
