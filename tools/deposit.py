"""MCN settings adapter for EthStaker Deposit CLI 1.3.0."""
import argparse
from decimal import Decimal
import getpass
import importlib.metadata
import json
import os
from pathlib import Path
import re
import runpy
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / ".tools/ethstaker"))


def network_settings():
    node = runpy.run_path(str(ROOT / "mcn-node"), run_name="mcn_config")
    node["verify_bundle"]()
    values = {}
    for line in (ROOT / "network/config.yaml").read_text().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key] = value.strip().strip('"')
    identity = node["IDENTITY"]
    return identity, values


def configure_upstream(identity, values):
    if importlib.metadata.version("ethstaker_deposit") != "1.3.0":
        raise ValueError("EthStaker Deposit CLI 1.3.0 required. Run ./setup-deposit.")
    from ethstaker_deposit import credentials
    from ethstaker_deposit.utils import constants, validation
    # The upstream CLI's Ethereum amount cap is also imported by value into
    # these modules. MCN uses the same SSZ/signing format with a larger cap.
    maximum = int(values["MAX_EFFECTIVE_BALANCE_ELECTRA"])
    constants.MAX_DEPOSIT_AMOUNT = maximum
    credentials.MAX_DEPOSIT_AMOUNT = maximum
    validation.MAX_DEPOSIT_AMOUNT = maximum
    return {
        "network_name": "mcn",
        "genesis_fork_version": identity["genesis_fork_version"],
        "exit_fork_version": values["CAPELLA_FORK_VERSION"],
        "genesis_validator_root": identity["genesis_validators_root"],
        "min_activation_amount": int(values["MIN_ACTIVATION_BALANCE"]) / 10**9,
        "min_deposit_amount": int(values["MIN_DEPOSIT_AMOUNT"]) / 10**9,
    }


def deposit_amount(text, values):
    text = text.strip()
    if not re.fullmatch(r"[0-9]{1,12}(?:\.[0-9]{1,9})?", text):
        raise ValueError("Введите сумму MCN числом без пробелов, с точностью не более 9 знаков.")
    amount = int(Decimal(text) * 10**9)
    minimum = int(values["MIN_ACTIVATION_BALANCE"])
    maximum = int(values["MAX_EFFECTIVE_BALANCE_ELECTRA"])
    if not minimum <= amount <= maximum:
        raise ValueError(f"Для нового валидатора укажите от {minimum // 10**9} до {maximum // 10**9} MCN.")
    return amount


def choose_amount(text, values):
    if text is None:
        default = str(int(values["MIN_ACTIVATION_BALANCE"]) // 10**9)
        text = input(f"Сумма депозита в MCN [{default}]: ").strip() or default
    amount = deposit_amount(text, values)
    print(f"Сумма депозита: {Decimal(amount) / 10**9} MCN")
    return amount


def create(identity, values, amount):
    settings = configure_upstream(identity, values)
    import ethstaker_deposit
    os.chdir(Path(ethstaker_deposit.__file__).resolve().parents[1])
    from ethstaker_deposit.deposit import cli
    from eth_utils import is_checksum_address
    address = input("Адрес вывода MCN (0x…): ").strip()
    if not is_checksum_address(address) or int(address[2:], 16) == 0:
        raise ValueError("Скопируйте ненулевой адрес вывода из кошелька с контрольным регистром.")
    if input("Повторите адрес вывода: ").strip() != address:
        raise ValueError("Адреса вывода должны совпадать.")
    folder = Path.home() / "mcn-validator"
    output = folder / "validator_keys"
    if output.exists():
        raise ValueError(f"{output} already exists. Keep the existing keys and backup.")
    os.umask(0o077)
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    cli.main(args=[
        "--language", "English", "new-mnemonic",
        "--num_validators", "1", "--mnemonic_language", "english",
        "--folder", str(folder), "--withdrawal_address", address, "--compounding",
        "--amount", format(Decimal(amount) / 10**9, "f"),
        "--devnet_chain_setting", json.dumps(settings, separators=(",", ":")),
    ], standalone_mode=False)


def checked_deposit(path, identity, values):
    from ethstaker_deposit.settings import get_devnet_chain_setting
    from ethstaker_deposit.utils.validation import validate_deposit
    settings = configure_upstream(identity, values)
    deposits = json.loads(path.read_text())
    if not isinstance(deposits, list) or len(deposits) != 1:
        raise ValueError("Expected one validator in the deposit JSON.")
    item = deposits[0]
    if item.get("fork_version") != identity["genesis_fork_version"][2:]:
        raise ValueError("Deposit signature belongs to another network.")
    chain = get_devnet_chain_setting(**settings)
    if type(item.get("amount")) is not int or not validate_deposit(item, chain):
        raise ValueError("Invalid deposit signature or data root.")
    credentials = bytes.fromhex(item["withdrawal_credentials"])
    if len(credentials) != 32 or credentials[:12] != b"\x02" + bytes(11):
        raise ValueError("Expected compounding withdrawal credentials (0x02).")
    deposit_amount(format(Decimal(item["amount"]) / 10**9, "f"), values)
    return item


def details(path, identity, values):
    item = checked_deposit(path, identity, values)
    credentials = bytes.fromhex(item["withdrawal_credentials"])
    amount = Decimal(item["amount"]) / 10**9
    print(f"Network: MCN Mainnet (Chain ID {identity['chain_id']})")
    print(f"Contract: {values['DEPOSIT_CONTRACT_ADDRESS']}")
    print(f"pubkey (validator): 0x{item['pubkey']}")
    print(f"Withdrawal address: 0x{credentials[12:].hex()}")
    print(f"Value (MCN): {amount}")
    print(f"Value (wei): {item['amount'] * 10**9}")
    for key in ("pubkey", "withdrawal_credentials", "signature", "deposit_data_root"):
        print(f"{key}: 0x{item[key]}")
    print("Submit the deposit once. Record its transaction hash before retrying.")


def rebuild(args, identity, values, amount):
    from ethstaker_deposit.key_handling.keystore import Keystore
    from ethstaker_deposit.settings import get_devnet_chain_setting
    from ethstaker_deposit.utils.ssz import (
        DepositData, DepositMessage, compute_deposit_domain, compute_signing_root,
    )
    from ethstaker_deposit.utils.validation import validate_deposit
    from py_ecc.bls import G2ProofOfPossession as bls

    original = checked_deposit(args.deposit_data, identity, values)
    output = args.output.expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise ValueError(f"Выходной файл уже существует: {output}")
    keystore = Keystore.from_file(str(args.from_keystore.expanduser()))
    keystore_pubkey = keystore.pubkey.lower()
    if keystore_pubkey.startswith("0x"):
        keystore_pubkey = keystore_pubkey[2:]
    if keystore_pubkey != original["pubkey"]:
        raise ValueError("Keystore не соответствует pubkey исходного депозита.")

    print(f"Validator pubkey: 0x{original['pubkey']}")
    print(f"Withdrawal address: 0x{original['withdrawal_credentials'][24:]}")
    print(f"New deposit: {Decimal(amount) / 10**9} MCN")
    print("Это новая сумма полного депозита, а не доплата к уже отправленному.")
    confirmation = input("Повторите новую сумму в MCN: ")
    if deposit_amount(confirmation, values) != amount:
        raise ValueError("Суммы не совпадают. Файл не создан.")
    password = getpass.getpass("Пароль существующего keystore: ")
    secret_bytes = keystore.decrypt(password)
    signing_key = int.from_bytes(secret_bytes, "big")
    pubkey = bls.SkToPk(signing_key)
    if pubkey.hex() != original["pubkey"]:
        raise ValueError("Расшифрованный ключ не соответствует pubkey исходного депозита.")

    chain = get_devnet_chain_setting(**configure_upstream(identity, values))
    message = DepositMessage(pubkey=pubkey,
        withdrawal_credentials=bytes.fromhex(original["withdrawal_credentials"]), amount=amount)
    signing_root = compute_signing_root(message,
        compute_deposit_domain(fork_version=chain.GENESIS_FORK_VERSION))
    data = DepositData(**message.as_dict(), signature=bls.Sign(signing_key, signing_root))
    # Keep network and withdrawal identity, replacing the amount-dependent fields.
    result = dict(original)
    result.update(amount=amount, signature=data.signature.hex(),
        deposit_message_root=message.hash_tree_root.hex(), deposit_data_root=data.hash_tree_root.hex())
    if not validate_deposit(result, chain):
        raise ValueError("Новая подпись или корень депозита не прошли проверку.")
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump([result], file, indent=2)
        file.write("\n")
    print(f"Deposit data saved: {output}")
    details(output, identity, values)


def main():
    parser = argparse.ArgumentParser(description="Подготовка депозитных данных MCN")
    commands = parser.add_subparsers(dest="command", required=True)
    create_parser = commands.add_parser("create")
    create_parser.add_argument("--amount", help="Сумма в MCN; без параметра запрашивается интерактивно")
    create_parser.add_argument("--from-keystore", type=Path, help="Существующий BLS keystore для переподписи")
    create_parser.add_argument("--deposit-data", type=Path, help="Исходный публичный deposit_data JSON")
    create_parser.add_argument("--output", type=Path, help="Новый deposit_data JSON; существующие файлы не заменяются")
    view = commands.add_parser("details")
    view.add_argument("file", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        repair_args = (args.from_keystore, args.deposit_data, args.output)
        if any(repair_args) and not all(repair_args):
            parser.error("Для переподписи нужны вместе --from-keystore, --deposit-data и --output.")
    try:
        identity, values = network_settings()
        if args.command == "create":
            amount = choose_amount(args.amount, values)
            if args.from_keystore:
                rebuild(args, identity, values, amount)
            else:
                create(identity, values, amount)
        else:
            details(args.file, identity, values)
    except ImportError:
        parser.exit(1, "MCN: Установите генератор командой ./setup-deposit.\n")
    except (OSError, ValueError, KeyError, importlib.metadata.PackageNotFoundError) as error:
        parser.exit(1, f"MCN: {error}\n")
    except (EOFError, KeyboardInterrupt):
        parser.exit(1, "\nMCN: Операция отменена.\n")


if __name__ == "__mp_main__":
    # Spawned verification workers need the same custom-network amount cap.
    worker_identity, worker_values = network_settings()
    configure_upstream(worker_identity, worker_values)

if __name__ == "__main__":
    main()
