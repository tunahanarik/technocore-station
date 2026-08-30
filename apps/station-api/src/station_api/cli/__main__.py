"""``python -m station_api.cli`` - local, interactive, secret-aware commands.

Design constraints, all deliberate:

* The seed is **never** a command line argument. Arguments land in shell
  history, in ``ps`` output and in parent-process environments.
* Passphrases are read with ``getpass``, so they are not echoed and not in
  history either.
* The file path is an argument (the user has to name the file somehow), but it
  is never logged or echoed back.
* Success prints the public DID and fingerprint. Nothing else. Never the seed.
* An existing active identity aborts the import; Station holds one identity.
* The source file is opened read-only and is never modified or deleted.
"""

from __future__ import annotations

import argparse
import sys
from getpass import getpass
from pathlib import Path

from technocore_conform import fingerprint_from_public_key, public_key_from_seed
from technocore_conform import short_fingerprint as make_short_fingerprint

from station_api.config import load_settings
from station_api.db.migrations_runner import initialise_database
from station_api.identity.service import IdentityService, IdentityServiceError
from station_api.seed_import import SeedImportError, parse_official_seed
from station_api.vault import ProtectionMode
from station_api.vault.errors import VaultError
from station_api.vault.passphrase import (
    MIN_PASSPHRASE_CHARS,
    PassphrasePolicyError,
    validate_passphrase,
)

IMPORT_CONFIRMATION = "SEED ICE AKTAR"


def _prompt_passphrase() -> str | None:
    """Ask for a vault passphrase twice, or allow an explicit opt-out."""
    print()
    print("Onerilen koruma: DPAPI + parola.")
    print(f"Parola en az {MIN_PASSPHRASE_CHARS} karakter olmalidir.")
    print("Parolasiz devam etmek icin bos birakip Enter tuslayin (onerilmez).")

    while True:
        first = getpass("Kasa parolasi: ")
        if not first:
            print()
            print("UYARI: Parolasiz modda seed yalniz DPAPI ile korunur.")
            print("Bu Windows kullanicisi olarak calisan bir saldirgan seed'e erisebilir.")
            answer = input("Parolasiz devam edilsin mi? (evet/hayir): ").strip().lower()
            if answer == "evet":
                return None
            continue

        try:
            validate_passphrase(first)
        except PassphrasePolicyError as exc:
            print(f"Hata: {exc}")
            continue

        second = getpass("Kasa parolasi (tekrar): ")
        if first != second:
            print("Hata: Parolalar eslesmiyor.")
            continue
        return first


def import_seed_command(seed_path: Path, label: str) -> int:
    settings = load_settings()
    settings.ensure_data_dir()

    if not seed_path.is_file():
        # The path is not echoed back: it can contain a username or a hint.
        print("Hata: Belirtilen yolda okunabilir bir dosya bulunamadi.", file=sys.stderr)
        return 2

    try:
        seed = bytearray(parse_official_seed(seed_path.read_bytes()))
    except SeedImportError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print("Hata: Dosya okunamadi.", file=sys.stderr)
        return 2

    try:
        engine = initialise_database(settings.database_path, stage=2)
        service = IdentityService(engine=engine, data_dir=settings.data_dir)

        current = service.describe()
        if current.did is not None and current.state.value != "revoked":
            print(
                "Hata: Bu bilgisayarda zaten aktif bir kimlik var. "
                "Once mevcut kimligi revoke edin.",
                file=sys.stderr,
            )
            return 3

        public_key = public_key_from_seed(bytes(seed))
        fingerprint = fingerprint_from_public_key(public_key)

        print()
        print("Iceri aktarilacak kimlik:")
        print(f"  Fingerprint: {make_short_fingerprint(fingerprint)}")
        print()
        print("Bu islem seed'i bu bilgisayarin DPAPI kasasina yazar.")
        print("Seed hicbir zaman ekranda gosterilmez ve aga gonderilmez.")
        print(f"Devam etmek icin tam olarak su metni yazin: {IMPORT_CONFIRMATION}")
        if input("Onay: ").strip() != IMPORT_CONFIRMATION:
            print("Iptal edildi.", file=sys.stderr)
            return 4

        passphrase = _prompt_passphrase()
        protection = ProtectionMode.DPAPI_PASSPHRASE if passphrase else ProtectionMode.DPAPI

        view = service.import_seed(
            seed=bytes(seed), protection=protection, passphrase=passphrase, label=label
        )
    except IdentityServiceError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 3
    except VaultError as exc:
        print(f"Hata: Secret kasasi kullanilamadi. {exc}", file=sys.stderr)
        return 3
    finally:
        for index in range(len(seed)):
            seed[index] = 0

    print()
    print("Kimlik iceri aktarildi.")
    print(f"  DID        : {view.did}")
    print(f"  Fingerprint: {make_short_fingerprint(view.fingerprint or '')}")
    print(f"  Koruma     : {view.protection}")
    print()
    print("Sonraki adim: recovery dosyasi olusturun ve restore-test yapin.")
    print("Restore-test tamamlanmadan hicbir Technocore yazma islemi acilmaz.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m station_api.cli",
        description="Technocore Station yerel araclari.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    importer = sub.add_parser(
        "import-seed",
        help="Resmi bir seed dosyasini yerel kasaya aktarir.",
        description=(
            "Yalniz 64 hex karakterlik resmi seed bicimini kabul eder. "
            "Seed ve parola komut satiri argumani olarak verilemez."
        ),
    )
    importer.add_argument(
        "--file",
        required=True,
        type=Path,
        help="Resmi seed dosyasinin yolu. Dosya degistirilmez.",
    )
    importer.add_argument("--label", default="", help="Kimlik icin kisa etiket.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "import-seed":
        path: Path = args.file
        label: str = args.label
        return import_seed_command(path, label)
    return 1  # pragma: no cover - argparse enforces the choices


if __name__ == "__main__":
    sys.exit(main())
