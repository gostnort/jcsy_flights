import sqlite3
import os


class FlightDatabase:
    # 标准数据库名称
    DEFAULT_DB_NAME = "flights.db"
    
    def __init__(self, db_name: str = ""):
        # Store database in src/database directory
        src_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        if db_name == "":
            self.db_path = os.path.join(src_dir, "src", "database", self.DEFAULT_DB_NAME)
        else:
            self.db_path = os.path.join(src_dir, "src", "database", db_name)
        self.db_name = db_name # Store the db_name for potential use by tests
        self.connection = None
        self.cursor = None
        if not os.path.exists(self.db_path):
            self.initialize_database()
        self.connect()
        if not self.connection:
            os.remove(self.db_path)
            self.initialize_database()
            self.connect()
            if not self.connection:
                raise Exception("Failed to connect to the database")


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
        if self.connection: # Ensure connection exists before trying to commit/rollback
            if exc_type is None: # No exception
                self.connection.commit()
            else: # An exception occurred
                self.connection.rollback()
        self.close() # Always close


    def initialize_database(self):
        """Create database tables if they don't exist"""
        with self:
            # 1. JCSY header flight info table
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS jcsy_flights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                airline TEXT NOT NULL,
                flight_number TEXT NOT NULL,
                flight_date DATE NOT NULL,
                departure_airport TEXT,
                arrival_airport TEXT,
                std_text TEXT,
                std DATETIME,
                etd DATETIME,
                atd DATETIME,
                sta DATETIME,
                eta DATETIME,
                ata DATETIME,
                inbound_not INTEGER NOT NULL,
                processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (airline, flight_number, flight_date)
            )
            ''')
            # 2. Query Flights Table (linked to header flight)
            self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS query_flights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                jcsy_flight_id INTEGER NOT NULL,
                airline TEXT NOT NULL,
                flight_number TEXT NOT NULL,
                flight_date DATE NOT NULL,
                departure_airport TEXT NOT NULL,
                arrival_airport TEXT NOT NULL,
                std_text TEXT,
                std DATETIME,
                etd DATETIME,
                atd DATETIME,
                sta DATETIME,
                eta DATETIME,
                ata DATETIME,
                delayed BOOLEAN DEFAULT 0,
                query_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                booked_count_non_economy INTEGER,
                booked_count_economy INTEGER,
                checked_count_non_economy INTEGER,
                checked_count_economy INTEGER,
                check_count_infant INTEGER,
                bags_count_piece INTEGER,
                bags_count_weight INTEGER,
                FOREIGN KEY (jcsy_flight_id) REFERENCES jcsy_flights(id) ON DELETE CASCADE
            )
            ''')
            # Create indexes for faster queries
            self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_jcsy_flights_date 
            ON jcsy_flights(flight_date)
            ''')
            self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_query_flights_jcsy_id 
            ON query_flights(jcsy_flight_id)
            ''')
            # Create index on airline and flight_number for faster lookup
            self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_jcsy_flights_number
            ON jcsy_flights(airline, flight_number)
            ''')
            # Create index on timestamps for sorting
            self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_jcsy_flights_processed
            ON jcsy_flights(processed_at)
            ''')
            self.cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_query_flights_timestamp
            ON query_flights(query_timestamp)
            ''')
            self.connection.commit()

    def delete_jcsy_flight_by_header(self, airline: str, flight_number: str, flight_date: str):
        """
        Deletes a JCSY flight entry and its associated query_flights
        based on airline, flight_number, and flight_date.
        The flight_date should be in 'YYYY-MM-DD' format.
        """
        if not self.connection:
            self.connect()
        try:
            self.cursor.execute("""
                DELETE FROM jcsy_flights
                WHERE airline = ? AND flight_number = ? AND flight_date = ?
            """, (airline, flight_number, flight_date))
            self.connection.commit()
            # print(f"Deleted {self.cursor.rowcount} JCSY flight entries for {airline}{flight_number} on {flight_date}")
            return self.cursor.rowcount > 0 # Return True if any row was deleted
        except sqlite3.Error as e:
            print(f"Error deleting JCSY flight data: {e}")
            # self.connection.rollback() # Rollback if commit is managed outside or if an error occurs mid-transaction
            return False
