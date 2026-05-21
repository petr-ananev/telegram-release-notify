import logging
import os
import sys

from aiogram import Bot, Dispatcher, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from dotenv import load_dotenv

from release_notifier import ReleaseNotifier

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FSM States
class ReleaseForm(StatesGroup):
    get_environment = State()
    get_release = State()
    get_rc = State()
    get_commits = State()
    processing = State()


# Router
router = Router()


def get_notifier() -> ReleaseNotifier:
    """Create ReleaseNotifier instance."""
    return ReleaseNotifier()


@router.message(F.text == "/release")
async def cmd_release(message: Message, state: FSMContext) -> None:
    """Start release process."""
    await state.set_state(ReleaseForm.get_environment)
    await message.answer("🚀 Отправка релиза. Укажи среду (QA, PROD, etc):")


@router.message(ReleaseForm.get_environment)
async def get_environment(message: Message, state: FSMContext) -> None:
    """Get environment."""
    await state.update_data(environment=message.text)
    await state.set_state(ReleaseForm.get_release)
    await message.answer(f"✅ Среда: {message.text}\n\nУкажи версию релиза (например, 26.1.0):")


@router.message(ReleaseForm.get_release)
async def get_release(message: Message, state: FSMContext) -> None:
    """Get release version."""
    await state.update_data(release=message.text)
    await state.set_state(ReleaseForm.get_rc)
    await message.answer(f"✅ Версия: {message.text}\n\nУкажи номер RC (например, 7):")


@router.message(ReleaseForm.get_rc)
async def get_rc(message: Message, state: FSMContext) -> None:
    """Get RC number."""
    await state.update_data(rc=message.text)
    await state.set_state(ReleaseForm.get_commits)
    await message.answer(
        f"✅ RC: {message.text}\n\nУкажи commits через пробел или запятую:\n"
        '(пример: "abc123(BugFix DEV-123 Fix)" "def456(Feature DEV-456 Add)")'
    )


@router.message(ReleaseForm.get_commits)
async def get_commits(message: Message, state: FSMContext) -> None:
    """Get commits and process."""
    await state.set_state(ReleaseForm.processing)

    # Parse commits
    text = message.text.strip()
    commits = [c.strip() for c in text.replace(",", " ").split() if c.strip()]

    # Get data
    data = await state.get_data()
    environment = data["environment"]
    release = data["release"]
    rc = data["rc"]

    # Processing message
    processing_msg = await message.answer(
        f"⏳ Обработка...\n"
        f"Среда: {environment}\n"
        f"Версия: {release}-rc{rc}\n"
        f"Commits: {len(commits)}"
    )

    try:
        # Process release
        notifier = get_notifier()
        results = notifier.process_release(environment, release, rc, commits)

        # Build result message
        result_lines = [
            f"📋 Результаты обработки:",
            f"Найдено тикетов: {results['tickets_found']}",
            "",
        ]

        success_count = 0
        fail_count = 0

        for success, msg in results["status_changes"]:
            result_lines.append(f"{'✅' if success else '❌'} {msg}")
            if success:
                success_count += 1
            else:
                fail_count += 1

        result_lines.append("")
        for success, msg in results["assignee_changes"]:
            result_lines.append(f"{'✅' if success else '❌'} {msg}")

        result_lines.append("")
        result_lines.append(f"Итого: ✅ {success_count} | ❌ {fail_count}")

        # Edit processing message
        await processing_msg.edit_text("\n".join(result_lines))

        # Send telegram notification
        if results["issues"]:
            message_text = notifier.build_message(environment, release, rc, results["issues"])
            if notifier.send_telegram(message_text):
                await message.answer("✅ Сообщение отправлено в чат релизов")
            else:
                await message.answer("⚠️ Ошибка отправки сообщения в Telegram")

    except Exception as e:
        logger.exception("Error processing release")
        await processing_msg.edit_text(f"❌ Ошибка: {str(e)}")

    await state.clear()


async def main() -> None:
    """Start bot."""
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    token = os.environ["BOT_TOKEN"]
    bot = Bot(token=token)
    dp = Dispatcher()

    dp.include_router(router)

    logger.info("Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
