# русреал — каталог ботов

Статический сайт с каталогом ботов, автоматически синхронизируется с Notion.

## Структура

```
├── index.html          # сайт
├── bots.json           # данные (генерируется автоматически)
├── images/             # фото карточек (скачиваются автоматически)
├── scripts/
│   └── sync.py         # скрипт синхронизации с Notion
└── .github/workflows/
    └── sync.yml        # GitHub Action (запуск раз в день)
```

## Настройка (один раз)

### 1. Создать репозиторий на GitHub
- Зайди на github.com → New repository
- Название: `rusreal-bots` (или любое)
- Public ✓ (нужно для GitHub Pages)
- Загрузи все файлы из этой папки

### 2. Добавить токен Notion в Secrets
- В репозитории → Settings → Secrets and variables → Actions
- New repository secret
- Name: `NOTION_TOKEN`
- Value: твой токен (`ntn_...`)

### 3. Включить GitHub Pages
- Settings → Pages
- Source: Deploy from a branch
- Branch: `main` / `(root)`
- Save

### 4. Первый запуск синхронизации
- Actions → Sync from Notion → Run workflow
- Дождись завершения (~1-2 минуты)
- Сайт обновится автоматически

## Обновление данных

Каждый день в 03:00 UTC Action сам тянет данные из Notion.
Для немедленного обновления: Actions → Sync from Notion → Run workflow.

## Добавление новых ботов

Просто добавь запись в базу Notion — при следующей синхронизации
бот появится на сайте автоматически.
