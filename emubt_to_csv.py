from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import csv
import re

def script_dir() -> Path:
    # When frozen (PyInstaller), use the exe location; otherwise use the .py location
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent

def list_emubt_files(folder: str | Path = "."):
    """
    Scan the given folder (default = current working directory)
    and return a list of .emubt files (Path objects), case-insensitive.
    """
    folder = Path(folder)
    files = list(folder.glob("*.emubt")) + list(folder.glob("*.EMUBT"))
    return sorted(files)

def _parse_tokens_to_ints(data_str: str):
    """Split space-separated tokens; accept hex (3C, 0x3c, C) or decimal (60)."""
    toks = re.split(r"\s+", data_str.strip())
    vals = []
    for t in toks:
        if not t:
            continue
        if t.lower().startswith("0x"):
            base = 16
        else:
            base = 16 if re.search(r"[A-Fa-f]", t) else 10
        vals.append(int(t, base))
    return vals

def _reshape(vals, width):
    return [vals[i:i+width] for i in range(0, len(vals), width)]

def emubt_to_csv_tables(emubt_path: Path, out_dir: Path | None = None, *, output="decimal"):
    """
    Read an .emubt XML file and write each <symbol> as its own CSV, laid out as the actual table.
    - CSV filename: <emubt_stem>__<symbol_name_sanitized>.csv
    - `output`: "decimal" (default) or "hex" (uppercase, no 0x)
    """
    emubt_path = Path(emubt_path)
    out_dir = Path(out_dir) if out_dir else emubt_path.parent

    def sanitize(name: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", name or "unnamed")

    tree = ET.parse(emubt_path)
    root = tree.getroot()

    written = []
    for el in root.findall(".//symbol"):
        name = el.get("name") or "unnamed"
        w = el.get("width")
        h = el.get("height")
        data = el.get("data")
        if not (w and h and data is not None):
            continue
        w, h = int(w), int(h)

        # Parse tokens -> ints (translate hex to numeric)
        nums = _parse_tokens_to_ints(data)

        # Ensure correct count
        if len(nums) != w * h:
            continue

        # Reshape to actual table layout
        rows = _reshape(nums, w)

        # Choose output format
        if output == "hex":
            rows_fmt = [[format(v & 0xFF, "X") for v in row] for row in rows]
        else:  # decimal
            rows_fmt = rows

        # Write CSV per symbol
        csv_name = f"{emubt_path.stem}__{sanitize(name)}.csv"
        csv_path = out_dir / csv_name
        with open(csv_path, "w", newline="") as fp:
            writer = csv.writer(fp)
            for row in rows_fmt:
                writer.writerow(row)
        written.append(csv_path)

    return written

if __name__ == "__main__":
    folder = script_dir()                 # <— key change
    emubt_files = list_emubt_files(folder)
    if not emubt_files:
        print(f"No .emubt files found in {folder}")
    for emubt_file in emubt_files:
        written_csvs = emubt_to_csv_tables(emubt_file, output="decimal")
        for csv_path in written_csvs:
            print(f"Exported table -> {csv_path}")