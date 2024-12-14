from PySide6.QtWidgets import (
    QMainWindow, 
    QWidget, 
    QVBoxLayout, 
    QHBoxLayout,
    QTextEdit, 
    QPushButton,
    QLabel,
    QFrame,
    QScrollArea
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from datetime import datetime
from flight_scraper import FlightScraper
from flight_processor import FlightProcessor, SearchWorker

class TimeLabel(QLabel):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setFrameStyle(QFrame.Shape.Box | QFrame.Shadow.Sunken)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumWidth(50)
        # Set Segoe UI Bold font
        font = QFont("Segoe UI", 12, QFont.Weight.Bold)
        self.setFont(font)
        self.setText(f"{title}\n--:--")
        
    def set_time(self, time_str, is_delayed=None):
        if not time_str:
            self.setText("--:--")
            self.setStyleSheet("")
            return
            
        self.setText(time_str)
        if is_delayed is not None:
            # Convert HSV to RGB for stylesheet
            color = QColor.fromHsv(2, int(0.7 * 255), int(0.5 * 255)) if is_delayed else QColor.fromHsv(130, int(0.7 * 255), int(0.5 * 255))
            self.setStyleSheet(f"background-color: {color.name()};")

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flight Arrival Time Checker")
        self.setMinimumSize(680, 480)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(0)  # Remove spacing between widgets
        
        # Create text input area with container
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Paste flight information here...")
        self.input_font = QFont("Courier New", 12)
        self.input_text.setFont(self.input_font)
        input_layout.addWidget(self.input_text)
        
        # Create flight label area with container and scroll
        label_container = QWidget()
        label_layout = QVBoxLayout(label_container)
        label_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create scroll area for current_flight_label
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        self.current_flight_label = QLabel()
        self.current_flight_label.setWordWrap(True)
        self.current_flight_label.setFixedHeight(140)
        self.current_flight_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll_area.setWidget(self.current_flight_label)
        label_layout.addWidget(scroll_area)
        
        # Create button row with fixed height
        CONTROL_HEIGHT = 70
        button_widget = QWidget()
        button_widget.setFixedHeight(CONTROL_HEIGHT)  # Fixed height for buttons
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.search_button = QPushButton("Search Flights")
        self.search_button.setFixedHeight(CONTROL_HEIGHT - 10)
        self.search_button.clicked.connect(self.start_search)
        
        self.accept_button = QPushButton("Accept")
        self.accept_button.setFixedHeight(CONTROL_HEIGHT - 10)
        self.accept_button.clicked.connect(self.accept_time)
        
        self.reject_button = QPushButton("Reject")
        self.reject_button.setFixedHeight(CONTROL_HEIGHT - 10)
        self.reject_button.clicked.connect(self.reject_time)
        
        self.print_button = QPushButton("Print")
        self.print_button.setFixedHeight(CONTROL_HEIGHT - 10)
        self.print_button.clicked.connect(self.print_results)
        
        # Add buttons to button layout
        button_layout.addWidget(self.search_button)
        button_layout.addWidget(self.accept_button)
        button_layout.addWidget(self.reject_button)
        button_layout.addWidget(self.print_button)
        
        # Create time display row with fixed height
        time_widget = QWidget()
        time_widget.setFixedHeight(CONTROL_HEIGHT)  # Fixed height for time labels
        time_layout = QHBoxLayout(time_widget)
        time_layout.setContentsMargins(0, 0, 0, 0)
        
        self.ata_label = TimeLabel("Actual Arrival (ATA)")
        self.sta_label = TimeLabel("Scheduled Arrival (STA)")
        
        time_layout.addWidget(self.ata_label)
        time_layout.addWidget(self.sta_label)
        
        # Add widgets to layout
        layout.addWidget(input_container, 1)  # Stretch factor 1
        layout.addWidget(label_container)
        layout.addWidget(button_widget)  # No stretch (fixed height)
        layout.addWidget(time_widget)    # No stretch (fixed height)
        
        self.flight_scraper = FlightScraper()
        self.flight_processor = FlightProcessor(self)
        
        # Initially disable Accept/Reject/Print buttons
        self.set_response_buttons_enabled(False)
        self.print_button.setEnabled(False)
        
    def set_response_buttons_enabled(self, enabled):
        self.accept_button.setEnabled(enabled)
        self.reject_button.setEnabled(enabled)

    def show_final_results(self):
        # Get final results from flight processor
        result = self.flight_processor.get_final_results()
        if result:
            self.input_text.setText(result)
            # Enable print button when processing is complete
            self.print_button.setEnabled(True)
        
    def print_results(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            self.input_text.print_(printer)

    def start_search(self):
        text = self.input_text.toPlainText()
        if self.flight_processor.start_processing(text):
            self.search_button.setEnabled(False)
            self.process_next_flight()
        else:
            self.current_flight_label.setText("Please paste flight information first!")

    def process_next_flight(self):
        """Start searching for the next flight"""
        if not self.flight_processor.flights_to_process:
            # Only show final results when there are no more flights to process
            self.show_final_results()
            return

        self.current_flight = self.flight_processor.flights_to_process[0]  # Store current flight
        JCSY_TITLE_LINES = 2
        total = len(self.flight_processor.current_lines) - JCSY_TITLE_LINES
        current = self.current_flight['index'] - JCSY_TITLE_LINES
        
        # Show processing status
        self.current_flight_label.setText(
            f"Processing flight {current + 1} of {total}: {self.current_flight['number']} from {self.current_flight['depapt']}\n" +
            f"{'-'*50}\n" + self.current_flight_label.text()
        )
        
        # Create and start worker thread for current flight
        if self.flight_processor.search_worker:
            self.flight_processor.search_worker.stop()
            self.flight_processor.search_worker.wait()
            self.flight_processor.search_worker.deleteLater()
            
        self.flight_processor.search_worker = SearchWorker(self.flight_scraper, self.current_flight)
        self.flight_processor.search_worker.result_ready.connect(self.handle_search_result)
        self.flight_processor.search_worker.error_occurred.connect(self.handle_search_error)
        self.flight_processor.search_worker.search_complete.connect(self.handle_search_complete)
        self.flight_processor.search_worker.start()

    def handle_search_result(self, result):
        """Handle search result in main thread"""
        # Store times in member variables
        self.current_sta = result['sta']
        self.current_ata = result['ata']
        if not result['snippet'] and self.current_ata:
            self.accept_time(quiet=True)
        else:
            search_result = f"Processing: Flight {self.current_flight['number']} from {self.current_flight['depapt']}\n\n"
            search_result += f"{result['snippet']}\n"
            search_result += f"{'-'*50}\n"
            if self.current_sta:
                ata_delayed = self.current_ata > self.current_sta if self.current_ata else None
                self.ata_label.set_time(
                    f"ATA: {self.current_ata.strftime('%H:%M')}" if self.current_ata else "ATA: --:--", 
                    ata_delayed
                )
                self.sta_label.set_time(
                    f"STA: {self.current_sta.strftime('%H:%M')}" if self.current_sta else "STA: --:--"
                )
            self.current_flight_label.setText(search_result + self.current_flight_label.text())
            self.set_response_buttons_enabled(True)
            # Don't process next flight - wait for user input

    def handle_search_error(self, error_message):
        """Handle error in main thread"""
        self.current_flight_label.setText(
            f"Error processing {self.current_flight['number']} from {self.current_flight['depapt']}: {error_message}\n{'-'*50}\n" + 
            self.current_flight_label.text()
        )
        self.reject_time()

    def handle_search_complete(self):
        """Handle search completion"""
        if self.flight_processor.search_worker:
            self.flight_processor.search_worker.stop()
            self.flight_processor.search_worker.wait()
            self.flight_processor.search_worker.deleteLater()
            self.flight_processor.search_worker = None
        
        # Don't call show_final_results here
        # The final results will be shown by process_next_flight after the last flight is processed
        self.is_processing = False
        self.search_button.setEnabled(True)

    def accept_time(self, quiet=False):
        if self.flight_processor.flights_to_process:
            flight = self.flight_processor.flights_to_process[0]
            if self.current_ata:
                parts = flight['line'].split()
                if len(parts) >= 2:
                    ata_time = self.current_ata.strftime("%H%M")
                    new_line = f"{parts[0]} /{parts[1].strip('/')}  {ata_time}"
                    if len(parts) > 2:
                        new_line += " " + " ".join(parts[2:])
                    self.flight_processor.processed_lines[flight['index']] = new_line
                    
                    # Always show processing status in current_flight_label
                    self.current_flight_label.setText(
                        f"Accepted: {new_line}\n{'-'*50}\n" + 
                        self.current_flight_label.text())
            
            self.flight_processor.flights_to_process.pop(0)
            if not quiet:
                self.set_response_buttons_enabled(False)
            # Clear current times
            self.current_sta = None
            self.current_ata = None
            
            # Clean up current thread before starting next flight
            if self.flight_processor.search_worker:
                self.flight_processor.search_worker.stop()
                self.flight_processor.search_worker.wait()
                self.flight_processor.search_worker.deleteLater()
                self.flight_processor.search_worker = None
            
            # Small delay before starting next flight
            QTimer.singleShot(100, self.process_next_flight)

    def reject_time(self):
        if self.flight_processor.flights_to_process:
            flight = self.flight_processor.flights_to_process[0]
            # Keep original line in its position
            self.flight_processor.processed_lines[flight['index']] = flight['line']
            # Prepend rejected flight info to result history
            self.current_flight_label.setText(
                f"Rejected: {flight['line']}\n{'-'*50}\n" + 
                self.current_flight_label.text())
            self.flight_processor.flights_to_process.pop(0)
        self.set_response_buttons_enabled(False)
        
        # Clean up current thread before starting next flight
        if self.flight_processor.search_worker:
            self.flight_processor.search_worker.stop()
            self.flight_processor.search_worker.wait()
            self.flight_processor.search_worker.deleteLater()
            self.flight_processor.search_worker = None
            
        # Small delay before starting next flight
        QTimer.singleShot(100, self.process_next_flight)

    def resizeEvent(self, event):
        """Handle window resize events to adjust font sizes"""
        super().resizeEvent(event)
        width = event.size().width()
        
        # Determine font size based on window width
        if width >= 1280:
            font_size = 16
        elif width >= 1024:
            font_size = 14
        else:
            font_size = 12
            
        # Update input text font
        self.input_font.setPointSize(font_size)
        self.input_text.setFont(self.input_font)

    def closeEvent(self, event):
        """Handle window close event"""
        if self.flight_processor.search_worker:
            self.flight_processor.search_worker.stop()
            self.flight_processor.search_worker.wait()
            self.flight_processor.search_worker.deleteLater()
            self.flight_processor.search_worker = None
        self.is_processing = False
        super().closeEvent(event)