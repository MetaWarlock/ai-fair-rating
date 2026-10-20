# AI Fair Rating

**Один разработчик — одна лучшая измеренная модель.**

Skill и небольшой Python-скрипт строят понятный рейтинг по [Artificial Analysis Intelligence Index](https://artificialanalysis.ai/evaluations/artificial-analysis-intelligence-index). Режимы и версии одной компании не занимают несколько мест на графике.

![AI Fair Rating](examples/rating.png)

Автор: [Telegram](https://t.me/warlocksu) · [warlock.su](https://warlock.su)

## Как выбираются модели

1. Загружается полный публичный каталог [Artificial Analysis](https://artificialanalysis.ai/models/comparisons).
2. Остаются только числовые, независимо измеренные результаты. Предварительные оценки и записи без явного статуса измерения исключаются.
3. У OpenAI и Anthropic допускается **только xhigh**. У остальных разработчиков ограничений режима нет.
4. У Meta исключён релиз **Muse Wonder Full**: он [не доступен через публичный API](https://dev.meta.ai/docs/models). Используется измеренный результат обычной Muse Wonder. Это правило доступности; гипотеза, что Full представляет собой только мультиагентный harness, не считается установленным фактом.
5. По `creator.id` выбирается одна модель с максимальным исходным баллом.
6. На график попадают результаты **от 35 баллов включительно**. Отбор и сортировка выполняются до округления; подписи показывают два знака.

Страны и названия разработчиков берутся из самого источника. Количество компаний меняется с обновлением данных. Это сравнение достижений в одном индексе при указанных настройках; оно не утверждает равный вычислительный бюджет или доступность модели в определённой подписке. Название режима max само по себе не доказывает мультиагентность.

## Запуск

Нужен Python 3.10+; API-ключ не требуется.

```bash
git clone https://github.com/MetaWarlock/ai-fair-rating.git
cd ai-fair-rating
python -m venv .venv
```

Активировать окружение:

```powershell
# Windows PowerShell
.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Установить зависимости и построить свежий рейтинг:

```bash
python -m pip install -r skills/ai-fair-rating/requirements.txt
python skills/ai-fair-rating/scripts/rating.py --output output
```

В `output/` появятся:

| Файл | Содержимое |
| --- | --- |
| `rating.png` | График для публикации |
| `rating.svg` | Масштабируемая версия; контакты кликабельны |
| `rating.csv` | Модели, страны, точные баллы и ссылки |
| `metadata.json` | Дата получения данных, версия индекса, правила и проверка зазора флагов |
| `snapshot.json` | Исходный снимок для воспроизводимого построения |

Повторить построение без обновления данных AA:

```bash
python skills/ai-fair-rating/scripts/rating.py --snapshot output/snapshot.json --output output/replay
```

Дата исходного снимка сохраняется. Новые флаги при необходимости загружаются отдельно; уже используемые флаги входят в skill.

Необязательные параметры:

```bash
python skills/ai-fair-rating/scripts/rating.py --min-score 40 --telegram https://t.me/yourname --website https://example.com
```

## Использование как skill

Скопируйте целиком папку [`skills/ai-fair-rating`](skills/ai-fair-rating) в каталог skills своего AI-агента. В ней уже находятся инструкции, скрипт, зависимости и флаги; остальной репозиторий для работы skill не нужен.

Пример запроса:

> Используй $ai-fair-rating: получи свежие данные, построй рейтинг и покажи картинку.

Контакты автора стоят на графике по умолчанию и меняются параметрами командной строки. Перед публикацией агент проверяет картинку. Сам skill ничего не публикует и не создаёт расписаний.

## Структура

```text
AGENTS.md                 правила работы с проектом
README.md                 запуск и методология
LICENSE                   MIT для кода и инструкций
skills/ai-fair-rating/
  SKILL.md                инструкции агента
  agents/openai.yaml      метаданные skill
  requirements.txt        три зависимости
  scripts/rating.py       получение, отбор и график
  assets/flags/           флаги и их атрибуция
tests/test_rating.py      отбор, декодирование, воспроизводимость и зазор
examples/                 опубликованный пример с датой данных
```

Проверки:

```bash
python -m unittest discover -s tests -v
```

Если формат источника изменится, скрипт завершится с понятной ошибкой. Он не подменяет полный каталог несколькими изначально выбранными моделями и не использует старые данные без явного `--snapshot`.

## Источник и лицензии

Данные и методология: [Artificial Analysis](https://artificialanalysis.ai/methodology/intelligence-benchmarking). Содержимое источника не перелицензируется этим проектом; полный сырой каталог не входит в Git.

Код и инструкции: [MIT](LICENSE). Флаги: Twemoji 14.0.2, [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/), Twitter, Inc. and other contributors; [атрибуция](skills/ai-fair-rating/assets/flags/ATTRIBUTION.md).

AI Fair Rating is a reusable agent skill and CLI for a deduplicated Artificial Analysis developer ranking. One measured model per developer, xhigh-only for OpenAI/Anthropic, a minimum score of 35, and reproducible snapshots. The skill instructions are in English; chart labels and this guide are in Russian.
