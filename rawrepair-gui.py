import sys
import os
import glob
from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QLabel, QLineEdit, QFileDialog, QProgressBar, QTextEdit, QMessageBox, QCheckBox
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import rawpy
import imageio

class FileRepairWorker(QThread):
    progress_updated = pyqtSignal(int)
    log_updated = pyqtSignal(str)
    repair_finished = pyqtSignal(str)
    tiff_converted = pyqtSignal(str)

    def __init__(self, reference_file_path, encrypted_folder_path, convert_to_tiff, convert_folder):
        super().__init__()
        self.reference_file_path = reference_file_path
        self.encrypted_folder_path = encrypted_folder_path
        self.convert_to_tiff = convert_to_tiff
        self.convert_folder = convert_folder
        self.file_extension = None

    def run(self):
        # Detect file extension of the reference file
        self.detect_file_extension()

        repaired_folder_path = os.path.join(self.encrypted_folder_path, "Repaired")
        os.makedirs(repaired_folder_path, exist_ok=True)

        if self.convert_to_tiff:
            converted_folder_path = os.path.join(self.encrypted_folder_path, "Converted")
            os.makedirs(converted_folder_path, exist_ok=True)

        encrypted_files = glob.glob(os.path.join(self.encrypted_folder_path, f'*.{self.file_extension}.*'))

        total_files = len(encrypted_files)

        for i, encrypted_file in enumerate(encrypted_files):
            file_name, _ = os.path.splitext(os.path.basename(encrypted_file))
            progress_value = (i + 1) * 100 // total_files
            self.progress_updated.emit(progress_value)
            self.log_updated.emit(f"Processing {file_name}...")
            repaired_file_path = os.path.join(repaired_folder_path, file_name)  # Remove extension

            if self.file_extension.upper() == "CR2":
                self.repair_cr2_file(encrypted_file, self.reference_file_path, repaired_file_path)
            else:
                self.repair_arw_nef_file(encrypted_file, self.reference_file_path, repaired_file_path)

            if self.convert_to_tiff:
                tiff_file_path = os.path.join(converted_folder_path, f"{file_name}.TIFF")  # Correct TIFF extension
                self.save_as_tiff(repaired_file_path, tiff_file_path)
                self.tiff_converted.emit(f"{file_name} converted to TIFF.")

        if self.convert_to_tiff:
            self.repair_finished.emit(f"Repaired files saved to the 'Repaired' folder.\nTIFF files converted and saved to the 'Converted' folder.")
        else:
            self.repair_finished.emit("Repaired files saved to the 'Repaired' folder.")

    def detect_file_extension(self):
        # Extract file extension from reference file path
        _, ext = os.path.splitext(self.reference_file_path)
        self.file_extension = ext.lstrip(".").upper()

    def repair_cr2_file(self, encrypted_file, reference_file, output_file):
        with open(reference_file, 'rb') as f:
            buf = bytearray(f.read())
            pos = buf.rfind(b'\xFF\xD8\xFF\xC4')
            reference_header = buf[:pos]
            reference_header[0x62:0x65] = b'\0\0\0'

        with open(encrypted_file, 'rb') as f:
            buf = bytearray(f.read())
            pos = buf.rfind(b'\xFF\xD8\xFF\xC4')
            actual_body = buf[pos:]

        with open(output_file, 'wb') as f:
            f.write(reference_header)
            f.write(actual_body)

    def repair_arw_nef_file(self, encrypted_file, reference_file, output_file):
        ref_start, ref_end = self.find_raw_data_bounds(reference_file)
        corrupt_start, corrupt_end = self.find_raw_data_bounds(encrypted_file)
        self.merge_and_save_repaired_file(reference_file, encrypted_file, output_file, ref_end, corrupt_start, corrupt_end)

    def find_raw_data_bounds(self, file_path):
        with open(file_path, 'rb') as f:
            data = f.read()
            last_offset = data.rfind(b'\xFF\xD9\x00\x00')
            file_size = len(data)
        return last_offset, file_size

    def merge_and_save_repaired_file(self, reference_file_path, corrupt_file_path, output_file_path, ref_end, corrupt_start, corrupt_end):
        with open(reference_file_path, 'rb') as ref_file, open(corrupt_file_path, 'rb') as corrupt_file, open(output_file_path, 'wb') as output_file:
            output_file.write(ref_file.read(ref_end))
            if corrupt_start < ref_end:
                zero_data_count = ref_end - corrupt_start
                zero_data = bytearray(zero_data_count)
                output_file.write(zero_data)
            corrupt_file.seek(corrupt_start)
            output_file.write(corrupt_file.read(corrupt_end - corrupt_start))

    def save_as_tiff(self, input_file, output_file):
        with rawpy.imread(input_file) as raw:
            rgb = raw.postprocess()
        base_filename = os.path.splitext(os.path.basename(input_file))[0]  # Remove extension
        output_file = os.path.join(os.path.dirname(output_file), f"{base_filename}.TIFF")
        imageio.imsave(output_file, rgb)

class FileRepairApp(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("Raw Repair Tool")
        self.setGeometry(100, 100, 400, 400)

        layout = QVBoxLayout()

        self.reference_label = QLabel("Reference File:")
        self.reference_path_edit = QLineEdit()
        self.reference_browse_button = QPushButton("Browse", self)
        self.reference_browse_button.setObjectName("browseButton")
        self.reference_browse_button.clicked.connect(self.browse_reference_file)

        self.encrypted_label = QLabel("Encrypted Folder:")
        self.encrypted_path_edit = QLineEdit()
        self.encrypted_browse_button = QPushButton("Browse", self)
        self.encrypted_browse_button.setObjectName("browseButton")
        self.encrypted_browse_button.clicked.connect(self.browse_encrypted_folder)

        self.convert_checkbox = QCheckBox("Convert to TIFF")
        self.convert_checkbox.setObjectName("convertCheckbox")
        self.convert_checkbox.stateChanged.connect(self.toggle_convert_checkbox)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)

        self.repair_button = QPushButton("Repair", self)
        self.repair_button.setObjectName("blueButton")
        self.repair_button.clicked.connect(self.repair_files)

        layout.addWidget(self.reference_label)
        layout.addWidget(self.reference_path_edit)
        layout.addWidget(self.reference_browse_button)
        layout.addWidget(self.encrypted_label)
        layout.addWidget(self.encrypted_path_edit)
        layout.addWidget(self.encrypted_browse_button)
        layout.addWidget(self.convert_checkbox)
        layout.addWidget(self.progress_bar)
        layout.addWidget(self.log_box)
        layout.addWidget(self.repair_button)

        self.setLayout(layout)

        self.setStyleSheet("""
        #browseButton, #blueButton {
            background-color: #3498db;
            border: none;
            color: white;
            padding: 10px 20px;
            font-size: 16px;
            border-radius: 4px;
        }
        #browseButton:hover, #blueButton:hover {
            background-color: #2980b9;
        }
        """)

        self.convert_folder = ""

    def browse_reference_file(self):
        reference_file, _ = QFileDialog.getOpenFileName(self, "Select Reference File", "", "Supported Files (*.ARW *.NEF *.CR2)")
        if reference_file:
            self.reference_path_edit.setText(reference_file)

    def browse_encrypted_folder(self):
        encrypted_folder = QFileDialog.getExistingDirectory(self, "Select Encrypted Folder")
        if encrypted_folder:
            self.encrypted_path_edit.setText(encrypted_folder)

    def toggle_convert_checkbox(self, state):
        if state == Qt.CheckState.Checked:
            self.convert_folder = QFileDialog.getExistingDirectory(self, "Select Converted Folder")
            if not self.convert_folder:
                self.convert_checkbox.setChecked(False)

    def repair_files(self):
        reference_file_path = self.reference_path_edit.text()
        encrypted_folder_path = self.encrypted_path_edit.text()
        convert_to_tiff = self.convert_checkbox.isChecked()

        if not os.path.exists(reference_file_path):
            self.show_message("Error", "Reference file does not exist.")
            return
        if not os.path.exists(encrypted_folder_path):
            self.show_message("Error", "Encrypted folder does not exist.")
            return

        self.worker = FileRepairWorker(reference_file_path, encrypted_folder_path, convert_to_tiff, self.convert_folder)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.log_updated.connect(self.update_log)
        self.worker.repair_finished.connect(self.repair_finished)
        self.worker.tiff_converted.connect(self.update_log)
        self.worker.start()

    def update_progress(self, value):
        self.progress_bar.setValue(value)

    def update_log(self, message):
        self.log_box.append(message)

    def repair_finished(self, message):
        self.show_message("Success", message)

    def show_message(self, title, message):
        QMessageBox.information(self, title, message)

if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = FileRepairApp()
    window.show()
    sys.exit(app.exec())
