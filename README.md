# MCN Mainnet · полный узел

Это руководство рассчитано на Ubuntu 24.04 и обычную учётную запись с доступом к `sudo`. Для полного узла работают два клиента — Geth исполняет транзакции, Prysm Beacon Chain ведёт консенсус. Для подписания блоков и аттестаций после подготовки узла переходите к [руководству валидатора](VALIDATORS.md).

## 1. Подготовьте сервер

Войдите на сервер по SSH и установите зависимости

```sh
sudo apt update
sudo apt install -y git python3 python3-venv ca-certificates curl jq
timedatectl status
```

В выводе времени строка `System clock synchronized` должна показывать `yes`. Используйте SSD и контролируйте свободное место через `df -h`.

## 2. Скачайте конфигурацию и установите клиенты

```sh
cd "$HOME"
git clone https://github.com/MCNBlockchain/start-mcn.git
cd "$HOME/start-mcn"
./install-clients
```

Скрипт определяет Linux x86_64 или ARM64, скачивает Geth 1.17.10 и Prysm Beacon Chain 7.3.1 из закреплённых релизов и сохраняет исполняемые файлы в `bin/`. Для установки клиента валидатора используйте `./install-clients --validator`. Установщик сверяет скачанные файлы с контрольными суммами из `tools/clients.json`.

Если клиенты уже установлены отдельно, укажите их пути через `MCN_GETH` и `MCN_BEACON` вместо установки в `bin/`. [Релизы клиентов](SOURCES.md)

## 3. Запустите узел

```sh
./start
./start status
```

Узел продолжает работать после закрытия SSH. При первой загрузке статус показывает подготовку базы Geth, затем состояние обоих клиентов. Geth использует финализированный хеш из публичного RPC MCN как цель и получает данные от пиров. Prysm загружает историю консенсуса. Длительность зависит от сети, SSD и доступности пиров.

```sh
./start logs
./start wait
```

`wait` завершается с сообщением `Node ready.`, когда оба клиента готовы и финальность продвигается. Пока Prysm показывает `is_syncing: true`, загрузка истории продолжается. Если `wait` завершился по таймауту, посмотрите журналы, состояние клиентов и снова выполните команду. Данные сохраняются.

## 4. Включите запуск после перезагрузки

Остановите узел перед передачей управления systemd

```sh
cd "$HOME/start-mcn"
./start stop
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/mcn-node.service" <<'UNIT'
[Unit]
Description=MCN Mainnet full node
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
WorkingDirectory=%h/start-mcn
ExecStart=%h/start-mcn/start foreground
Restart=on-failure
RestartSec=10
TimeoutStopSec=300
UMask=0077

[Install]
WantedBy=default.target
UNIT
sudo loginctl enable-linger "$USER"
systemctl --user daemon-reload
systemctl --user enable --now mcn-node
```

После этого управляйте узлом через `systemctl --user restart mcn-node` и `systemctl --user stop mcn-node`. Для диагностики используйте `./start status`, `./start logs` и `journalctl --user -u mcn-node -n 50 --no-pager`.

## Сеть и данные

Разрешите исходящие подключения к пирам и HTTPS. Для входящих P2P-соединений откройте TCP/UDP 30303 для Geth, TCP/UDP 13000 и UDP 12000 для Prysm в firewall сервера и панели провайдера. При настройке firewall сохраните доступ по SSH.

| Локальный интерфейс | Адрес |
| --- | --- |
| JSON-RPC MCN, Chain ID 2325 | `http://127.0.0.1:8545` |
| Engine API с JWT | `http://127.0.0.1:8551` |
| Beacon REST API | `http://127.0.0.1:3500` |
| Beacon gRPC для валидатора | `127.0.0.1:4000` |

Базы и журналы находятся в `.mcn-data/`. Сохраните этот каталог при обновлении. При использовании `MCN_DATA_DIR` задавайте одинаковое значение во всех командах и в настройках службы.
