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
    QMessageBox,
    QProgressBar
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from datetime import datetime
from flight_scraper import FlightScraper
from parallel_flight_processor import ParallelFlightProcessor

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

class ParallelMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flight Arrival Time Checker (Parallel)")
        self.setMinimumSize(720, 580)
        
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
        
        # Create progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setVisible(False)
        
        # Create flight label area with container and scroll
        label_container = QWidget()
        label_layout = QVBoxLayout(label_container)
        label_layout.setContentsMargins(0, 0, 0, 0)
        
        # Create scroll area for current_flight_label
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setMinimumHeight(140)  # Set minimum height for scroll area
        
        scroll_widget = QWidget()  # Add container widget
        scroll_layout = QVBoxLayout(scroll_widget)  # Add layout
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        
        self.current_flight_label = QLabel()
        self.current_flight_label.setWordWrap(True)
        self.current_flight_label.setMinimumHeight(140)  # Set minimum height for label
        self.current_flight_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        scroll_layout.addWidget(self.current_flight_label)
        scroll_area.setWidget(scroll_widget)  # Set container as scroll area widget
        label_layout.addWidget(scroll_area)
        
        # Create button row with fixed height
        CONTROL_HEIGHT = 70
        button_widget = QWidget()
        button_widget.setFixedHeight(CONTROL_HEIGHT)  # Fixed height for buttons
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.search_button = QPushButton("Search Flights (Parallel)")
        self.search_button.setFixedHeight(CONTROL_HEIGHT - 10)
        self.search_button.clicked.connect(self.start_search)
        
        self.auto_accept_checkbox = QLabel("Auto-accepting results")
        
        self.print_button = QPushButton("Print")
        self.print_button.setFixedHeight(CONTROL_HEIGHT - 10)
        self.print_button.clicked.connect(self.print_results)
        
        # Add buttons to button layout
        button_layout.addWidget(self.search_button)
        button_layout.addWidget(self.auto_accept_checkbox)
        button_layout.addWidget(self.print_button)
        
        # Add widgets to layout
        layout.addWidget(input_container, 1)  # Stretch factor 1
        layout.addWidget(self.progress_bar)
        layout.addWidget(label_container)
        layout.addWidget(button_widget)  # No stretch (fixed height)
        
        self.flight_scraper = FlightScraper()
        self.flight_processor = ParallelFlightProcessor(self.flight_scraper, max_workers=5)
        
        # Connect signals from parallel processor
        self.flight_processor.all_flights_processed.connect(self.handle_all_flights_processed)
        self.flight_processor.flight_result_ready.connect(self.handle_flight_result)
        self.flight_processor.flight_error.connect(self.handle_flight_error)
        self.flight_processor.processing_status_update.connect(self.update_progress)
        
        # Initially disable Print button
        self.print_button.setEnabled(False)
    
    def update_progress(self, current, total):
        """Update progress bar with current processing status"""
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
            self.progress_bar.setFormat(f"Processing flights: {current}/{total} ({percent}%)")
    
    def start_search(self):
        """Start flight search with parallel processing"""
        text = self.input_text.toPlainText()
        if not text:
            self.current_flight_label.setText("Please paste flight information first!")
            return

        try:
            # Reset UI
            self.current_flight_label.setText("")
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            
            # Check if we need manual STD input
            if 'std' not in self.flight_scraper.jcsy_flight:
                # Parse JCSY line first to see if we need manual input
                self.flight_scraper.parse_jcsy_line(text)
                
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
                            self.progress_bar.setVisible(False)
                            return
                        else:
                            self.flight_scraper.jcsy_flight['std'] = self.flight_scraper.set_4digit_time(time_str)
                        if not self.flight_scraper.jcsy_flight['std']:
                            QMessageBox.warning(self, "Error", 
                                "Failed to set departure time. Please try again.")
                            self.progress_bar.setVisible(False)
                            return
                    else:
                        self.progress_bar.setVisible(False)
                        return  # User cancelled

            # Disable search button during processing
            self.search_button.setEnabled(False)
            
            # Start parallel processing
            if not self.flight_processor.start_processing(text):
                self.search_button.setEnabled(True)
                self.progress_bar.setVisible(False)
                self.current_flight_label.setText("Error starting flight processing")
                
        except Exception as e:
            self.search_button.setEnabled(True)
            self.progress_bar.setVisible(False)
            self.current_flight_label.setText(f"Error: {str(e)}")

    def handle_flight_result(self, result, flight):
        """Handle result from a single flight"""
        # Auto-accept the result and update the flight line
        if result and result.get('ata'):
            parts = flight['line'].split()
            if len(parts) >= 2:
                ata_time = result['ata'].strftime("%H%M")
                if flight.get('is_yesterday', False) or result.get('is_yesterday', False):
                    ata_time = f"{ata_time}-"  # Add dash for yesterday's flight
                    new_line = f"{parts[0]} /{parts[1].strip('/')} {ata_time}"  # One less space
                else:
                    new_line = f"{parts[0]} /{parts[1].strip('/')}  {ata_time}"  # Normal format
                if len(parts) > 2:
                    new_line += " " + " ".join(parts[2:])
                    
                # Update the line in the processor
                self.flight_processor.update_flight_line(flight, new_line)
                
                # Update the UI text
                self.input_text.setText(self.flight_processor.get_current_results())
                
                # Add info to the log display
                ata_str = result['ata'].strftime("%I:%M%p")
                sta_str = result['sta'].strftime("%I:%M%p") if result.get('sta') else "--:--"
                is_delayed = result.get('ata') > result.get('sta') if result.get('ata') and result.get('sta') else False
                
                status = "DELAYED" if is_delayed else "ON TIME"
                self.current_flight_label.setText(
                    f"Processed: {flight['airline']}{flight['number']} from {flight['depapt']}\n"
                    f"ATA: {ata_str}, STA: {sta_str}, Status: {status}\n"
                    f"{'-'*50}\n" + self.current_flight_label.text())

    def handle_flight_error(self, error_message, flight):
        """Handle error from a single flight"""
        # Log the error
        self.current_flight_label.setText(
            f"Error processing {flight['airline']}{flight['number']} from {flight['depapt']}: {error_message}\n"
            f"{'-'*50}\n" + self.current_flight_label.text()
        )
        
    def handle_all_flights_processed(self):
        """Handle completion of all flight processing"""
        # Re-enable search button
        self.search_button.setEnabled(True)
        self.print_button.setEnabled(True)
        
        # Hide progress bar and set to 100%
        self.progress_bar.setValue(100)
        
        # Update the final text
        self.input_text.setText(self.flight_processor.get_final_results())
        
        # Display completion message
        self.current_flight_label.setText(
            f"All flights processed\n{'-'*50}\n" + self.current_flight_label.text()
        )
        
        # Hide progress bar after a delay
        QTimer.singleShot(2000, lambda: self.progress_bar.setVisible(False))
        
    def print_results(self):
        """Print the results"""
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            self.input_text.print_(printer)

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
        self.flight_processor.cleanup()
        super().closeEvent(event) 