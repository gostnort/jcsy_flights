from PySide6.QtCore import QThread, Signal, QThreadPool, QRunnable, QObject, Slot
from datetime import datetime

class WorkerSignals(QObject):
    """Signals for worker thread communication"""
    result_ready = Signal(dict)  # Pass the result data
    error_occurred = Signal(str)  # Pass the error message
    finished = Signal()  # Signal when worker is done

class SearchWorker(QRunnable):
    """Worker runnable for flight searches"""
    def __init__(self, flight_scraper, flight):
        super().__init__()
        self.flight_scraper = flight_scraper
        self.flight = flight  # flight is now a dict with airline, number, depapt, line, row
        self.signals = WorkerSignals()
        self.is_running = True

    @Slot()
    def run(self):
        if not self.is_running:
            self.signals.finished.emit()
            return
                
        try:
            result = self.flight_scraper.search_flight_info(self.flight)
            # Always emit result, even if empty, handle logic in main thread
            self.signals.result_ready.emit(result)
        except Exception as e:
            print(f"SearchWorker error: {e}") # Log error
            self.signals.error_occurred.emit(str(e))
        finally:
            self.signals.finished.emit()

    def stop(self):
        self.is_running = False


class FlightProcessorSignals(QObject):
    """Signals for FlightProcessor to communicate with UI"""
    flight_started = Signal(dict)  # Pass flight info when processing starts
    flight_completed = Signal(dict, str)  # Pass flight info and status when processing completes
    all_flights_completed = Signal()  # Signal when all flights are processed
    status_update = Signal(str)  # General status updates


class FlightProcessor(QObject):
    def __init__(self, main_window):
        super().__init__()
        # UI reference
        self.main_window = main_window
        
        # Signals
        self.signals = FlightProcessorSignals()
        
        # Worker thread management
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(5)  # Limit to 5 threads
        self.active_workers = {}  # Track active workers by flight row
        
        # Current flight processing state
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
        
        # Processing flag
        self.is_processing = False

    def cleanup_workers(self):
        """Centralized worker cleanup"""
        # Stop all active workers
        for worker in self.active_workers.values():
            if hasattr(worker, 'stop'):
                worker.stop()
        
        # Clear the worker dictionary
        self.active_workers.clear()
        
        # Wait for all threads to finish
        self.thread_pool.waitForDone()

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
                         
            # Start processing all flights in parallel (up to max thread count)
            self.process_flights()
            
            return True
            
        except Exception as e:
            print(f"Error starting processing: {str(e)}")
            self.is_processing = False # Ensure state is reset
            return False

    def process_flights(self):
        """Process flights in parallel up to the maximum thread count"""
        # Calculate how many new workers we can start
        active_count = len(self.active_workers)
        max_new_workers = min(
            self.thread_pool.maxThreadCount() - active_count,
            len([f for f in self.flights_to_process if self.processing_states.get(f['row']) == 'pending'])
        )
        
        # Start new workers up to the limit
        for _ in range(max_new_workers):
            # Find the next pending flight
            next_flight = None
            for flight in self.flights_to_process:
                if self.processing_states.get(flight['row']) == 'pending':
                    next_flight = flight
                    break
                    
            if not next_flight:
                break  # No more pending flights
                
            # Mark as processing
            self.update_flight_state(next_flight['row'], 'processing')
            
            # Create and start worker
            worker = SearchWorker(self.main_window.flight_scraper, next_flight)
            
            # Connect signals
            worker.signals.result_ready.connect(lambda result, flight=next_flight: self.handle_result(flight, result))
            worker.signals.error_occurred.connect(lambda error, flight=next_flight: self.handle_error(flight, error))
            worker.signals.finished.connect(lambda flight=next_flight: self.handle_worker_finished(flight))
            
            # Store worker reference
            self.active_workers[next_flight['row']] = worker
            
            # Start the worker
            self.thread_pool.start(worker)
            
            # Emit signal that flight processing started
            self.signals.flight_started.emit(next_flight)
            
            # Log but don't show duplicate message
            print(f"Started processing flight {next_flight['airline']}{next_flight['number']} (Row: {next_flight['row']})")

    def handle_result(self, flight, result):
        """Handle successful flight search result"""
        self.finalize_flight_result(flight, result)
        
    def handle_error(self, flight, error):
        """Handle error in flight search"""
        error_msg = f"Error processing flight {flight['airline']}{flight['number']}: {error}"
        self.signals.status_update.emit(error_msg)
        print(error_msg)
        self.finalize_flight_result(flight, None, error=True)
        
    def handle_worker_finished(self, flight):
        """Handle worker completion and potentially start new workers"""
        # Remove from active workers
        row = flight['row']
        if row in self.active_workers:
            del self.active_workers[row]
            
        # Process next flights if any pending
        if any(self.processing_states.get(f['row']) == 'pending' for f in self.flights_to_process):
            self.process_flights()
        
        # Check if all processing is complete
        if not self.active_workers and not any(self.processing_states.get(f['row']) == 'pending' for f in self.flights_to_process):
            self.is_processing = False
            completion_msg = "All flights processed."
            self.signals.status_update.emit(completion_msg)
            print(completion_msg)
            self.signals.all_flights_completed.emit()
        
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
        
        status = "error"
        if error:
            self.update_flight_state(flight['row'], 'error')
            # Keep original line on error
            self.processed_lines[row_index] = flight['line'] 
            print(f"Kept original line for flight {flight['airline']}{flight['number']} due to error.")
        elif result and result.get('display_time') != '----':
            parts = flight['line'].split()
            if len(parts) >= 2:
                # Format: FLT /ARPT DISPLAY_TIME [RestOfLine]
                # Note: display_time already includes any 'd' prefix and '+/-' suffix
                original_spacing = " " if len(flight['line']) > len(f"{parts[0]} /{parts[1].strip('/')}") + 6 else "  "
                new_line = f"{parts[0]} /{parts[1].strip('/')}{original_spacing}{result['display_time']}"
                
                # Append remaining original parts if they exist beyond time
                time_start_approx = 18
                if len(flight['line']) > time_start_approx: 
                    potential_rest = flight['line'][time_start_approx:].lstrip()
                    if potential_rest and not potential_rest[:4].isdigit():
                        new_line += " " + potential_rest
                        
                self.processed_lines[row_index] = new_line
                self.update_flight_state(flight['row'], 'updated')
                status = "updated"
                print(f"Updated line for flight {flight['airline']}{flight['number']}: {new_line}")
            else:
                print(f"Could not format line for flight {flight['airline']}{flight['number']} - keeping original.")
                self.processed_lines[row_index] = flight['line']
                self.update_flight_state(flight['row'], 'format_error')
                status = "format_error"
        else:
            # No valid display time, keep original
            self.processed_lines[row_index] = flight['line']
            self.update_flight_state(flight['row'], 'no_time_found')
            status = "no_time_found"
            print(f"No valid time found for flight {flight['airline']}{flight['number']} - keeping original.")
            
        # Emit signal that flight processing is completed with status
        self.signals.flight_completed.emit(flight, status)

    def get_final_results(self):
        """Return the final processed text with all lines in original order"""
        return '\n'.join(self.processed_lines) if self.processed_lines else ""

    def cleanup(self):
        """Full cleanup when closing"""
        self.cleanup_workers()
        self.is_processing = False
        self.current_sta = None
        self.current_ata = None
        self.processing_states = {}