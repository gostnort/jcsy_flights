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
            # Always emit result, even if empty, handle logic in main thread
            self.result_ready.emit(result)
        except Exception as e:
            print(f"SearchWorker error: {e}") # Log error
            self.error_occurred.emit(str(e))
        # Removed search_complete emit, handled by result/error signals

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
        
        # Track processing state for each flight
        self.processing_states = {}
        self.initial_flight_count = 0 # Store initial total

    def cleanup_worker(self):
        """Centralized worker cleanup"""
        if self.search_worker:
            self.search_worker.stop()
            self.search_worker.wait() # Wait for thread to finish
            self.search_worker.deleteLater() # Schedule for deletion
            self.search_worker = None

    def start_processing(self, text):
        if self.is_processing:
            print("Processing already in progress.")
            return False
        if not text:
            print("Input text is empty.")
            return False
            
        try:
            # Use the scraper instance from main_window
            if not self.main_window.flight_scraper:
                 raise ValueError("FlightScraper not initialized in main window.")
                 
            # Get flights using the scraper instance
            self.flights_to_process = self.main_window.flight_scraper.get_flight_list(text)
            
            # Check if JCSY parsing worked (scraper sets its date)
            if not self.main_window.flight_scraper.flightview_date:
                 # Error message already printed by scraper
                 return False
                 
            self.initial_flight_count = len(self.flights_to_process) # Store initial count
            self.current_lines = text.splitlines() # Keep original lines
            self.processed_lines = self.current_lines.copy() # Start with original
            self.processing_states = {flight['row']: 'pending' for flight in self.flights_to_process}
            self.is_processing = True
            print(f"Processing started for {self.initial_flight_count} flights.") # Use initial count
            return True
            
        except Exception as e:
            print(f"Error starting processing: {str(e)}")
            self.is_processing = False # Ensure state is reset
            return False

    def process_next_flight(self):
        """Fetches the next flight and prepares the worker, returns info or None"""
        if not self.is_processing or not self.flights_to_process:
            self.is_processing = False
            return None

        self.cleanup_worker() 
        
        self.current_flight = self.flights_to_process[0] 
        # Calculate current number based on states
        processed_count = sum(1 for state in self.processing_states.values() if state not in ['pending', 'processing'])
        current_num = processed_count + 1
        
        self.update_flight_state(self.current_flight['row'], 'processing')
        
        self.search_worker = SearchWorker(self.main_window.flight_scraper, self.current_flight)
        return {
            'worker': self.search_worker,
            'current': current_num, 
            'total': self.initial_flight_count, # Use stored initial total
            'flight': self.current_flight
        }
        
    def update_flight_state(self, row, state):
        """Update the state of a flight in processing_states"""
        if row in self.processing_states:
            self.processing_states[row] = state

    def finalize_flight_result(self, flight, result, error=False):
        """Updates processed_lines based on search result or error"""
        row_index = flight['row'] - 1
        if row_index < 0 or row_index >= len(self.processed_lines):
             print(f"Error: Invalid row index {row_index} for flight {flight['airline']}{flight['number']}")
             return # Skip update if index is bad
             
        if error:
            self.update_flight_state(flight['row'], 'error')
            # Keep original line on error
            self.processed_lines[row_index] = flight['line'] 
            print(f"Kept original line for flight {flight['airline']}{flight['number']} due to error.")
        elif result and (result.get('sta') or result.get('ata')):
            # Use ATA if available, otherwise STA
            time_to_use = result.get('ata') or result.get('sta')
            if time_to_use:
                parts = flight['line'].split()
                ata_time_str = time_to_use.strftime("%H%M")
                is_yesterday = result.get('is_yesterday', False)
                
                # Format: FLT /ARPT HHMM(-) potentially followed by other text
                if len(parts) >= 2:
                     formatted_time = f"{ata_time_str}-" if is_yesterday else f" {ata_time_str}" # Note leading space for today
                     # Rebuild line: FlightCode /Airport [ExtraSpace?]FormattedTime OriginalRestOfLine...
                     # Need careful spacing based on original line structure
                     original_spacing = " " if len(flight['line']) > len(f"{parts[0]} /{parts[1].strip('/')}") + 6 else "  " # Heuristic: check if space after airport
                     new_line = f"{parts[0]} /{parts[1].strip('/')}{original_spacing}{formatted_time.strip()}"
                     
                     # Append remaining original parts if they exist beyond time
                     # Find where original time might have started (approx char 17-19?)
                     time_start_approx = 18
                     if len(flight['line']) > time_start_approx: 
                         # Check if the rest starts with non-time chars
                         potential_rest = flight['line'][time_start_approx:].lstrip()
                         if potential_rest and not potential_rest[:4].isdigit(): # If it doesn't look like another time
                             new_line += " " + potential_rest
                             
                     self.processed_lines[row_index] = new_line
                     self.update_flight_state(flight['row'], 'updated')
                     print(f"Updated line for flight {flight['airline']}{flight['number']}: {new_line}")
                else:
                     print(f"Could not format line for flight {flight['airline']}{flight['number']} - keeping original.")
                     self.processed_lines[row_index] = flight['line']
                     self.update_flight_state(flight['row'], 'format_error')
            else:
                 # No valid time found, keep original
                 self.processed_lines[row_index] = flight['line']
                 self.update_flight_state(flight['row'], 'no_time_found')
                 print(f"No valid time found for flight {flight['airline']}{flight['number']} - keeping original.")
        else:
            # No result or no time in result, keep original
            self.processed_lines[row_index] = flight['line']
            self.update_flight_state(flight['row'], 'no_result')
            print(f"No result for flight {flight['airline']}{flight['number']} - keeping original.")
            
        # Remove the processed flight from the queue
        if self.flights_to_process and self.flights_to_process[0]['row'] == flight['row']:
            self.flights_to_process.pop(0)
        else:
             print(f"Warning: Processed flight {flight['row']} was not at the front of the queue.")

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
        self.processing_states = {}