import asyncio
import json
import logging
import os
import urllib.request
from datetime import datetime, timedelta
import calendar
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN

ROOT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "tasks.json"
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

class AddTask(StatesGroup):
    title = State()
    due = State()

class SetDue(StatesGroup):
    value = State()

class SetInterval(StatesGroup):
    value = State()

def menu():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Новая задача", callback_data="nav:add"), InlineKeyboardButton(text="📋 Мои задачи", callback_data="nav:list")], [InlineKeyboardButton(text="✅ Выполненные", callback_data="nav:done"), InlineKeyboardButton(text="🌙 Тихие часы", callback_data="nav:quiet")], [InlineKeyboardButton(text="❔ Помощь", callback_data="nav:help")]])

def calendar_kb(year, month):
    weeks = calendar.monthcalendar(year, month)
    rows = [[InlineKeyboardButton(text=x, callback_data="noop") for x in ("Пн","Вт","Ср","Чт","Пт","Сб","Вс")]]
    for week in weeks:
        rows.append([InlineKeyboardButton(text=str(day) if day else "·", callback_data=f"day:{year}:{month}:{day}" if day else "noop") for day in week])
    prev = datetime(year, month, 1) - timedelta(days=1)
    nxt = (datetime(year, month, 28) + timedelta(days=4)).replace(day=1)
    rows.append([InlineKeyboardButton(text="‹", callback_data=f"cal:{prev.year}:{prev.month}"), InlineKeyboardButton(text=datetime(year,month,1).strftime("%B %Y"), callback_data="noop"), InlineKeyboardButton(text="›", callback_data=f"cal:{nxt.year}:{nxt.month}")])
    rows.append([InlineKeyboardButton(text="Без даты и времени", callback_data="day:none")])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="nav:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def time_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{h:02d}:00", callback_data=f"tm:{h}:0"), InlineKeyboardButton(text=f"{h:02d}:30", callback_data=f"tm:{h}:30")] for h in range(7,24)])

def repeat_kb():
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=label, callback_data=f"freq:{minutes}")] for label, minutes in (("Без повтора",0),("Каждые 30 минут",30),("Каждый час",60),("Каждые 3 часа",180),("Раз в день",1440),("Раз в неделю",10080))])

def load():
    try:
        return json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"users": {}}

def save(data):
    temp = DATA_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, DATA_FILE)

def user(data, uid):
    return data.setdefault("users", {}).setdefault(str(uid), {"tasks": [], "quiet": True})

def parse_date(value):
    value = (value or "").strip()
    if value.lower() in ("нет", "без срока"):
        return None
    for fmt in ("%d.%m.%Y %H:%M", "%Y-%m-%d %H:%M"):
        try:
            result = datetime.strptime(value, fmt)
            if result <= datetime.now():
                raise ValueError
            return result.isoformat(timespec="minutes")
        except ValueError:
            continue
    raise ValueError

def task_label(task):
    due = datetime.fromisoformat(task["due"]).strftime("%d.%m.%Y в %H:%M") if task.get("due") else "срок не задан"
    mins = task.get("interval", 60)
    repeat = (f"каждые {mins // 60} ч" if mins >= 60 and mins % 60 == 0 else f"каждые {mins} мин") if task.get("repeat") else "без повтора"
    return f"📝 {task['text']}\n🕒 {due} · 🔔 {repeat}"

def task_keyboard(task):
    tid = task["id"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Готово", callback_data=f"done:{tid}"), InlineKeyboardButton(text="⏰ Отложить 10 мин", callback_data=f"snooze:{tid}")],
        [InlineKeyboardButton(text="🔔 Автонапоминание", callback_data=f"repeat:{tid}"), InlineKeyboardButton(text="🕒 Интервал", callback_data=f"interval:{tid}")],
        [InlineKeyboardButton(text="📅 Изменить срок", callback_data=f"date:{tid}"), InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete:{tid}")],
        [InlineKeyboardButton(text="➕ Новая задача", callback_data="nav:add"), InlineKeyboardButton(text="📋 Мои задачи", callback_data="nav:list")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="nav:home")],
    ])

@dp.message(CommandStart())
async def start(message: Message):
    await message.answer("Привет! Я помогу не забыть важное. Добавь задачу — напоминания можно настроить отдельно для каждой.", reply_markup=menu())

@dp.callback_query(F.data == "nav:add")
async def add_start(query: CallbackQuery, state: FSMContext):
    await state.set_state(AddTask.title)
    await query.message.edit_text("➕ Новая задача\n\nЧто нужно сделать? Напиши задачу одним сообщением.")
    await query.answer()

@dp.message(AddTask.title)
async def add_title(message: Message, state: FSMContext):
    title = (message.text or "").strip()
    if not title or len(title) > 300:
        await message.answer("Напиши текст задачи длиной до 300 символов.")
        return
    await state.update_data(title=title)
    await state.set_state(AddTask.due)
    now=datetime.now()
    await message.answer("📅 Когда впервые напомнить об этой задаче? Выбери дату и затем время. Если пока не хочешь назначать напоминание, нажми «Без даты и времени».", reply_markup=calendar_kb(now.year,now.month))

@dp.callback_query(F.data.startswith("cal:"))
async def calendar_page(query: CallbackQuery):
    _, y, m = query.data.split(":")
    await query.message.edit_reply_markup(reply_markup=calendar_kb(int(y), int(m)))
    await query.answer()

@dp.callback_query(F.data == "noop")
async def noop(query: CallbackQuery): await query.answer()

@dp.callback_query(F.data.startswith("day:"))
async def choose_day(query: CallbackQuery, state: FSMContext):
    parts = query.data.split(":")
    if len(parts) == 2 and parts[1] == "none":
        await state.update_data(due=None, no_date=True)
        await query.message.edit_text("📭 Первое напоминание не назначено. Если включить повтор, первое напоминание придёт через выбранный интервал от текущего момента.", reply_markup=repeat_kb())
    else:
        _, ys, ms, ds = parts
        await state.update_data(chosen_day=f"{ys}-{int(ms):02d}-{int(ds):02d}")
        await query.message.edit_text("🕒 Во сколько прислать первое напоминание в выбранный день?", reply_markup=time_kb())
    await query.answer()

@dp.callback_query(F.data.startswith("tm:"))
async def choose_time(query: CallbackQuery, state: FSMContext):
    _, hs, mins = query.data.split(":")
    info = await state.get_data()
    due = datetime.fromisoformat(info["chosen_day"]).replace(hour=int(hs), minute=int(mins))
    if due <= datetime.now():
        await query.answer("Выбери будущее время", show_alert=True); return
    await state.update_data(due=due.isoformat(timespec="minutes"))
    await query.message.edit_text("Как часто напоминать?", reply_markup=repeat_kb())
    await query.answer()

@dp.callback_query(F.data.startswith("freq:"))
async def choose_frequency(query: CallbackQuery, state: FSMContext):
    minutes=int(query.data.split(":")[1]); info=await state.get_data()
    data=load(); record=user(data, query.from_user.id)
    ident=max((t["id"] for t in record["tasks"]),default=0)+1
    due=info.get("due")
    if due is None and minutes:
        due=(datetime.now()+timedelta(minutes=minutes)).isoformat(timespec="minutes")
    task={"id":ident,"text":info["title"],"due":due,"status":"active","repeat":minutes>0,"interval":minutes or 60}
    record["tasks"].append(task); save(data); await state.clear()
    finish_keyboard=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Готово",callback_data=f"created_done:{ident}")]])
    await query.message.edit_text("✅ Задача добавлена\n"+task_label(task),reply_markup=finish_keyboard)
    await query.answer()

@dp.callback_query(F.data.startswith("created_done:"))
async def created_done(query: CallbackQuery):
    # This button is only a navigation shortcut. It must not complete the task.
    await query.message.edit_text("🏠 Главное меню",reply_markup=menu())
    await query.answer("Задача сохранена")

@dp.callback_query(F.data == "nav:list")
async def list_tasks(query: CallbackQuery):
    await render_task_list(query, 0)

@dp.callback_query(F.data.startswith("listpage:"))
async def list_page(query: CallbackQuery):
    await render_task_list(query, int(query.data.split(":")[1]))

async def render_task_list(query: CallbackQuery, page: int):
    record = user(load(), query.from_user.id)
    tasks = [task for task in record["tasks"] if task["status"] == "active"]
    if not tasks:
        await query.message.edit_text("Активных задач нет. Самое время добавить новую!", reply_markup=menu())
        await query.answer()
        return
    page_size = 6
    pages = (len(tasks) + page_size - 1) // page_size
    page = max(0, min(page, pages - 1))
    visible = tasks[page * page_size:(page + 1) * page_size]
    text = f"📋 Активные задачи · {page + 1}/{pages}\nНажми действие под нужной задачей:\n\n" + "\n\n".join(task_label(t) for t in visible)
    rows = []
    for t in visible:
        rows.append([InlineKeyboardButton(text=f"✅ {t['id']} Готово", callback_data=f"done:{t['id']}"), InlineKeyboardButton(text=f"⏰ {t['id']} +10 мин", callback_data=f"snooze:{t['id']}"), InlineKeyboardButton(text=f"🗑 {t['id']}", callback_data=f"delete:{t['id']}")])
    paging = []
    if page > 0: paging.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"listpage:{page-1}"))
    if page + 1 < pages: paging.append(InlineKeyboardButton(text="Дальше ➡️", callback_data=f"listpage:{page+1}"))
    if paging: rows.append(paging)
    rows.extend([[InlineKeyboardButton(text="➕ Новая задача", callback_data="nav:add")], [InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:home")]])
    await query.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
    await query.answer()

@dp.callback_query(F.data == "nav:done")
async def completed(query: CallbackQuery):
    tasks = [task for task in user(load(), query.from_user.id)["tasks"] if task["status"] == "done"]
    await query.message.edit_text("🏆 Выполнено:\n" + "\n".join(f"• {t['text']}" for t in tasks[-30:]) if tasks else "Пока нет выполненных задач.", reply_markup=menu())
    await query.answer()

@dp.callback_query(F.data.in_({"nav:help", "nav:home"}))
async def help_message(query: CallbackQuery):
    text = "🏠 Главное меню" if query.data == "nav:home" else "Добавь задачу и срок. У каждой задачи есть кнопки: готово, отложить, автонапоминание, интервал и срок. Тихие часы: 22:00–08:00."
    await query.message.edit_text(text, reply_markup=menu())
    await query.answer()

@dp.callback_query(F.data == "nav:quiet")
async def quiet_menu(query: CallbackQuery):
    data=load(); enabled=user(data,query.from_user.id).get("quiet",True)
    buttons=[[InlineKeyboardButton(text="22:00–08:00"+(" ✓" if enabled else ""),callback_data="quiet:22:8"),InlineKeyboardButton(text="23:00–07:00"+(" ✓" if not enabled else ""),callback_data="quiet:23:7")], [InlineKeyboardButton(text="Выключить тихие часы",callback_data="quiet:off")],[InlineKeyboardButton(text="🏠 Меню",callback_data="nav:home")]]
    await query.message.edit_text("🌙 Тихие часы — общая настройка для всех напоминаний. Выбери режим:",reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)); await query.answer()

@dp.callback_query(F.data.startswith("quiet:"))
async def quiet_set(query: CallbackQuery):
    data=load(); rec=user(data,query.from_user.id); parts=query.data.split(":")
    rec["quiet"]=parts[1]!="off"
    if rec["quiet"]: rec["quiet_start"]=int(parts[1]); rec["quiet_end"]=int(parts[2])
    save(data); await query.answer("Настройка сохранена")
    await quiet_menu(query)

@dp.callback_query(F.data.startswith(("done:", "delete:", "snooze:", "repeat:", "delete_yes:", "delete_no:")))
async def task_action(query: CallbackQuery):
    action, raw_id = query.data.split(":", 1)
    data = load()
    record = user(data, query.from_user.id)
    task = next((item for item in record["tasks"] if item["id"] == int(raw_id) and item["status"] == "active"), None)
    if action == "delete":
        confirm = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗑 Да, удалить", callback_data=f"delete_yes:{raw_id}"), InlineKeyboardButton(text="↩️ Отмена", callback_data=f"delete_no:{raw_id}")], [InlineKeyboardButton(text="📋 К списку", callback_data="nav:list")]])
        await query.message.edit_text("Удалить задачу?\n\n" + task_label(task) if task else "Задача уже удалена.", reply_markup=confirm if task else menu())
        await query.answer()
        return
    if action == "delete_no":
        await query.message.edit_text("Удаление отменено.\n\n" + task_label(task) if task else "Задача не найдена.", reply_markup=task_keyboard(task) if task else menu())
        await query.answer()
        return
    if not task:
        await query.answer("Задача уже изменена или удалена.", show_alert=True)
        return
    if action == "done":
        task["status"] = "done"
        save(data)
        await query.message.edit_text("✅ Выполнено!\n" + task_label(task), reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 К активным задачам", callback_data="nav:list")], [InlineKeyboardButton(text="🏠 Главное меню", callback_data="nav:home")]]))
    elif action == "delete_yes":
        record["tasks"].remove(task)
        save(data)
        await query.message.edit_text("🗑 Задача удалена.", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="📋 К списку задач", callback_data="nav:list")], [InlineKeyboardButton(text="🏠 Главное меню", callback_data="nav:home")]]))
    elif action == "snooze":
        task["due"] = (datetime.now() + timedelta(minutes=10)).isoformat(timespec="minutes")
        save(data)
        await query.message.edit_text("⏰ Напомню через 10 минут.\n" + task_label(task), reply_markup=task_keyboard(task))
    else:
        task["repeat"] = not task.get("repeat", False)
        save(data)
        await query.message.edit_text(("🔔 Автонапоминание включено." if task["repeat"] else "🔕 Автонапоминание выключено.") + "\n" + task_label(task), reply_markup=task_keyboard(task))
    await query.answer()

@dp.callback_query(F.data.startswith("interval:"))
async def interval_start(query: CallbackQuery, state: FSMContext):
    await state.set_state(SetInterval.value)
    await state.update_data(task_id=int(query.data.split(":")[1]))
    await query.message.answer("Введи интервал повтора в минутах (от 5 до 10080). Например: 60 или 1440 для раза в день.")
    await query.answer()

@dp.message(SetInterval.value)
async def interval_save(message: Message, state: FSMContext):
    try:
        minutes = int(message.text)
        if not 5 <= minutes <= 10080: raise ValueError
    except (ValueError, TypeError):
        await message.answer("Нужно число от 5 до 10080 минут.")
        return
    info = await state.get_data()
    data = load()
    task = next((t for t in user(data, message.from_user.id)["tasks"] if t["id"] == info["task_id"] and t["status"] == "active"), None)
    if task:
        task["interval"] = minutes
        save(data)
        await message.answer("Интервал сохранён: " + task_label(task), reply_markup=task_keyboard(task))
    else:
        await message.answer("Задача не найдена.")
    await state.clear()

@dp.callback_query(F.data.startswith("date:"))
async def date_start(query: CallbackQuery, state: FSMContext):
    await state.set_state(SetDue.value)
    await state.update_data(task_id=int(query.data.split(":")[1]))
    await query.message.answer("Введи новый срок ДД.ММ.ГГГГ ЧЧ:ММ или «без срока».")
    await query.answer()

@dp.message(SetDue.value)
async def date_save(message: Message, state: FSMContext):
    try:
        due = parse_date(message.text)
    except ValueError:
        await message.answer("Дата не распознана. Пример: 25.12.2026 18:30.")
        return
    info = await state.get_data()
    data = load()
    task = next((t for t in user(data, message.from_user.id)["tasks"] if t["id"] == info["task_id"] and t["status"] == "active"), None)
    if task:
        task["due"] = due
        save(data)
        await message.answer("Срок обновлён:\n" + task_label(task), reply_markup=task_keyboard(task))
    else:
        await message.answer("Задача не найдена.")
    await state.clear()

async def reminder_loop(bot: Bot):
    while True:
        now = datetime.now()
        data = load()
        changed = False
        for uid, record in data.get("users", {}).items():
            for task in record.get("tasks", []):
                if task.get("status") != "active" or not task.get("due"):
                    continue
                due = datetime.fromisoformat(task["due"])
                if due > now:
                    continue
                quiet_start=record.get("quiet_start",22); quiet_end=record.get("quiet_end",8)
                quiet=record.get("quiet",True) and (now.hour >= quiet_start or now.hour < quiet_end)
                if quiet:
                    target=now.replace(hour=quiet_end,minute=0,second=0,microsecond=0)
                    if now.hour >= quiet_start: target += timedelta(days=1)
                    task["due"] = target.isoformat(timespec="minutes")
                    changed = True
                    continue
                try:
                    await bot.send_message(int(uid), "⏰ Напоминание\n" + task_label(task), reply_markup=task_keyboard(task))
                    task["due"] = (now + timedelta(minutes=task.get("interval", 60))).isoformat(timespec="minutes") if task.get("repeat") else None
                    changed = True
                except Exception:
                    logging.exception("Не удалось отправить напоминание")
        if changed:
            save(data)
        await asyncio.sleep(20)

async def main():
    if not BOT_TOKEN or BOT_TOKEN.startswith("PASTE_"):
        raise RuntimeError("Вставь токен бота в config.py")
    proxy = urllib.request.getproxies().get("https") or urllib.request.getproxies().get("http")
    session = AiohttpSession(proxy=proxy) if proxy else AiohttpSession()
    bot = Bot(BOT_TOKEN, session=session)
    job = asyncio.create_task(reminder_loop(bot))
    try:
        await dp.start_polling(bot)
    finally:
        job.cancel()
        await session.close()

if __name__ == "__main__":
    asyncio.run(main())


