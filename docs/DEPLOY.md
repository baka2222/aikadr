# Запуск на VPS

Сайт — `/`, кабинет авторов и администрации — `/admin`. Нужны Docker Engine с Compose, домен с A-записью на VPS, доступные входящие порты 80/443, настоящий SMTP-отправитель. На VPS с 1 ядром и 3 ГБ RAM сборка Next.js может потребовать дополнительного swap; по возможности собирайте образы заранее на рабочем компьютере/CI.

## 1. Настройки и первая загрузка

Перенесите проект, создайте `.env` по `.env.example`. Задайте случайные `POSTGRES_PASSWORD`, `SESSION_SECRET` (не менее 32 символов), `ADMIN_PASSWORD` (не менее 12 символов). Для пароля PostgreSQL используйте URL-безопасные буквы/цифры/дефисы, поскольку он включён в `DATABASE_URL`. Укажите настоящий `ADMIN_EMAIL` и заполните SMTP по [SMTP.md](SMTP.md). Установите `APP_ENV=production`, `SECURE_COOKIES=true`, `HOST_PORT=80`; уберите `dev-mail` из `COMPOSE_PROFILES`.

Далее команды предполагают расположение проекта `/opt/aikadr`. Если выбрали другую папку, замените этот путь во всех командах и хуке продления сертификата.

```bash
cd /opt/aikadr
chmod 600 .env
mkdir -p certbot-www
docker compose up --build -d
docker compose ps
```

Пока HTTPS не включён, вход по HTTP не сохранит защищённую cookie. Сначала получите сертификат.

## 2. HTTPS на Nginx

В конфигурации уже подготовлен webroot для проверки домена. Замените `your-domain.example` на ваш домен, направленный на VPS:

```bash
sudo apt-get update
sudo apt-get install -y certbot
sudo certbot certonly --webroot -w /opt/aikadr/certbot-www --cert-name aikadr -d your-domain.example
docker compose -f docker-compose.yml -f docker-compose.production.yml up -d
docker compose exec nginx nginx -t
```

Certbot запросит контактный email и согласие с условиями. Сертификат с именем `aikadr` ожидается в `/etc/letsencrypt/live/aikadr/`. Production-конфигурация перенаправляет HTTP на HTTPS, кроме проверки сертификата. Теперь открывайте `https://your-domain.example/admin`.

Для применения обновлённого сертификата создайте `/etc/letsencrypt/renewal-hooks/deploy/aikadr-reload`:

```sh
#!/bin/sh
cd /opt/aikadr || exit 1
docker compose -f docker-compose.yml -f docker-compose.production.yml exec -T nginx nginx -s reload
```

```bash
sudo chmod 755 /etc/letsencrypt/renewal-hooks/deploy/aikadr-reload
sudo systemctl enable --now certbot.timer
sudo certbot renew --dry-run
```

Порт 80 нужен и для последующих проверок. Инструкции соответствуют [официальному webroot-режиму Certbot](https://eff-certbot.readthedocs.io/en/stable/using.html#webroot); получение настоящего сертификата проверяется уже на вашем домене/VPS.

## 3. Первое наполнение

1. Войдите с `ADMIN_EMAIL` и паролем владельца: для студии код из письма не требуется.
2. «Оформление»: загрузите фон, выберите тему, отредактируйте тексты и логотип. Сохраните, затем обновите главную.
3. «Пользователи»: создайте авторов, модераторов, при необходимости дополнительных супер-администраторов. Временные пароли передайте лично; действующий email понадобится для самостоятельного восстановления пароля.
4. Автор создаёт сериал → эпизод → загружает видео → проверяет воспроизведение → публикует сериал. Каталог показывает опубликованные сериалы хотя бы с одним готовым видео. Пустые записи остаются в студии.
5. «Тарифы»: создайте настоящие тарифы и сохраните реквизиты. До заполнения данных продажа подписок не открывается.
6. Проверьте регистрацию, письмо, бесплатный эпизод, оплату с чеком и доступ после ручного подтверждения.

Ссылки на `/admin` нет в публичной навигации. Это удобство интерфейса; права на все административные действия дополнительно проверяет API.

## Обновления и резервная копия

Перед обновлением сохраните базу с видео:

```bash
docker compose exec -T postgres pg_dump -U kadr -Fc -b -f /tmp/aikadr.dump kadr
docker compose cp postgres:/tmp/aikadr.dump ./aikadr-backup.dump
docker compose -f docker-compose.yml -f docker-compose.production.yml up --build -d
```

Копию переносите с VPS на другой диск/машину. Отдельно сохраняйте volume `kadr_data` с обложками, `.env` и сертификаты в защищённом месте. Восстановление сначала проверяйте на отдельной базе. `docker compose down -v` удалит данные — для обновлений эта команда не нужна.

Видео занимают PostgreSQL Large Objects; резервная копия `pg_dump -b` включает их. При загрузке нужны место под временный файл, новую версию видео и WAL. Ограничение файла — 2 ГБ, оно не резервирует свободное место на диске. На сервере с диском 40 ГБ начните с небольших оптимизированных MP4, следите за свободным местом и выносите резервные копии с сервера.

Перекодирование на VPS не выполняется. Для широкой совместимости подготовьте MP4 H.264/AAC с `faststart` на компьютере автора, затем загрузите готовый файл. `faststart` переносит индекс MP4 в начало, поэтому воспроизведение может начаться до загрузки целого файла. Автоматического переключения качества/HLS и CDN в этой версии нет.

Telegram по желанию: заполните три поля `TELEGRAM_*`, добавьте `COMPOSE_PROFILES=telegram`, повторите production-команду запуска. Без бота оплаты доступны в студии.
