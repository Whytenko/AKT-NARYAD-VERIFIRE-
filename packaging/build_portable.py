#!/usr/bin/env python3

from __future__ import annotations

import platform
import subprocess
import sys
import hashlib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def zip_dir(source_dir: Path, target_zip: Path) -> None:
    if target_zip.exists():
        target_zip.unlink()
    with ZipFile(target_zip, "w", ZIP_DEFLATED) as archive:
        for file_path in source_dir.rglob("*"):
            archive.write(file_path, file_path.relative_to(source_dir.parent))


def sha256sum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    spec_path = project_root / "packaging" / "portable.spec"
    dist_dir = project_root / "dist"
    release_dir = project_root / "release"
    app_name = "AKTNaryadVerifier"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        str(spec_path),
    ]
    print(" ".join(cmd))
    subprocess.run(cmd, cwd=project_root, check=True)

    app_dir = dist_dir / app_name
    if not app_dir.exists():
        raise RuntimeError(f"Папка сборки не найдена: {app_dir}")

    release_dir.mkdir(parents=True, exist_ok=True)
    os_name = platform.system().lower()
    arch = platform.machine().lower().replace("amd64", "x64")
    zip_path = release_dir / f"{app_name}_{os_name}_{arch}.zip"
    zip_dir(app_dir, zip_path)
    checksum = sha256sum(zip_path)
    checksum_path = release_dir / f"{zip_path.name}.sha256"
    checksum_path.write_text(f"{checksum}  {zip_path.name}\n", encoding="utf-8")

    readme_path = release_dir / f"README_{os_name}_{arch}.txt"
    readme_path.write_text(
        "\n".join(
            [
                f"{app_name} portable package",
                "",
                "1) Распакуйте архив в любую пользовательскую папку (без прав администратора).",
                "2) Запустите приложение (AKTNaryadVerifier.exe / AKTNaryadVerifier).",
                "3) Рабочая папка пользователя:",
                "   - Windows: %LOCALAPPDATA%\\AktNaryadVerifier",
                "   - macOS: ~/Library/Application Support/AktNaryadVerifier",
                "   - Linux: ~/.local/share/AktNaryadVerifier",
                "4) Добавляйте PDF в папку input внутри рабочей папки пользователя.",
                "",
                "Важно: для OCR требуется бинарник Tesseract в системе или рядом с приложением.",
            ]
        ),
        encoding="utf-8",
    )

    print(f"✅ Portable архив: {zip_path}")
    print(f"✅ SHA-256: {checksum_path}")
    print(f"✅ Инструкция: {readme_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
