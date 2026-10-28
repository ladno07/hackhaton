# Интеграции (Д2)

Внешние системы (сайт федерации, система проведения олимпиад, учётные системы
Минспорта) получают данные платформы через API по токену, узнают о событиях
через вебхуки и загружают результаты соревнований импортом.

Управление — кабинет федерации (`admin`) → «Интеграции». Схема всех запросов —
Swagger http://localhost:8080/docs (раздел «API для внешних систем») и
[openapi.json](openapi.json).

## Токены доступа

Токен выпускает сотрудник федерации и отмечает права:

| Право | Что разрешает |
| --- | --- |
| `competitions:read` | Календарь соревнований без черновиков |
| `applications:read` | Одобренные заявки участников соревнования |
| `results:read` | Опубликованные протоколы |
| `results:write` | Импорт результатов: публикация протокола и новые редакции |

- Токен вида `ock_…` показывается один раз; в базе хранится только SHA-256.
  В списке видны префикс, права, автор, срок и время последнего запроса.
- Срок действия необязателен. Отозванный или истёкший токен сразу перестаёт
  работать (401).
- Токен действует от имени выпустившего сотрудника и только пока у него есть
  роль федерации. Кабинет Минспорта токены не выпускает.
- Токен принимается только адресами `/api/v1/…`, а сессионный JWT сайта — только
  адресами кабинета: одно нельзя подменить другим.
- Выпуск, отзыв и каждый импорт через API пишутся в журнал действий (роль
  `api`, название и id токена).

```bash
curl -H "Authorization: Bearer ock_…" "http://localhost:8080/api/v1/competitions?state=open"
```

| Метод | Адрес | Право |
| --- | --- | --- |
| GET | `/api/v1/me` | любое |
| GET | `/api/v1/competitions?state=&from=&to=` | `competitions:read` |
| GET | `/api/v1/competitions/{id}` | `competitions:read` |
| GET | `/api/v1/competitions/{id}/applications` | `applications:read` |
| GET | `/api/v1/competitions/{id}/protocol` | `results:read` |
| POST | `/api/v1/competitions/{id}/results?dry_run=` | `results:write` |
| POST | `/api/v1/competitions/{id}/results.csv?dry_run=&reason=` | `results:write` |

Спортсмен во всех ответах обозначается публичным ID `FSP-000123`; дата
рождения и контакты не передаются. Коды ошибок: 401 — нет токена, он отозван
или истёк; 403 — у токена нет права; 404 — соревнование не найдено (черновики
скрыты) или протокол не опубликован; 409/422 — данные не прошли проверку,
причина в `detail`.

## Вебхуки

Вебхук — адрес, на который платформа отправляет POST с JSON при событии:

| Событие | Когда |
| --- | --- |
| `competition.published` | Соревнование вышло из черновика (один раз; повторное открытие регистрации не считается) |
| `application.approved` | Одобрена заявка спортсмена; для командной заявки — по событию на каждого участника |
| `protocol.published` | Опубликован протокол или его новая редакция (исправление, апелляция, импорт) |
| `ping` | Кнопка «Проверить» |

```http
POST /webhook HTTP/1.1
Content-Type: application/json; charset=utf-8
X-OrenCode-Event: protocol.published
X-OrenCode-Delivery: 42
X-OrenCode-Timestamp: 1767225600
X-OrenCode-Signature: sha256=5f0c…

{"id": "protocol.published:12:v2", "event": "protocol.published",
 "occurred_at": "2026-10-28T09:00:00+00:00",
 "data": {"competition": {...}, "version": 2, "reason": "…", "results": [...]}}
```

- **Подпись.** `HMAC-SHA256(secret, timestamp + "." + body)`. Секрет `whsec_…`
  показывается при создании вебхука и при смене секрета.

  ```python
  import hashlib, hmac

  def verify(secret: str, headers, body: bytes) -> bool:
      signed = headers["X-OrenCode-Timestamp"].encode() + b"." + body
      expected = "sha256=" + hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
      return hmac.compare_digest(expected, headers["X-OrenCode-Signature"])
  ```

- **Надёжность.** Событие пишется в таблицу `webhook_deliveries` в той же
  транзакции, что и само действие (outbox): откат действия — нет события.
  Worker уведомлений раз в минуту отправляет очередь. Ответ 2xx — доставлено;
  иначе повтор через 1, 5, 15, 60 и 240 минут, после шестой попытки — «Ошибка».
  В журнале доставки видны код ответа, текст ошибки, тело запроса и кнопка
  «Отправить снова».
- **Повторы.** Поле `id` уникально для события и не меняется между попытками —
  получатель по нему отбрасывает дубли.
- **Безопасность.** Адреса localhost и внутренних сетей (10/8, 192.168/16,
  127/8, link-local и т. п.) отклоняются при сохранении и повторно проверяются
  после DNS-разрешения перед каждой отправкой; редиректы не выполняются. Для
  локальной отладки можно включить `WEBHOOK_ALLOW_PRIVATE=true`.
- Выключенный вебхук не получает новых событий, накопленные ждут включения.

## Импорт результатов

Источник — CSV (из кабинета или `results.csv` в API) или JSON (API).

```csv
athlete;place;score
FSP-000001;1;95,5
FSP-000002;2;80
```

- Разделитель `;`, `,` или табуляция, кодировка UTF-8 или Windows-1251, дробные
  баллы через точку или запятую. Заголовки: `athlete` (или `Спортсмен`,
  `athlete_id`) — ID `FSP-000123` или внутренний номер; `team` (`Команда`) — id
  или название допущенной команды для командного зачёта; `place` (`Место`);
  `score` (`Баллы`). Размер — до 2 МБ.
- JSON: `{"results": [{"athlete": "FSP-000001", "place": 1, "score": 95.5}], "reason": null}`.
- Проверки те же, что при ручной публикации: все одобренные участники ровно по
  одному разу, места по правилу «1, 1, 3», в команде одинаковые место и баллы.
  Ошибки возвращаются списком с номерами строк и ID спортсменов.
- `dry_run` проверяет файл и возвращает протокол в том виде, как он будет
  опубликован, ничего не сохраняя. В кабинете сначала всегда выполняется
  проверка, и только потом доступна публикация.
- Первый импорт публикует протокол (соревнование завершено, приём заявок
  закрыт). Если протокол уже опубликован, импорт создаёт новую редакцию и
  требует основание `reason`. Дальше всё как при ручной публикации:
  уведомления участникам и тренерам, пересчёт рейтинга, история редакций,
  событие `protocol.published`.

## Где в коде

| Что | Где |
| --- | --- |
| Модели `ApiToken`, `Webhook`, `WebhookDelivery` | [backend/app/models/__init__.py](../backend/app/models/__init__.py), миграция `0019_integrations` |
| Права токенов, outbox, подпись, отправка, разбор CSV | [backend/app/services/integrations.py](../backend/app/services/integrations.py) |
| Управление и API `/api/v1` | [backend/app/routers/integrations.py](../backend/app/routers/integrations.py) |
| Точки генерации событий | `set_state`, `moderate`, `publish_results`, `apply_correction` в [competitions.py](../backend/app/routers/competitions.py); `review` в [competition_teams.py](../backend/app/routers/competition_teams.py) |
| Интерфейс | [frontend/src/integrations.tsx](../frontend/src/integrations.tsx) |
| Тесты | [backend/tests/test_integrations.py](../backend/tests/test_integrations.py) |
