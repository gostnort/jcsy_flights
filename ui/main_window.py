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
    QSplitter,
    QProgressBar
)
from PySide6.QtGui import QFont, QColor
from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtPrintSupport import QPrinter, QPrintDialog
from flight_scraper import FlightScraper
from flights_dispatch import FlightProcessor

class MainWindow(QMainWindow):
    # Signal to update UI from worker threads
    update_status_signal = Signal(str)
    processing_complete_signal = Signal()
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JCSY Time Checker 0.41 (Multi-threaded)")
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
        
        # --- Create Progress Bar --- 
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(20)
        self.progress_bar.setVisible(False)
        # ---------------------------
        
        # Create button row 
        CONTROL_HEIGHT = 50
        button_widget = QWidget()
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
        
        # Configure Splitter Appearance/Behavior
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
        # Set initial size ratio
        splitter.setSizes([200, 100]) # Give input more initial space
        
        # Add widgets to main layout with stretch factors
        layout.addWidget(list_type_widget)        # Stretch 0 (default)
        layout.addWidget(splitter, 1)             # Stretch 1 - contains input and label
        layout.addWidget(self.progress_bar)       # Progress bar between splitter and buttons
        layout.addWidget(button_widget)           # Buttons at the bottom
        
        # Initialize scraper and processor AFTER getting config
        self.flight_scraper = None 
        self.flight_processor = None
        
        self.print_button.setEnabled(False)
        
        # Connect signals
        self.update_status_signal.connect(self.update_status)
        self.processing_complete_signal.connect(self.show_final_results)
        
        # Processing state
        self.total_flights = 0
        self.processed_flights = 0
        
    def update_status(self, message):
        """Update status label with new message"""
        self.current_flight_label.setText(message + "\n" + self.current_flight_label.text())
        
    def update_progress(self, current, total):
        """Update progress bar based on processing state"""
        if total > 0:
            percent = int((current / total) * 100)
            self.progress_bar.setValue(percent)
            self.progress_bar.setFormat(f"Processing flights: {current}/{total} ({percent}%)")
            
            # Ensure progress bar is visible during processing
            if not self.progress_bar.isVisible():
                self.progress_bar.setVisible(True)
        
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
                self.update_status("Processing finished, but no results generated.")
        
        self.search_button.setEnabled(True) # Re-enable search button
        
        # Hide progress bar when finished, but only after showing 100%
        self.progress_bar.setValue(100)
        QTimer.singleShot(1000, lambda: self.progress_bar.setVisible(False))
        
    def print_results(self):
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dialog = QPrintDialog(printer, self)
        
        if dialog.exec() == QPrintDialog.DialogCode.Accepted:
            self.input_text.print_(printer)

    def start_search(self):
        text = self.input_text.toPlainText()
        if not text:
            self.update_status("Please paste flight information first!")
            return
            
        selected_type_id = self.list_type_group.checkedId()
        list_type = 'arrival' if selected_type_id == 1 else 'departure'
        home_airport = 'LAX' 
        
        try:
            # Reset UI first
            self.current_flight_label.setText("") # Clear existing messages
            self.print_button.setEnabled(False)
            self.search_button.setEnabled(False)
            self.progress_bar.setValue(0)
            self.progress_bar.setVisible(True)
            
            # Set up flight scraper and processor
            self.flight_scraper = FlightScraper(list_type=list_type, home_airport=home_airport)
            self.flight_processor = FlightProcessor(self)
            
            # Connect signals
            self.connect_processor_signals()
            
            # Show initial message
            self.update_status("Starting multi-threaded processing...")
            
            # Start processing
            if not self.flight_processor.start_processing(text):
                self.update_status("Error: Could not initialize processing. Check JCSY format.")
                self.search_button.setEnabled(True)
                self.progress_bar.setVisible(False)
                return
                
            if not self.flight_scraper.flightview_date:
                self.update_status("Error: Failed to parse date from JCSY line.")
                self.search_button.setEnabled(True)
                self.progress_bar.setVisible(False)
                return
                
            # Store total flights for progress tracking
            self.total_flights = self.flight_processor.initial_flight_count
            self.processed_flights = 0
            
            # Update progress with flight count
            self.update_progress(0, self.total_flights)
            
        except Exception as e:
            self.update_status(f"Error during setup: {str(e)}")
            self.search_button.setEnabled(True)
            self.progress_bar.setVisible(False)
    
    def connect_processor_signals(self):
        """Connect signals from flight processor to UI handlers"""
        if not self.flight_processor:
            return
            
        # Connect signals directly to handler methods
        self.flight_processor.signals.flight_started.connect(self.handle_flight_started)
        self.flight_processor.signals.flight_completed.connect(self.handle_flight_completed)
        self.flight_processor.signals.status_update.connect(self.update_status)
        self.flight_processor.signals.all_flights_completed.connect(self.show_final_results)
            
    def handle_flight_started(self, flight):
        """Handle when a flight search is started"""
        flight_id = f"{flight['airline']}{flight['number']}"
        self.update_status(f"Processing: {flight_id} ({flight['depapt']} -> {flight['arrapt']})")
        
    def handle_flight_completed(self, flight, status):
        """Handle when a flight search is completed"""
        flight_id = f"{flight['airline']}{flight['number']}"
        self.update_status(f"Completed: {flight_id} - Status: {status}")
        
        # Update progress tracking
        self.processed_flights += 1
        self.update_progress(self.processed_flights, self.total_flights)

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