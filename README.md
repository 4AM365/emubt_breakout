# EMUBT Table Export / Re-ingest Tools

These are two small utilities for working with `.emubt` files that contain XML-encoded tables.

---

## 1. `emubt_export`

**Purpose:**  
Scans for `.emubt` files in the same folder as the program and exports each `<symbol>` table to a CSV file.

**Details:**
- Output CSVs are named:  <emubt_filename_stem>__<symbol_name>.csv

- Tables are written out as a grid, either in decimal or hex format (default = decimal).
- The original `.emubt` files are never modified.

**Usage:**
- Place `emubt_export.exe` in the same folder as your `.emubt` files.  
- Run it (double-click or from command line).  
- CSVs will appear alongside the `.emubt` files.

---

## 2. `emubt_reingest`

**Purpose:**  
Reads CSVs exported in the format above and re-encodes them back into `.emubt` files.

**Details:**
- Looks for CSVs named with the `__` separator.  
- Matches them to the corresponding `<symbol>` inside the source `.emubt`.  
- Writes a new file named: altered_<original>.emubt

- Only updates symbols where valid CSVs are found.

**Usage:**
- Place `emubt_reingest.exe` in the same folder as the `.emubt` files and CSVs.  
- Run it.  
- Altered `.emubt` files will be written with the `altered_` prefix.

---

## Notes

- Both tools automatically detect the folder they live in.  
- Only `.emubt` files in the same directory are processed.  
- The original `.emubt` files are never overwritten—output uses new filenames.  
- Works when packaged as `.exe` with PyInstaller.  

---

