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
from PySide6.QtCore import Qt
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from datetime import datetime
from flight_scraper import FlightScraper

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
        self.blocked_label = TimeLabel("Gate Arrival (Blocked)")
        
        time_layout.addWidget(self.ata_label)
        time_layout.addWidget(self.sta_label)
        time_layout.addWidget(self.blocked_label)
        
        # Add widgets to layout
        layout.addWidget(input_container, 1)  # Stretch factor 1
        layout.addWidget(label_container, 1)  # Stretch factor 1
        layout.addWidget(button_widget)  # No stretch (fixed height)
        layout.addWidget(time_widget)    # No stretch (fixed height)
        
        self.flight_scraper = FlightScraper()
        self.flights_to_process = []
        self.current_lines = []
        self.processed_lines = []
        
        # Initially disable Accept/Reject/Print buttons
        self.set_response_buttons_enabled(False)
        self.print_button.setEnabled(False)
        
    def set_response_buttons_enabled(self, enabled):
        self.accept_button.setEnabled(enabled)
        self.reject_button.setEnabled(enabled)

    def show_final_results(self):
        # Filter out None values and join lines
        result = '\n'.join(line for line in self.processed_lines if line is not None)
        self.input_text.setText(result + "\n\nProcessing complete")
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
            self.current_lines = text.split('\n')
            self.flights_to_process = self.flight_scraper.get_flight_list(text)
            self.processed_lines = [None] * len(self.current_lines)  # Initialize with None
            
            # Copy non-flight lines directly
            for i, line in enumerate(self.current_lines):
                if line.startswith('JCSY:') or line.startswith('FLT/') or line.startswith('##'):
                    self.processed_lines[i] = line
                    
            self.process_next_flight()
        except Exception as e:
            self.current_flight_label.setText(f"Error: {str(e)}")
            
    def compare_times(self, time1_str, time2_str):
        """
        Compare two times in format HH:MMAM/PM
        Returns True if time1 is later than time2, considering AM/PM crossover
        """
        if not time1_str or not time2_str:
            return None
        
        time1 = datetime.strptime(time1_str, "%I:%M%p")
        time2 = datetime.strptime(time2_str, "%I:%M%p")
        
        # Check for AM/PM crossover
        time1_is_pm = "PM" in time1_str
        time2_is_pm = "PM" in time2_str
        
        if time2_is_pm and not time1_is_pm:  # STA is PM, comparison is AM
            return True  # Always delayed (red)
        elif not time2_is_pm and time1_is_pm:  # STA is AM, comparison is PM
            return True  # Always delayed (red)
        
        # Normal comparison if both are AM or both are PM
        return time1 > time2
        
    def process_next_flight(self):
        if not self.flights_to_process:
            self.show_final_results()
            return
            
        flight = self.flights_to_process[0]
        try:
            result = self.flight_scraper.search_flight_info(flight['number'], flight['origin'])
            if result:
                # Prepare new search result text
                search_result = f"Processing: Flight {flight['number']} from {flight['origin']}\n\n"
                search_result += f"{result.get('title', '')}\n"
                search_result += f"{result.get('snippet', '')}\n"
                search_result += f"{'-'*50}\n"  # Add separator line at the end
                
                # Prepend new text to existing content
                current_text = self.current_flight_label.text()
                self.current_flight_label.setText(search_result + current_text)
                
                times = self.flight_scraper.extract_arrival_time(result)
                if times:
                    if times['sta']:  # If we have scheduled time, we can compare
                        ata_delayed = self.compare_times(times['ata'], times['sta'])
                        blocked_delayed = self.compare_times(times['blocked'], times['sta'])
                        
                        self.ata_label.set_time(times['ata'], ata_delayed)
                        self.sta_label.set_time(times['sta'])
                        self.blocked_label.set_time(times['blocked'], blocked_delayed)
                        self.set_response_buttons_enabled(True)
                    else:
                        # Prepend error message
                        self.current_flight_label.setText(
                            "Could not find scheduled time\n" + self.current_flight_label.text()
                        )
                        self.reject_time()
                else:
                    # Prepend error message
                    self.current_flight_label.setText(
                        "Could not find arrival times\n" + self.current_flight_label.text()
                    )
                    self.reject_time()
            else:
                # Prepend error message
                self.current_flight_label.setText(
                    f"No search results found for flight {flight['number']}\n{'-'*50}\n" + 
                    self.current_flight_label.text()
                )
                self.reject_time()
        except Exception as e:
            # Prepend error message
            self.current_flight_label.setText(
                f"Error: {str(e)}\n{'-'*50}\n" + 
                self.current_flight_label.text()
            )
            self.reject_time()
            
    def accept_time(self):
        if self.flights_to_process:
            flight = self.flights_to_process[0]
            result = self.flight_scraper.search_flight_info(flight['number'], flight['origin'])
            times = self.flight_scraper.extract_arrival_time(result)
            if times and times['blocked']:
                parts = flight['line'].split()
                if len(parts) >= 2:
                    # Insert blocked time after origin airport without spaces
                    new_line = f"{parts[0]} /{parts[1].strip('/')}{times['blocked']}"
                    if len(parts) > 2:
                        new_line += " ".join(parts[2:])
                    # Store in the correct position
                    self.processed_lines[flight['index']] = new_line
            
        self.flights_to_process.pop(0)
        self.set_response_buttons_enabled(False)
        self.process_next_flight()
        
    def reject_time(self):
        if self.flights_to_process:
            flight = self.flights_to_process[0]
            # Keep original line in its position
            self.processed_lines[flight['index']] = flight['line']
            # Prepend rejected flight info to result history
            self.current_flight_label.setText(
                f"Rejected: {flight['line']}\n{'-'*50}\n" + 
                self.current_flight_label.text())
            self.flights_to_process.pop(0)
        self.set_response_buttons_enabled(False)
        self.process_next_flight()

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