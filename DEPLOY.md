# Деплой и релиз

## Порядок релиза (production)

Миграции — шаг развёртывания, а не действие рантайма: их выполняют одноразовые сервисы
`storefront-migrate` и `operations-migrate`, и остальные контейнеры стартуют только после того,
как те завершились с кодом 0. Запускать `manage.py migrate` внутри рабочего контейнера не нужно:
это второй путь миграции мимо развёртывания.

Все команды релиза идут через обёртку. Без `compose.prod.yaml` разворачивается dev-стек с его
монтированиями, а без явного `--env-file` Compose молча возьмёт `.env` из рабочей копии —
то есть подставит значения разработки туда, где нужны секреты production.

```bash
# the checks live inside dc(): a failing top-level `test` neither stops an interactive shell nor trips `set -e` inside an && list, so every call re-checks and refuses on its own
# run from the checkout root: compose.yaml is found there, and it is what counts as inside
dc() {
  : "${PROD_ENV_FILE:?set PROD_ENV_FILE to the production secrets file}"
  test -r "$PROD_ENV_FILE" || { echo "PROD_ENV_FILE is not readable" >&2; return 1; }
  local repo_root env_file
  repo_root="$(realpath .)"
  env_file="$(realpath "$PROD_ENV_FILE")"
  # resolved first, so neither a relative path nor a symlink leading back in passes for external
  case "$env_file" in
    "$repo_root"/*) echo "PROD_ENV_FILE must live outside the checkout" >&2; return 1 ;;
  esac
  # the resolved path, so a symlink swapped after the check cannot redirect compose
  docker compose --env-file "$env_file" -f compose.yaml -f compose.prod.yaml "$@"
}

# 1. применить миграции схемы обеим базам, до старта рантайма
dc up --exit-code-from storefront-migrate storefront-migrate
dc up --exit-code-from operations-migrate operations-migrate

# 2. поднять рантайм
dc up -d

# 3. обязательно наполнить/обновить каталог и остатки
dc exec backend python manage.py seed_menu
```

Процессы приложения работают под uid/gid 10001 с read-only корневой файловой системой, без
capabilities и с лимитами памяти и процессов. Статика собирается при сборке образа. Писать
можно только в tmpfs `/tmp` и, у backend, в `/tmp/prometheus` и том `media`.

Владельца тома `media` выставляет `media-init` перед стартом backend. Это порядок запуска, а не
восстановление: повторно он не запускается ни политикой перезапуска, ни сам по себе. Если в
том попали файлы root (восстановление из копии, запись с хоста), владельца возвращают явно:

```bash
dc run --rm --no-deps media-init
```

### Файл секретов

`PROD_ENV_FILE` указывает на обычный файл (не symlink) вне рабочей копии, в защищённом
каталоге, например `/etc/asian-restaurant/production.env`. Ни `.env`, ни любой другой файл внутри рабочей копии источником истины не является:
он содержит значения разработки и в production не используется. Значения-заглушки из
`.env.example` приложение отвергает при старте — процесс не поднимется, а не поднимется тихо
с чужим секретом.

`dc()` передаёт Compose уже разрешённый путь, поэтому подмена symlink после проверки ничего не
даёт. От подмены самого файла между проверкой и чтением проверка не защищает: это задача прав.
Каталог и файл доступны только root и deploy-пользователю (здесь его группа `deploy`):

```bash
sudo install -d -o root -g deploy -m 0750 /etc/asian-restaurant
sudo chown root:deploy /etc/asian-restaurant/production.env
sudo chmod 0640 /etc/asian-restaurant/production.env
```

### Ключ подписи

Docker secret из файла монтируется в контейнер с владельцем и правами файла на хосте, а процессы
приложения работают под uid/gid 10001. Ключ читает группа 10001 и больше никто, кроме root:

```bash
sudo chown root:10001 /etc/asian-restaurant/identity_jwt_private_key.pem
sudo chmod 0440 /etc/asian-restaurant/identity_jwt_private_key.pem
```

Без этого backend не поднимется: production-проверка настроек требует читаемый
`IDENTITY_JWT_PRIVATE_KEY_FILE`. Gid 10001 на хосте не должен принадлежать группе с
участниками: они получат чтение ключа.

### Если рантайм не стартует

Сервисы ждут `Exited (0)` от своих одноразовых шагов, поэтому упавшая миграция или
`media-init` выглядят как незапустившийся стек:

```bash
dc ps --all
dc logs storefront-migrate operations-migrate media-init
```

### Почему seed_menu обязателен

Миграция `menu/0002` добавляет `Product.stock_quantity` со значением по умолчанию
`0`. Товар с `stock_quantity = 0` считается недоступным (`available = false`) и
не отдаётся в меню. `seed_menu` — идемпотентный upsert по `code`, который
проставляет реальные остатки (`DEFAULT_STOCK = 50`) и копирует изображения.

**Без шага `seed_menu` после `migrate` всё меню окажется недоступным.** Шаг
безопасно повторять: существующие товары обновляются, ничего не удаляется.

## TLS и обязательные требования к ingress

Стек не терминирует TLS. Production-рендер публикует nginx **только на loopback**
(`127.0.0.1:80`), а `DJANGO_SSL_REDIRECT` включён по умолчанию. Значит перед стеком обязан стоять
ingress, и он должен удовлетворять трём условиям — иначе приложение либо зациклится на редиректе,
либо потеряет различение клиентов:

1. **Терминировать TLS** и проксировать на `127.0.0.1:80`.
2. **Стирать клиентские `X-Forwarded-*`** и выставлять их сам. nginx внутри стека доверяет тому,
   что пришло от ingress, и не перезаписывает эти заголовки: `X-Forwarded-Proto` он пробрасывает,
   `X-Forwarded-For` дополняет. Доверие здесь безопасно ровно потому, что дотянуться до слушателя,
   кроме ingress, некому. Если ingress не стирает клиентские значения, клиент сможет объявить себя
   пришедшим по https и подделать адрес для rate limit.
3. **Выставлять `X-Forwarded-Proto: https`** для запросов, пришедших по TLS. Без этого Django
   считает запрос незащищённым и отвечает редиректом на тот же URL — бесконечно.

Проверить конфигурацию можно `bash scripts/check_prod_config.sh`: гейт падает, если появится
публикация порта за пределы loopback, если редирект выключат или если nginx снова начнёт
перезаписывать заголовки.

## Порядок выката штатных ролей

Роль едет из storefront в Operations через событие авторизации. Пока Operations не получил
роли, он авторизует по прежнему флагу, поэтому порядок шагов важен: обратный оставит
сотрудников без доступа.

1. Выкатить контракт, мост и Operations — они уже понимают `roles` и `roles_known`, но
   продолжают принимать события без ролей.
2. Выкатить storefront с новыми ролями.
3. `python manage.py emit_authz_state` — переотправит текущее состояние всех штатных
   пользователей. Версия при этом не меняется, и проекция дописывает роли к существующей
   записи; это единственное разрешённое обогащение на одной версии.
4. Дождаться пустых `orders.ops` и `operations.bridge.*`, затем проверить, что не осталось
   активных записей без ролей:

```bash
dc exec operations-api python manage.py shell -c "from operations.models import EmployeeAuthorization as E; print(E.objects.filter(role_active=True, roles_known=False).count())"
```

   Ноль означает, что каждому активному субъекту роль доставлена.
5. Выдержать максимальный TTL прежних JWT — токены, выпущенные до шага 2, несут старую роль.
6. Отдельным коммитом убрать совместимость: приём `restaurant_employee` в Operations и
   ветку авторизации по флагу при `roles_known=False`.

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
пересоздать контейнер: `dc up -d redis`.
