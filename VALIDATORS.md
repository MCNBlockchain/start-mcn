# MCN Mainnet · новый валидатор

Для активации одного валидатора нужен депозит **10 000 MCN** и дополнительный баланс кошелька для комиссии. Инструкция создаёт один ключ с withdrawal credentials `0x02` и выбранной суммой от 10 000 до 100 000 MCN. Рабочая среда сервера — Ubuntu 24.04.

## 1. Запустите полный узел

Выполните [инструкцию полного узла](README.md), затем установите дополнительный клиент

```sh
cd "$HOME/start-mcn"
./install-clients --validator
./start wait
```

До успешного завершения `wait` оставьте подписание выключенным.

## 2. Создайте ключ на своём защищённом компьютере

Выберите адрес MCN, которым вы управляете, для возврата стейка и выплат. Адрес начинается с `0x` и содержит 40 шестнадцатеричных символов после префикса. Сохраните доступ к кошельку этого адреса.

На защищённом компьютере с Ubuntu 24.04 установите зависимости и генератор, пока есть интернет

```sh
sudo apt update
sudo apt install -y git python3 python3-venv ca-certificates
git clone https://github.com/MCNBlockchain/start-mcn.git
cd start-mcn
./setup-deposit
```

Отключите сеть на этом компьютере и выполните

```sh
./create-validator
```

Сумма запрашивается отдельно; значение по умолчанию — 10 000 MCN. Для нового ключа можно указать её явно:

```sh
./create-validator --amount 90500
```

Команда выше создаёт новый ключ. Если ключ уже создан, используйте раздел переподготовки ниже, чтобы сохранить его pubkey.


Интерактивный генератор попросит адрес вывода и пароль шифрования keystore. Он покажет мнемоническую фразу и попросит её повторить. Запишите фразу отдельно и сохраните пароль. Результаты находятся в `$HOME/mcn-validator/validator_keys/`.

- `keystore-*.json` содержит зашифрованный ключ подписи. На сервер передаётся этот файл.
- `deposit_data-*.json` содержит публичные поля и подпись депозита. Он нужен для следующего шага.
- Мнемоническая фраза восстанавливает ключ. Храните её офлайн вместе с защищённой резервной копией.

`create-validator` использует EthStaker Deposit CLI 1.3.0. Адаптер MCN задаёт домен сети, минимальную сумму и верхний предел суммы из `network/config.yaml`. Генерация фразы, вывод ключей и шифрование выполняются библиотекой EthStaker. [Исходный проект](https://github.com/ethstaker/ethstaker-deposit-cli/tree/v1.3.0)

## 3. Подготовьте депозит

На том же компьютере выведите поля из созданного JSON

```sh
./deposit-details "$HOME"/mcn-validator/validator_keys/deposit_data-*.json
```

Команда выводит адрес вывода, сумму и четыре поля для функции `deposit`. Запишите публичный ключ `pubkey` для поиска валидатора. Убедитесь, что адрес вывода принадлежит вам.

В браузере откройте кошелёк, добавьте сеть MCN и выберите её

| Поле кошелька | Значение |
| --- | --- |
| Название | MCN Mainnet |
| RPC | `https://rpc.mcnblockchain.com` |
| Chain ID | `2325` |
| Символ | `MCN` |
| Обозреватель | `https://mcnscan.org` |

Откройте [контракт депозита в MCNScan](https://mcnscan.org/address/0x00000000219ab540356cBB839Cbe05303d7705Fa?tab=write_contract), перейдите на вкладку записи контракта и подключите кошелёк. Найдите payable-функцию `deposit`.

| Поле формы | Что вставить |
| --- | --- |
| `pubkey` | Строку `pubkey` из `deposit-details` |
| `withdrawal_credentials` | Строку `withdrawal_credentials` |
| `signature` | Строку `signature` |
| `deposit_data_root` | Строку `deposit_data_root` |
| Отправляемая сумма, Value | Точное значение `Value (wei)` из `deposit-details`; для 10 000 MCN — `10000000000000000000000` |

Вставляйте в целочисленное поле `Send native MCN` значение `Value (wei)` без разделителей. Не умножайте готовую сумму wei повторно. В подтверждении кошелька сумма в MCN должна совпадать с `Value (MCN)`.

Все четыре строки должны включать `0x`. Перед подписью в кошельке сверьте сеть 2325, адрес контракта `0x00000000219ab540356cBB839Cbe05303d7705Fa` и сумму. Вызовите функцию и сохраните хеш транзакции. При задержке сначала проверьте этот хеш в MCNScan, чтобы повторным вызовом случайно не внести второй депозит.


## Изменение суммы до первого депозита

Сумма входит в BLS-подпись и SSZ-корни. Ручное изменение `amount` в JSON или только суммы в форме создаёт несоответствие. Если транзакция ещё не отправлена, переподготовьте публичные данные на защищённом офлайн-компьютере из существующего keystore:

```sh
./create-validator --amount 90500 \
  --from-keystore "$HOME"/mcn-validator/validator_keys/keystore-*.json \
  --deposit-data "$HOME"/mcn-validator/validator_keys/deposit_data-*.json \
  --output "$HOME/mcn-validator/deposit_data-90500.json"

./deposit-details "$HOME/mcn-validator/deposit_data-90500.json"
```

Если файлов несколько, укажите конкретные имена вместо `*`. Команда попросит повторить новую сумму и скрыто ввести пароль keystore. Pubkey и withdrawal credentials сохраняются; подпись и оба корня рассчитываются заново. Исходные JSON и keystore не изменяются, существующий выходной файл не перезаписывается.

Перенесите в форму все четыре поля из нового `deposit-details` и его `Value (wei)`. Для 90 500 MCN это `90500000000000000000000`. Не добавляйте множитель к уже готовому значению wei. В окне кошелька итоговая сумма должна быть **90 500 MCN** и должен отображаться ваш реальный отправитель.

Этот режим готовит полный депозит до первой отправки, а не доплату к уже внесённому. Если депозит уже включён в цепочку, сначала определите состояние валидатора и сумму требуемого пополнения.

## 4. Перенесите keystore на сервер

С компьютера, где создавались ключи, скопируйте зашифрованный keystore. Замените `USER@SERVER` на имя пользователя и адрес сервера, под которыми установлен узел

```sh
ssh USER@SERVER 'umask 077; mkdir -p "$HOME/mcn-validator/keystores"'
scp "$HOME"/mcn-validator/validator_keys/keystore-*.json USER@SERVER:mcn-validator/keystores/
```

На сервере из каталога `start-mcn` создайте пароль кошелька Prysm. Это отдельный пароль хранения импортированных ключей. Команда запросит его скрытым вводом дважды

```sh
python3 - <<'PY'
from pathlib import Path
import getpass
import os
folder = Path.home() / "mcn-validator"
folder.mkdir(mode=0o700, exist_ok=True)
password = getpass.getpass("Новый пароль кошелька Prysm: ")
confirmation = getpass.getpass("Повторите пароль: ")
if len(password) < 12 or password != confirmation:
    raise SystemExit("Пароли должны совпадать и содержать минимум 12 символов.")
fd = os.open(folder / "wallet-password.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w") as output:
    output.write(password + "\n")
PY
./bin/validator accounts import \
  --keys-dir="$HOME/mcn-validator/keystores" \
  --wallet-dir="$HOME/mcn-validator/wallet" \
  --wallet-password-file="$HOME/mcn-validator/wallet-password.txt"
```

При импорте введите пароль keystore из шага 2. Посмотрите публичные ключи в кошельке и сверьте их с `pubkey` депозита

```sh
./bin/validator accounts list \
  --wallet-dir="$HOME/mcn-validator/wallet" \
  --wallet-password-file="$HOME/mcn-validator/wallet-password.txt"
```

## 5. Запустите подписание

Выберите адрес получения комиссий за предложенные блоки. Можно использовать тот же адрес, что выбран для вывода. Замените `YOUR_MCN_ADDRESS` на свой адрес

```sh
./run-validator --fee-recipient YOUR_MCN_ADDRESS
```

Команда ожидает готовности полного узла и запускает Prysm Validator в текущем терминале. Если ключ ещё в очереди активации, клиент ожидает обязанностей.

Для работы после закрытия SSH остановите этот процесс через `Ctrl+C` и создайте службу. В `ExecStart` также укажите свой адрес

```sh
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/mcn-validator.service" <<'UNIT'
[Unit]
Description=MCN Mainnet validator
Requires=mcn-node.service
After=mcn-node.service

[Service]
Type=simple
WorkingDirectory=%h/start-mcn
ExecStart=%h/start-mcn/run-validator --fee-recipient YOUR_MCN_ADDRESS
Restart=on-failure
RestartSec=30
TimeoutStopSec=300
UMask=0077

[Install]
WantedBy=default.target
UNIT
```

Откройте файл `$HOME/.config/systemd/user/mcn-validator.service` в редакторе и замените `YOUR_MCN_ADDRESS`. Затем выполните

```sh
systemctl --user daemon-reload
systemctl --user enable --now mcn-validator
journalctl --user -u mcn-validator -n 50 --no-pager
```

## 6. Проверьте активацию

Откройте [Beacon Explorer](https://beacon.mcnscan.org), вставьте `pubkey` в поиск и посмотрите статус валидатора. При `pending` ожидайте очереди. При `active` контролируйте включение аттестаций и журнал клиента. Если транзакция успешна, но ключ долго отсутствует в консенсусе, сохраните хеш депозита и публичный ключ для диагностики.

## Перенос действующего валидатора

Для существующего ключа используйте его keystore и историю защиты от слэшинга. Остановите прежнюю службу, экспортируйте историю на прежнем сервере и импортируйте её на новом до первого подписания. Каталог `$HOME/mcn-validator/data` содержит эту историю. Один публичный ключ должен обслуживаться одним активным клиентом подписи. [Команды переноса Prysm](https://prysm.offchainlabs.com/docs/validators/slashing-protection-history/)
