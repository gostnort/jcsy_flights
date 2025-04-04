import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from ui.parallel_main_window import ParallelMainWindow

def main():
    app = QApplication(sys.argv)
    window = ParallelMainWindow()
    window.show()
    
    # Handle cleanup on app exit
    app.aboutToQuit.connect(window.flight_processor.cleanup)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 