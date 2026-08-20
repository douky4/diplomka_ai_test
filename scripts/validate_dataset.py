"""Kontrola konzistence obrázků a metadata.csv před nasazením."""

import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path

from PIL import Image, UnidentifiedImageError


PROJECT_DIR = Path(__file__).resolve().parents[1]
METADATA_PATH = PROJECT_DIR / "metadata.csv"
REQUIRED_COLUMNS = {
    "image_id", "file_name", "label", "technique", "difficulty",
    "source_dataset", "subject_id", "width", "height", "split", "is_active",
}


def is_active(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "ano"}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    errors = []
    warnings = []
    ids = set()
    file_names = set()
    hashes = {}
    labels = Counter()
    techniques = Counter()
    active_count = 0

    if not METADATA_PATH.exists():
        print(f"CHYBA: Soubor neexistuje: {METADATA_PATH}")
        return 1

    with METADATA_PATH.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            print(f"CHYBA: Chybí sloupce: {', '.join(sorted(missing))}")
            return 1

        for row_number, row in enumerate(reader, start=2):
            image_id = row["image_id"].strip()
            file_name = row["file_name"].strip()
            label = row["label"].strip().lower()
            technique = row["technique"].strip() or "unknown"
            image_path = PROJECT_DIR / file_name

            if not image_id:
                errors.append(f"Řádek {row_number}: chybí image_id")
            elif image_id in ids:
                errors.append(f"Řádek {row_number}: duplicitní image_id {image_id}")
            ids.add(image_id)

            if file_name in file_names:
                errors.append(f"Řádek {row_number}: stejný soubor je uveden vícekrát ({file_name})")
            file_names.add(file_name)

            if label not in {"photo", "ai"}:
                errors.append(f"Řádek {row_number}: label musí být photo nebo ai")
            if not image_path.is_file():
                errors.append(f"Řádek {row_number}: chybí {file_name}")
                continue

            try:
                with Image.open(image_path) as image:
                    image.verify()
                with Image.open(image_path) as image:
                    actual_width, actual_height = image.size
            except (UnidentifiedImageError, OSError) as exc:
                errors.append(f"Řádek {row_number}: obrázek nelze otevřít ({exc})")
                continue

            try:
                expected_size = (int(row["width"]), int(row["height"]))
                if expected_size != (actual_width, actual_height):
                    errors.append(
                        f"Řádek {row_number}: metadata uvádějí {expected_size[0]}×{expected_size[1]}, "
                        f"soubor má {actual_width}×{actual_height}"
                    )
            except ValueError:
                errors.append(f"Řádek {row_number}: width a height musí být celá čísla")

            file_hash = hashlib.sha256(image_path.read_bytes()).hexdigest()
            if file_hash in hashes:
                errors.append(f"Řádek {row_number}: obsah je duplicitní s {hashes[file_hash]}")
            hashes[file_hash] = file_name

            if is_active(row["is_active"]):
                active_count += 1
                labels[label] += 1
                techniques[technique] += 1

    if labels and len(labels) < 2:
        warnings.append("Aktivní dataset neobsahuje obě třídy photo a ai")
    if labels and labels["photo"] != labels["ai"]:
        warnings.append(f"Aktivní třídy nejsou vyvážené: photo={labels['photo']}, ai={labels['ai']}")

    print(f"Zkontrolováno záznamů: {len(ids)}")
    print(f"Aktivních obrázků: {active_count}")
    print(f"Třídy: {dict(labels)}")
    print(f"Techniky: {dict(techniques)}")
    for warning in warnings:
        print(f"VAROVÁNÍ: {warning}")
    for error in errors:
        print(f"CHYBA: {error}")

    if errors:
        print(f"Dataset neprošel kontrolou ({len(errors)} chyb).")
        return 1
    print("Dataset je v pořádku.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
