import sqlite3
import os
from typing import List, Dict, Optional, Any, Tuple

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
                raw_data TEXT,
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
                booked_count_non_economy INTEGER,
                booked_count_economy INTEGER,
                checked_count_non_economy INTEGER,
                checked_count_economy INTEGER,
                check_count_infant INTEGER,
                bags_count_piece INTEGER,
                bags_count_weight INTEGER,
                raw_data TEXT,
                FOREIGN KEY (jscy_flight_id) REFERENCES jscy_flights(id) ON DELETE CASCADE
            )
            ''')
            
            # Drop the old query_results table if it exists
            self.cursor.execute("DROP TABLE IF EXISTS query_results")
            
            # 3. Query Results View (for UI display) - created as a VIEW for auto-updating
            self.cursor.execute('''
            CREATE VIEW IF NOT EXISTS query_results AS
            SELECT 
                qf.id,
                qf.jscy_flight_id,
                qf.flight_number AS query_flight_number,
                CASE WHEN qf.is_arrival = 1 THEN qf.arrival_airport ELSE qf.departure_airport END AS airport,
                qf.booked_count_non_economy,
                qf.booked_count_economy,
                qf.checked_count_non_economy,
                qf.checked_count_economy,
                qf.check_count_infant,
                qf.bags_count_piece,
                qf.bags_count_weight,
                qf.query_timestamp AS last_updated,
                qf.delayed,
                qf.std, qf.etd, qf.atd,
                qf.sta, qf.eta, qf.ata,
                CASE WHEN qf.is_arrival = 1 THEN qf.sta ELSE qf.std END AS scheduled_time,
                CASE WHEN qf.is_arrival = 1 THEN qf.eta ELSE qf.etd END AS estimated_time,
                CASE WHEN qf.is_arrival = 1 THEN qf.ata ELSE qf.atd END AS actual_time
            FROM query_flights qf
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
            
            # Create index on airline and flight_number for faster lookup
            self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_jscy_flights_number
            ON jscy_flights(airline, flight_number)
            ''')
            
            # Create index on timestamps for sorting
            self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_jscy_flights_processed
            ON jscy_flights(processed_at)
            ''')
            
            self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_query_flights_timestamp
            ON query_flights(query_timestamp)
            ''')
            
            self.connection.commit() 