"""Offline deposit-amount and same-key recovery checks. No network or real keys."""
import contextlib
from decimal import Decimal
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("mcn_deposit", ROOT / "tools/deposit.py")
deposit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deposit)


class DepositAmountTests(unittest.TestCase):
    def setUp(self):
        original_cwd = Path.cwd()
        self.addCleanup(os.chdir, original_cwd)
        self.identity, self.values = deposit.network_settings()
        settings = deposit.configure_upstream(self.identity, self.values)
        from ethstaker_deposit.settings import get_devnet_chain_setting
        self.chain = get_devnet_chain_setting(**settings)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        from py_ecc.bls import G2ProofOfPossession as bls
        from ethstaker_deposit.key_handling.keystore import Pbkdf2Keystore
        from ethstaker_deposit.utils.ssz import (
            DepositData, DepositMessage, compute_deposit_domain, compute_signing_root,
        )
        # Deterministic disposable key, never used on any network.
        self.secret = bls.KeyGen(bytes(range(32)))
        self.pubkey = bls.SkToPk(self.secret)
        self.password = "disposable-test-password"
        self.keyfile = self.directory / "keystore.json"
        Pbkdf2Keystore.encrypt(secret=self.secret.to_bytes(32, "big"),
            password=self.password, path="m/12381/3600/0/0/0").save(str(self.keyfile))
        message = DepositMessage(pubkey=self.pubkey,
            withdrawal_credentials=b"\x02" + bytes(11) + bytes.fromhex("11" * 20),
            amount=10_000 * 10**9)
        domain = compute_deposit_domain(fork_version=self.chain.GENESIS_FORK_VERSION)
        signed = DepositData(**message.as_dict(), signature=bls.Sign(self.secret, compute_signing_root(message, domain)))
        self.original = {key: value.hex() if isinstance(value, bytes) else value for key, value in signed.as_dict().items()}
        self.original.update(deposit_message_root=message.hash_tree_root.hex(),
            deposit_data_root=signed.hash_tree_root.hex(), fork_version="23251200",
            network_name="mcn", deposit_cli_version="1.3.0")
        self.oldfile = self.directory / "original.json"
        self.oldfile.write_text(json.dumps([self.original]))
        self.output = self.directory / "90500.json"

    def args(self):
        return SimpleNamespace(from_keystore=self.keyfile, deposit_data=self.oldfile, output=self.output)

    def rebuild(self, amount="90500", confirmation="90500", password=None):
        amount_gwei = deposit.deposit_amount(amount, self.values)
        with patch("builtins.input", return_value=confirmation), \
             patch.object(deposit.getpass, "getpass", return_value=password or self.password), \
             contextlib.redirect_stdout(io.StringIO()):
            deposit.rebuild(self.args(), self.identity, self.values, amount_gwei)

    def test_same_key_90500_has_valid_new_signature_and_unchanged_identity(self):
        old_bytes, key_bytes = self.oldfile.read_bytes(), self.keyfile.read_bytes()
        self.rebuild()
        updated = deposit.checked_deposit(self.output, self.identity, self.values)
        self.assertEqual(updated["amount"], 90_500 * 10**9)
        self.assertEqual(updated["pubkey"], self.original["pubkey"])
        self.assertEqual(updated["withdrawal_credentials"], self.original["withdrawal_credentials"])
        self.assertNotEqual(updated["signature"], self.original["signature"])
        self.assertNotEqual(updated["deposit_data_root"], self.original["deposit_data_root"])
        self.assertNotEqual(updated["deposit_message_root"], self.original["deposit_message_root"])
        self.assertEqual(self.oldfile.read_bytes(), old_bytes)
        self.assertEqual(self.keyfile.read_bytes(), key_bytes)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        # Independent SSZ merkleization for the 90,500 MCN DepositData root.
        h = lambda b: hashlib.sha256(b).digest()
        pubkey_root = h(bytes.fromhex(updated["pubkey"]) + bytes(16))
        sig = bytes.fromhex(updated["signature"])
        signature_root = h(h(sig[:64]) + h(sig[64:] + bytes(32)))
        amount_root = updated["amount"].to_bytes(8, "little") + bytes(24)
        root = h(h(pubkey_root + bytes.fromhex(updated["withdrawal_credentials"])) + h(amount_root + signature_root))
        self.assertEqual(root.hex(), updated["deposit_data_root"])

    def test_manual_amount_edit_is_rejected(self):
        forged = dict(self.original, amount=90_500 * 10**9)
        self.oldfile.write_text(json.dumps([forged]))
        with self.assertRaises(ValueError):
            self.rebuild()
        self.assertFalse(self.output.exists())

    def test_wrong_password_mismatch_and_existing_output_do_not_write(self):
        with self.assertRaises(ValueError):
            self.rebuild(password="wrong-password")
        self.assertFalse(self.output.exists())
        with self.assertRaises(ValueError):
            self.rebuild(confirmation="10000")
        self.assertFalse(self.output.exists())
        self.output.write_text("keep this file")
        with self.assertRaises(ValueError):
            self.rebuild()
        self.assertEqual(self.output.read_text(), "keep this file")

    def test_different_keystore_is_rejected_before_password_prompt(self):
        key = json.loads(self.keyfile.read_text())
        key["pubkey"] = "11" * 48
        self.keyfile.unlink()  # Upstream keystores are deliberately read-only.
        self.keyfile.write_text(json.dumps(key))
        with patch.object(deposit.getpass, "getpass", side_effect=AssertionError("Password should not be requested")):
            with self.assertRaisesRegex(ValueError, "Keystore"):
                deposit.rebuild(self.args(), self.identity, self.values, 90_500 * 10**9)
        self.assertFalse(self.output.exists())

    def test_exact_amount_bounds_and_precision(self):
        self.assertEqual(deposit.deposit_amount("90500", self.values), 90_500 * 10**9)
        self.assertEqual(deposit.deposit_amount("10000.000000001", self.values), 10_000 * 10**9 + 1)
        for invalid in ["0", "9999", "100000.000000001", "NaN", "Infinity", "90 500", "1e5", "-90500", "10000.0000000001"]:
            with self.subTest(amount=invalid), self.assertRaises(ValueError):
                deposit.deposit_amount(invalid, self.values)

    def test_new_key_generator_receives_the_selected_amount(self):
        from eth_utils import to_checksum_address
        address = to_checksum_address("0x" + "11" * 20)
        import ethstaker_deposit
        os.chdir(Path(ethstaker_deposit.__file__).resolve().parents[1])
        import ethstaker_deposit.deposit
        with patch("builtins.input", return_value=address), \
             patch.object(deposit.Path, "home", return_value=self.directory), \
             patch.object(ethstaker_deposit.deposit.cli, "main") as cli:
            deposit.create(self.identity, self.values, 90_500 * 10**9)
        args = cli.call_args.kwargs["args"]
        self.assertEqual(args[args.index("--amount") + 1], "90500")

    def test_details_prints_exact_wei_and_mcn(self):
        self.rebuild()
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            deposit.details(self.output, self.identity, self.values)
        self.assertIn("Value (MCN): 90500", output.getvalue())
        self.assertIn("Value (wei): 90500000000000000000000", output.getvalue())


if __name__ == "__main__":
    unittest.main()
