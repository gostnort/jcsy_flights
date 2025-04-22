import json
import sqlite3
from typing import Dict, Any, Optional, List
from src.database.flight_db import FlightDatabase
from src.database.config_parser import JSCYConfigParser

class FlightRepository:
    """Repository for adding and updating flight data in the database"""
    
    def __init__(self, db: Optional[FlightDatabase] = None):
        """Initialize with an existing database or create a new one"""
        self.db = db if db is not None else FlightDatabase()
        self.jscy_parser = JSCYConfigParser.get_parser()
        
    def add_jscy_flight(self, flight_data: Dict[str, Any]) -> int:
        """
        Add a new JSCY flight to the database
        
        Args:
            flight_data: Dictionary containing flight information
            
        Returns:
            The ID of the inserted flight record
        """
        with self.db as db:
            try:
                # Store complex data as JSON string if present
                raw_data = flight_data.get('raw_data')
                if raw_data and isinstance(raw_data, (dict, list)):
                    raw_data = json.dumps(raw_data)
                else:
                    raw_data = None
                
                # Note: When adding flights from JSCY data, time fields (std, etd, atd, sta, eta, ata)
                # will initially be NULL since JSCY format doesn't include time information.
                # These fields can be updated later when actual time data becomes available.
                db.cursor.execute('''
                INSERT INTO jscy_flights (
                    airline, flight_number, departure_airport, arrival_airport,
                    std, etd, atd, sta, eta, ata, original_line, processed_line,
                    flight_date, delayed, is_arrival, raw_data
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    flight_data.get('airline'),
                    flight_data.get('number'),
                    flight_data.get('depapt'),
                    flight_data.get('arrapt'),
                    flight_data.get('std'),  # Will be NULL for JSCY input
                    flight_data.get('etd'),  # Will be NULL for JSCY input
                    flight_data.get('atd'),  # Will be NULL for JSCY input
                    flight_data.get('sta'),  # Will be NULL for JSCY input
                    flight_data.get('eta'),  # Will be NULL for JSCY input
                    flight_data.get('ata'),  # Will be NULL for JSCY input
                    flight_data.get('line'),
                    flight_data.get('processed_line'),
                    flight_data.get('flight_date'),
                    1 if flight_data.get('delayed', False) else 0,
                    1 if flight_data.get('is_arrival', True) else 0,
                    raw_data
                ))
                
                db.connection.commit()
                return db.cursor.lastrowid
            except sqlite3.IntegrityError:
                # Flight already exists, update it instead
                db.cursor.execute('''
                UPDATE jscy_flights
                SET std = ?,
                    etd = ?,
                    atd = ?,
                    sta = ?,
                    eta = ?,
                    ata = ?,
                    processed_line = ?,
                    delayed = ?,
                    raw_data = ?,
                    processed_at = CURRENT_TIMESTAMP
                WHERE airline = ? AND flight_number = ? AND flight_date = ?
                ''', (
                    flight_data.get('std'),
                    flight_data.get('etd'),
                    flight_data.get('atd'),
                    flight_data.get('sta'),
                    flight_data.get('eta'),
                    flight_data.get('ata'),
                    flight_data.get('processed_line'),
                    1 if flight_data.get('delayed', False) else 0,
                    raw_data,
                    flight_data.get('airline'),
                    flight_data.get('number'),
                    flight_data.get('flight_date')
                ))
                
                db.connection.commit()
                
                # Get the ID of the existing flight
                db.cursor.execute('''
                SELECT id FROM jscy_flights 
                WHERE airline = ? AND flight_number = ? AND flight_date = ?
                ''', (
                    flight_data.get('airline'),
                    flight_data.get('number'),
                    flight_data.get('flight_date')
                ))
                
                result = db.cursor.fetchone()
                return result['id'] if result else None
                
    def add_query_flight(self, jscy_flight_id: int, query_data: Dict[str, Any]) -> int:
        """
        Add a query flight result linked to a JSCY flight
        
        Args:
            jscy_flight_id: The ID of the related JSCY flight
            query_data: Dictionary containing query result information
            
        Returns:
            The ID of the inserted query record
        """
        with self.db as db:
            # Store complex data as JSON string
            if 'raw_data' in query_data and isinstance(query_data['raw_data'], (dict, list)):
                query_data['raw_data'] = json.dumps(query_data['raw_data'])
                
            db.cursor.execute('''
            INSERT INTO query_flights (
                jscy_flight_id, source, airline, flight_number,
                departure_airport, arrival_airport,
                std, etd, atd, sta, eta, ata,
                delayed, is_arrival, 
                booked_count_non_economy, booked_count_economy,
                checked_count_non_economy, checked_count_economy, check_count_infant,
                bags_count_piece, bags_count_weight,
                raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                jscy_flight_id,
                query_data.get('source', 'unknown'),
                query_data.get('airline'),
                query_data.get('flight_number'),
                query_data.get('departure_airport'),
                query_data.get('arrival_airport'),
                query_data.get('std'),  # Store raw datetime from source
                query_data.get('etd'),
                query_data.get('atd'),
                query_data.get('sta'),
                query_data.get('eta'),
                query_data.get('ata'),
                1 if query_data.get('delayed', False) else 0,
                1 if query_data.get('is_arrival', True) else 0,
                query_data.get('booked_count_non_economy'),
                query_data.get('booked_count_economy'),
                query_data.get('checked_count_non_economy'),
                query_data.get('checked_count_economy'),
                query_data.get('check_count_infant'),
                query_data.get('bags_count_piece'),
                query_data.get('bags_count_weight'),
                query_data.get('raw_data')
            ))
            
            db.connection.commit()
            return db.cursor.lastrowid
    
    def process_jscy_content(self, content: str) -> List[int]:
        """
        Process JSCY format content from UI input
        
        Args:
            content: Multi-line string of JSCY content (e.g. from a textbox)
            
        Returns:
            List of IDs for the stored flights
        """
        # Parse the content using the configuration-driven parser
        parsed_flights = self.jscy_parser.parse_jscy_content(content)
        flight_ids = []
        
        for flight_data in parsed_flights:
            # Determine arrival/departure airports based on is_arrival flag and available airport data
            is_arrival = flight_data.get('is_arrival', False)
            header_airport = flight_data.get('header_airport')
            flight_line_airport = flight_data.get('flight_line_airport')
            std = flight_data.get('std')  # Get STD from parsed data
            
            # Default values
            departure_airport = None
            arrival_airport = None
            
            if is_arrival:
                # For arrival flights:
                # - arrival_airport comes from the header
                # - departure_airport comes from the flight line
                arrival_airport = header_airport
                departure_airport = flight_line_airport
            else:
                # For departure flights:
                # - departure_airport comes from the header
                # - arrival_airport comes from the flight line
                departure_airport = header_airport
                arrival_airport = flight_line_airport
            
            # Prepare data for storage
            db_flight_data = {
                'airline': flight_data.get('airline'),
                'number': flight_data.get('flight_number'),
                'depapt': departure_airport,
                'arrapt': arrival_airport,
                'flight_date': flight_data.get('flight_date'),
                'line': flight_data.get('line', ''),
                'processed_line': flight_data.get('line', ''),
                'is_arrival': is_arrival,
                'raw_data': None,  # No header line in new parser
                'std': std        # Always store time as STD regardless of arrival/departure
            }
            
            # Skip incomplete records
            if not departure_airport or not arrival_airport:
                print(f"Skipping incomplete flight record: missing airport information")
                continue
            
            # Add the flight to the database
            flight_id = self.add_jscy_flight(db_flight_data)
            
            if flight_id:
                # Prepare query data (from the flight line)
                query_data = {
                    'source': 'JSCY',
                    'airline': flight_data.get('airline'),
                    'flight_number': flight_data.get('flight_number'),
                    'departure_airport': departure_airport,
                    'arrival_airport': arrival_airport,
                    'is_arrival': is_arrival,
                    'std': std,  # Always include STD regardless of arrival/departure
                    'booked_count_non_economy': flight_data.get('booked_count_non_economy', 0),
                    'booked_count_economy': flight_data.get('booked_count_economy', 0),
                    'checked_count_non_economy': flight_data.get('checked_count_non_economy', 0),
                    'checked_count_economy': flight_data.get('checked_count_economy', 0),
                    'check_count_infant': flight_data.get('check_count_infant', 0),
                    'bags_count_piece': flight_data.get('bags_count_piece', 0),
                    'bags_count_weight': flight_data.get('bags_count_weight', 0),
                    'raw_data': None  # No raw data in new parser
                }
                
                # Add the query data
                query_id = self.add_query_flight(flight_id, query_data)
                
                flight_ids.append(flight_id)
                
        return flight_ids
            
    def update_flight_status(self, flight_id: int, status_data: Dict[str, Any]) -> bool:
        """
        Update the status of a flight with data from scrapers or direct input
        
        Args:
            flight_id: The ID of the flight to update
            status_data: Dictionary with updated fields, can be direct field values
                        or nested data from FlightStatsScraper/FlightViewScraper
            
        Returns:
            True if successful, False if flight not found
        """
        with self.db as db:
            # Check if flight exists
            db.cursor.execute("SELECT id FROM jscy_flights WHERE id = ?", (flight_id,))
            if not db.cursor.fetchone():
                return False
                
            # Map fields from scrapers if needed
            processed_data = {}
            
            # Check if this is data from FlightStatsScraper
            if 'departure' in status_data and 'arrival' in status_data:
                # Map scraper data to our fields
                if 'departure' in status_data:
                    departure = status_data['departure']
                    # Map scheduled/estimated/actual times
                    if departure.get('scheduled') and departure['scheduled'] != 'N/A':
                        processed_data['std'] = departure['scheduled'] 
                    if departure.get('estimated') and departure['estimated'] != 'N/A':
                        processed_data['etd'] = departure['estimated']
                    if departure.get('actual') and departure['actual'] != 'N/A':
                        processed_data['atd'] = departure['actual']
                        
                if 'arrival' in status_data:
                    arrival = status_data['arrival']
                    # Map scheduled/estimated/actual times
                    if arrival.get('scheduled') and arrival['scheduled'] != 'N/A':
                        processed_data['sta'] = arrival['scheduled']
                    if arrival.get('estimated') and arrival['estimated'] != 'N/A':
                        processed_data['eta'] = arrival['estimated']
                    if arrival.get('actual') and arrival['actual'] != 'N/A':
                        processed_data['ata'] = arrival['actual']
                
                # Determine delayed status
                if 'status' in status_data:
                    processed_data['delayed'] = 1 if 'delay' in status_data['status'].lower() else 0
                
                # Use processed data for update
                status_data = processed_data
            
            # Build dynamic update query based on provided fields
            fields = []
            params = []
            
            # Add each field that's provided
            for field in ['std', 'etd', 'atd', 'sta', 'eta', 'ata', 'delayed', 'processed_line']:
                if field in status_data:
                    fields.append(f"{field} = ?")
                    params.append(status_data[field])
                    
            # Nothing to update
            if not fields:
                return True
                
            # Add timestamp and ID
            fields.append("processed_at = CURRENT_TIMESTAMP")
            params.append(flight_id)
            
            # Execute update
            query = f"UPDATE jscy_flights SET {', '.join(fields)} WHERE id = ?"
            db.cursor.execute(query, params)
            db.connection.commit()
            
            return True
            
    def delete_flight(self, flight_id: int) -> bool:
        """
        Delete a flight and its related data
        
        Args:
            flight_id: The ID of the flight to delete
            
        Returns:
            True if successful, False if flight not found
        """
        with self.db as db:
            db.cursor.execute("SELECT id FROM jscy_flights WHERE id = ?", (flight_id,))
            if not db.cursor.fetchone():
                return False
                
            # Delete flight (query_flights will be deleted via CASCADE)
            db.cursor.execute("DELETE FROM jscy_flights WHERE id = ?", (flight_id,))
            db.connection.commit()
            return True 