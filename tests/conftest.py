import pytest
import datetime
import sys
import os

# Add project root to sys.path to allow importing src modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from bin.database.flight_db import FlightDatabase
# Assuming safe_int_convert might be useful for default passenger data,
# though direct integer literals are fine too.
# from src.ui.import_button import safe_int_convert # Not strictly needed for this fixture's direct inserts

# --- JCSY Data for the Fixture ---
# Header: "JCSY: CA0984/04JUL/LAX,I"
# Query Flights: AS2182 LAS, AA3276 PHL, DL3634 SJC
# For the date "04JUL", we'll use the current year.
# Passenger data will be default/placeholder values.

# Determine the year for "04JUL"
current_year = datetime.date.today().year
fixture_flight_date = datetime.date(current_year, 7, 4) # July 4th of current year
fixture_flight_date_str = fixture_flight_date.strftime('%Y-%m-%d')

JCSY_HEADER_FIXTURE_DATA = {
    "airline": "CA",
    "flight_number": "0984",
    "flight_date": fixture_flight_date_str,
    "departure_airport": None, # Since it's Inbound to LAX
    "arrival_airport": "LAX",  # From header LAX,I
    "inbound_not": 1           # 1 for Inbound 'I'
}

QUERY_FLIGHTS_FIXTURE_DATA = [
    {
        "airline": "AS", "flight_number": "2182", "flight_date": fixture_flight_date_str,
        "departure_airport": "LAS", "arrival_airport": "LAX", # Arrival LAX from header
        "std_text": "1000", "std": datetime.datetime(current_year, 7, 4, 10, 0, 0),
        # Using some default passenger/bag counts
        "booked_count_non_economy": 10, "booked_count_economy": 50,
        "checked_count_non_economy": 8, "checked_count_economy": 45, "check_count_infant": 2,
        "bags_count_piece": 60, "bags_count_weight": 1200
    },
    {
        "airline": "AA", "flight_number": "3276", "flight_date": fixture_flight_date_str,
        "departure_airport": "PHL", "arrival_airport": "LAX",
        "std_text": "1130", "std": datetime.datetime(current_year, 7, 4, 11, 30, 0),
        "booked_count_non_economy": 5, "booked_count_economy": 30,
        "checked_count_non_economy": 5, "checked_count_economy": 28, "check_count_infant": 1,
        "bags_count_piece": 35, "bags_count_weight": 700,
        # Some times present, some not, for testing refresh logic later
        "ata": datetime.datetime(current_year, 7, 4, 14, 0, 0)
    },
    {
        "airline": "DL", "flight_number": "3634", "flight_date": fixture_flight_date_str,
        "departure_airport": "SJC", "arrival_airport": "LAX",
        "std_text": "1200", # std will be null to test refresh
        "std": None, "atd": None, "eta": None, "ata": None, # All times missing
        "booked_count_non_economy": 0, "booked_count_economy": 20,
        "checked_count_non_economy": 0, "checked_count_economy": 18, "check_count_infant": 0,
        "bags_count_piece": 20, "bags_count_weight": 400
    }
]


@pytest.fixture(scope="function") # Default scope, new DB for each test function
def populated_db():
    """
    Pytest fixture that sets up an in-memory SQLite database
    with a predefined JCSY flight header and related query flights.
    """
    # print("\nSetting up in-memory DB for populated_db fixture...")
    db = FlightDatabase(db_name=":memory:")
    db.initialize_database() # Create schema

    try:
        with db: # Manages connection
            # Insert JCSY Header Flight
            cursor = db.cursor
            cursor.execute("""
                INSERT INTO jcsy_flights
                    (airline, flight_number, flight_date, departure_airport, arrival_airport, inbound_not)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                JCSY_HEADER_FIXTURE_DATA["airline"],
                JCSY_HEADER_FIXTURE_DATA["flight_number"],
                JCSY_HEADER_FIXTURE_DATA["flight_date"],
                JCSY_HEADER_FIXTURE_DATA["departure_airport"],
                JCSY_HEADER_FIXTURE_DATA["arrival_airport"],
                JCSY_HEADER_FIXTURE_DATA["inbound_not"]
            ))
            jcsy_flight_id = cursor.lastrowid
            if not jcsy_flight_id:
                pytest.fail("Failed to insert jcsy_flights header for fixture.")

            # Insert Query Flights
            for qf_data in QUERY_FLIGHTS_FIXTURE_DATA:
                cursor.execute("""
                    INSERT INTO query_flights (
                        jcsy_flight_id, airline, flight_number, flight_date,
                        departure_airport, arrival_airport, std_text, std, atd, eta, ata,
                        booked_count_non_economy, booked_count_economy,
                        checked_count_non_economy, checked_count_economy, check_count_infant,
                        bags_count_piece, bags_count_weight
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    jcsy_flight_id,
                    qf_data["airline"], qf_data["flight_number"], qf_data["flight_date"],
                    qf_data["departure_airport"], qf_data["arrival_airport"],
                    qf_data.get("std_text"), qf_data.get("std"), qf_data.get("atd"),
                    qf_data.get("eta"), qf_data.get("ata"),
                    qf_data.get("booked_count_non_economy", 0), qf_data.get("booked_count_economy", 0),
                    qf_data.get("checked_count_non_economy", 0), qf_data.get("checked_count_economy", 0),
                    qf_data.get("check_count_infant", 0),
                    qf_data.get("bags_count_piece", 0), qf_data.get("bags_count_weight", 0)
                ))
            db.connection.commit()

        # print(f"Fixture DB setup complete. jcsy_flight_id: {jcsy_flight_id}")
        yield db # Provide the db instance to the test

    finally:
        # print("Tearing down in-memory DB for populated_db fixture...")
        if db and db.connection:
            db.close()

# Example of how a test would use this fixture:
# def test_something_with_db(populated_db):
#     # populated_db is an instance of FlightDatabase with data
#     with populated_db as db:
#         db.cursor.execute("SELECT COUNT(*) FROM query_flights")
#         count = db.cursor.fetchone()[0]
#     assert count == len(QUERY_FLIGHTS_FIXTURE_DATA)

print("tests/conftest.py created with populated_db fixture.")
