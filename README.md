# release-notify

Скрипт для отправки уведомлений о релизе в Telegram-чат. Автоматически извлекает Jira-тикеты из коммитов, получает их информацию через JIRA API, меняет статусы и исполнителей, затем отправляет сообщение со ссылками.

## Как это работает

1. Из списка коммитов извлекаются номера Jira-тикетов (например, `DEV-12345`)
2. Для каждого тикета получается информация через JIRA API (заголовок, статус, reporter)
3. В зависимости от типа тикета меняется статус используя `workflow_matrix.json`:
   - **Bug** → `DEV Ready For Testing`
   - **Task/Sub-task/Improvement** → `Testing`
4. Меняется исполнитель (assignee):
   - Если reporter в списке тестировщиков → назначается на reporter
   - Иначе → назначается на QA lead
5. Сообщение формируется и отправляется в Telegram-чат

## Требования

- Python 3.11+
- Доступ к JIRA API (username/password)
- Telegram бот с токеном

## Установка

```bash
pip install -r requirements.txt
cp .env.example .env  # заполни конфиг
```

## Настройка

Скопируй `.env.example` в `.env` и заполни значения:

```bash
cp .env.example .env
```

| Переменная         | Описание |
|--------------------|----------|
| `BOT_TOKEN`        | Токен Telegram-бота (от [@BotFather](https://t.me/BotFather)) |
| `CHAT_ID`          | ID чата/группы куда отправлять сообщение |
| `JIRA_HOST`        | Хост Jira (например, `jira.yourcompany.com`) |
| `JIRA_USERNAME`    | Username для JIRA API |
| `JIRA_PASSWORD`    | Password для JIRA API |
| `JIRA_QA_TESTERS`  | Usernames тестировщиков через запятую (например, `user1,user2,user3`) |
| `JIRA_QA_LEAD`     | Username QA lead для назначения если reporter не в списке тестировщиков |
| `TELEGRAM_PROXY`   | Прокси для запросов к Telegram API (необязательно). Формат: `socks5://user:pass@host:port` или `http://user:pass@host:port` |

## Использование

### Вариант 1: Интерактивный бот

```bash
python bot.py
```

В Telegram напиши команду `/release` боту и следуй его подсказкам:
1. Укажи среду (QA, PROD, etc)
2. Укажи версию релиза (26.1.0)
3. Укажи номер RC (7)
4. Укажи commits через пробел или запятую

Бот автоматически:
- Извлечёт тикеты из commits
- Получит информацию через JIRA API
- Поменяет статусы и assignee
- Отправит сообщение в чат релизов
- Покажет результаты в текущем чате

### Вариант 2: CLI скрипт

```bash
python release_notify.py <environment> <release> <rc> <commit1> [commit2 ...]
```

| Параметр      | Описание |
|---------------|----------|
| `environment` | Название среды, на которую деплоится релиз (например, `QA`, `PROD`) |
| `release`     | Версия релиза (например, `26.1.0`) |
| `rc`          | Номер release candidate |
| `commit...`   | Один или несколько коммитов в формате `hash(Type TICKET-123 Description)` |

Пример запуска:

```bash
python release_notify.py QA 26.1.0 7 \
  "abc12345(BugFix DEV-12345 Fix something)" \
  "def67890(BugFix DEV-67890 Fix something else)"
```

Скрипт выведет результаты в консоль и отправит сообщение в Telegram.

## Пример сообщения в Telegram

```
📋 На QA 26.1.0-rc7:
DEV-12345 - Fix null pointer exception in payment flow
DEV-67890 - Update user profile page layout
```

Каждый тикет — кликабельная ссылка на соответствующую задачу в Jira.

## Структура проекта

```
.
├── bot.py                  # интерактивный Telegram бот
├── release_notify.py       # CLI скрипт
├── release_notifier.py     # основная логика (JIRA API, Telegram, workflow)
├── workflow_matrix.json    # матрица переходов между статусами
├── .env                    # секреты (не коммитится)
├── .env.example            # шаблон .env
├── requirements.txt        # зависимости
├── .gitignore
└── README.md
```

## Workflow Matrix

Файл `workflow_matrix.json` содержит матрицу возможных переходов между статусами для каждого типа тикета (Bug, Task, Sub-task, Improvement).

Структура:
```json
{
  "Bug": {
    "текущий_статус": {
      "целевой_статус": "название_transition"
    }
  }
}
```

Скрипт использует BFS для поиска кратчайшего пути от текущего статуса к целевому и проходит по цепочке переходов.
