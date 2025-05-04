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
    QTabWidget,
    QTableView,
    QHeaderView,
    QAbstractItemView,
    QLineEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout
)
from PySide6.QtGui import QFont, QColor, QStandardItemModel, QStandardItem
from PySide6.QtCore import Qt, QTimer
from PySide6.QtPrintSupport import QPrinter, QPrintDialog

from src.scrapers import FlightScraper
from src.processors import FlightProcessor
from src.database import FlightDatabase
from src.ui.markdown_window import MarkdownWindow

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("JCSY Time Checker 0.5")
        self.setMinimumSize(800, 600)
        
        # Initialize database
        self.db = FlightDatabase()
        self.db.initialize_database()
        
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
        
        # Add markdown viewer button
        self.markdown_button = QPushButton("Markdown View")
        self.markdown_button.clicked.connect(self.open_markdown_viewer)
        list_type_layout.addWidget(self.markdown_button)
        # ---------------------------
        
        # Create tab widget for main/history views
        self.tab_widget = QTabWidget()
        
        # --- Create main processing tab ---
        main_tab = QWidget()
        main_layout = QVBoxLayout(main_tab)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
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
        
        # --- Configure Splitter Appearance/Behavior ---
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
        
        # Add components to main tab
        main_layout.addWidget(splitter, 1)
        main_layout.addWidget(button_widget)
        
        # Create history tab
        history_tab = QWidget()
        history_layout = QVBoxLayout(history_tab)
        
        # Create search bar for history
        search_layout = QHBoxLayout()
        search_layout.setContentsMargins(0, 0, 0, 0)
        self.history_search_input = QLineEdit()
        self.history_search_input.setPlaceholderText("Search flight history (airline, flight number, airport)...")
        self.history_search_button = QPushButton("Search")
        self.history_search_button.clicked.connect(self.search_history)
        search_layout.addWidget(self.history_search_input, 1)
        search_layout.addWidget(self.history_search_button)
        
        # Create table for flight history
        self.history_table = QTableView()
        self.history_model = QStandardItemModel()
        self.history_model.setHorizontalHeaderLabels([
            "Date", "Flight", "From", "To", "STD/STA", "ETD/ETA", "ATD/ATA", "Delayed"
        ])
        self.history_table.setModel(self.history_model)
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.history_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.history_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.history_table.doubleClicked.connect(self.show_flight_details)
        
        # Add components to history tab
        history_layout.addLayout(search_layout)
        history_layout.addWidget(self.history_table, 1)
        
        # Add reload button for history
        self.reload_history_button = QPushButton("Reload History")
        self.reload_history_button.clicked.connect(self.load_recent_flights)
        history_layout.addWidget(self.reload_history_button)
        
        # Add tabs to tab widget
        self.tab_widget.addTab(main_tab, "Process JSCY")
        self.tab_widget.addTab(history_tab, "Flight History")
        
        # Add widgets to main layout
        layout.addWidget(list_type_widget)
        layout.addWidget(self.tab_widget, 1)
        
        # Initialize scraper and processor
        self.flight_scraper = None 
        self.flight_processor = None
        
        self.print_button.setEnabled(False)
        
        # Load recent flights into history tab
        try:
            self.load_recent_flights()
        except Exception as e:
            print(f"Error loading recent flights: {str(e)}")
        
    def cleanup_app_resources(self):
        """Safely cleans up resources"""
        print("MainWindow cleanup_app_resources called...") # For debugging
        if self.flight_processor:
            print("Calling flight_processor.cleanup()...")
            self.flight_processor.cleanup()
        
        # Close database connection
        if hasattr(self, 'db'):
            self.db.close()
            
        print("Resources cleaned up.")

    def show_final_results(self):
        if self.flight_processor:
            result = self.flight_processor.get_final_results()
            if result:
                self.input_text.setText(result)
                self.print_button.setEnabled(True)
            else:
                 self.current_flight_label.setText("Processing finished, but no results generated.")
        self.search_button.setEnabled(True) # Re-enable search button
        
        # Reload flight history after processing is complete
        try:
            self.load_recent_flights()
        except Exception as e:
            print(f"Error reloading flight history: {str(e)}")
        
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
        self.cleanup_app_resources()
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
        
    def load_recent_flights(self):
        """Load recent flights into history table"""
        try:
            # Clear the current model
            self.history_model.setRowCount(0)
            
            # Get recent flights from database
            recent_flights = self.db.get_recent_flights(limit=100)
            
            # Populate table
            for flight in recent_flights:
                row = []
                
                # Format date YYYYMMDD -> YYYY-MM-DD
                date_str = flight.get('flight_date', '')
                if len(date_str) == 8:
                    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                else:
                    formatted_date = date_str
                row.append(QStandardItem(formatted_date))
                
                # Flight number
                row.append(QStandardItem(f"{flight.get('airline', '')}{flight.get('flight_number', '')}"))
                
                # Airports
                row.append(QStandardItem(flight.get('departure_airport', '')))
                row.append(QStandardItem(flight.get('arrival_airport', '')))
                
                # Times based on arrival/departure
                is_arrival = flight.get('is_arrival', True)
                if is_arrival:
                    # For arrivals, show STA
                    row.append(QStandardItem(flight.get('sta', '')))
                    row.append(QStandardItem(flight.get('eta', '')))
                    row.append(QStandardItem(flight.get('ata', '')))
                else:
                    # For departures, show STD
                    row.append(QStandardItem(flight.get('std', '')))
                    row.append(QStandardItem(flight.get('etd', '')))
                    row.append(QStandardItem(flight.get('atd', '')))
                
                # Delayed status
                is_delayed = flight.get('delayed', 0) == 1
                delayed_item = QStandardItem("Yes" if is_delayed else "No")
                if is_delayed:
                    delayed_item.setForeground(QColor("red"))
                row.append(delayed_item)
                
                # Store the flight ID in the first column for later retrieval
                row[0].setData(flight.get('id', ''), Qt.ItemDataRole.UserRole)
                
                # Add row to model
                self.history_model.appendRow(row)
                
            # Resize columns to content
            self.history_table.resizeColumnsToContents()
            
        except Exception as e:
            print(f"Error loading flight history: {str(e)}")
            
    def search_history(self):
        """Search flight history based on user input"""
        search_term = self.history_search_input.text().strip()
        if not search_term:
            self.load_recent_flights()
            return
            
        try:
            # Clear the current model
            self.history_model.setRowCount(0)
            
            # Search flights
            flights = self.db.search_flights(search_term)
            
            # Populate table
            for flight in flights:
                row = []
                
                # Format date YYYYMMDD -> YYYY-MM-DD
                date_str = flight.get('flight_date', '')
                if len(date_str) == 8:
                    formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
                else:
                    formatted_date = date_str
                row.append(QStandardItem(formatted_date))
                
                # Flight number
                row.append(QStandardItem(f"{flight.get('airline', '')}{flight.get('flight_number', '')}"))
                
                # Airports
                row.append(QStandardItem(flight.get('departure_airport', '')))
                row.append(QStandardItem(flight.get('arrival_airport', '')))
                
                # Times based on arrival/departure
                is_arrival = flight.get('is_arrival', True)
                if is_arrival:
                    # For arrivals, show STA
                    row.append(QStandardItem(flight.get('sta', '')))
                    row.append(QStandardItem(flight.get('eta', '')))
                    row.append(QStandardItem(flight.get('ata', '')))
                else:
                    # For departures, show STD
                    row.append(QStandardItem(flight.get('std', '')))
                    row.append(QStandardItem(flight.get('etd', '')))
                    row.append(QStandardItem(flight.get('atd', '')))
                
                # Delayed status
                is_delayed = flight.get('delayed', 0) == 1
                delayed_item = QStandardItem("Yes" if is_delayed else "No")
                if is_delayed:
                    delayed_item.setForeground(QColor("red"))
                row.append(delayed_item)
                
                # Store the flight ID in the first column for later retrieval
                row[0].setData(flight.get('id', ''), Qt.ItemDataRole.UserRole)
                
                # Add row to model
                self.history_model.appendRow(row)
                
            # Resize columns to content
            self.history_table.resizeColumnsToContents()
            
        except Exception as e:
            print(f"Error searching flight history: {str(e)}")
            
    def show_flight_details(self, index):
        """Show detailed information for a selected flight"""
        # Get the flight ID from the first column of the selected row
        row = index.row()
        id_index = self.history_model.index(row, 0)
        flight_id = id_index.data(Qt.ItemDataRole.UserRole)
        
        if not flight_id:
            return
            
        try:
            # Get flight details from database
            flight_details = self.db.get_flight_with_queries(flight_id)
            
            if not flight_details:
                return
                
            # Create and show dialog with flight details
            dialog = QDialog(self)
            dialog.setWindowTitle(f"Flight Details: {flight_details.get('airline', '')}{flight_details.get('flight_number', '')}")
            dialog.setMinimumSize(600, 400)
            
            layout = QVBoxLayout(dialog)
            
            # Create form layout for flight info
            form_layout = QFormLayout()
            form_layout.addRow("Flight:", QLabel(f"{flight_details.get('airline', '')}{flight_details.get('flight_number', '')}"))
            
            # Format date
            date_str = flight_details.get('flight_date', '')
            if len(date_str) == 8:
                formatted_date = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            else:
                formatted_date = date_str
            form_layout.addRow("Date:", QLabel(formatted_date))
            
            form_layout.addRow("From:", QLabel(flight_details.get('departure_airport', '')))
            form_layout.addRow("To:", QLabel(flight_details.get('arrival_airport', '')))
            
            # Add all time fields
            form_layout.addRow("Scheduled Departure Time (STD):", QLabel(flight_details.get('std', 'N/A')))
            form_layout.addRow("Estimated Departure Time (ETD):", QLabel(flight_details.get('etd', 'N/A')))
            form_layout.addRow("Actual Departure Time (ATD):", QLabel(flight_details.get('atd', 'N/A')))
            form_layout.addRow("Scheduled Arrival Time (STA):", QLabel(flight_details.get('sta', 'N/A')))
            form_layout.addRow("Estimated Arrival Time (ETA):", QLabel(flight_details.get('eta', 'N/A')))
            form_layout.addRow("Actual Arrival Time (ATA):", QLabel(flight_details.get('ata', 'N/A')))
            
            # Delayed status
            is_delayed = flight_details.get('delayed', 0) == 1
            delay_label = QLabel("Yes" if is_delayed else "No")
            if is_delayed:
                delay_label.setStyleSheet("color: red; font-weight: bold;")
            form_layout.addRow("Delayed:", delay_label)
            
            # Add JSCY line
            jscy_line = QLabel(flight_details.get('original_line', ''))
            jscy_line.setFont(QFont("Courier New", 10))
            form_layout.addRow("Original Line:", jscy_line)
            
            processed_line = QLabel(flight_details.get('processed_line', ''))
            processed_line.setFont(QFont("Courier New", 10))
            form_layout.addRow("Processed Line:", processed_line)
            
            # Add query information if available
            if flight_details.get('queries'):
                # Add a label for the queries section
                layout.addLayout(form_layout)
                layout.addWidget(QLabel("<b>Query History:</b>"))
                
                # Create table for queries
                query_table = QTableView()
                query_model = QStandardItemModel()
                query_model.setHorizontalHeaderLabels([
                    "Source", "STD", "ETD", "ATD", "STA", "ETA", "ATA", "Delayed", "Timestamp"
                ])
                
                for query in flight_details['queries']:
                    row = []
                    row.append(QStandardItem(query.get('source', '')))
                    
                    # Add all time fields
                    row.append(QStandardItem(query.get('std', '')))
                    row.append(QStandardItem(query.get('etd', '')))
                    row.append(QStandardItem(query.get('atd', '')))
                    row.append(QStandardItem(query.get('sta', '')))
                    row.append(QStandardItem(query.get('eta', '')))
                    row.append(QStandardItem(query.get('ata', '')))
                    
                    # Delayed status
                    is_delayed = query.get('delayed', 0) == 1
                    delayed_item = QStandardItem("Yes" if is_delayed else "No")
                    if is_delayed:
                        delayed_item.setForeground(QColor("red"))
                    row.append(delayed_item)
                    
                    # Format timestamp
                    timestamp = query.get('query_timestamp', '')
                    row.append(QStandardItem(timestamp))
                    
                    query_model.appendRow(row)
                
                query_table.setModel(query_model)
                query_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
                query_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
                layout.addWidget(query_table)
            else:
                layout.addLayout(form_layout)
                layout.addWidget(QLabel("No query information available"))
            
            # Add close button
            button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
            button_box.rejected.connect(dialog.reject)
            layout.addWidget(button_box)
            
            dialog.setLayout(layout)
            dialog.exec()
        except Exception as e:
            print(f"Error showing flight details: {str(e)}")

    def open_markdown_viewer(self):
        """Open the markdown viewer window"""
        try:
            # Create a FlightGet instance for the markdown window
            from bin.database.flight_db import FlightDatabase
            from bin.database.flight_get import FlightGet
            
            db = FlightDatabase()
            db.connect()
            flight_getter = FlightGet(db)
            
            # Create and show the markdown window
            markdown_window = MarkdownWindow(flight_getter, self)
            markdown_window.show()
            
            # Store reference to prevent garbage collection
            self.markdown_window = markdown_window
            
        except Exception as e:
            print(f"Error opening markdown viewer: {str(e)}")
