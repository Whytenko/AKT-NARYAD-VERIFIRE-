import re
import sys
from pathlib import Path
from types import SimpleNamespace
import pdfplumber
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.app_paths import ensure_runtime_layout, get_input_dir, get_reference_dir

def _parse_float(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(',', '.'))
    except Exception:
        return None

def parse_field(text: str) -> str:
    match = re.search(r'Месторождение[^А-Я]*([А-Я][а-я]+ское|[А-Я][а-я]+ное)', text)
    return match.group(1) if match else ""

def parse_bush(text: str) -> str:
    match = re.search(r'Куст[^0-9]*([0-9]+)', text)
    if match:
        return match.group(1)
    # формат "Номер скважины / куст ... 622 / 27"
    match = re.search(r'скважины\s*/\s*куст[^0-9]*\d+\s*/\s*([0-9]+)', text, re.IGNORECASE)
    return match.group(1) if match else ""

def _nth_number(line: str, n: int):
    nums = re.findall(r'\d+[.,]?\d*', line)
    if len(nums) >= n:
        return _parse_float(nums[n - 1])
    return None

def parse_relocation_values(text: str):
    v1 = None
    v3 = None
    for line in text.split('\n'):
        if 'Переезд перфораторной партии' not in line and 'Переезд комп.партии' not in line and 'Переезд комп. партии' not in line:
            continue
        if re.search(r'переезд .*1\s*гр', line, re.IGNORECASE) and v1 is None:
            m = re.search(r'0,0\s+0,0\s+([0-9]+[.,]?[0-9]*)', line)
            v1 = _parse_float(m.group(1)) if m else _nth_number(line, 5)
        if re.search(r'переезд .*3\s*гр', line, re.IGNORECASE) and v3 is None:
            m = re.search(r'0,0\s+0,0\s+([0-9]+[.,]?[0-9]*)', line)
            v3 = _parse_float(m.group(1)) if m else _nth_number(line, 5)
    # Fallback: search near "1 гр" and "3 гр"
    if v1 is None:
        match1 = re.search(r'Переезд перфораторной партии.*?1\s*гр[^0-9]*([0-9]+[.,]?[0-9]*)', text, re.IGNORECASE | re.DOTALL)
        v1 = _parse_float(match1.group(1)) if match1 else None
    if v3 is None:
        match3 = re.search(r'Переезд перфораторной партии.*?3\s*гр[^0-9]*([0-9]+[.,]?[0-9]*)', text, re.IGNORECASE | re.DOTALL)
        v3 = _parse_float(match3.group(1)) if match3 else None
    return v1, v3

def get_report_values(field: str, bush: str):
    excel_path = get_reference_dir() / "17. Отчет по километражу.xlsx"
    if not excel_path.exists():
        return None, None
    df = pd.read_excel(excel_path, sheet_name="Sheet1", header=None)
    for i in range(2, df.shape[0]):
        f = str(df.iloc[i, 0]).strip()
        b = str(df.iloc[i, 1]).strip()
        if not f or f == "nan":
            continue
        if field.lower() in f.lower() and b == str(bush):
            # столбцы "Проезд, 1 категории" и "Проезд, 3 категории" (1-based: 4 и 5)
            v1 = _parse_float(df.iloc[i, 3])
            v3 = _parse_float(df.iloc[i, 4])
            return v1, v3
    return None, None

def process_pdf(pdf_path: Path):
    with pdfplumber.open(pdf_path) as pdf:
        text = pdf.pages[0].extract_text() if pdf.pages else ""
    field = parse_field(text)
    bush = parse_bush(text)
    v1, v3 = parse_relocation_values(text)
    field, bush, v1, v3, ml_used = _apply_ml_overrides(pdf_path, field, bush, v1, v3)
    r1, r3 = get_report_values(field, bush) if field and bush else (None, None)

    print(f"\nОтчет по километражу: {pdf_path.name}")
    print(f"Куст: {bush if bush else 'не найден'}")
    print(f"Переезд 1 гр.: {v1 if v1 is not None else 'не найдено'}")
    print(f"Переезд 3 гр.: {v3 if v3 is not None else 'не найдено'}")
    if r1 is not None:
        r1 = r1 * 2
    if r3 is not None:
        r3 = r3 * 2
    print(f"По отчету 1 гр.: {r1 if r1 is not None else 'не найдено'}")
    print(f"По отчету 3 гр.: {r3 if r3 is not None else 'не найдено'}")

    if v1 is not None and r1 is not None:
        diff1 = abs(v1 - r1)
        print("Результат 1 гр.: ✅ СООТВЕТСТВУЕТ" if diff1 <= 0.1 else "Результат 1 гр.: ❌ НЕ СООТВЕТСТВУЕТ")
    if v3 is not None and r3 is not None:
        diff3 = abs(v3 - r3)
        print("Результат 3 гр.: ✅ СООТВЕТСТВУЕТ" if diff3 <= 0.1 else "Результат 3 гр.: ❌ НЕ СООТВЕТСТВУЕТ")

def _apply_ml_overrides(pdf_path: Path, field: str, bush: str, v1, v3):
    try:
        from src.extractors.ml_assist import MLAssist, _parse_ru_int, _parse_ru_float
    except Exception:
        try:
            from ml_assist import MLAssist, _parse_ru_int, _parse_ru_float
        except Exception:
            return field, bush, v1, v3, False

    assist = MLAssist.load()
    if assist is None:
        return field, bush, v1, v3, False

    match = assist.match(SimpleNamespace(filename=pdf_path.name))
    if match is None or match.method != "exact-file":
        return field, bush, v1, v3, False

    row = match.row
    changed = False

    if "field" in row and not pd.isna(row["field"]):
        value = str(row["field"]).strip()
        if value:
            field = value
            changed = True
    if "well_bush" in row and not pd.isna(row["well_bush"]):
        parsed = _parse_ru_int(row["well_bush"])
        if parsed is not None:
            bush = str(parsed)
            changed = True
    if "km_reloc_1gr" in row and not pd.isna(row["km_reloc_1gr"]):
        parsed = _parse_ru_float(row["km_reloc_1gr"])
        if parsed is not None:
            v1 = parsed
            changed = True
    if "km_reloc_3gr" in row and not pd.isna(row["km_reloc_3gr"]):
        parsed = _parse_ru_float(row["km_reloc_3gr"])
        if parsed is not None:
            v3 = parsed
            changed = True

    return field, bush, v1, v3, changed

def main(args=None):
    ensure_runtime_layout(copy_reference=True)
    input_dir = get_input_dir()

    cli_args = args if args is not None else sys.argv[1:]
    if cli_args:
        pdf_paths = []
        for arg in cli_args:
            candidate = Path(arg)
            if not candidate.is_absolute():
                candidate = input_dir / arg
            if candidate.exists() and candidate.suffix.lower() == ".pdf":
                pdf_paths.append(candidate)
        if not pdf_paths:
            print("❌ PDF файлы не найдены")
            return
    else:
        pdf_paths = list(input_dir.glob("*.pdf"))

    if not pdf_paths:
        print("❌ Файлы не найдены")
        return

    for pdf in pdf_paths:
        process_pdf(pdf)

if __name__ == "__main__":
    main()
