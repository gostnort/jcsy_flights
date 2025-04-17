from PySide6.QtWidgets import (
    QMainWindow, 
    QWidget, 
    QVBoxLayout, 
    QHBoxLayout,
    QTextEdit, 
    QPushButton,
    QLabel,
    QScrollArea,
    QRadioButton,
    QButtonGroup,
    QSplitter
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, QTimer
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from flight_scraper import FlightScraper
from flights_dispatch import FlightProcessor

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Flight Arrival/Departure Time Checker")
        self.setMinimumSize(610, 480) # Adjusted min height after removing time labels
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(0)
        
        # --- List Type Selection --- 
        list_type_widget = QWidget()
        list_type_layout = QHBoxLayout(list_type_widget)
        list_type_layout.setContentsMargins(5, 5, 5, 5)
        list_type_label = QLabel("Flights type in the list:")
        self.arrival_radio = QRadioButton("Arrivals")
        self.departure_radio = QRadioButton("Departures")
        self.list_type_group = QButtonGroup(self)
        self.list_type_group.addButton(self.arrival_radio, 1)
        self.list_type_group.addButton(self.departure_radio, 2)
        self.arrival_radio.setChecked(True) # Default to Arrival
        list_type_layout.addWidget(list_type_label)
        list_type_layout.addWidget(self.arrival_radio)
        list_type_layout.addWidget(self.departure_radio)
        list_type_layout.addStretch()
        # ---------------------------
        
        # --- Create Splitter --- 
        splitter = QSplitter(Qt.Orientation.Vertical)
        # -----------------------
        
        # Create text input area (will be added to splitter)
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 0, 0, 0)
        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("Paste flight information here (JCSY format expected)...")
        self.input_font = QFont("Courier New", 12)
        self.input_text.setFont(self.input_font)
        input_layout.addWidget(self.input_text)
        splitter.addWidget(input_container) # Add to splitter
        
        # Create flight label area with scroll (will be added to splitter)
        label_container = QWidget()
        label_layout = QVBoxLayout(label_container)
        label_layout.setContentsMargins(0, 0, 0, 0)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        self.current_flight_label = QLabel("Status messages will appear here...")
        self.current_flight_label.setWordWrap(True)
        self.current_flight_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.current_flight_label.setStyleSheet("padding: 5px;")
        self.current_flight_label.setMinimumHeight(60)
        scroll_layout.addWidget(self.current_flight_label)
        scroll_area.setWidget(scroll_widget)
        label_layout.addWidget(scroll_area)
        splitter.addWidget(label_container) # Add to splitter
        
        # --- Configure Splitter Appearance/Behavior (Optional) ---
        splitter.setHandleWidth(5) # Make the handle slightly thicker
        splitter.setStyleSheet("""
            QSplitter::handle:vertical {
                background-color: #AAAAAA;
                height: 5px; /* Thickness of the handle */
            }
            QSplitter::handle:vertical:hover {
                background-color: #CCCCCC;
            }
        """)
        # Set initial size ratio (optional, sums don't matter, only ratio)
        splitter.setSizes([200, 100]) # Give input more initial space
        # ----------------------------------------------------------
        
        # Create button row 
        CONTROL_HEIGHT = 60
        button_widget = QWidget()
        button_widget.setFixedHeight(CONTROL_HEIGHT)
        button_layout = QHBoxLayout(button_widget)
        button_layout.setContentsMargins(0, 0, 0, 0)
        
        self.search_button = QPushButton("Process List")
        self.search_button.setFixedHeight(CONTROL_HEIGHT - 10)
        self.search_button.clicked.connect(self.start_search)
        
        self.print_button = QPushButton("Print")
        self.print_button.setFixedHeight(CONTROL_HEIGHT - 10)
        self.print_button.clicked.connect(self.print_results)
        
        button_layout.addWidget(self.search_button)
        button_layout.addWidget(self.print_button)
        
        # Add widgets to main layout with stretch factors
        layout.addWidget(list_type_widget)       # Stretch 0 (default)
        layout.addWidget(splitter, 1)    # Stretch 1
        layout.addWidget(button_widget)         # Stretch 0 (fixed height)
        
        # Initialize scraper and processor AFTER getting config
        self.flight_scraper = None 
        self.flight_processor = None
        
        self.print_button.setEnabled(False)
        
    def cleanup_app_resources(self):
        """Safely cleans up resources like the flight processor."""
        print("MainWindow cleanup_app_resources called...") # For debugging
        if self.flight_processor:
            print("Calling flight_processor.cleanup()...")
            self.flight_processor.cleanup()
        else:
            print("Flight processor was not initialized, nothing to clean up.")

    def show_final_results(self):
        if self.flight_processor:
            result = self.flight_processor.get_final_results()
            if result:
                self.input_text.setText(result)
                self.print_button.setEnabled(True)
            else:
                 self.current_flight_label.setText("Processing finished, but no results generated.")
        self.search_button.setEnabled(True) # Re-enable search button
        
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
            
        selected_type_id = self.list_type_group.checkedId()
        list_type = 'arrival' if selected_type_id == 1 else 'departure'
        home_airport = 'LAX' 
        
        try:
            self.flight_scraper = FlightScraper(list_type=list_type, home_airport=home_airport)
            self.flight_processor = FlightProcessor(self)
            
            self.current_flight_label.setText("Starting processing...")
            self.print_button.setEnabled(False)
            self.search_button.setEnabled(False)
            
            if not self.flight_processor.start_processing(text):
                self.current_flight_label.setText("Error: Could not initialize processing. Check JCSY format.")
                self.search_button.setEnabled(True)
                return
                
            if not self.flight_scraper.flightview_date:
                 self.current_flight_label.setText("Error: Failed to parse date from JCSY line.")
                 self.search_button.setEnabled(True)
                 return

            self.process_next_flight_in_queue()
            
        except Exception as e:
            self.current_flight_label.setText(f"Error during setup: {str(e)}")
            self.search_button.setEnabled(True)

    def handle_search_error(self, error_message):
        """Handle search error - Log, keep original line, move to next"""
        if self.flight_processor and self.flight_processor.current_flight:
            flight = self.flight_processor.current_flight
            print(f"Error processing flight {flight['airline']}{flight['number']}: {error_message}")
            self.current_flight_label.setText(
                f"Error on {flight['airline']}{flight['number']}: {error_message}\n" 
                f"Keeping original line: {flight['line']}\n{'-'*50}\n" +
                self.current_flight_label.text()
            )
            self.flight_processor.finalize_flight_result(flight, None, error=True)
            self.process_next_flight_in_queue()
        else:
            self.current_flight_label.setText(f"An unexpected error occurred: {error_message}")
            self.handle_search_complete() 

    def handle_search_complete(self):
        """Called when a single worker finishes (successfully or with error)"""
        # This is now less important as we trigger next flight directly
        # but good for cleanup if needed in future.
        if self.flight_processor and self.flight_processor.search_worker:
            self.flight_processor.cleanup_worker() 

    def resizeEvent(self, event):
        """Handle window resize events to adjust font sizes"""
        super().resizeEvent(event)
        width = event.size().width()
        
        # Determine font size based on window width
        if width >= 850:
            font_size = 16
        elif width >= 750:
            font_size = 14
        else:
            font_size = 11
            
        # Update input text font
        self.input_font.setPointSize(font_size)
        self.input_text.setFont(self.input_font)

    def closeEvent(self, event):
        """Handle window close event"""
        if self.flight_processor:
            self.flight_processor.cleanup()
        super().closeEvent(event)

    def process_next_flight_in_queue(self):
        """Gets the next flight from the processor and starts its worker"""
        if not self.flight_processor:
             return 
             
        process_info = self.flight_processor.process_next_flight()
        
        if not process_info:
            self.show_final_results()
            return

        self.current_flight_label.setText(
            f"Processing flight {process_info['current']} of {process_info['total']}: "
            f"{process_info['flight']['airline']}{process_info['flight']['number']} "
            f"({process_info['flight']['depapt']} -> {process_info['flight']['arrapt']})\n"
            f"Original: {process_info['flight']['line']}\n{'-'*50}\n" +
            self.current_flight_label.text()
        )
        
        self.input_text.setText('\n'.join(self.flight_processor.processed_lines))
        QTimer.singleShot(0, lambda: self.input_text.verticalScrollBar().setValue(self.input_text.verticalScrollBar().maximum()))
        
        worker = process_info['worker']
        worker.result_ready.connect(self.handle_search_result)
        worker.error_occurred.connect(self.handle_search_error)
        worker.start()

    def handle_search_result(self, result):
        """Handle search result - update line automatically"""
        if not self.flight_processor or not self.flight_processor.current_flight:
            return
            
        flight = self.flight_processor.current_flight
        
        # Let processor finalize the result (update line, state)
        self.flight_processor.finalize_flight_result(flight, result)
        
        # Show status briefly
        sta = result.get('sta')
        ata = result.get('ata')
        is_yesterday = result.get('is_yesterday', False)
        status_msg = f"Updated: {flight['airline']}{flight['number']}" if (sta or ata) else f"No time found: {flight['airline']}{flight['number']}"
        if is_yesterday: status_msg += " (Yesterday)"
        self.current_flight_label.setText(f"{status_msg}\n{'-'*50}\n" + self.current_flight_label.text())
        
        QTimer.singleShot(100, self.process_next_flight_in_queue)