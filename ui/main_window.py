from PySide6.QtWidgets import (
    QMainWindow, 
    QWidget, 
    QVBoxLayout, 
    QHBoxLayout,
    QTextEdit, 
    QPushButton,
    QLabel,
    QFrame,
    QScrollArea,
    QInputDialog,
    QMessageBox
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
        if not text:
            self.current_flight_label.setText("Please paste flight information first!")
            return

        try:
            if not self.flight_processor.start_processing(text):
                return
                
            if 'std' not in self.flight_scraper.jcsy_flight:
                time_str, ok = QInputDialog.getText(
                    self,
                    "Manual Input Required",
                    "Enter JCSY flight departure time (24-hour format, e.g., 2220 for 10:20 PM):"
                )
                if ok and time_str:
                    if len(time_str) != 4 or not time_str.isdigit():
                        QMessageBox.warning(self, "Invalid Input", 
                            "Please enter time in 24-hour format (e.g., 2220 for 10:20 PM)")
                        return
                    else:
                        self.flight_scraper.jcsy_flight['std'] = self.flight_scraper.set_4digit_time(time_str)
                    if not self.flight_scraper.jcsy_flight['std']:
                        QMessageBox.warning(self, "Error", 
                            "Failed to set departure time. Please try again.")
                        return
                else:
                    return  # User cancelled

            self.search_button.setEnabled(False)
            # Start processing with flight processor's method
            self.update_processing_status(
                self.flight_processor.process_next_flight()
            )
            
        except Exception as e:
            self.current_flight_label.setText(f"Error: {str(e)}")


    def accept_time(self, quiet=False):
        """Accept current flight's time"""
        if self.flight_processor.flights_to_process:
            flight = self.flight_processor.flights_to_process[0]
            if self.flight_processor.current_ata:
                parts = flight['line'].split()
                if len(parts) >= 2:
                    ata_time = self.flight_processor.current_ata.strftime("%H%M")
                    if flight.get('is_yesterday', False):  # Check if it's yesterday's flight
                        ata_time = f"{ata_time}-"  # Add dash for yesterday's flight
                        new_line = f"{parts[0]} /{parts[1].strip('/')} {ata_time}"  # One less space
                    else:
                        new_line = f"{parts[0]} /{parts[1].strip('/')}  {ata_time}"  # Normal format
                    if len(parts) > 2:
                        new_line += " " + " ".join(parts[2:])
                    self.flight_processor.processed_lines[flight['row'] -1] = new_line
                    
                    if not quiet:
                        # Show processing status in current_flight_label
                        self.current_flight_label.setText(
                            f"Accepted: {new_line}\n{'-'*50}\n" + 
                            self.current_flight_label.text())
            
            self.flight_processor.flights_to_process.pop(0)
            if not quiet:
                self.set_response_buttons_enabled(False)
            
            # Clear current times
            self.flight_processor.current_sta = None
            self.flight_processor.current_ata = None
            
            # Start next flight
            QTimer.singleShot(100, lambda: self.update_processing_status(
                self.flight_processor.process_next_flight()
            ))

    def reject_time(self):
        """Reject current flight and keep original line"""
        if self.flight_processor.flights_to_process:
            flight = self.flight_processor.flights_to_process[0]
            # Keep original line
            self.flight_processor.processed_lines[flight['row']] = flight['line']
            # Show in current_flight_label
            self.current_flight_label.setText(
                f"Rejected: {flight['line']}\n{'-'*50}\n" + 
                self.current_flight_label.text())
            
            self.flight_processor.flights_to_process.pop(0)
            self.set_response_buttons_enabled(False)
            
            # Start next flight
            QTimer.singleShot(100, lambda: self.update_processing_status(
                self.flight_processor.process_next_flight()
            ))

    def handle_search_error(self, error_message):
        """Handle search error"""
        if self.flight_processor.current_flight:
            self.current_flight_label.setText(
                f"Error processing {self.flight_processor.current_flight['airline']}"
                f"{self.flight_processor.current_flight['number']} from "
                f"{self.flight_processor.current_flight['depapt']}: {error_message}\n{'-'*50}\n" + 
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
        
        self.flight_processor.is_processing = False
        self.search_button.setEnabled(True)

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
        self.flight_processor.cleanup()  # Call cleanup instead of direct worker handling
        super().closeEvent(event)

    def update_processing_status(self, process_info):
        """Update UI with current processing status and handle worker"""
        if not process_info:
            self.show_final_results()
            return

        # Show processing status
        self.current_flight_label.setText(
            f"Processing flight {process_info['current']} of {process_info['total']}: "
            f"{process_info['flight']['airline']}{process_info['flight']['number']} "
            f"from {process_info['flight']['depapt']}\n"
            f"{'-'*50}\n" + self.current_flight_label.text()
        )
        
        # Setup and start worker
        worker = process_info['worker']
        worker.result_ready.connect(self.handle_search_result)
        worker.error_occurred.connect(self.handle_search_error)
        worker.search_complete.connect(self.handle_search_complete)
        worker.start()

    def handle_search_result(self, result):
        """Handle search result"""
        if not self.flight_processor.current_flight:  # Safety check
            return
            
        # Store times in processor
        self.flight_processor.current_sta = result['sta']
        self.flight_processor.current_ata = result['ata']
        # Update current flight's is_yesterday flag
        self.flight_processor.current_flight['is_yesterday'] = result.get('is_yesterday', False)
        
        if not result['sta'] and not result['ata']:
            self.reject_time()
            return
            
        if not result['snippet'] and self.flight_processor.current_ata:
            # For FlightView results, quietly accept
            self.accept_time(quiet=True)
            # Update input text
            self.input_text.setText('\n'.join(self.flight_processor.processed_lines))
        else:
            # For FlightAware results, show in current_flight_label and wait for user input
            self.show_flightaware_result(result)

    def show_flightaware_result(self, result):
        """Show FlightAware result and wait for user input"""
        flight = self.flight_processor.current_flight
        search_result = (
            f"Processing: Flight {flight['airline']}{flight['number']} "
            f"from {flight['depapt']}\n\n"
        )
        search_result += f"{result['snippet']}\n"
        search_result += f"{'-'*50}\n"
        
        if self.flight_processor.current_sta:
            ata_delayed = (self.flight_processor.current_ata > self.flight_processor.current_sta 
                         if self.flight_processor.current_ata else None)
            self.ata_label.set_time(
                f"ATA: {self.flight_processor.current_ata.strftime('%H:%M')}" 
                if self.flight_processor.current_ata else "ATA: --:--", 
                ata_delayed
            )
            self.sta_label.set_time(
                f"STA: {self.flight_processor.current_sta.strftime('%H:%M')}" 
                if self.flight_processor.current_sta else "STA: --:--"
            )
        self.current_flight_label.setText(search_result + self.current_flight_label.text())
        self.set_response_buttons_enabled(True)