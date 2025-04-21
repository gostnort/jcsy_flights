import sqlite3
import os
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any, Tuple
import json

class FlightDatabase:
    def __init__(self, db_path: str = None):
        """Initialize the flight database"""
        if db_path is None:
            # Create database in the same directory as the application
            db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "flights.db")
            
        self.db_path = db_path
        self.connection = None
        self.cursor = None
        
    def connect(self):
        """Connect to the SQLite database"""
        self.connection = sqlite3.connect(self.db_path)
        # Enable foreign keys for referential integrity
        self.connection.execute("PRAGMA foreign_keys = ON")
        # Enable column names in result sets
        self.connection.row_factory = sqlite3.Row
        self.cursor = self.connection.cursor()
        
    def close(self):
        """Close the database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None
            self.cursor = None
            
    def __enter__(self):
        """Context manager entry"""
        self.connect()
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.close()
        

    def initialize_database(self):
        """Create database tables if they don't exist"""
        with self:
            # 1. JSCY Main Flight Info Table
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS jscy_flights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                airline TEXT NOT NULL,
                flight_number TEXT NOT NULL,
                flight_date DATE NOT NULL,
                departure_airport TEXT NOT NULL,
                arrival_airport TEXT NOT NULL,
                std DATETIME,
                etd DATETIME,
                atd DATETIME,
                sta DATETIME,
                eta DATETIME,
                ata DATETIME,
                original_line TEXT NOT NULL,
                processed_line TEXT,
                delayed BOOLEAN DEFAULT 0,
                is_arrival BOOLEAN NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (airline, flight_number, flight_date)
            )
            ''')
            
            # 2. Query Flights Table (linked to main flight)
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS query_flights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jscy_flight_id INTEGER NOT NULL,
                source TEXT NOT NULL,
                airline TEXT NOT NULL,
                flight_number TEXT NOT NULL,
                flight_date DATE NOT NULL,
                departure_airport TEXT NOT NULL,
                arrival_airport TEXT NOT NULL,
                std DATETIME,
                etd DATETIME,
                atd DATETIME,
                sta DATETIME,
                eta DATETIME,
                ata DATETIME,
                delayed BOOLEAN DEFAULT 0,
                is_arrival BOOLEAN NOT NULL,
                query_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                raw_data TEXT,
                FOREIGN KEY (jscy_flight_id) REFERENCES jscy_flights(id) ON DELETE CASCADE
            )
            ''')
            
            # 3. Query Results Table (for UI display)
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS query_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jscy_flight_id INTEGER NOT NULL,
                display_line TEXT NOT NULL,
                summary TEXT,
                status TEXT,
                last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_complete BOOLEAN DEFAULT 0,
                has_error BOOLEAN DEFAULT 0,
                error_message TEXT,
                FOREIGN KEY (jscy_flight_id) REFERENCES jscy_flights(id) ON DELETE CASCADE
            )
            ''')
            
            # Create indexes for faster queries
            self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_jscy_flights_date 
            ON jscy_flights(flight_date)
            ''')
            
            self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_query_flights_jscy_id 
            ON query_flights(jscy_flight_id)
            ''')
            
            self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_query_results_jscy_id 
            ON query_results(jscy_flight_id)
            ''')
            
            self.connection.commit()
            
    def add_jscy_flight(self, flight_data: Dict[str, Any]) -> int:
        """
        Add a new JSCY flight to the database
        
        Args:
            flight_data: Dictionary containing flight information
            
        Returns:
            The ID of the inserted flight record
        """
        with self:
            try:
                self.cursor.execute('''
                INSERT INTO jscy_flights (
                    airline, flight_number, departure_airport, arrival_airport,
                    std, etd, atd, sta, eta, ata, original_line, processed_line,
                    flight_date, delayed, is_arrival
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    flight_data.get('airline'),
                    flight_data.get('number'),
                    flight_data.get('depapt'),
                    flight_data.get('arrapt'),
                    flight_data.get('std'),  # Store raw datetime from source
                    flight_data.get('etd'),
                    flight_data.get('atd'),
                    flight_data.get('sta'),
                    flight_data.get('eta'),
                    flight_data.get('ata'),
                    flight_data.get('line'),
                    flight_data.get('processed_line'),
                    flight_data.get('flight_date'),
                    1 if flight_data.get('delayed', False) else 0,
                    1 if flight_data.get('is_arrival', True) else 0
                ))
                
                self.connection.commit()
                return self.cursor.lastrowid
            except sqlite3.IntegrityError:
                # Flight already exists, update it instead
                self.cursor.execute('''
                UPDATE jscy_flights
                SET std = ?,
                    etd = ?,
                    atd = ?,
                    sta = ?,
                    eta = ?,
                    ata = ?,
                    processed_line = ?,
                    delayed = ?,
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
                    flight_data.get('airline'),
                    flight_data.get('number'),
                    flight_data.get('flight_date')
                ))
                
                self.connection.commit()
                
                # Get the ID of the existing flight
                self.cursor.execute('''
                SELECT id FROM jscy_flights 
                WHERE airline = ? AND flight_number = ? AND flight_date = ?
                ''', (
                    flight_data.get('airline'),
                    flight_data.get('number'),
                    flight_data.get('flight_date')
                ))
                
                result = self.cursor.fetchone()
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
        with self:
            # Store complex data as JSON string
            if 'raw_data' in query_data and isinstance(query_data['raw_data'], (dict, list)):
                query_data['raw_data'] = json.dumps(query_data['raw_data'])
                
            self.cursor.execute('''
            INSERT INTO query_flights (
                jscy_flight_id, source, airline, flight_number,
                departure_airport, arrival_airport,
                std, etd, atd, sta, eta, ata,
                delayed, is_arrival, raw_data
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                query_data.get('raw_data')
            ))
            
            self.connection.commit()
            return self.cursor.lastrowid
            
    def update_query_result(self, jscy_flight_id: int, result_data: Dict[str, Any]) -> int:
        """
        Update or create a query result for UI display
        
        Args:
            jscy_flight_id: The ID of the related JSCY flight
            result_data: Dictionary containing result information
            
        Returns:
            The ID of the updated or inserted result record
        """
        with self:
            # Check if a result already exists for this flight
            self.cursor.execute('''
            SELECT id FROM query_results WHERE jscy_flight_id = ?
            ''', (jscy_flight_id,))
            
            existing = self.cursor.fetchone()
            
            if existing:
                # Update existing result
                self.cursor.execute('''
                UPDATE query_results SET
                    display_line = ?,
                    summary = ?,
                    status = ?,
                    last_updated = CURRENT_TIMESTAMP,
                    is_complete = ?,
                    has_error = ?,
                    error_message = ?
                WHERE jscy_flight_id = ?
                ''', (
                    result_data.get('display_line'),
                    result_data.get('summary'),
                    result_data.get('status'),
                    1 if result_data.get('is_complete', False) else 0,
                    1 if result_data.get('has_error', False) else 0,
                    result_data.get('error_message'),
                    jscy_flight_id
                ))
                
                self.connection.commit()
                return existing['id']
            else:
                # Insert new result
                self.cursor.execute('''
                INSERT INTO query_results (
                    jscy_flight_id, display_line, summary, status,
                    is_complete, has_error, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    jscy_flight_id,
                    result_data.get('display_line'),
                    result_data.get('summary'),
                    result_data.get('status'),
                    1 if result_data.get('is_complete', False) else 0,
                    1 if result_data.get('has_error', False) else 0,
                    result_data.get('error_message')
                ))
                
                self.connection.commit()
                return self.cursor.lastrowid
                
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
        with self:
            self.cursor.execute('''
            SELECT * FROM jscy_flights
            WHERE airline = ? AND flight_number = ?
            ORDER BY flight_date DESC
            LIMIT ?
            ''', (airline, flight_number, limit))
            
            results = self.cursor.fetchall()
            return [dict(row) for row in results]
            
    def get_recent_flights(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get the most recently processed flights
        
        Args:
            limit: Maximum number of records to return
            
        Returns:
            List of flight records
        """
        with self:
            self.cursor.execute('''
            SELECT * FROM jscy_flights
            ORDER BY processed_at DESC
            LIMIT ?
            ''', (limit,))
            
            results = self.cursor.fetchall()
            return [dict(row) for row in results]
    
    def get_flight_with_queries(self, flight_id: int) -> Dict[str, Any]:
        """
        Get a flight with all its queries
        
        Args:
            flight_id: The ID of the flight
            
        Returns:
            Dictionary with flight data and queries
        """
        with self:
            # Get flight data
            self.cursor.execute('''
            SELECT * FROM jscy_flights WHERE id = ?
            ''', (flight_id,))
            
            flight = self.cursor.fetchone()
            
            if not flight:
                return None
                
            # Get query data
            self.cursor.execute('''
            SELECT * FROM query_flights WHERE jscy_flight_id = ?
            ORDER BY query_timestamp DESC
            ''', (flight_id,))
            
            queries = self.cursor.fetchall()
            
            # Combine data
            flight_dict = dict(flight)
            flight_dict['queries'] = [dict(q) for q in queries]
            flight_dict['result'] = None  # Will be handled by UI layer
            
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
        with self:
            search_pattern = f"%{search_term}%"
            
            self.cursor.execute('''
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
            
            results = self.cursor.fetchall()
            return [dict(row) for row in results] 