from PySide6.QtCore import QThread, Signal
from datetime import datetime
from src.database.flight_db import FlightDatabase
from typing import List, Dict, Any, Optional

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
    """
    Processes flight data and provides search functionality.
    """
    
    def __init__(self, flights_data: List[Dict[str, Any]]):
        """
        Initialize the flight processor with a list of flight data.
        
        Args:
            flights_data: List of dictionaries containing flight information
        """
        self.flights = flights_data
    
    def search_flights(
        self, 
        origin: Optional[str] = None, 
        destination: Optional[str] = None,
        departure_date: Optional[datetime.date] = None,
        return_date: Optional[datetime.date] = None,
        max_price: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for flights based on the provided criteria.
        
        Args:
            origin: Origin airport code
            destination: Destination airport code
            departure_date: Date of departure
            return_date: Date of return (for round trips)
            max_price: Maximum price for the flight
            
        Returns:
            List of flight dictionaries matching the search criteria
        """
        results = []
        
        for flight in self.flights:
            if origin and flight.get('origin') != origin:
                continue
                
            if destination and flight.get('destination') != destination:
                continue
                
            if departure_date and flight.get('departure_date') != departure_date:
                continue
                
            if return_date and flight.get('return_date') != return_date:
                continue
                
            if max_price and flight.get('price', float('inf')) > max_price:
                continue
                
            results.append(flight)
            
        return results
    
    def get_flight_by_id(self, flight_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a flight by its ID.
        
        Args:
            flight_id: The ID of the flight to retrieve
            
        Returns:
            The flight dictionary if found, None otherwise
        """
        for flight in self.flights:
            if flight.get('id') == flight_id:
                return flight
        return None
    
    def sort_flights_by_price(self, ascending: bool = True) -> List[Dict[str, Any]]:
        """
        Sort flights by price.
        
        Args:
            ascending: Whether to sort in ascending order (True) or descending (False)
            
        Returns:
            Sorted list of flight dictionaries
        """
        return sorted(self.flights, key=lambda x: x.get('price', float('inf')), reverse=not ascending)
    
    def sort_flights_by_duration(self, ascending: bool = True) -> List[Dict[str, Any]]:
        """
        Sort flights by duration.
        
        Args:
            ascending: Whether to sort in ascending order (True) or descending (False)
            
        Returns:
            Sorted list of flight dictionaries
        """
        return sorted(self.flights, key=lambda x: x.get('duration', float('inf')), reverse=not ascending)

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
            self.flight_db_ids = {}  # Reset database IDs
            
            # Store JSCY flights in database
            self._store_flights_in_database()
            
            self.is_processing = True
            print(f"Processing started for {self.initial_flight_count} flights.") # Use initial count
            return True
            
        except Exception as e:
            print(f"Error starting processing: {str(e)}")
            self.is_processing = False # Ensure state is reset
            return False
            
    def _store_flights_in_database(self):
        """Store all flights from the current list in the database"""
        # Get the flight date from the scraper
        flight_date = self.main_window.flight_scraper.flightview_date
        if not flight_date:
            print("Cannot store flights: No flight date available")
            return
            
        # Store each flight
        for flight in self.flights_to_process:
            flight_data = {
                'airline': flight['airline'],
                'number': flight['number'],
                'depapt': flight['depapt'],
                'arrapt': flight['arrapt'],
                'line': flight['line'],
                'flight_date': flight_date,
                'delayed': False,  # Default not delayed
                'is_arrival': self.main_window.flight_scraper.list_type == 'arrival'
            }
            
            # Add to database and store the ID
            db_id = self.db.add_jscy_flight(flight_data)
            if db_id:
                self.flight_db_ids[flight['row']] = db_id
                print(f"Flight {flight['airline']}{flight['number']} stored in database with ID {db_id}")
            else:
                print(f"Failed to store flight {flight['airline']}{flight['number']} in database")

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
        
        # Update flight status in database
        self._update_flight_status(self.current_flight['row'], 'PROCESSING')
        
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
            
    def _update_flight_status(self, row, status):
        """Update flight status in database"""
        if row in self.flight_db_ids:
            flight_id = self.flight_db_ids[row]
            # We can't directly update a status field anymore since it's been replaced
            # Instead we'll update the processing state in another field
            with self.db as db:
                # For now, just update the processed_line field with the status
                db.cursor.execute('''
                UPDATE jscy_flights
                SET processed_line = IFNULL(processed_line, '') || ' (' || ? || ')'
                WHERE id = ?
                ''', (status, flight_id))
                db.connection.commit()

    def finalize_flight_result(self, flight, result, error=False):
        """Updates processed_lines based on search result or error and stores in database"""
        row_index = flight['row'] - 1
        if row_index < 0 or row_index >= len(self.processed_lines):
             print(f"Error: Invalid row index {row_index} for flight {flight['airline']}{flight['number']}")
             return # Skip update if index is bad
             
        if error:
            self.update_flight_state(flight['row'], 'error')
            # Keep original line on error
            self.processed_lines[row_index] = flight['line'] 
            print(f"Kept original line for flight {flight['airline']}{flight['number']} due to error.")
            
            # Update database with error
            if flight['row'] in self.flight_db_ids:
                flight_id = self.flight_db_ids[flight['row']]
                self._update_flight_status(flight['row'], 'ERROR')
                
                # Store error in query results
                error_data = {
                    'display_line': flight['line'],
                    'summary': 'Error during processing',
                    'status': 'ERROR',
                    'is_complete': True,
                    'has_error': True,
                    'error_message': 'Search failed'
                }
                self.db.update_query_result(flight_id, error_data)
                
        elif result and result.get('display_time') != '----':
            # Use the display_time directly as it now includes all prefixes/suffixes
            time_to_use = result.get('display_time')
            if time_to_use:
                parts = flight['line'].split()
                # Format: FLT /ARPT [d]HHMM[*][-/+] potentially followed by other text
                if len(parts) >= 2:
                    # Always add a space after airport code, the 'd' prefix is part of the time field
                    original_spacing = " " if len(flight['line']) > len(f"{parts[0]} /{parts[1].strip('/')}") + 6 else "   "
                    new_line = f"{parts[0]} /{parts[1].strip('/')}{original_spacing}{time_to_use}"
                    
                    # confirm that the current line is included neccessary data for a flight.
                    time_start_approx = 18
                    if len(flight['line']) > time_start_approx: 
                        potential_rest = flight['line'][time_start_approx:].lstrip()
                        if potential_rest and not potential_rest[:4].isdigit():
                            new_line += " " + potential_rest
                            
                    self.processed_lines[row_index] = new_line
                    self.update_flight_state(flight['row'], 'updated')
                    print(f"Updated line for flight {flight['airline']}{flight['number']}: {new_line}")
                    
                    # Update database with result
                    if flight['row'] in self.flight_db_ids:
                        flight_id = self.flight_db_ids[flight['row']]
                        
                        # Update main flight record
                        with self.db as db:
                            # Determine if flight is delayed
                            is_delayed = False
                            
                            # For arrivals, check if ATA > STA
                            # For departures, check if ATD > STD
                            if result.get('ata') and result.get('sta'):
                                is_delayed = result['ata'] > result['sta']
                            elif result.get('atd') and result.get('std'):
                                is_delayed = result['atd'] > result['std']
                                
                            # Format times to database format
                            std_time = result.get('std').strftime('%H:%M') if result.get('std') else None
                            etd_time = result.get('etd').strftime('%H:%M') if result.get('etd') else None
                            atd_time = result.get('atd').strftime('%H:%M') if result.get('atd') else None
                            sta_time = result.get('sta').strftime('%H:%M') if result.get('sta') else None
                            eta_time = result.get('eta').strftime('%H:%M') if result.get('eta') else None
                            ata_time = result.get('ata').strftime('%H:%M') if result.get('ata') else None
                            
                            db.cursor.execute('''
                            UPDATE jscy_flights
                            SET std = ?,
                                etd = ?,
                                atd = ?,
                                sta = ?,
                                eta = ?,
                                ata = ?,
                                processed_line = ?,
                                delayed = ?
                            WHERE id = ?
                            ''', (
                                std_time,
                                etd_time, 
                                atd_time,
                                sta_time,
                                eta_time,
                                ata_time,
                                new_line,
                                1 if is_delayed else 0,
                                flight_id
                            ))
                            db.connection.commit()
                        
                        # Store query data
                        if result.get('source', 'FlightView') == 'FlightView':
                            source = 'FlightView'
                        else:
                            source = 'FlightStats'
                            
                        # Check if flight is delayed
                        is_delayed = False
                        if self.main_window.flight_scraper.list_type == 'arrival':
                            # For arrivals, check if ATA > STA
                            if result.get('ata') and result.get('sta'):
                                is_delayed = result['ata'] > result['sta']
                        else:
                            # For departures, check if ATD > STD
                            if result.get('atd') and result.get('std'):
                                is_delayed = result['atd'] > result['std']
                            
                        query_data = {
                            'source': source,
                            'airline': flight['airline'],
                            'flight_number': flight['number'],
                            'departure_airport': flight['depapt'],
                            'arrival_airport': flight['arrapt'],
                            'std': std_time,
                            'etd': etd_time,
                            'atd': atd_time,
                            'sta': sta_time,
                            'eta': eta_time,
                            'ata': ata_time,
                            'delayed': is_delayed,
                            'is_yesterday': result.get('is_yesterday', False),
                            'raw_data': result
                        }
                        
                        self.db.add_query_flight(flight_id, query_data)
                        
                        # Update query result
                        delay_status = " (Delayed)" if is_delayed else ""
                        result_data = {
                            'display_line': new_line,
                            'summary': f"Time: {time_to_use}{delay_status}" + (" (Yesterday)" if result.get('is_yesterday', False) else ""),
                            'status': 'COMPLETED',
                            'is_complete': True,
                            'has_error': False
                        }
                        
                        self.db.update_query_result(flight_id, result_data)
                else:
                    print(f"Could not format line for flight {flight['airline']}{flight['number']} - keeping original.")
                    self.processed_lines[row_index] = flight['line']
                    self.update_flight_state(flight['row'], 'format_error')
                    self._update_flight_status(flight['row'], 'FORMAT_ERROR')
            else:
                 # No valid time found, keep original
                 self.processed_lines[row_index] = flight['line']
                 self.update_flight_state(flight['row'], 'no_time_found')
                 print(f"No valid time found for flight {flight['airline']}{flight['number']} - keeping original.")
                 self._update_flight_status(flight['row'], 'NO_TIME_FOUND')
        else:
            # No result or no time in result, keep original
            self.processed_lines[row_index] = flight['line']
            self.update_flight_state(flight['row'], 'no_result')
            print(f"No result for flight {flight['airline']}{flight['number']} - keeping original.")
            self._update_flight_status(flight['row'], 'NO_RESULT')
            
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
        self.db.close() 