# Checkpoint-sync MCN Mainnet

Источник checkpoint — синхронизированный Prysm на RPC-сервере MCN. Новая beacon-нода получает финализированное состояние и соответствующий блок через HTTPS Beacon API. Geth выполняет собственную загрузку исполнения. Checkpoint используется при создании новой базы Prysm.

## Запуск новой ноды

После установки клиентов из каталога `start-mcn` выполните

```sh
./start
./start logs
./start wait
```

В журнале Prysm появится `Downloaded checkpoint sync state and block`. Начальный `head_slot` будет близок к финализированной точке сети. Клиент догружает оставшиеся блоки и проверяет исполнение. Готовность узла определяется через `./start wait`.

По умолчанию используется `https://rpc.mcnblockchain.com`. Для другого доверенного источника задайте его URL через `MCN_CHECKPOINT_URL`. В службе systemd переменная сохраняется в drop-in

```sh
mkdir -p "$HOME/.config/systemd/user/mcn-node.service.d"
cat > "$HOME/.config/systemd/user/mcn-node.service.d/checkpoint.conf" <<'UNIT'
[Service]
Environment=MCN_CHECKPOINT_URL=https://rpc.mcnblockchain.com
UNIT
systemctl --user daemon-reload
```

Уже созданная база Prysm используется при следующем запуске. Чтобы на новой базе загружать историю от genesis, задайте пустую переменную `MCN_CHECKPOINT_URL=`. Источник должен принадлежать MCN Mainnet, быть синхронизированным, иметь финализированную точку и завершённую проверку исполнения.

## Проверка источника

```sh
curl -fsS https://rpc.mcnblockchain.com/eth/v1/beacon/genesis | jq .data
curl -fsS https://rpc.mcnblockchain.com/eth/v1/node/syncing | jq .data
curl -fsS https://rpc.mcnblockchain.com/eth/v1/beacon/states/head/finality_checkpoints | jq .data.finalized
```

Genesis validators root MCN Mainnet — `0x6d7b05bfda475be67119697fe38000be692cbff0cbd78890eae8d40823e0cf91`, версия genesis fork — `0x23251200`. При настройке доверия сверяйте финализированный root на одной и той же эпохе с другим доверенным узлом MCN.

## Публикация Beacon API

Prysm слушает локальный REST API `127.0.0.1:3500`. HTTPS-прокси выдаёт только GET-маршруты идентичности сети, статуса, финальности, финализированного состояния SSZ и блоков. Ограничены частота запросов и число соединений на адрес.

| Данные | Путь |
| --- | --- |
| Идентичность сети | `/eth/v1/beacon/genesis` |
| Готовность источника | `/eth/v1/node/syncing` |
| Финализированная точка | `/eth/v1/beacon/states/head/finality_checkpoints` |
| Параметры сети | `/eth/v1/config/spec` |
| Финализированное состояние SSZ | `/eth/v2/debug/beacon/states/finalized` |
| Блок SSZ | `/eth/v2/beacon/blocks/{slot_or_root}` |

[Checkpoint-sync в Prysm](https://prysm.offchainlabs.com/docs/setup/checkpoint-sync/)
