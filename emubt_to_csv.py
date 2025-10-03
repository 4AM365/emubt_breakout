from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import csv
import re

# --- lightweight GUI (works fine in a PyInstaller exe) ----------------------
try:
    import tkinter as tk
    from tkinter import filedialog, messagebox
except Exception:
    tk = None
    filedialog = None
    messagebox = None


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


def pick_folder_gui(default_dir: Path | None = None) -> Path | None:
    """Show a native folder chooser and return a Path or None if cancelled."""
    if tk is None or filedialog is None:
        return None
    root = tk.Tk()
    root.withdraw()  # hide the empty root window
    root.update_idletasks()
    initialdir = str(default_dir) if default_dir and default_dir.exists() else str(script_dir())
    folder = filedialog.askdirectory(title="Select folder with .emubt files", initialdir=initialdir)
    root.destroy()
    return Path(folder) if folder else None


def show_message(title: str, text: str):
    # Show a message box if available; otherwise print to stdout.
    if messagebox is not None and tk is not None:
        try:
            # Need a transient root to show a message box if not already in a Tk loop
            r = tk.Tk()
            r.withdraw()
            messagebox.showinfo(title, text)
            r.destroy()
            return
        except Exception:
            pass
    print(f"[{title}] {text}")


def main():
    # If a folder was passed on the command line, use it; else, pop a GUI
    folder: Path | None = None
    if len(sys.argv) >= 2:
        folder = Path(sys.argv[1])

    if folder is None or not folder.exists():
        folder = pick_folder_gui(default_dir=script_dir())

    # If user cancels or invalid path, exit quietly
    if folder is None or not folder.exists():
        show_message("No folder selected", "Operation cancelled.")
        return

    # Immediately start processing after folder is chosen
    emubt_files = list_emubt_files(folder)
    if not emubt_files:
        show_message("No files found", f"No .emubt files found in:\n{folder}")
        return

    total_csv = 0
    errors: list[tuple[Path, str]] = []

    for emubt_file in emubt_files:
        try:
            written_csvs = emubt_to_csv_tables(emubt_file, out_dir=folder, output="decimal")
            total_csv += len(written_csvs)
        except Exception as e:
            errors.append((emubt_file, str(e)))

    # Summary dialog
    summary = [
        f"Folder: {folder}",
        f".emubt files processed: {len(emubt_files)}",
        f"CSV files written: {total_csv}",
    ]
    if errors:
        summary.append(f"Errors: {len(errors)}")
        truncated = "\n".join(f"- {p.name}: {msg}"[:300] for p, msg in errors[:5])
        if len(errors) > 5:
            truncated += f"\n...and {len(errors) - 5} more."
        summary.append(truncated)

    show_message("Done", "\n".join(summary))


if __name__ == "__main__":
    main()