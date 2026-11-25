"""Download and unpack the pinned EthStaker source, including language/word lists."""
import hashlib
from pathlib import Path
import shutil
import tarfile
import tempfile
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    requirement = (ROOT / "tools/deposit-requirements.txt").read_text().strip()
    url, expected = requirement.split(" @ ", 1)[1].split("#sha256=", 1)
    tools = ROOT / ".tools"
    tools.mkdir(exist_ok=True)
    destination = tools / "ethstaker"
    with tempfile.TemporaryDirectory(prefix=".ethstaker-", dir=tools) as temporary:
        folder = Path(temporary)
        archive_path = folder / "source.tar.gz"
        with urlopen(Request(url, headers={"User-Agent": "start-mcn"}), timeout=120) as response:
            with archive_path.open("wb") as output:
                shutil.copyfileobj(response, output)
        if hashlib.sha256(archive_path.read_bytes()).hexdigest() != expected:
            raise ValueError("EthStaker source SHA-256 mismatch")
        extracted = folder / "source"
        extracted.mkdir()
        with tarfile.open(archive_path) as archive:
            for member in archive:
                parts = Path(member.name).parts
                if parts[0] != "ethstaker-deposit-cli-1.3.0" or ".." in parts:
                    raise ValueError("Invalid source archive path")
                if len(parts) == 1:
                    continue
                path = extracted.joinpath(*parts[1:])
                if member.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as source, path.open("wb") as output:
                        shutil.copyfileobj(source, output)
                else:
                    raise ValueError("Unexpected source archive entry")
        # Repeated setup keeps the verified source and refuses a different tree.
        if destination.exists():
            for path in extracted.rglob("*"):
                if path.is_file() and (
                    not (destination / path.relative_to(extracted)).is_file()
                    or path.read_bytes() != (destination / path.relative_to(extracted)).read_bytes()
                ):
                    raise ValueError("Existing EthStaker source differs. Restore .tools/ethstaker first.")
        else:
            extracted.rename(destination)


if __name__ == "__main__":
    main()
