import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import sys

SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
PROJECT_ROOT = SCRIPT_DIR.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    from .main_parser import FinalUnifiedParser
except Exception:
    from main_parser import FinalUnifiedParser

from src.utils.app_paths import ensure_runtime_layout, get_input_dir, get_reference_dir

MONTH_NAMES = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}

def _pick_sheet_candidates(sheet_names, month_name, year):
    year_suffix = str(year)[-2:]
    target = f"{month_name}{year_suffix}"

    normalized = {name: name.replace(" ", "") for name in sheet_names}
    year_candidates = [
        name for name, norm in normalized.items()
        if norm == target
    ]
    candidates = []
    # Prefer base month sheet first to avoid stale/incorrect year tabs.
    for name in sheet_names:
        if name.strip() == month_name:
            candidates.append(name)
            break
    if year_candidates and year_candidates[0] not in candidates:
        candidates.append(year_candidates[0])
    return candidates

def get_table_data(dt, well_type):
    """
    Получает данные из таблицы с ПРАВИЛЬНОЙ логикой
    """
    hour = dt.hour
    lookup_dt = dt
    if hour in (0, 1, 2):
        # 00:00, 01:00, 02:00 относятся к 24:00/02:00 предыдущего дня
        lookup_dt = dt - timedelta(days=1)
    day = lookup_dt.day
    month = lookup_dt.month
    
    ref_dir = get_reference_dir()
    if dt.year == 2026:
        excel_path = ref_dir / "20. Отчет по температуре 2026.xlsx"
    else:
        excel_path = ref_dir / "20. Отчет по температуре.xlsx"
    if not excel_path.exists():
        pattern = "20. Отчет по температуре*2026*.xlsx" if dt.year == 2026 else "20. Отчет по температуре*.xlsx"
        candidates = sorted(ref_dir.glob(pattern))
        if candidates:
            excel_path = candidates[0]
    
    month_name = MONTH_NAMES.get(month)
    if not month_name:
        return None
    
    try:
        excel = pd.ExcelFile(excel_path)
        sheet_candidates = _pick_sheet_candidates(excel.sheet_names, month_name, dt.year)
        if not sheet_candidates:
            return None

        for sheet_name in sheet_candidates:
            df = pd.read_excel(excel_path, sheet_name=sheet_name, header=None)
        
            # 1. Находим таблицу ВАТЬЕГАН или ПОВХ
            start_row = None
            for i in range(df.shape[0]):
                cell = str(df.iloc[i, 0])
                if well_type in cell:
                    start_row = i
                    break

            if start_row is None:
                continue

            # 2. Находим начало данных (через 2 строки)
            data_start = start_row + 2

            # 3. Находим БЛИЖАЙШЕЕ время в таблице
            # Часы в таблице: 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 2
            table_hours = [4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 2]

            # Если час 0 - это 24, если 1-2 часа - используем 2 (ближайшее значение в таблице)
            if hour == 0:
                search_hour = 24
            elif hour in (1, 2):
                search_hour = 2
            else:
                search_hour = hour

            # Находим ближайший час
            closest_hour = min(table_hours, key=lambda x: abs(x - search_hour))

            # 4. Определяем день в таблице
            # ОСОБЕННОСТЬ: 00:00 30 ноября -> это данные дня 30 в таблице!
            # 02:00 30 ноября -> это тоже данные дня 30 в таблице!
            table_day = day  # По умолчанию тот же день

            # 5. Находим строку с нужным временем
            time_row = None
            for i in range(data_start, min(data_start + 15, df.shape[0])):
                time_cell = str(df.iloc[i, 0]).strip()
                try:
                    cell_hour = float(time_cell.replace(',', '.'))
                    if abs(cell_hour - closest_hour) < 0.1:
                        time_row = i
                        break
                except Exception:
                    continue

            if time_row is None:
                continue

            # 6. Определяем колонку дня
            # В Excel: колонка 0 = "Время", колонка 1 = день 1, колонка 2 = день 2
            excel_col = table_day  # день 30 -> колонка 30

            if excel_col >= df.shape[1]:
                continue

            # 7. Получаем значение
            value = df.iloc[time_row, excel_col]

            if pd.isna(value):
                continue

            # 8. Преобразуем в число
            try:
                temp = float(str(value).replace(',', '.'))
                return temp
            except Exception:
                continue

        return None
            
    except Exception as e:
        print(f"Ошибка: {e}")
        return None

def _parse_float(value):
    if value is None:
        return None
    try:
        return float(str(value).replace(',', '.'))
    except Exception:
        return None

def analyze_period(well_name, well_type, start_dt, end_dt, pdf_temp):
    temps = []
    current_dt = start_dt

    while current_dt <= end_dt:
        temp = get_table_data(current_dt, well_type)
        if temp is not None:
            temps.append(temp)
        current_dt += timedelta(hours=1)

    print(f"\nОтчет по температуре: {well_name}")
    if temps:
        avg_temp = sum(temps) / len(temps)
        if pdf_temp is not None:
            diff = abs(pdf_temp - avg_temp)
            print(f"Средняя температура: {avg_temp:.2f}°C")
            print(f"Температура в акте: {pdf_temp:.2f}°C")
            print(f"Разница: {diff:.2f}°C")
            print(f"📋 РЕЗУЛЬТАТ: ", end="")
            if diff <= 5.0:
                print("✅ СООТВЕТСТВУЕТ (±5°C)")
            else:
                print("❌ НЕ СООТВЕТСТВУЕТ")
        else:
            print("Температура в акте: не найдена")
    else:
        print("Нет данных для анализа")

def analyze_from_pdf(pdf_path: Path):
    parser = FinalUnifiedParser()
    well_data = parser.parse_all(str(pdf_path))
    
    field = (well_data.field or "").lower()
    if "ватьеган" in field:
        well_type = "ВАТЬЕГАН"
        well_name = "Ватьеганское"
    elif "повхов" in field:
        well_type = "ПОВХ"
        well_name = "Повховское"
    else:
        print(f"❌ Не удалось определить месторождение: {well_data.field}")
        return
    
    try:
        start_dt = datetime.strptime(well_data.start_date, "%d.%m.%Y %H:%M")
        end_dt = datetime.strptime(well_data.end_date, "%d.%m.%Y %H:%M")
    except Exception:
        print(f"❌ Не удалось распарсить даты: {well_data.start_date} - {well_data.end_date}")
        return
    
    pdf_temp = _parse_float(well_data.temperature)
    analyze_period(pdf_path.name, well_type, start_dt, end_dt, pdf_temp)

def main(args=None):
    ensure_runtime_layout(copy_reference=True)
    cli_args = args if args is not None else sys.argv[1:]
    input_dir = get_input_dir()
    if cli_args:
        for arg in cli_args:
            candidate = Path(arg)
            if not candidate.is_absolute():
                candidate = input_dir / arg
            if not candidate.exists():
                print(f"❌ Файл не найден: {candidate}")
                continue
            analyze_from_pdf(candidate)
        return

    pdf_files = list(input_dir.glob("*.pdf"))
    if not pdf_files:
        print("❌ Файлы не найдены")
        return
    for pdf_file in pdf_files:
        analyze_from_pdf(pdf_file)


if __name__ == "__main__":
    main()
