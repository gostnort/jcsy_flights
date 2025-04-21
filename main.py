import sys
import os

# Add the src directory to the path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PySide6.QtWidgets import QApplication
from src.ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    
    # Connect cleanup function to application exit
    # Use the MainWindow's safe cleanup method
    app.aboutToQuit.connect(window.cleanup_app_resources)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 