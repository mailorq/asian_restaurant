# Деплой и релиз

## Порядок релиза (production)

```bash
# 1. применить миграции схемы
python manage.py migrate --noinput

# 2. обязательно наполнить/обновить каталог и остатки
python manage.py seed_menu

# 3. собрать статику (если нужно)
python manage.py collectstatic --noinput
```

### Почему seed_menu обязателен

Миграция `menu/0002` добавляет `Product.stock_quantity` со значением по умолчанию
`0`. Товар с `stock_quantity = 0` считается недоступным (`available = false`) и
не отдаётся в меню. `seed_menu` — идемпотентный upsert по `code`, который
проставляет реальные остатки (`DEFAULT_STOCK = 50`) и копирует изображения.

**Без шага `seed_menu` после `migrate` всё меню окажется недоступным.** Шаг
безопасно повторять: существующие товары обновляются, ничего не удаляется.

## Переменные окружения

Все ключи описаны в [.env.example](.env.example). Значимые для этого этапа:

| Переменная | Назначение | Прод |
|---|---|---|
| `CART_REDIS_URL` | серверная корзина (отдельная redis-db от кэша) | `redis://redis:6379/0` |
| `RATELIMIT_TRUST_XFF` | доверять `X-Forwarded-For` в rate-limit | `true` **только** за прокси, который очищает и переустанавливает заголовок; иначе `false` |

## Redis

Корзина требует персистентности и отказа от вытеснения ключей. В
[compose.yaml](compose.yaml) redis запускается с `--appendonly yes
--maxmemory-policy noeviction` и томом `redis_data`. При изменении команды redis
пересоздать контейнер: `docker compose up -d redis`.
