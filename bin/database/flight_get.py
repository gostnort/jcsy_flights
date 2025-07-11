from bin.database.flight_db import FlightDatabase
from datetime import datetime, date
import os


# Get flight data from database
class FlightGet:
    def __init__(self, db_name: str | None = None, path_without_db_name: str = ""):
        final_db_spec: str
        if db_name is None:
            # Default behavior: use "flights.db" in standard location relative to this file's project structure
            src_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))) # .../FlightInfoSystem
            # Ensure "src/database" exists for the default flights.db (FlightDatabase constructor handles this too)
            db_dir_for_default = os.path.join(src_dir, "src", "database")
            if not os.path.exists(db_dir_for_default) and path_without_db_name == "": # Only create if not using custom path
                os.makedirs(db_dir_for_default, exist_ok=True)
            final_db_spec = os.path.join(db_dir_for_default, FlightDatabase.DEFAULT_DB_NAME)

            if path_without_db_name != "": # if path_without_db_name is given, it overrides default dir for default DB name
                final_db_spec = os.path.join(path_without_db_name, FlightDatabase.DEFAULT_DB_NAME)

        else: # A specific db_name (filename) is given
            if path_without_db_name == "":
                src_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
                # Ensure "src/database" exists if a specific db_name is to be placed there by default
                db_dir_for_specific = os.path.join(src_dir, "src", "database")
                if not os.path.exists(db_dir_for_specific):
                     os.makedirs(db_dir_for_specific, exist_ok=True)
                final_db_spec = os.path.join(db_dir_for_specific, db_name)
            else:
                # Ensure custom path exists
                if not os.path.exists(path_without_db_name):
                    os.makedirs(path_without_db_name, exist_ok=True)
                final_db_spec = os.path.join(path_without_db_name, db_name)

        self.db = FlightDatabase(final_db_spec)
        # self.db_name_arg_for_test_patch = db_name # For PatchedFlightGet in tests to reference original intent
        self._cursor = None


    def return_flight_id(self, table:str, airline:str, flight_number:str, flight_date:date): # Return type hint was list, but it returns a Row or None
        if len(flight_number) < 4:
            flight_number = flight_number.zfill(4)
        # Convert datetime to date string in YYYY-MM-DD format
        date_str = flight_date.strftime('%Y-%m-%d')
        self.db.connect() # Ensure connection and cursor are active
        self.db.cursor.execute(f'SELECT id FROM {table} WHERE airline = ? AND flight_number = ? AND flight_date = ?', 
                             (airline, flight_number, date_str))
        result = self.db.cursor.fetchone()
        if result is None:
            # Consider if raising an error or returning None/empty is more appropriate.
            # For an ID lookup, an error might be fine if ID is expected to exist.
            # For consistency with other methods, let's make it return None or print an error.
            print(f"No flight ID found for {airline} {flight_number} on {flight_date} in table {table}")
            return None # Or raise ValueError as before, depending on desired contract
        return result # result is already a Row object, can be dict(result) if needed by caller, or just result[0] for ID.
                      # The original code implies it returns a tuple/row with one element (the ID).
    

    def return_related_flights_IDs(self, table:str, header_flight_id:int) -> list[int]:
        self.db.connect() # Ensure connection and cursor are active
        # 'table' parameter is not used in the original query 'SELECT id FROM query_flights...'
        # Assuming it should be query_flights or the table param should be used.
        # For now, keeping original query structure but using the passed table name.
        # If 'table' is always 'query_flights' for this method, it can be hardcoded.
        # Let's assume the query should use the 'table' parameter if it's meant to be flexible.
        # Original: self.db.cursor.execute('SELECT id FROM query_flights WHERE jcsy_flight_id = ?', (header_flight_id,))
        actual_table_to_query = 'query_flights' # Defaulting to original, ignoring 'table' param for this specific query logic
        if table != 'query_flights':
            print(f"Warning: return_related_flights_IDs called with table='{table}', but currently hardcoded to query 'query_flights'.")

        self.db.cursor.execute(f'SELECT id FROM {actual_table_to_query} WHERE jcsy_flight_id = ?', (header_flight_id,))
        rows = self.db.cursor.fetchall()
        if not rows:
            print(f"No related flights found for header ID {header_flight_id} in table {actual_table_to_query}")
            return []
        return [row[0] for row in rows] # row[0] because sqlite.Row can be accessed by index for single column select
    

    def return_flight_data(self, table: str, id: int) -> dict:
        self.db.connect() # Ensure connection and cursor are active
        # Make sure 'table' is a trusted value!
        query = f"SELECT * FROM {table} WHERE id = ?"
        self.db.cursor.execute(query, (id,))
        row = self.db.cursor.fetchone()
        if row is None:
            print(f"Error loading flight data: No item with that key for table {table}, id {id}")
            return None
        return dict(row) # Convert sqlite.Row to dict
