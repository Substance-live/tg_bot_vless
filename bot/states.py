"""FSM-состояния бота."""

from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class ActivateStates(StatesGroup):
    waiting_key = State()  # ждём сообщение с ключом активации (ручной ввод)
