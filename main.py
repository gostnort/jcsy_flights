import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from ui.main_window import MainWindow

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    
    # Handle cleanup on app exit
    app.aboutToQuit.connect(window.flight_processor.cleanup)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 