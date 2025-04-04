from PySide6.QtCore import QThread, Signal, QObject, QMutex, QWaitCondition
from datetime import datetime
import time
import queue

class ParallelSearchWorker(QThread):
    """Worker thread for flight searches"""
    result_ready = Signal(dict, object)  # flight result, flight object
    search_complete = Signal(object)     # flight object
    error_occurred = Signal(str, object) # error message, flight object

    def __init__(self, flight_scraper, flight, worker_id):
        super().__init__()
        self.flight_scraper = flight_scraper
        self.flight = flight  # flight is now a dict with airline, number, depapt, line, row
        self.worker_id = worker_id
        self.is_running = True

    def run(self):
        if not self.is_running:
            return
                
        try:
            # Add small random delay to prevent rate limiting
            # time.sleep(0.2 * self.worker_id)
            
            result = self.flight_scraper.search_flight_info(self.flight)
            if result:
                self.result_ready.emit(result, self.flight)
            else:
                self.error_occurred.emit("No results found", self.flight)
        except Exception as e:
            self.error_occurred.emit(str(e), self.flight)
                
        self.search_complete.emit(self.flight)

    def stop(self):
        self.is_running = False


class ParallelFlightProcessor(QObject):
    """Process multiple flights in parallel"""
    
    # Signals to communicate with main window
    all_flights_processed = Signal()
    flight_result_ready = Signal(dict, object)  # result, flight
    flight_error = Signal(str, object)          # error message, flight
    processing_status_update = Signal(int, int) # current, total
    
    def __init__(self, flight_scraper, max_workers=5):
        super().__init__()
        self.flight_scraper = flight_scraper
        self.max_workers = max_workers
        
        # Thread management
        self.workers = {}
        self.is_processing = False
        self.mutex = QMutex()
        
        # Flight processing state
        self.flights_to_process = queue.Queue()
        self.flights_in_progress = set()
        self.flights_completed = set()
        
        # Text processing
        self.current_lines = []
        self.processed_lines = []
        self.processing_states = {}
        
        # Result tracking for each flight
        self.flight_results = {}

    def cleanup_workers(self):
        """Stop and clean up all worker threads"""
        for worker_id, worker in list(self.workers.items()):
            worker.stop()
            worker.wait()
            worker.deleteLater()
            self.workers.pop(worker_id, None)

    def start_processing(self, text):
        """Start processing all flights in parallel"""
        if self.is_processing:
            return False
        if not text:
            return False
            
        try:
            # Reset state
            self.cleanup_workers()
            self.flights_to_process = queue.Queue()
            self.flights_in_progress = set()
            self.flights_completed = set()
            self.flight_results = {}
            
            # Parse text
            self.current_lines = [line for line in text.splitlines() if line and len(line) >= 11]
            self.processed_lines = self.current_lines.copy()
            
            # Get flight list
            flight_list = self.flight_scraper.get_flight_list(text)
            
            # Initialize processing state and add to queue
            for flight in flight_list:
                row = flight['row']
                self.processing_states[row] = 'pending'
                self.flights_to_process.put(flight)
            
            # Start processing
            self.is_processing = True
            self.start_worker_threads()
            
            return True
            
        except Exception as e:
            print(f"Error starting parallel processing: {str(e)}")
            return False

    def start_worker_threads(self):
        """Start worker threads up to max_workers"""
        if self.flights_to_process.empty() and not self.flights_in_progress:
            # All flights processed
            self.is_processing = False
            self.all_flights_processed.emit()
            return
        
        # Start new workers up to max_workers
        while len(self.workers) < self.max_workers and not self.flights_to_process.empty():
            try:
                flight = self.flights_to_process.get(block=False)
                self.start_worker_for_flight(flight)
            except queue.Empty:
                break
    
    def start_worker_for_flight(self, flight):
        """Start a worker thread for a specific flight"""
        worker_id = flight['row']
        
        # Track flight as in progress
        self.mutex.lock()
        self.flights_in_progress.add(worker_id)
        self.processing_states[worker_id] = 'processing'
        self.mutex.unlock()
        
        # Create and start worker
        worker = ParallelSearchWorker(self.flight_scraper, flight, len(self.workers))
        worker.result_ready.connect(self.handle_worker_result)
        worker.error_occurred.connect(self.handle_worker_error)
        worker.search_complete.connect(self.handle_worker_complete)
        
        self.workers[worker_id] = worker
        worker.start()
        
        # Update processing status
        self.update_processing_status()
    
    def update_processing_status(self):
        """Emit current processing status"""
        total = len(self.processing_states)
        completed = len(self.flights_completed)
        self.processing_status_update.emit(completed, total)

    def handle_worker_result(self, result, flight):
        """Handle successful result from a worker"""
        flight_id = flight['row']
        self.flight_results[flight_id] = result
        
        # Store the result in the flight object for reference
        flight['result'] = result
        
        # Signal the result to UI
        self.flight_result_ready.emit(result, flight)
    
    def handle_worker_error(self, error_message, flight):
        """Handle error from a worker"""
        flight_id = flight['row']
        self.processing_states[flight_id] = 'error'
        
        # Signal the error to UI
        self.flight_error.emit(error_message, flight)
    
    def handle_worker_complete(self, flight):
        """Handle worker thread completion"""
        flight_id = flight['row']
        
        # Clean up the worker
        if flight_id in self.workers:
            worker = self.workers[flight_id]
            worker.stop()
            worker.wait()
            worker.deleteLater()
            self.workers.pop(flight_id)
        
        # Update flight status
        self.mutex.lock()
        if flight_id in self.flights_in_progress:
            self.flights_in_progress.remove(flight_id)
            self.flights_completed.add(flight_id)
        
        # If this flight doesn't have a result yet and isn't marked as error, mark as completed
        if flight_id not in self.flight_results and self.processing_states.get(flight_id) != 'error':
            self.processing_states[flight_id] = 'completed'
        self.mutex.unlock()
        
        # Update status and check if we need to start more workers
        self.update_processing_status()
        self.start_worker_threads()
    
    def update_flight_line(self, flight, line_text):
        """Update a specific line in the processed output"""
        row = flight['row']
        if 0 <= row - 1 < len(self.processed_lines):
            self.processed_lines[row - 1] = line_text
            self.processing_states[row] = 'completed'
    
    def get_current_results(self):
        """Return the current processed text with all lines in original order"""
        return '\n'.join(self.processed_lines) if self.processed_lines else ""
    
    def get_final_results(self):
        """Return the final processed text with all lines in original order"""
        return self.get_current_results()
    
    def cleanup(self):
        """Full cleanup when closing"""
        self.cleanup_workers()
        self.is_processing = False 