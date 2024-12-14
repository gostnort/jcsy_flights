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
        self.flight = flight
        self.is_running = True

    def run(self):
        if not self.is_running:
            return
                
        try:
            result = self.flight_scraper.search_flight_info(
                self.flight['number'], 
                self.flight['depapt']
            )
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
        self.main_window = main_window
        self.search_worker = None
        self.is_processing = False
        self.current_flight = None
        self.flights_to_process = []
        self.current_lines = []
        self.processed_lines = []
        self.current_sta = None
        self.current_ata = None

    def start_processing(self, text):
        if self.is_processing:
            return False          
        if not text:
            return False
            
        try:
            self.current_lines = text.split('\n')
            self.flights_to_process = self.main_window.flight_scraper.get_flight_list(text)
            self.processed_lines = [None] * len(self.current_lines)
            
            # Copy non-flight lines directly
            for i, line in enumerate(self.current_lines):
                if line.startswith('JCSY:') or line.startswith('FLT/') or line.startswith('##'):
                    self.processed_lines[i] = line
            
            self.is_processing = True
            return True
            
        except Exception as e:
            print(f"Error starting processing: {str(e)}")
            return False

    def process_next_flight(self):
        if not self.flights_to_process:
            return None

        self.current_flight = self.flights_to_process[0]
        total = len(self.current_lines)
        current = self.current_flight['index']
        
        # Clean up previous worker if exists
        if self.search_worker:
            self.search_worker.stop()
            self.search_worker.wait()
            self.search_worker.deleteLater()
            
        # Create new worker
        self.search_worker = SearchWorker(self.main_window.flight_scraper, self.current_flight)
        return {
            'worker': self.search_worker,
            'current': current + 1,
            'total': total,
            'flight': self.current_flight
        }

    def handle_result(self, result):
        self.current_sta = result['sta']
        self.current_ata = result['ata']
        return {
            'sta': self.current_sta,
            'ata': self.current_ata,
            'delayed': self.current_ata > self.current_sta if self.current_ata else None,
            'is_flightview': not result['snippet']
        }

    def accept_current_flight(self):
        if not self.flights_to_process:
            return None
            
        flight = self.flights_to_process[0]
        new_line = None
        
        if self.current_ata:
            parts = flight['line'].split()
            if len(parts) >= 2:
                ata_time = self.current_ata.strftime("%H%M")
                new_line = f"{parts[0]} /{parts[1].strip('/')}  {ata_time}"
                if len(parts) > 2:
                    new_line += " " + " ".join(parts[2:])
                self.processed_lines[flight['index']] = new_line
        
        self.flights_to_process.pop(0)
        self.current_sta = None
        self.current_ata = None
        
        return new_line

    def reject_current_flight(self):
        if not self.flights_to_process:
            return None
            
        flight = self.flights_to_process[0]
        self.processed_lines[flight['index']] = flight['line']
        self.flights_to_process.pop(0)
        return flight['line']

    def get_final_results(self):
        """
        Return the final processed text with all lines in original order
        """
        # Filter out None values but maintain original order
        result_lines = []
        for line in self.processed_lines:
            if line is not None:
                result_lines.append(line)
        return '\n'.join(result_lines) if result_lines else ""

    def cleanup(self):
        if self.search_worker:
            self.search_worker.stop()
            self.search_worker.wait()
            self.search_worker.deleteLater()
            self.search_worker = None
        self.is_processing = False 