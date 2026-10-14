import sys
import os
import glob
import time
import traceback

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QLineEdit, QFileDialog, QProgressBar,
    QTextEdit, QMessageBox, QCheckBox, QGroupBox, QFrame,
    QMainWindow
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QPalette, QColor

import rawpy
import imageio


# ---------------------------------------------------------------------------
# Worker Thread
# ---------------------------------------------------------------------------
class FileRepairWorker(QThread):
    progress_updated = pyqtSignal(int)
    log_updated = pyqtSignal(str)
    repair_finished = pyqtSignal(str, bool)   # message, success
    tiff_converted = pyqtSignal(str)

    def __init__(self, reference_file_path, encrypted_folder_path,
                 convert_to_tiff, convert_folder):
        super().__init__()
        self.reference_file_path = reference_file_path
        self.encrypted_folder_path = encrypted_folder_path
        self.convert_to_tiff = convert_to_tiff
        self.convert_folder = convert_folder
        self.file_extension = None
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    # ------------------------- main loop --------------------------------
    def run(self):
        try:
            self.detect_file_extension()
            repaired_folder_path = os.path.join(self.encrypted_folder_path, "Repaired")
            os.makedirs(repaired_folder_path, exist_ok=True)

            if self.convert_to_tiff and self.convert_folder:
                os.makedirs(self.convert_folder, exist_ok=True)

            all_files = glob.glob(os.path.join(self.encrypted_folder_path, '*.*'))
            encrypted_files = [
                f for f in all_files
                if f".{self.file_extension.lower()}." in f.lower()
            ]
            total_files = len(encrypted_files)

            if total_files == 0:
                self.repair_finished.emit(
                    "No encrypted files found to repair.", False
                )
                return

            self.log_updated.emit(
                f"Found {total_files} encrypted file(s) to process."
            )

            for i, encrypted_file in enumerate(encrypted_files):
                if self._cancelled:
                    self.repair_finished.emit("Operation cancelled by user.", False)
                    return

                base = os.path.basename(encrypted_file)
                file_name = base.split(f".{self.file_extension.lower()}.")[0]

                progress_value = (i + 1) * 100 // total_files
                self.progress_updated.emit(progress_value)
                self.log_updated.emit(f"[{i + 1}/{total_files}] Processing {file_name}...")

                repaired_file_path = os.path.join(
                    repaired_folder_path,
                    f"{file_name}.{self.file_extension.lower()}"
                )

                try:
                    if self.file_extension.upper() == "CR2":
                        self.repair_cr2_file(
                            encrypted_file, self.reference_file_path, repaired_file_path
                        )
                    else:
                        self.repair_arw_nef_file(
                            encrypted_file, self.reference_file_path, repaired_file_path
                        )
                except Exception as e:
                    self.log_updated.emit(f"  ✗ Repair failed for {file_name}: {e}")
                    continue

                self.log_updated.emit(f"  ✓ Repaired → {repaired_file_path}")

                if self.convert_to_tiff and self.convert_folder:
                    tiff_file_path = os.path.join(
                        self.convert_folder, f"{file_name}.TIFF"
                    )
                    try:
                        self.save_as_tiff(repaired_file_path, tiff_file_path)
                        self.tiff_converted.emit(f"  ✓ TIFF saved → {tiff_file_path}")
                    except Exception as e:
                        self.log_updated.emit(f"  ✗ TIFF conversion failed: {e}")

            msg = f"Repaired files saved to:\n{repaired_folder_path}"
            if self.convert_to_tiff and self.convert_folder:
                msg += f"\n\nTIFF files saved to:\n{self.convert_folder}"
            self.repair_finished.emit(msg, True)

        except Exception:
            self.repair_finished.emit(
                "Unexpected error:\n" + traceback.format_exc(), False
            )

    # ------------------------- helpers ----------------------------------
    def detect_file_extension(self):
        _, ext = os.path.splitext(self.reference_file_path)
        self.file_extension = ext.lstrip(".").upper()

    def repair_cr2_file(self, encrypted_file, reference_file, output_file):
        with open(reference_file, 'rb') as f:
            buf = bytearray(f.read())
            pos = buf.rfind(b'\xFF\xD8\xFF\xC4')
            reference_header = buf[:pos] if pos != -1 else buf
            if len(reference_header) > 0x65:
                reference_header[0x62:0x65] = b'\0\0\0'

        with open(encrypted_file, 'rb') as f:
            buf = bytearray(f.read())
            pos = buf.rfind(b'\xFF\xD8\xFF\xC4')
            actual_body = buf[pos:] if pos != -1 else buf

        with open(output_file, 'wb') as f:
            f.write(reference_header)
            f.write(actual_body)

    def repair_arw_nef_file(self, encrypted_file, reference_file, output_file):
        ref_start, ref_end = self.find_raw_data_bounds(reference_file)
        corrupt_start, corrupt_end = self.find_raw_data_bounds(encrypted_file)
        self.merge_and_save_repaired_file(
            reference_file, encrypted_file, output_file,
            ref_end, corrupt_start, corrupt_end
        )

    def find_raw_data_bounds(self, file_path):
        with open(file_path, 'rb') as f:
            data = f.read()
            last_offset = data.rfind(b'\xFF\xD9\x00\x00')
            return last_offset, len(data)

    def merge_and_save_repaired_file(self, reference_file_path, corrupt_file_path,
                                     output_file_path, ref_end,
                                     corrupt_start, corrupt_end):
        with open(reference_file_path, 'rb') as ref_file, \
             open(corrupt_file_path, 'rb') as corrupt_file, \
             open(output_file_path, 'wb') as output_file:
            output_file.write(ref_file.read(ref_end))
            if corrupt_start < ref_end:
                output_file.write(bytearray(ref_end - corrupt_start))
            corrupt_file.seek(corrupt_start)
            output_file.write(corrupt_file.read(corrupt_end - corrupt_start))

    def save_as_tiff(self, input_file, output_file):
        with rawpy.imread(input_file) as raw:
            rgb = raw.postprocess()
        imageio.imsave(output_file, rgb)


# ---------------------------------------------------------------------------
# Path Input Row
# ---------------------------------------------------------------------------
class PathRow(QWidget):
    """A reusable row with a label, read-only path field and browse button."""

    def __init__(self, label_text, browse_callback, placeholder=""):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.label = QLabel(label_text)
        self.label.setFixedWidth(120)
        self.label.setStyleSheet("font-weight: 600; color: #c5c9d1;")

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(placeholder)
        self.path_edit.setReadOnly(True)
        self.path_edit.setStyleSheet("""
            QLineEdit {
                padding: 8px 10px;
                border: 1px solid #3f4248;
                border-radius: 6px;
                background: #2b2d31;
                color: #d7dae0;
                selection-background-color: #2f7fd1;
            }
            QLineEdit:focus {
                border: 1px solid #2f7fd1;
                background: #303236;
            }
            QLineEdit:read-only { color: #a9b1bd; }
        """)

        self.browse_button = QPushButton("Browse")
        self.browse_button.setFixedWidth(90)
        self.browse_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.browse_button.clicked.connect(browse_callback)

        layout.addWidget(self.label)
        layout.addWidget(self.path_edit, 1)
        layout.addWidget(self.browse_button)

    def set_path(self, path):
        self.path_edit.setText(path)

    def get_path(self):
        return self.path_edit.text().strip()

    def set_enabled(self, enabled):
        self.browse_button.setEnabled(enabled)


# ---------------------------------------------------------------------------
# Main Window
# ---------------------------------------------------------------------------
class FileRepairApp(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Raw Repair Tool")
        self.setMinimumSize(680, 620)

        self.convert_folder = ""
        self.worker = None

        self._build_ui()
        self._apply_styles()

    # ------------------------- UI construction --------------------------
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(16)

        # Header
        title = QLabel("RAW File Repair Tool")
        title.setStyleSheet(
            "font-size: 22px; font-weight: 700; color: #f0f2f5;"
        )
        subtitle = QLabel(
            "Repair encrypted RAW files (ARW · NEF · CR2) using a valid reference file."
        )
        subtitle.setStyleSheet("color: #8a919b; font-size: 13px;")

        root.addWidget(title)
        root.addWidget(subtitle)

        # Separator
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #34363b;")
        root.addWidget(line)

        # Input group
        input_group = QGroupBox("Input")
        input_layout = QVBoxLayout(input_group)
        input_layout.setSpacing(12)

        self.reference_row = PathRow(
            "Reference File",
            self.browse_reference_file,
            "Select a valid RAW file to use as reference…"
        )
        self.encrypted_row = PathRow(
            "Encrypted Folder",
            self.browse_encrypted_folder,
            "Select the folder containing encrypted files…"
        )
        self.convert_row = PathRow(
            "TIFF Output Folder",
            self.browse_convert_folder,
            "Select folder for TIFF output (optional)…"
        )

        self.convert_checkbox = QCheckBox("Convert repaired files to TIFF")
        self.convert_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        self.convert_checkbox.stateChanged.connect(self.toggle_convert_checkbox)

        self.convert_row.setVisible(False)

        input_layout.addWidget(self.reference_row)
        input_layout.addWidget(self.encrypted_row)
        input_layout.addWidget(self.convert_checkbox)
        input_layout.addWidget(self.convert_row)

        root.addWidget(input_group)

        # Log group
        log_group = QGroupBox("Log")
        log_layout = QVBoxLayout(log_group)
        log_layout.setContentsMargins(12, 16, 12, 12)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setPlaceholderText("Processing log will appear here…")
        self.log_box.setStyleSheet("""
            QTextEdit {
                background: #17181a;
                color: #d7dae0;
                border: 1px solid #2f3136;
                border-radius: 6px;
                padding: 8px;
                font-family: 'Menlo', 'Consolas', monospace;
                font-size: 12px;
                selection-background-color: #2f7fd1;
            }
        """)
        log_layout.addWidget(self.log_box)
        root.addWidget(log_group, 1)

        # Progress + buttons
        bottom = QVBoxLayout()
        bottom.setSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFixedHeight(22)

        self.status_label = QLabel("Ready.")
        self.status_label.setStyleSheet("color: #8a919b; font-size: 12px;")

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.repair_button = QPushButton("Start Repair")
        self.repair_button.setObjectName("primaryButton")
        self.repair_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.repair_button.setFixedHeight(42)
        self.repair_button.clicked.connect(self.repair_files)

        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setObjectName("dangerButton")
        self.cancel_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_button.setFixedHeight(42)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_repair)

        self.clear_button = QPushButton("Clear Log")
        self.clear_button.setObjectName("ghostButton")
        self.clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_button.setFixedHeight(42)
        self.clear_button.clicked.connect(self.log_box.clear)

        btn_row.addWidget(self.repair_button, 2)
        btn_row.addWidget(self.cancel_button, 1)
        btn_row.addWidget(self.clear_button, 1)

        bottom.addWidget(self.progress_bar)
        bottom.addWidget(self.status_label)
        bottom.addLayout(btn_row)
        root.addLayout(bottom)

    # ------------------------- Styling ----------------------------------
    def _apply_styles(self):
        self.setStyleSheet("""
            /* ---------- Global ---------- */
            QMainWindow, QWidget {
                background: #1e1f22;
                font-family: 'Segoe UI', 'Inter', sans-serif;
                font-size: 13px;
                color: #d7dae0;
            }

            QLabel {
                color: #d7dae0;
                background: transparent;
            }

            /* ---------- Group boxes ---------- */
            QGroupBox {
                border: 1px solid #34363b;
                border-radius: 10px;
                margin-top: 14px;
                padding-top: 14px;
                font-weight: 600;
                color: #a9b1bd;
                background: #26282c;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 14px;
                padding: 0 6px;
                background: #1e1f22;
                color: #8ab4f8;
            }

            /* ---------- Generic buttons ---------- */
            QPushButton {
                background: #34363b;
                color: #d7dae0;
                border: 1px solid #3f4248;
                border-radius: 6px;
                padding: 6px 12px;
                font-weight: 500;
            }
            QPushButton:hover    { background: #3f4248; border-color: #4a4d54; }
            QPushButton:pressed  { background: #2b2d31; }
            QPushButton:disabled {
                background: #26282c;
                color: #5c6169;
                border-color: #2f3136;
            }

            /* ---------- Primary ---------- */
            QPushButton#primaryButton {
                background: #2f7fd1;
                color: #ffffff;
                border: none;
                font-size: 15px;
                font-weight: 600;
            }
            QPushButton#primaryButton:hover    { background: #3b8fe0; }
            QPushButton#primaryButton:pressed  { background: #276cb2; }
            QPushButton#primaryButton:disabled { background: #2a4a68; color: #7f8b99; }

            /* ---------- Danger ---------- */
            QPushButton#dangerButton {
                background: #3a2626;
                color: #f28b82;
                border: 1px solid #5a3030;
                font-size: 15px;
                font-weight: 600;
            }
            QPushButton#dangerButton:hover    { background: #4a2e2e; }
            QPushButton#dangerButton:disabled {
                background: #26282c;
                color: #5c6169;
                border-color: #2f3136;
            }

            /* ---------- Ghost ---------- */
            QPushButton#ghostButton {
                background: transparent;
                color: #a9b1bd;
                border: 1px solid #3f4248;
                font-size: 15px;
            }
            QPushButton#ghostButton:hover { background: #2b2d31; }

            /* ---------- Progress bar ---------- */
            QProgressBar {
                border: 1px solid #3f4248;
                border-radius: 6px;
                background: #26282c;
                text-align: center;
                color: #d7dae0;
                font-weight: 600;
            }
            QProgressBar::chunk {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2f7fd1, stop:1 #56a8f5
                );
                border-radius: 5px;
            }

            /* ---------- Checkbox ---------- */
            QCheckBox {
                spacing: 8px;
                color: #d7dae0;
                background: transparent;
            }
            QCheckBox::indicator {
                width: 16px; height: 16px;
                border: 1px solid #4a4d54;
                border-radius: 4px;
                background: #2b2d31;
            }
            QCheckBox::indicator:hover {
                border-color: #5a5e66;
            }
            QCheckBox::indicator:checked {
                background: #2f7fd1;
                border-color: #2f7fd1;
            }

            /* ---------- Scrollbars ---------- */
            QScrollBar:vertical {
                background: #26282c;
                width: 10px;
                margin: 0;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #4a4d54;
                min-height: 24px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical:hover { background: #5a5e66; }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar::add-page:vertical,
            QScrollBar::sub-page:vertical { background: transparent; }
        """)

    # ------------------------- Callbacks --------------------------------
    def browse_reference_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Reference File",
            "",
            "Supported Files (*.ARW *.arw *.NEF *.nef *.CR2 *.cr2);;All Files (*)"
        )
        if path:
            self.reference_row.set_path(path)

    def browse_encrypted_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Encrypted Folder")
        if folder:
            self.encrypted_row.set_path(folder)

    def browse_convert_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Select TIFF Output Folder")
        if folder:
            self.convert_folder = folder
            self.convert_row.set_path(folder)
            return True
        return False

    def toggle_convert_checkbox(self, state):
        checked = self.convert_checkbox.isChecked()
        self.convert_row.setVisible(checked)

        if checked:
            if not self.convert_folder:
                if not self.browse_convert_folder():
                    self.convert_checkbox.setChecked(False)
                    self.convert_row.setVisible(False)
                    self.show_message(
                        "Warning",
                        "No TIFF output folder selected. TIFF conversion disabled.",
                        QMessageBox.Icon.Warning
                    )

    def repair_files(self):
        reference_file_path = self.reference_row.get_path()
        encrypted_folder_path = self.encrypted_row.get_path()
        convert_to_tiff = self.convert_checkbox.isChecked()

        if not reference_file_path or not os.path.exists(reference_file_path):
            self.show_message("Error", "Please select a valid reference file.",
                              QMessageBox.Icon.Critical)
            return
        if not encrypted_folder_path or not os.path.exists(encrypted_folder_path):
            self.show_message("Error", "Please select a valid encrypted folder.",
                              QMessageBox.Icon.Critical)
            return

        # reset UI for a new run
        self.progress_bar.setValue(0)
        self.log_box.clear()
        self.status_label.setText("Processing…")
        self._set_controls_enabled(False)

        self.worker = FileRepairWorker(
            reference_file_path,
            encrypted_folder_path,
            convert_to_tiff,
            self.convert_folder
        )
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.log_updated.connect(self.update_log)
        self.worker.tiff_converted.connect(self.update_log)
        self.worker.repair_finished.connect(self.repair_finished)
        self.worker.start()

    def cancel_repair(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.status_label.setText("Cancelling…")

    # ------------------------- Updates ----------------------------------
    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_log(self, message):
        timestamp = time.strftime("%H:%M:%S")
        self.log_box.append(f"[{timestamp}] {message}")
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum()
        )

    def repair_finished(self, message, success):
        self._set_controls_enabled(True)
        self.status_label.setText("Done." if success else "Finished with issues.")

        icon = QMessageBox.Icon.Information if success else QMessageBox.Icon.Warning
        title = "Success" if success else "Notice"
        self.show_message(title, message, icon)

    def _set_controls_enabled(self, enabled):
        self.repair_button.setEnabled(enabled)
        self.cancel_button.setEnabled(not enabled)
        self.convert_checkbox.setEnabled(enabled)
        self.reference_row.set_enabled(enabled)
        self.encrypted_row.set_enabled(enabled)
        self.convert_row.set_enabled(enabled)

    def show_message(self, title, message, icon=QMessageBox.Icon.Information):
        box = QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(icon)
        box.setText(message)
        box.setStandardButtons(QMessageBox.StandardButton.Ok)
        box.exec()


# ---------------------------------------------------------------------------
if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName("Raw Repair Tool")
    app.setStyle("Fusion")

    # Dark palette so native dialogs (file picker, message boxes,
    # menus, tooltips) match the stylesheet.
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window,          QColor("#1e1f22"))
    palette.setColor(QPalette.ColorRole.WindowText,      QColor("#d7dae0"))
    palette.setColor(QPalette.ColorRole.Base,            QColor("#26282c"))
    palette.setColor(QPalette.ColorRole.AlternateBase,   QColor("#2b2d31"))
    palette.setColor(QPalette.ColorRole.ToolTipBase,     QColor("#26282c"))
    palette.setColor(QPalette.ColorRole.ToolTipText,     QColor("#d7dae0"))
    palette.setColor(QPalette.ColorRole.Text,            QColor("#d7dae0"))
    palette.setColor(QPalette.ColorRole.Button,          QColor("#34363b"))
    palette.setColor(QPalette.ColorRole.ButtonText,      QColor("#d7dae0"))
    palette.setColor(QPalette.ColorRole.BrightText,      QColor("#ff6b6b"))
    palette.setColor(QPalette.ColorRole.Link,            QColor("#5dade2"))
    palette.setColor(QPalette.ColorRole.Highlight,       QColor("#2f7fd1"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    palette.setColor(QPalette.ColorGroup.Disabled,
                     QPalette.ColorRole.Text,        QColor("#5c6169"))
    palette.setColor(QPalette.ColorGroup.Disabled,
                     QPalette.ColorRole.ButtonText,  QColor("#5c6169"))
    app.setPalette(palette)

    window = FileRepairApp()
    window.show()
    sys.exit(app.exec())
