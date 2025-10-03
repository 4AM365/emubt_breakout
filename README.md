# EMUBT Table Export / Re-ingest Tools

These are two small utilities for working with `.emubt` files that contain XML-encoded tables. The .exe files are located in the 'dist' folder.

---

## 1. `emubt_to_csv.exe`

**Purpose:**  
Scans for `.emubt` files in the specified folder and exports each table to a CSV file.

**Details:**
- Output CSVs are named:  <your_table_filename>__<ecumaster_table_name>.csv

- Tables are written out as a grid, either in decimal or hex format (default = decimal).
- The original `.emubt` files are never modified.

**Usage:**
- Run emubt_to_csv.exe (double-click or from command line).
- Enter the emubt folder path into the pop-up and press enter, or navigate traditionally.
- CSVs will appear alongside the `.emubt` files.

---

## 2. `csv_to_emubt.exe`

**Purpose:**  
Reads CSVs exported in the format above and re-encodes them back into `.emubt` files.

**Details:**
- Looks for CSVs named with the `__` separator.  
- Matches them to the corresponding `<symbol>` inside the source `.emubt`.  
- Writes a new file named: altered_<original>.emubt

- Only updates symbols where valid CSVs are found.

**Usage:**
- Run 'csv_to_emubt.exe'
- Enter the emubt folder path into the pop-up and press enter, or navigate traditionally.
- Altered `.emubt` files will be written with the `altered_` prefix.

---

## Notes

- Only `.emubt` files in the same directory are processed.  
- The original `.emubt` files are never overwritten—output uses new filenames.  
- Works when packaged as `.exe` with PyInstaller.  
- Tested on EMU Black v2
---

