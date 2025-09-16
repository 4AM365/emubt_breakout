import xml.etree.ElementTree as ET
from pathlib import Path
import csv, re, sys

CSV_SUFFIX = "__"  # <emubt_stem>__<symbol_name>.csv

def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name or "unnamed")

def _parse_token(s: str) -> int:
    s = s.strip()
    if not s:
        raise ValueError("empty token")
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s, 16) if re.search(r"[A-Fa-f]", s) else int(s, 10)

def _flatten(rows):
    out = []
    for r in rows:
        out.extend(r)
    return out

def _ints_to_hex_tokens(vals):
    return [format(v & 0xFF, "X") for v in vals]

def list_csv_tables(folder: str | Path = "."):
    folder = Path(folder)
    return sorted(folder.glob(f"*{CSV_SUFFIX}*.csv"))

def reencode_csvs_to_emubt(folder: str | Path = ".", out_prefix: str = "altered_"):
    folder = Path(folder)
    csvs = list_csv_tables(folder)
    if not csvs:
        print(f"No CSVs found matching pattern '*{CSV_SUFFIX}*.csv' in {folder}.")
        return []

    # Group CSVs by emubt stem
    groups = {}
    for c in csvs:
        if CSV_SUFFIX not in c.stem:
            continue
        stem, sympart = c.stem.split(CSV_SUFFIX, 1)
        groups.setdefault(stem, []).append((c, sympart))

    outputs = []
    for stem, items in groups.items():
        # case-insensitive lookup of <stem>.emubt
        src_emubt = next((p for p in folder.glob("*.*")
                          if p.suffix.lower()==".emubt" and p.stem.lower()==stem.lower()), None)
        if not src_emubt:
            print(f"[SKIP] {stem}: source .emubt not found in {folder}")
            continue

        try:
            tree = ET.parse(src_emubt)
            root = tree.getroot()
        except Exception as e:
            print(f"[ERROR] {src_emubt.name}: XML parse failed: {e}")
            continue

        symmap = {}
        for el in root.findall(".//symbol"):
            nm = _sanitize(el.get("name") or "unnamed")
            w = el.get("width"); h = el.get("height"); data = el.get("data")
            if not (w and h and data is not None):
                continue
            try:
                symmap[nm] = (el, int(w), int(h))
            except Exception:
                pass

        changed = 0
        for csv_path, symname in items:
            nm = _sanitize(symname)
            if nm not in symmap:
                print(f"[WARN] {src_emubt.name}: no matching <symbol> for '{nm}' (from {csv_path.name})")
                continue

            el, w, h = symmap[nm]

            try:
                rows = []
                with open(csv_path, "r", newline="") as fp:
                    rdr = csv.reader(fp)
                    for row in rdr:
                        row = [tok for tok in row if tok is not None and tok.strip() != ""]
                        if row: rows.append(row)
                if not rows:
                    raise ValueError("empty CSV")
            except Exception as e:
                print(f"[ERROR] {csv_path.name}: {e}")
                continue

            widths = {len(r) for r in rows if r}
            if len(widths) != 1:
                print(f"[ERROR] {csv_path.name}: inconsistent row lengths")
                continue

            ch, cw = len(rows), list(widths)[0]
            if cw * ch != w * h:
                print(f"[ERROR] {csv_path.name}: size mismatch CSV({cw}x{ch}) vs XML({w}x{h})")
                continue

            try:
                nums = [_parse_token(tok) for tok in _flatten(rows)]
                if len(nums) != w * h:
                    raise ValueError(f"value count {len(nums)} != expected {w*h}")
            except Exception as e:
                print(f"[ERROR] {csv_path.name}: parse tokens failed: {e}")
                continue

            el.set("data", " ".join(_ints_to_hex_tokens(nums)))
            changed += 1
            print(f"[OK] Updated '{nm}' from {csv_path.name}")

        if changed:
            out_emubt = folder / f"{out_prefix}{src_emubt.name}"
            try:
                tree.write(out_emubt, encoding="utf-8", xml_declaration=True)
                outputs.append(out_emubt)
                print(f"[SAVED] {out_emubt.name} ({changed} symbol(s) updated)")
            except Exception as e:
                print(f"[ERROR] Save failed for {out_emubt.name}: {e}")
        else:
            print(f"[INFO] {src_emubt.name}: no changes")

    return outputs

def script_dir() -> Path:
    # Use the EXE’s folder when frozen; otherwise the .py’s folder
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent

if __name__ == "__main__":
    folder = script_dir()  # <-- scans the EXE’s own directory when packaged
    print(f"Re-encoding CSVs in: {folder}")
    reencode_csvs_to_emubt(folder, out_prefix="altered_")
