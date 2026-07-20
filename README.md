# Asian Restaurant

Сервис заказа паназиатской кухни: витрина с меню, серверная корзина, оформление
заказов с валидацией остатков и адреса, история заказов и интерфейс сотрудника.

## Стек

- **Backend:** Django 5.2, Django Ninja, PostgreSQL 16, Redis 7, RabbitMQ 3.13.
- **Frontend:** React 18, TypeScript, Vite, Tailwind CSS, TanStack Query, Zustand.
- **Инфраструктура:** Docker Compose, Prometheus, nginx (раздача SPA и прокси API).

## Архитектура

- **Меню** (`menu`) — каталог, остатки (`stock_quantity`), журнал изменений
  остатков (`StockAdjustment`).
- **Корзина** (`cart`) — серверная, в Redis. Атомарные операции через Lua
  (compare-and-set по версии), гостевая корзина по signed-cookie, слияние в
  пользовательскую при входе, сверка со стоком, fail-closed `503` при недоступности
  Redis.
- **Заказы** (`orders`) — checkout только для авторизованных: телефон из аккаунта,
  идемпотентность (`idempotency_key` и `(cart, version)`), `select_for_update` по
  остаткам, серверная проверка адреса (геокодер с кешем), запись заказа и
  transactional outbox в одной транзакции, стейт-машина статусов.
- **Сотрудник** (`employee`) — управление заказами, инвентарём и пользователями;
  доступ только для суперпользователя или группы `restaurant_employee`.

Публикация событий заказа в RabbitMQ идёт через transactional outbox
(`OrderOutbox`) с publisher confirms; consumer-runtime — на этапе Stage 5.

## Быстрый старт

```bash
# 1. окружение
cp .env.example .env            # заполнить секреты

# 2. поднять стек
docker compose up -d

# 3. миграции и каталог (обязательно, иначе остатки = 0)
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py seed_menu

# 4. администратор и первый сотрудник
docker compose exec backend python manage.py createsuperuser
docker compose exec backend python manage.py grant_employee <телефон>
```

- Витрина: `http://localhost` (nginx) или `http://localhost:5173` (Vite dev).
- API и Swagger: `http://localhost:8000/api/docs`.
- OpenAPI-схема: `http://localhost:8000/api/openapi.json`.

## Переменные окружения

Полный список — в [.env.example](.env.example). Ключевые:

| Переменная | Назначение |
|---|---|
| `DATABASE_URL` | подключение к PostgreSQL |
| `REDIS_URL` | кэш и rate-limit (db 1) |
| `CART_REDIS_URL` | серверная корзина (db 0) |
| `RABBITMQ_URL` | шина событий заказов |
| `RATELIMIT_TRUST_XFF` | доверять `X-Forwarded-For` (только за доверенным прокси) |
| `GEOCODER_*` | серверная проверка адреса доставки |

## API

Все ручки под префиксом `/api`.

| Группа | Назначение |
|---|---|
| `/auth` | регистрация, вход, `me`, CSRF |
| `/menu` | каталог и карточки товаров |
| `/cart` | серверная корзина (гость и пользователь) |
| `/orders` | checkout, история, проверка адреса |
| `/employee` | заказы, инвентарь, пользователи, роли (для сотрудников) |

## Роли и доступ сотрудника

Доступ к `/api/employee/*` имеет только суперпользователь или член группы
`restaurant_employee`. Флаг `is_staff` сам по себе доступа не даёт. Выдаёт и
отзывает роль только суперпользователь — через API (`POST
/api/employee/users/{id}/role`) или команду `grant_employee`; каждое изменение
пишется в `EmployeeRoleAudit`.

## Тесты

```bash
docker compose exec backend pytest
```

Тесты требуют PostgreSQL и Redis (поднимаются в стеке). Внешний геокодер в тестах
отключён; rate-limit и корзина изолированы.

## Структура

```
backend/
  accounts/   учётные записи, роль сотрудника, аудит
  menu/       каталог, остатки, StockAdjustment
  cart/       серверная корзина (Redis, Lua)
  orders/     checkout, заказы, геокодер, outbox, RabbitMQ
  employee/   API интерфейса сотрудника
  common/     rate-limit и общие утилиты
  config/     настройки, сборка API
frontend/
  src/api/    клиентские хуки (TanStack Query)
  src/pages/  экраны (home, menu, product, orders)
  src/components/, src/stores/
```

## Релиз

Порядок деплоя и обязательный шаг `seed_menu` — в [DEPLOY.md](DEPLOY.md).

### - [mailor](https://github.com/mailorq) — fullstack dev