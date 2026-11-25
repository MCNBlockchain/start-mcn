# Релизы клиентов

Версии клиентов заданы в `network/identity.json`.

- [Geth 1.17.10](https://github.com/ethereum/go-ethereum/releases/tag/v1.17.10)
- [Prysm Beacon Chain 7.3.1](https://github.com/OffchainLabs/prysm/releases/tag/v7.3.1)

Генератор депозитов использует [EthStaker Deposit CLI 1.3.0](https://github.com/ethstaker/ethstaker-deposit-cli/tree/v1.3.0). SHA-256 исходного архива закреплён в `tools/deposit-requirements.txt`. Адаптер `tools/deposit.py` задаёт параметры сети MCN и предел суммы депозита.
