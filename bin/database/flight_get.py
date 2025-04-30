from bin.database.flight_db import FlightDatabase
from datetime import datetime, date
import os


# Get flight data from database
class FlightGet:
    def __init__(self, db_name: str, path_without_db_name: str = ""):
        if path_without_db_name == "":
            src_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            db_path = os.path.join(src_dir, "src", "database", db_name)
            self.db = FlightDatabase(db_path)
        else:
            self.db = FlightDatabase(path_without_db_name + db_name)


    def return_flight_id(self, table:str, airline:str, flight_number:str, flight_date:date) -> list:
        if len(flight_number) < 4:
            flight_number = flight_number.zfill(4)
        # Convert datetime to date string in YYYY-MM-DD format
        date_str = flight_date.strftime('%Y-%m-%d')
        self.db.cursor.execute('SELECT id FROM jcsy_flights WHERE airline = ? AND flight_number = ? AND flight_date = ?', 
                             (airline, flight_number, date_str))
        result = self.db.cursor.fetchone()
        if result is None:
            raise ValueError(f"No flight found for {airline} {flight_number} on {flight_date}")
        return result
    

    def return_related_flights_IDs(self, table:str, header_flight_id:int) -> list[int]:
        self.db.cursor.execute('SELECT id FROM query_flights WHERE jcsy_flight_id = ?', (header_flight_id,))
        return [row[0] for row in self.db.cursor.fetchall()]
    

    def return_flight_data(self, table: str, id: int) -> dict:
        # Make sure 'table' is a trusted value!
        query = f"SELECT * FROM {table} WHERE id = ?"
        self.db.cursor.execute(query, (id,))
        return self.db.cursor.fetchone()
