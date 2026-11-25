"""MCN settings adapter for EthStaker Deposit CLI 1.3.0."""
import argparse
from decimal import Decimal
import importlib.metadata
import json
import os
from pathlib import Path
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


def create(identity, values):
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
        "--amount", str(int(values["MIN_ACTIVATION_BALANCE"]) // 10**9),
        "--devnet_chain_setting", json.dumps(settings, separators=(",", ":")),
    ], standalone_mode=False)


def details(path, identity, values):
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
    if not validate_deposit(item, chain):
        raise ValueError("Invalid deposit signature or data root.")
    credentials = bytes.fromhex(item["withdrawal_credentials"])
    if credentials[0] != 2:
        raise ValueError("Expected compounding withdrawal credentials (0x02).")
    amount = Decimal(item["amount"]) / 10**9
    minimum = Decimal(values["MIN_ACTIVATION_BALANCE"]) / 10**9
    if amount < minimum:
        raise ValueError(f"Activation requires at least {minimum} MCN.")
    print(f"Network: MCN Mainnet (Chain ID {identity['chain_id']})")
    print(f"Contract: {values['DEPOSIT_CONTRACT_ADDRESS']}")
    print(f"Withdrawal address: 0x{credentials[12:].hex()}")
    print(f"Value (MCN): {amount}")
    for key in ("pubkey", "withdrawal_credentials", "signature", "deposit_data_root"):
        print(f"{key}: 0x{item[key]}")
    print("Submit the deposit once. Record its transaction hash before retrying.")


def main():
    parser = argparse.ArgumentParser(description="Подготовка депозитных данных MCN")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("create")
    view = commands.add_parser("details")
    view.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        identity, values = network_settings()
        if args.command == "create":
            create(identity, values)
        else:
            details(args.file, identity, values)
    except ImportError:
        parser.exit(1, "MCN: Установите генератор командой ./setup-deposit.\n")
    except (OSError, ValueError, KeyError, importlib.metadata.PackageNotFoundError) as error:
        parser.exit(1, f"MCN: {error}\n")


if __name__ == "__mp_main__":
    # Spawned verification workers need the same custom-network amount cap.
    worker_identity, worker_values = network_settings()
    configure_upstream(worker_identity, worker_values)

if __name__ == "__main__":
    main()
