import json
from typing import List, Dict, Any, Optional, Tuple
from src.database.flight_db import FlightDatabase

class FlightQuery:
    """Query operations for flight data in the database"""
    
    def __init__(self, db: Optional[FlightDatabase] = None):
        """Initialize with an existing database or create a new one"""
        self.db = db if db is not None else FlightDatabase()
        
    def get_flight_history(self, airline: str, flight_number: str, 
                          limit: int = 10) -> List[Dict[str, Any]]:
        """
        Get the history of a specific flight
        
        Args:
            airline: The airline code
            flight_number: The flight number
            limit: Maximum number of records to return
            
        Returns:
            List of flight records
        """
        with self.db as db:
            db.cursor.execute('''
            SELECT * FROM jscy_flights
            WHERE airline = ? AND flight_number = ?
            ORDER BY flight_date DESC
            LIMIT ?
            ''', (airline, flight_number, limit))
            
            results = db.cursor.fetchall()
            return self._process_json_fields([dict(row) for row in results])
            
    def get_recent_flights(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get the most recently processed flights
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of flight records
        """
        with self.db as db:
            db.cursor.execute('''
            SELECT * FROM jscy_flights
            ORDER BY processed_at DESC
            LIMIT ?
            ''', (limit,))
            
            results = db.cursor.fetchall()
            return self._process_json_fields([dict(row) for row in results])
    
    def get_flight_with_queries(self, flight_id: int) -> Dict[str, Any]:
        """
        Get a flight with all its queries
        
        Args:
            flight_id: The ID of the flight
            
        Returns:
            Dictionary with flight data and queries
        """
        with self.db as db:
            # Get flight data
            db.cursor.execute('''
            SELECT * FROM jscy_flights WHERE id = ?
            ''', (flight_id,))
            
            flight = db.cursor.fetchone()
            
            if not flight:
                return None
                
            # Get query data
            db.cursor.execute('''
            SELECT * FROM query_flights WHERE jscy_flight_id = ?
            ORDER BY query_timestamp DESC
            ''', (flight_id,))
            
            queries = db.cursor.fetchall()
            
            # Get the latest query results
            db.cursor.execute('''
            SELECT * FROM query_results WHERE jscy_flight_id = ?
            ORDER BY last_updated DESC LIMIT 1
            ''', (flight_id,))
            
            result = db.cursor.fetchone()
            
            # Combine data
            flight_dict = dict(flight)
            if 'raw_data' in flight_dict and flight_dict['raw_data']:
                try:
                    flight_dict['raw_data'] = json.loads(flight_dict['raw_data'])
                except (json.JSONDecodeError, TypeError):
                    pass
                    
            queries_list = []
            for q in queries:
                q_dict = dict(q)
                if 'raw_data' in q_dict and q_dict['raw_data']:
                    try:
                        q_dict['raw_data'] = json.loads(q_dict['raw_data'])
                    except (json.JSONDecodeError, TypeError):
                        pass
                queries_list.append(q_dict)
                
            flight_dict['queries'] = queries_list
            flight_dict['result'] = dict(result) if result else None
            
            return flight_dict
            
    def search_flights(self, search_term: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Search for flights by airline, flight number, airports
        
        Args:
            search_term: The search term
            limit: Maximum number of records to return
            
        Returns:
            List of matching flight records
        """
        with self.db as db:
            search_pattern = f"%{search_term}%"
            
            db.cursor.execute('''
            SELECT * FROM jscy_flights
            WHERE airline LIKE ? 
               OR flight_number LIKE ?
               OR departure_airport LIKE ?
               OR arrival_airport LIKE ?
               OR original_line LIKE ?
            ORDER BY processed_at DESC
            LIMIT ?
            ''', (
                search_pattern, search_pattern, search_pattern,
                search_pattern, search_pattern, limit
            ))
            
            results = db.cursor.fetchall()
            return self._process_json_fields([dict(row) for row in results])
            
    def get_flight_stats(self, flight_id: int) -> Dict[str, Any]:
        """
        Get the latest passenger and baggage stats for a flight
        
        Args:
            flight_id: The ID of the flight
            
        Returns:
            Dictionary with the latest stats or None if not found
        """
        with self.db as db:
            db.cursor.execute('''
            SELECT 
                booked_count_non_economy,
                booked_count_economy,
                checked_count_non_economy,
                checked_count_economy,
                check_count_infant,
                bags_count_piece,
                bags_count_weight
            FROM query_flights
            WHERE jscy_flight_id = ?
            ORDER BY query_timestamp DESC
            LIMIT 1
            ''', (flight_id,))
            
            result = db.cursor.fetchone()
            return dict(result) if result else None
            
    def get_flight_display_row(self, flight_id: int) -> Dict[str, Any]:
        """
        Get a single row of display-ready data for a flight
        
        Args:
            flight_id: The ID of the flight
            
        Returns:
            Dictionary with display-formatted data
        """
        with self.db as db:
            db.cursor.execute('''
            SELECT 
                f.id,
                f.airline || f.flight_number AS flight_number,
                f.flight_date,
                f.departure_airport,
                f.arrival_airport,
                CASE WHEN f.is_arrival = 1 THEN f.sta ELSE f.std END AS scheduled,
                CASE WHEN f.is_arrival = 1 THEN f.eta ELSE f.etd END AS estimated,
                CASE WHEN f.is_arrival = 1 THEN f.ata ELSE f.atd END AS actual,
                f.delayed,
                q.booked_count_non_economy,
                q.booked_count_economy,
                q.checked_count_non_economy,
                q.checked_count_economy,
                q.check_count_infant,
                q.bags_count_piece,
                q.bags_count_weight
            FROM jscy_flights f
            LEFT JOIN query_flights q ON f.id = q.jscy_flight_id
            WHERE f.id = ?
            ORDER BY q.query_timestamp DESC
            LIMIT 1
            ''', (flight_id,))
            
            result = db.cursor.fetchone()
            return dict(result) if result else None
            
    def get_all_display_rows(self, limit: int = 50, search_term: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get display-ready data for all flights
        
        Args:
            limit: Maximum number of records to return
            search_term: Optional search term to filter results
            
        Returns:
            List of display-formatted records
        """
        with self.db as db:
            query = '''
            SELECT 
                f.id,
                f.airline || f.flight_number AS flight_number,
                f.flight_date,
                f.departure_airport,
                f.arrival_airport,
                CASE WHEN f.is_arrival = 1 THEN f.sta ELSE f.std END AS scheduled,
                CASE WHEN f.is_arrival = 1 THEN f.eta ELSE f.etd END AS estimated,
                CASE WHEN f.is_arrival = 1 THEN f.ata ELSE f.atd END AS actual,
                f.delayed,
                q.booked_count_non_economy,
                q.booked_count_economy,
                q.checked_count_non_economy,
                q.checked_count_economy,
                q.check_count_infant,
                q.bags_count_piece,
                q.bags_count_weight
            FROM jscy_flights f
            LEFT JOIN (
                SELECT *, ROW_NUMBER() OVER (PARTITION BY jscy_flight_id ORDER BY query_timestamp DESC) as rn
                FROM query_flights
            ) q ON f.id = q.jscy_flight_id AND q.rn = 1
            '''
            
            params = []
            
            if search_term:
                query += '''
                WHERE f.airline LIKE ? 
                   OR f.flight_number LIKE ?
                   OR f.departure_airport LIKE ?
                   OR f.arrival_airport LIKE ?
                '''
                search_pattern = f"%{search_term}%"
                params.extend([search_pattern] * 4)
                
            query += 'ORDER BY f.processed_at DESC LIMIT ?'
            params.append(limit)
            
            db.cursor.execute(query, params)
            results = db.cursor.fetchall()
            return [dict(row) for row in results]
    
    def _process_json_fields(self, records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Process any JSON fields in the records"""
        for record in records:
            if 'raw_data' in record and record['raw_data']:
                try:
                    record['raw_data'] = json.loads(record['raw_data'])
                except (json.JSONDecodeError, TypeError):
                    pass
        return records 