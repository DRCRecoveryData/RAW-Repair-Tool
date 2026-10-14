# RAW Repair Tool

A cross-platform desktop application for repairing corrupted RAW image files using a valid reference file. Built with Python and PyQt6.

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![PyQt6](https://img.shields.io/badge/PyQt6-6.x-green)
![License](https://img.shields.io/badge/License-MIT-yellow)

---

## Overview

**RAW Repair Tool** reconstructs damaged or partially overwritten RAW files by splicing a valid file header from a reference image with the still-intact data body of the corrupted file. It supports the two most common consumer RAW families:

| Family | Extension | Camera brands |
|--------|-----------|---------------|
| Canon RAW 2 | `.CR2` | Canon |
| Sony / Nikon RAW | `.ARW`, `.NEF` | Sony, Nikon |

The tool auto-detects the target format from the reference file you select — no manual format switching required.

---

## Screenshots

<img width="1404" height="1360" alt="image" src="https://github.com/user-attachments/assets/af9ad0cf-2ea3-443d-9010-730a50cb40c7" />

## Features

- **Automatic format detection** — reads the reference file extension to determine whether to apply CR2 or ARW/NEF repair logic.
- **Batch processing** — repairs every encrypted file found in the selected folder in one run.
- **Optional TIFF conversion** — repaired RAW files can be post-processed and exported as 16-bit TIFF via `rawpy` + `imageio`.
- **Live progress bar** — tracks how many files have been processed.
- **Timestamped log console** — shows per-file success, failure, and TIFF conversion messages.
- **Non-blocking worker thread** — the GUI stays responsive during long repair jobs.
- **Cancel support** — abort a running batch at any time.
- **Dark theme** — modern Fusion-style dark palette applied across the app and native dialogs.
- **Cross-platform** — runs on Windows, macOS, and Linux.

---

## Requirements

- **Python 3.10 or newer**
- A valid, uncorrupted RAW file to use as the reference (same camera model and format as the corrupted files).

Python dependencies are installed automatically via pip:

- [`PyQt6`](https://pypi.org/project/PyQt6/) — GUI framework
- [`rawpy`](https://pypi.org/project/rawpy/) — LibRaw wrapper for RAW decoding
- [`imageio`](https://pypi.org/project/imageio/) — image writing (TIFF output)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/DRCRecoveryData/RAW-Repair-Tool.git
cd RAW-Repair-Tool
```

### 2. Create a virtual environment (recommended)

Modern Linux distributions (Debian 12+, Ubuntu 23.04+, Fedora 38+) block system-wide `pip install` to protect the OS Python. You will see:

```
error: externally-managed-environment
```

The correct fix is a virtual environment, **not** `--break-system-packages`.

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Your shell prompt should now show `(.venv)` at the start.

> **Ubuntu note:** if `python3 -m venv` fails, install the venv support package first:
> ```bash
> sudo apt update && sudo apt install -y python3-full python3-venv
> ```
> On Python 3.14 specifically, `pip install rawpy` may attempt a source build. Install the LibRaw development headers first:
> ```bash
> sudo apt install -y build-essential libraw-dev
> ```

### 3. Install dependencies

```bash
pip install --upgrade pip
pip install PyQt6 rawpy imageio
```

### 4. Run the application

```bash
python rawrepair-gui.py
```

---

## Usage

1. **Select the reference file** — click **Browse** next to *Reference File* and pick a valid, uncorrupted RAW file (`.CR2`, `.ARW`, or `.NEF`). The extension determines which repair algorithm runs.
2. **Select the encrypted folder** — click **Browse** next to *Encrypted Folder* and pick the directory containing the corrupted files.
3. **Enable TIFF conversion** *(optional)* — tick *Convert repaired files to TIFF*. A folder picker appears; choose where the TIFF files should be written.
4. **Click Start Repair** — the worker thread begins processing every matching file in the folder.
5. **Monitor progress** — the progress bar shows overall completion, and the log console prints per-file status with timestamps.
6. **Collect results** — repaired files are written to a `Repaired/` subfolder inside the encrypted folder. If TIFF conversion was enabled, TIFFs are saved to the folder you selected.

To abort a running job, click **Cancel**. The current file finishes, then the worker stops.

---

## How It Works

### CR2 repair

CR2 files are TIFF-based containers with a proprietary header block before the IFD0 table. The repair logic:

1. Reads the reference CR2 and locates the last JPEG-end marker sequence (`FF D8 FF C4`).
2. Takes the reference header up to that marker and zeroes bytes `0x62–0x65` (a Canon-specific field that must be blanked).
3. Reads the corrupted file, keeps everything from the same marker onward (the intact image body).
4. Concatenates: **reference header** + **corrupted body**.

### ARW / NEF repair

Sony ARW and Nikon NEF files are also TIFF-derived but use a different trailer layout. The repair logic:

1. Scans the reference file for the last `FF D9 00 00` marker and records its offset.
2. Scans the corrupted file for the same marker and records its offset.
3. Writes the reference bytes up to the marker.
4. If the corrupted marker comes *before* the reference end, pads with zero bytes to align the two streams.
5. Appends the corrupted data from its marker to the end of the file.

### TIFF conversion

After a successful repair, `rawpy` decodes the reconstructed RAW into an RGB array and `imageio` writes it as a TIFF:

```python
with rawpy.imread(repaired_path) as raw:
    rgb = raw.postprocess()
imageio.imsave(tiff_path, rgb)
```

---

## Project Structure

```
RAW-Repair-Tool/
├── Images/
│   ├── Screenshot from 2024-04-30 08-02-39.png
│   └── Screenshot from 2024-04-30 08-03-16.png
├── rawrepair-gui.py      # Main application (GUI + worker thread + repair logic)
├── README.md
└── LICENSE               # (if present)
```

The entire application lives in a single file, `rawrepair-gui.py`, organised into three sections:

| Section | Responsibility |
|---------|----------------|
| `FileRepairWorker` | `QThread` subclass that runs the repair loop off the GUI thread |
| `PathRow` | Reusable widget: label + read-only path field + Browse button |
| `FileRepairApp` | `QMainWindow` holding the layout, stylesheet, and callbacks |

---

## Technologies Used

- **Python 3** — application language
- **PyQt6** — GUI framework (widgets, signals/slots, threading)
- **rawpy** — Python wrapper around LibRaw for RAW decoding
- **imageio** — TIFF writing

---

## Known Limitations

- The repair algorithms assume the corrupted file retains a valid JPEG/RGB data body; heavily truncated files may not be recoverable.
- The ARW/NEF merge logic relies on `FF D9 00 00` trailer markers; RAW variants that use different end markers may need algorithm adjustments.
- CR2 repair targets Canon's `FF D8 FF C4` marker sequence specifically.
- TIFF conversion uses default `rawpy.postprocess()` parameters (no custom white balance, demosaic algorithm, or bit-depth control).
- Only one reference file can be used per batch — all corrupted files must be from the same camera model and format.

---

## Contributing

Contributions, bug reports, and feature requests are welcome.

1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/my-improvement`).
3. Commit your changes with a clear message.
4. Open a pull request describing what you changed and why.

If you hit a repair failure on a specific camera model, please open an issue and include:
- The camera make and model
- The file extension
- The log output from the app
- (If possible) a small sample of the corrupted file and the reference file

---

## License

This project is provided as-is for personal and professional recovery use. See the repository for license details.

---

## Acknowledgements

- [LibRaw](https://www.libraw.org/) — the underlying RAW decoding library behind `rawpy`
- [rawpy](https://github.com/letmaik/rawpy) — Python bindings for LibRaw
- The PyQt6 team — GUI framework
