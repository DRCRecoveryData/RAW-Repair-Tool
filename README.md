# RAW-Repair-Tool

![2024-04-30_074243](https://github.com/DRCRecoveryData/RAW-Repair-Tool/assets/85211068/a471ba57-58f2-4103-bf0a-e4dd94b2e1bf)


This is a PyQt6-based desktop application for repairing corrupted image files. The tool supports repairing two types of image files: CR2 (Canon RAW) and ARW/NEF (Sony/ Nikon RAW). It can automatically detect the file extension of the reference file to determine the type of files to repair.

## Features:
- Repair corrupted CR2 (Canon RAW) files.
- Repair corrupted ARW/NEF (Sony/Nikon RAW) files.
- Automatic detection of file extension for reference file.
- Option to convert repaired files to TIFF format.
- Progress bar to track repair process.
- Log box to display repair progress and messages.
- Cross-platform compatibility (Windows, macOS, Linux).

## How to Use:
1. Select the reference file (CR2, ARW, or NEF) used for repair.
2. Choose the folder containing the corrupted image files.
3. Optionally, select the option to convert repaired files to TIFF format.
4. Click the "Repair" button to start the repair process.
5. Monitor the repair progress in the progress bar and log box.
6. Once the repair is complete, repaired files will be saved in the "Repaired" folder, and if conversion was selected, TIFF files will be saved in the "Converted" folder.

## Technologies Used:
- Python 3
- PyQt6
- rawpy
- imageio

```pip install pyqt6 rawpy imageio```

## Contributions:
Contributions are welcome! If you encounter any issues or have suggestions for improvements, feel free to open an issue or submit a pull request.
