from PySide6.QtCore import QThread, Signal
from datetime import datetime

class SearchWorker(QThread):
    """Worker thread for flight searches"""
    result_ready = Signal(dict)  # Just pass the result data
    search_complete = Signal()
    error_occurred = Signal(str)  # Just pass the error message

    def __init__(self, flight_scraper, flight):
        super().__init__()
        self.flight_scraper = flight_scraper
        self.flight = flight  # flight is now a dict with airline, number, depapt, line, row
        self.is_running = True

    def run(self):
        if not self.is_running:
            return
                
        try:
            result = self.flight_scraper.search_flight_info(self.flight)
            if result:
                self.result_ready.emit(result)
            else:
                self.error_occurred.emit("No results found")
        except Exception as e:
            self.error_occurred.emit(str(e))
                
        self.search_complete.emit()

    def stop(self):
        self.is_running = False


class FlightProcessor:
    def __init__(self, main_window):
        # UI reference
        self.main_window = main_window
        
        # Worker thread management
        self.search_worker = None
        self.is_processing = False
        
        # Current flight processing state
        self.current_flight = None
        self.flights_to_process = []
        
        # Text processing
        self.current_lines = []
        self.processed_lines = []
        
        # Time tracking
        self.current_sta = None
        self.current_ata = None

    def cleanup_worker(self):
        """Centralized worker cleanup"""
        if self.search_worker:
            self.search_worker.stop()
            self.search_worker.wait()
            self.search_worker.deleteLater()
            self.search_worker = None

    def start_processing(self, text):
        if self.is_processing:
            return False          
        if not text:
            return False
            
        try:
            # Remove lines which are empty or less than 11 characters
            self.current_lines = [line for line in text.splitlines() if line and len(line) >= 11]
            
            self.flights_to_process = self.main_window.flight_scraper.get_flight_list(text)
            # Initialize processed_lines with original text
            self.processed_lines = self.current_lines.copy()
            
            self.is_processing = True
            return True
            
        except Exception as e:
            print(f"Error starting processing: {str(e)}")
            return False

    def process_next_flight(self):
        if not self.flights_to_process:
            return None

        self.cleanup_worker()  # Clean up any existing worker
        
        self.current_flight = self.flights_to_process[0]  # Set current flight
        JCSY_TITLE_LINES = 2
        total = len(self.current_lines) - JCSY_TITLE_LINES
        current = self.current_flight['row'] - JCSY_TITLE_LINES
        
        # Create new worker
        self.search_worker = SearchWorker(self.main_window.flight_scraper, self.current_flight)
        return {
            'worker': self.search_worker,
            'current': current,
            'total': total,
            'flight': self.current_flight
        }

    def get_final_results(self):
        """Return the final processed text with all lines in original order"""
        return '\n'.join(self.processed_lines) if self.processed_lines else ""

    def cleanup(self):
        """Full cleanup when closing"""
        self.cleanup_worker()
        self.is_processing = False
        self.current_flight = None
        self.current_sta = None
        self.current_ata = None