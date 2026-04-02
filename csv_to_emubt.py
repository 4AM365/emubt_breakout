import xml.etree.ElementTree as ET
from pathlib import Path
import csv, re, sys

# --- lightweight GUI (stdlib) -----------------------------------------------
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception:
    tk = None
    filedialog = None
    messagebox = None

CSV_SUFFIX = "__"  # <emubt_stem>__<symbol_name>.csv

def _sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name or "unnamed")

# ---------------------------------------------------------------------------
# Token parser — handles all reasonable numeric formats from ECU/map editors
# ---------------------------------------------------------------------------
# Accepted formats (case-insensitive):
#   0xFF, 0XFF          — hex with 0x prefix
#   FF, 3A, 0A          — bare hex (only if contains A-F, or forced_hex=True)
#   255, 255.0, 255.75  — decimal integer or float
#   -12, -0.5           — negatives
#   "255", '3A'         — quoted tokens (quotes stripped first)
#   1,234 / 1.234,5     — thousand-separator / EU decimal handled gracefully
# Returns a float so callers can round() to int or keep fractional precision.
# ---------------------------------------------------------------------------
_HEX_BARE = re.compile(r'^[0-9A-Fa-f]+$')
_HAS_HEX_LETTER = re.compile(r'[A-Fa-f]')

def _parse_token(s: str, *, forced_hex: bool = False) -> float:
    """Parse a numeric token and return its value as float.

    Raises ValueError with a descriptive message on failure.
    """
    if not isinstance(s, str):
        raise TypeError(f"expected str, got {type(s).__name__}")

    orig = s
    s = s.strip().strip("'\"")   # strip whitespace AND surrounding quotes

    if not s:
        raise ValueError(f"empty token (original: {orig!r})")

    # ---- 1. explicit 0x / 0X hex prefix ------------------------------------
    if s.lower().startswith("0x"):
        hex_part = s[2:]
        if not hex_part:
            raise ValueError(f"bare '0x' with no digits: {orig!r}")
        try:
            return float(int(hex_part, 16))
        except ValueError:
            raise ValueError(f"invalid hex token {orig!r}")

    # ---- 2. forced-hex mode (caller knows the field is always hex) ---------
    if forced_hex:
        if _HEX_BARE.match(s):
            try:
                return float(int(s, 16))
            except ValueError:
                pass
        raise ValueError(f"expected hex token, got {orig!r}")

    # ---- 3. bare hex — only when the token contains at least one A-F ------
    #   Guard: must be PURE hex chars with no decimal point or sign, so we
    #   don't misidentify things like "1E5" as hex (could be scientific notation).
    if _HEX_BARE.match(s) and _HAS_HEX_LETTER.search(s):
        # Ambiguity check: "1E5" looks like sci-notation, "1B3" is clearly hex.
        # We prefer decimal/float interpretation when the only hex letter is E/e
        # and it's flanked by digits (scientific-notation pattern).
        sci_pattern = re.match(r'^\d+[Ee]\d+$', s)
        if not sci_pattern:
            try:
                return float(int(s, 16))
            except ValueError:
                pass  # fall through to decimal attempt

    # ---- 4. decimal integer or float (including scientific notation) -------
    # Normalise thousand-separator commas ONLY when a period is also present
    # (e.g. "1,234.5" → "1234.5").  Lone comma as decimal separator
    # (European "255,0") is handled separately.
    cleaned = s
    if ',' in cleaned and '.' in cleaned:
        cleaned = cleaned.replace(',', '')       # "1,234.5" → "1234.5"
    elif ',' in cleaned and '.' not in cleaned:
        cleaned = cleaned.replace(',', '.')       # "255,0"   → "255.0"

    try:
        return float(cleaned)
    except ValueError:
        pass

    # ---- 5. last resort: strip any trailing non-numeric junk (units, etc.) -
    stripped = re.sub(r'[^0-9A-Fa-fx.+\-eE,]+$', '', s)
    if stripped and stripped != s:
        try:
            return _parse_token(stripped)         # recurse once on cleaned form
        except ValueError:
            pass

    raise ValueError(f"cannot parse {orig!r} as a number")


def _parse_token_to_int(s: str, **kw) -> int:
    """Convenience wrapper: parse token and return rounded int."""
    val = _parse_token(s, **kw)
    return int(round(val))


# ---------------------------------------------------------------------------
# CSV ingestion — tolerant of BOM on inner rows, quoted cells, empty lines
# ---------------------------------------------------------------------------

def _read_csv_rows(csv_path: Path) -> list[list[str]]:
    """Read CSV and return a list of non-empty token rows (all tokens stripped)."""
    rows = []
    with open(csv_path, "r", newline="", encoding="utf-8-sig") as fp:
        rdr = csv.reader(fp)
        for raw_row in rdr:
            # Strip whitespace, inner BOM chars, and surrounding quotes from each cell
            cleaned = []
            for cell in raw_row:
                tok = cell.strip().strip('\ufeff').strip("'\"")
                if tok:
                    cleaned.append(tok)
            if cleaned:
                rows.append(cleaned)
    return rows


def _flatten(rows):
    out = []
    for r in rows:
        out.extend(r)
    return out


def _ints_to_hex_tokens(vals):
    # No bit-masking — values may be 8-bit (u8), 12-bit (u12), or wider.
    # format() with "X" produces uppercase hex of the natural width (e.g. "42", "1B4").
    return [format(v, "X") for v in vals]


def _parse_rows_to_ints(rows: list[list[str]], source_name: str) -> list[int] | None:
    """Convert all tokens in rows to ints. Returns None and prints error on failure."""
    tokens = _flatten(rows)
    nums = []
    bad = []
    for i, tok in enumerate(tokens):
        try:
            nums.append(_parse_token_to_int(tok))
        except (ValueError, TypeError) as exc:
            bad.append((i, tok, str(exc)))

    if bad:
        # Report up to 5 bad tokens to avoid flooding the log
        for idx, tok, reason in bad[:5]:
            print(f"[ERROR] {source_name}: token [{idx}] {tok!r} → {reason}")
        if len(bad) > 5:
            print(f"[ERROR] {source_name}: …and {len(bad)-5} more bad token(s)")
        return None

    return nums


# ---------------------------------------------------------------------------

def list_csv_tables(folder: str | Path = "."):
    folder = Path(folder)
    return sorted(folder.glob("*.csv"))


def reencode_csvs_to_emubt(folder: str | Path = ".", out_prefix: str = "altered_"):
    folder = Path(folder)
    csvs = list_csv_tables(folder)
    if not csvs:
        print(f"No CSVs found in {folder}.")
        return []

    emubts = list(folder.glob("*.emubt"))

    if emubts:
        return _process_with_emubt_templates(folder, csvs, emubts, out_prefix)
    else:
        return _create_emubt_from_csvs(folder, csvs, out_prefix)


def _process_with_emubt_templates(folder, csvs, emubts, out_prefix):
    """Update existing .emubt files with data from CSVs."""
    groups = {}
    for c in csvs:
        csv_stem = c.stem
        if CSV_SUFFIX in csv_stem:
            emubt_stem, sympart = csv_stem.split(CSV_SUFFIX, 1)
            groups.setdefault(emubt_stem, []).append((c, sympart))
        else:
            groups.setdefault(None, []).append((c, csv_stem))

    outputs = []
    for stem, items in groups.items():
        if stem is None:
            for src_emubt in emubts:
                tree, root, symmap = _load_emubt(src_emubt)
                if tree is None:
                    continue

                changed = 0
                for csv_path, symname in items:
                    nm = _sanitize(symname)
                    if nm not in symmap:
                        continue
                    el, w, h = symmap[nm]
                    changed += _process_csv(csv_path, el, w, h)

                if changed:
                    _save_emubt(tree, folder, src_emubt, out_prefix, changed, outputs)
        else:
            src_emubt = next(
                (p for p in emubts if p.stem.lower() == stem.lower()), None
            )
            if not src_emubt:
                print(f"[SKIP] {stem}: source .emubt not found in {folder}")
                continue

            tree, root, symmap = _load_emubt(src_emubt)
            if tree is None:
                continue

            changed = 0
            for csv_path, symname in items:
                nm = _sanitize(symname)
                if nm not in symmap:
                    print(
                        f"[WARN] {src_emubt.name}: no matching <symbol> for "
                        f"{nm!r} (from {csv_path.name})"
                    )
                    continue
                el, w, h = symmap[nm]
                changed += _process_csv(csv_path, el, w, h)

            if changed:
                _save_emubt(tree, folder, src_emubt, out_prefix, changed, outputs)
            else:
                print(f"[INFO] {src_emubt.name}: no changes")

    return outputs


def _load_emubt(src_emubt: Path):
    """Parse an .emubt file and return (tree, root, symmap) or (None, None, None)."""
    try:
        tree = ET.parse(src_emubt)
        root = tree.getroot()
    except Exception as e:
        print(f"[ERROR] {src_emubt.name}: XML parse failed: {e}")
        return None, None, None

    symmap = {}
    for el in root.findall(".//symbol"):
        nm = _sanitize(el.get("name") or "unnamed")
        w = el.get("width")
        h = el.get("height")
        data = el.get("data")
        if not (w and h and data is not None):
            continue
        try:
            symmap[nm] = (el, int(w), int(h))
        except Exception:
            pass

    return tree, root, symmap


def _write_emubt(root: ET.Element, out_path: Path) -> None:
    """Write an ElementTree root to disk with the canonical EMU Black declaration.

    Python's ET.write() always produces single-quoted attributes in the XML
    declaration (<?xml version='1.0' encoding='utf-8'?>) which the ECU software
    rejects.  We write the declaration manually and serialise the tree as a
    Unicode string so the encoding is handled by the file open() call.
    """
    # Indent for readability (Python 3.9+; silently skip on older runtimes)
    try:
        ET.indent(root, space="  ")
    except AttributeError:
        pass

    xml_body = ET.tostring(root, encoding="unicode")
    with open(out_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n')
        fh.write(xml_body)
        fh.write("\n")


def _infer_storage(nums: list[int]) -> str:
    """Guess the storage type from the value range so the attribute is always present."""
    mx = max(nums) if nums else 0
    if mx <= 0xFF:
        return "u8"
    if mx <= 0xFFF:
        return "u12"
    if mx <= 0xFFFF:
        return "u16"
    return "u32"


def _save_emubt(tree, folder, src_emubt, out_prefix, changed, outputs):
    out_emubt = folder / f"{out_prefix}{src_emubt.name}"
    try:
        _write_emubt(tree.getroot(), out_emubt)
        outputs.append(out_emubt)
        print(f"[SAVED] {out_emubt.name} ({changed} symbol(s) updated)")
    except Exception as e:
        print(f"[ERROR] Save failed for {out_emubt.name}: {e}")


def _create_emubt_from_csvs(folder, csvs, out_prefix):
    """Create new .emubt files from CSV data when no template exists."""
    outputs = []
    for csv_path in csvs:
        try:
            rows = _read_csv_rows(csv_path)
        except Exception as e:
            print(f"[ERROR] {csv_path.name}: {e}")
            continue

        if not rows:
            print(f"[ERROR] {csv_path.name}: empty CSV")
            continue

        widths = {len(r) for r in rows}
        if len(widths) != 1:
            print(
                f"[ERROR] {csv_path.name}: inconsistent row lengths "
                f"{sorted(widths)} — check for stray commas or missing cells"
            )
            continue

        ch, cw = len(rows), list(widths)[0]
        nums = _parse_rows_to_ints(rows, csv_path.name)
        if nums is None:
            continue

        # Build the canonical EMU Black project structure:
        #   <project version="1.0">
        #     <tables>
        #       <symbol name="..." storage="uN" width="N" height="N" data="..." />
        #     </tables>
        #   </project>
        project = ET.Element("project")
        project.set("version", "1.0")
        tables = ET.SubElement(project, "tables")
        symbol = ET.SubElement(tables, "symbol")
        symbol.set("name", _sanitize(csv_path.stem))
        symbol.set("storage", _infer_storage(nums))
        symbol.set("width", str(cw))
        symbol.set("height", str(ch))
        symbol.set("data", " ".join(_ints_to_hex_tokens(nums)))

        out_emubt = folder / f"{out_prefix}{csv_path.stem}.emubt"
        try:
            _write_emubt(project, out_emubt)
            outputs.append(out_emubt)
            print(f"[SAVED] {out_emubt.name} ({cw}x{ch} symbol, storage={symbol.get('storage')})")
        except Exception as e:
            print(f"[ERROR] Save failed for {out_emubt.name}: {e}")

    return outputs


def _process_csv(csv_path: Path, el, w: int, h: int) -> int:
    """Read a CSV and write its values into an existing XML element.

    Returns 1 on success, 0 on any error.
    """
    try:
        rows = _read_csv_rows(csv_path)
    except Exception as e:
        print(f"[ERROR] {csv_path.name}: {e}")
        return 0

    if not rows:
        print(f"[ERROR] {csv_path.name}: empty CSV")
        return 0

    widths = {len(r) for r in rows}
    if len(widths) != 1:
        print(
            f"[ERROR] {csv_path.name}: inconsistent row lengths "
            f"{sorted(widths)} — check for stray commas or missing cells"
        )
        return 0

    ch, cw = len(rows), list(widths)[0]
    if cw * ch != w * h:
        print(
            f"[ERROR] {csv_path.name}: size mismatch — "
            f"CSV is {cw}×{ch}={cw*ch} cells, XML expects {w}×{h}={w*h} cells"
        )
        return 0

    nums = _parse_rows_to_ints(rows, csv_path.name)
    if nums is None:
        return 0

    el.set("data", " ".join(_ints_to_hex_tokens(nums)))
    print(f"[OK] Updated from {csv_path.name}")
    return 1


# ---------------------------------------------------------------------------

def script_dir() -> Path:
    return Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent


def pick_folder_gui(default_dir: Path | None = None) -> Path | None:
    if tk is None or filedialog is None:
        return None
    root = tk.Tk()
    root.withdraw()
    root.update_idletasks()
    initialdir = str(default_dir) if default_dir and default_dir.exists() else str(script_dir())
    folder = filedialog.askdirectory(
        title="Select folder with CSVs and .emubt", initialdir=initialdir
    )
    root.destroy()
    return Path(folder) if folder else None


def show_message(title: str, text: str):
    if messagebox is not None and tk is not None:
        try:
            r = tk.Tk()
            r.withdraw()
            messagebox.showinfo(title, text)
            r.destroy()
            return
        except Exception:
            pass
    print(f"[{title}] {text}")


def main():
    folder: Path | None = None
    if len(sys.argv) >= 2:
        folder = Path(sys.argv[1])

    if folder is None or not folder.exists():
        folder = pick_folder_gui(default_dir=script_dir())

    if folder is None or not folder.exists():
        show_message("Cancelled", "No folder selected.")
        return

    outputs = reencode_csvs_to_emubt(folder, out_prefix="altered_")

    if outputs:
        lines = [f"Saved {len(outputs)} file(s):"] + [f"• {p.name}" for p in outputs[:10]]
        if len(outputs) > 10:
            lines.append(f"...and {len(outputs)-10} more.")
        show_message("Done", "\n".join(lines))
    else:
        show_message("Done", "No changes saved. (See log messages for details.)")


if __name__ == "__main__":
    main()