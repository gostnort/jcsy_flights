from PySide6.QtWidgets import (
    QMainWindow, 
    QWidget, 
    QVBoxLayout, 
    QHBoxLayout,
    QTextEdit, 
    QPushButton,
    QLabel
)
from PySide6.QtGui import QFont
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from flight_scraper import FlightScraper

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flight Arrival Time Checker")
        self.setMinimumSize(670, 480)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create widgets
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Paste flight information here...")
        self.input_text.setMaximumHeight(200)
        # Set Courier New font for input_text
        self.input_font = QFont("Courier New", 12)  # Default size 10pt
        self.input_text.setFont(self.input_font)
        
        # Create button row
        button_layout = QHBoxLayout()
        
        self.search_button = QPushButton("Search Flights")
        self.search_button.clicked.connect(self.start_search)
        
        self.accept_button = QPushButton("Accept")
        self.accept_button.clicked.connect(self.accept_time)
        
        self.reject_button = QPushButton("Reject")
        self.reject_button.clicked.connect(self.reject_time)
        
        self.print_button = QPushButton("Print")
        self.print_button.clicked.connect(self.print_results)
        
        # Add buttons to button layout
        button_layout.addWidget(self.search_button)
        button_layout.addWidget(self.accept_button)
        button_layout.addWidget(self.reject_button)
        button_layout.addWidget(self.print_button)
        
        # Create result display areas
        self.current_flight_label = QLabel()
        self.current_flight_label.setWordWrap(True)
        
        # Result text for accepted times
        self.result_text = QTextEdit()
        self.result_text.setReadOnly(True)
        self.result_text.setMaximumHeight(100)
        # Set Consolas font for result_text
        self.result_font = QFont("Consolas", 12)  # Default size 10pt
        self.result_text.setFont(self.result_font)
        
        # Add widgets to layout
        layout.addWidget(self.input_text)
        layout.addLayout(button_layout)
        layout.addWidget(self.current_flight_label)
        layout.addWidget(self.result_text)
        
        self.flight_scraper = FlightScraper()
        self.flights_to_process = []
        self.current_lines = []  # Store current text lines
        self.processed_lines = []  # Store processed lines in original order
        
        # Initially disable Accept/Reject/Print buttons
        self.set_response_buttons_enabled(False)
        self.print_button.setEnabled(False)
        
    def set_response_buttons_enabled(self, enabled):
        self.accept_button.setEnabled(enabled)
        self.reject_button.setEnabled(enabled)

    def show_final_results(self):
        # Filter out None values and join lines
        result = '\n'.join(line for line in self.processed_lines if line is not None)
        self.input_text.setText(result)
        self.result_text.setText("Processing complete")
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
                    
            self.result_text.clear()
            self.process_next_flight()
        except Exception as e:
            self.current_flight_label.setText(f"Error: {str(e)}")
            
    def process_next_flight(self):
        if not self.flights_to_process:
            self.show_final_results()
            return
            
        flight = self.flights_to_process[0]
        try:
            result = self.flight_scraper.search_flight_info(flight['number'], flight['origin'])
            if result:
                search_result = f"Processing: Flight {flight['number']} from {flight['origin']}\n\n"
                search_result += f"{result.get('title', '')}\n{result.get('snippet', '')}"
                self.current_flight_label.setText(search_result)
                
                arrival_time = self.flight_scraper.extract_arrival_time(result)
                if arrival_time:
                    self.result_text.append(f"{flight['number']} arrival time: {arrival_time}")
                    self.set_response_buttons_enabled(True)
                else:
                    self.current_flight_label.setText(search_result + "\n\nCould not find arrival time in search results")
                    self.reject_time()
            else:
                self.current_flight_label.setText(self.current_flight_label.text() + f"No search results found for flight {flight['number']}")
                self.reject_time()
        except Exception as e:
            self.current_flight_label.setText(f"Error: {str(e)}")
            self.reject_time()
            
    def accept_time(self):
        if self.flights_to_process:
            flight = self.flights_to_process[0]
            result = self.flight_scraper.search_flight_info(flight['number'], flight['origin'])
            arrival_time = self.flight_scraper.extract_arrival_time(result)
            if arrival_time:
                parts = flight['line'].split()
                if len(parts) >= 2:
                    # Insert time after origin airport without spaces
                    new_line = f"{parts[0]} /{parts[1].strip('/')}{arrival_time}"
                    if len(parts) > 2:
                        new_line += " ".join(parts[2:])
                    # Store in the correct position
                    self.processed_lines[flight['index']] = new_line
                    self.result_text.append(f"Accepted: {new_line}")
            
        self.flights_to_process.pop(0)
        self.set_response_buttons_enabled(False)
        self.process_next_flight()
        
    def reject_time(self):
        if self.flights_to_process:
            flight = self.flights_to_process[0]
            # Keep original line in its position
            self.processed_lines[flight['index']] = flight['line']
            # Add rejected flight info to result history
            self.result_text.append(f"Rejected: {flight['line']}")
            self.flights_to_process.pop(0)
        self.set_response_buttons_enabled(False)
        self.process_next_flight()

    def resizeEvent(self, event):
        """Handle window resize events to adjust font sizes"""
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
        
        # Update result text font
        self.result_font.setPointSize(font_size)
        self.result_text.setFont(self.result_font)
        
        # Call parent's resize event handler
        super().resizeEvent(event)