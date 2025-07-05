# This file will contain functions for UI button actions.
# Initially, it will house the function for the "import" button.

import sys
import os
import datetime
import sqlite3

# Add project root to Python path to allow direct imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from bin.config.jcsy_config import JcsyParser
from bin.database.flight_db import FlightDatabase

# Initialize the parser and database
# For simplicity in a single-threaded UI context, global might be acceptable,
# but for broader applications, dependency injection is preferred.
# Error handling for initialization is important for robustness.
jcsy_parser = None
flight_db = None

try:
    jcsy_parser = JcsyParser(config_file="jcsy_config.yaml")
except Exception as e:
    print(f"CRITICAL: Error initializing JcsyParser: {e}. The import function will not work.")
    # Depending on the application, might raise e or handle more gracefully

try:
    # Ensure the database directory exists
    db_dir = os.path.join(project_root, "src", "database")
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    flight_db = FlightDatabase() # Uses default "flights.db" in src/database/
except Exception as e:
    print(f"CRITICAL: Error initializing FlightDatabase: {e}. The import function will not work.")
    # Depending on the application, might raise e or handle more gracefully

def parse_std_datetime(std_text: str, base_date: datetime.date) -> datetime.datetime | None:
    """
    Parses STD text (HHMM or HHMM+D) into a datetime object.
    Returns None if parsing fails.
    """
    if not std_text or not base_date:
        return None
    try:
        time_str = std_text[:4]
        hour = int(time_str[:2])
        minute = int(time_str[2:])

        day_offset = 0
        if len(std_text) > 4 and std_text[4] == '+':
            day_offset = int(std_text[5:])

        dt = datetime.datetime(base_date.year, base_date.month, base_date.day, hour, minute)
        dt += datetime.timedelta(days=day_offset)
        return dt
    except ValueError:
        return None # Invalid format

def safe_int_convert(value_str: str | None) -> int | None:
    """Safely converts a string (potentially None or empty) to an int, trimming leading zeros."""
    if value_str is None or not str(value_str).strip():
        return 0 # Default to 0 if empty or None
    try:
        # The parser should handle trim_leading_zeros based on YAML,
        # but as a safeguard or if direct values are passed:
        cleaned_value = str(value_str).lstrip('0')
        if not cleaned_value: # if it was all zeros e.g. "000"
            return 0
        return int(cleaned_value)
    except ValueError:
        return 0 # Default to 0 if conversion fails

def import_jcsy_data(jcsy_text_content: str):
    """
    Parses JCSY formatted text content and stores it in the database.
    """
    if not jcsy_parser:
        msg = "JCSY Parser not initialized. Cannot process data."
        print(msg)
        return {"status": "error", "message": msg}
    if not flight_db:
        msg = "Flight Database not initialized. Cannot process data."
        print(msg)
        return {"status": "error", "message": msg}

    try:
        parsed_data = jcsy_parser.parse_content(jcsy_text_content)
        # print(f"Parsed JCSY content: {parsed_data}") # For debugging

        header = parsed_data.get('header')
        flight_entries_dict = parsed_data.get('flight', {}) # It's a dict like {"flight_0": ..., "flight_1": ...}
        # print(f"DEBUG: Number of flight entries parsed: {len(flight_entries_dict)}") # Removed temporary debug print

        if not header:
            return {"status": "error", "message": "Failed to parse JCSY header."}

        with flight_db: # Handles connect and close
            # 1. Insert into jcsy_flights (main entry from header)
            header_flight_date_str = header.get('header_flight_date')
            # The JcsyParser's parse_header_date already returns a date object or string YYYYMMDD
            # Forcing it to string for consistency before DB.
            # If it's already a date object from parser:
            if isinstance(header_flight_date_str, datetime.date):
                db_flight_date = header_flight_date_str.strftime('%Y-%m-%d')
            elif isinstance(header_flight_date_str, str) and len(header_flight_date_str) == 8: # YYYYMMDD
                db_flight_date = f"{header_flight_date_str[:4]}-{header_flight_date_str[4:6]}-{header_flight_date_str[6:8]}"
            else: # Fallback or error
                 return {"status": "error", "message": f"Invalid flight date format from parser: {header_flight_date_str}"}


            # Determine departure/arrival for jcsy_flights based on inbound_not
            is_inbound = safe_int_convert(header.get('inbound_not')) == 1
            jcsy_main_departure_airport = None
            jcsy_main_arrival_airport = None

            if is_inbound: # Inbound flight, header_airport is the arrival
                jcsy_main_arrival_airport = header.get('header_airport')
            else: # Outbound flight, header_airport is the departure
                jcsy_main_departure_airport = header.get('header_airport')

            flight_db.cursor.execute("""
                INSERT INTO jcsy_flights (
                    airline, flight_number, flight_date, departure_airport,
                    arrival_airport, inbound_not,
                    std, etd, atd, sta, eta, ata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                header.get('header_airline'),
                header.get('header_flight_number'),
                db_flight_date,
                jcsy_main_departure_airport,
                jcsy_main_arrival_airport,
                safe_int_convert(header.get('inbound_not')),
                None, None, None, None, None, None # Time fields for jcsy_flights remain None
            ))
            jcsy_flight_id = flight_db.cursor.lastrowid
            if not jcsy_flight_id:
                 return {"status": "error", "message": "Failed to insert master JCSY flight record."}

            # 2. Iterate through flight_entries and insert into query_flights
            base_date_for_std = datetime.datetime.strptime(db_flight_date, '%Y-%m-%d').date()

            for flight_key, flight_data in flight_entries_dict.items():
                std_datetime = parse_std_datetime(flight_data.get('std_text'), base_date_for_std)
                is_delayed = 1 if flight_data.get('std_text', '').endswith(("+1", "+2")) else 0

                # Determine departure/arrival for query_flights based on inbound_not
                query_departure_airport = None
                query_arrival_airport = None
                if is_inbound:
                    # For inbound, the main header airport is the destination of segments,
                    # and the segment's 'airport' field is its origin.
                    query_arrival_airport = header.get('header_airport')
                    query_departure_airport = flight_data.get('airport')
                else:
                    # For outbound, the main header airport is the origin of segments,
                    # and the segment's 'airport' field is its destination.
                    query_departure_airport = header.get('header_airport')
                    query_arrival_airport = flight_data.get('airport')

                flight_db.cursor.execute("""
                    INSERT INTO query_flights (
                        jcsy_flight_id, airline, flight_number, flight_date,
                        departure_airport, arrival_airport, std_text, std,
                        delayed, booked_count_non_economy, booked_count_economy,
                        checked_count_non_economy, checked_count_economy, check_count_infant,
                        bags_count_piece, bags_count_weight
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    jcsy_flight_id,
                    flight_data.get('airline'),
                    flight_data.get('flight_number'),
                    db_flight_date,
                    query_departure_airport,
                    query_arrival_airport,
                    flight_data.get('std_text'),
                    std_datetime,
                    is_delayed,
                    safe_int_convert(flight_data.get('booked_count_non_economy')),
                    safe_int_convert(flight_data.get('booked_count_economy')),
                    safe_int_convert(flight_data.get('checked_count_non_economy')),
                    safe_int_convert(flight_data.get('checked_count_economy')),
                    safe_int_convert(flight_data.get('check_count_infant')),
                    safe_int_convert(flight_data.get('bags_count_piece')),
                    safe_int_convert(flight_data.get('bags_count_weight'))
                ))

            flight_db.connection.commit()

        num_flights_processed = len(flight_entries_dict)
        return {
            "status": "success",
            "message": f"Successfully imported JCSY data. Master record ID: {jcsy_flight_id}. Processed {num_flights_processed} flight segments."
        }

    except sqlite3.Error as e:
        # It's good practice to rollback on error if not using context manager for commit
        # flight_db.connection.rollback() # flight_db context manager handles this if exception occurs within 'with'
        print(f"Database error during JCSY data import: {e}")
        return {"status": "error", "message": f"Database error: {str(e)}"}
    except Exception as e:
        print(f"General error during JCSY data import: {e}")
        return {"status": "error", "message": f"Error during import: {str(e)}"}


if __name__ == '__main__':
    # Example usage (for testing purposes)
    sample_jcsy_text_from_yaml = """JCSY:CA0983/24APR/PEK,O
FLT/DEST/GTD   DEPT   BKD     CHK(NTC)   CHK(TC)    UCK     BAG
CM0306 /PTY/          000/001 000/001+00 000/000+00 000/000 002/0039
UA1843 /ORD/   2359   000/002 000/000+00 000/002+00 000/000 000/0000
UA2733 /IAH/   0050+1 001/006 000/000+00 001/006+00 000/000 008/0140"""

    if jcsy_parser and flight_db:
        print("Attempting to parse and import sample JCSY data from YAML example...")
        # Clean up database for fresh test
        # db_file = os.path.join(project_root, "src", "database", "flights.db")
        # if os.path.exists(db_file):
        #     os.remove(db_file)
        # flight_db.initialize_database() # Re-initialize

        result = import_jcsy_data(sample_jcsy_text_from_yaml)
        print(f"Import result: {result}")

        # You could add a SELECT query here to verify data
        if result["status"] == "success" and flight_db:
            try:
                with flight_db:
                    print("\nVerifying jcsy_flights table:")
                    for row in flight_db.cursor.execute("SELECT * FROM jcsy_flights"):
                        print(dict(row))
                    print("\nVerifying query_flights table:")
                    for row in flight_db.cursor.execute("SELECT * FROM query_flights"):
                        print(dict(row))
            except Exception as e:
                print(f"Error verifying data: {e}")

    else:
        print("Could not run test: JcsyParser or FlightDatabase not initialized.")

    print("\nbutton_functions.py updated with data insertion logic.")
