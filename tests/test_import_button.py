import pytest
import os
import datetime
import sys
import sqlite3

# Add project root to sys.path to allow importing src modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.import_button import import_jcsy_data, parse_std_datetime, safe_int_convert
from bin.database.flight_db import FlightDatabase
from bin.config.jcsy_config import JcsyParser # Using the actual parser

# --- Test Data ---
# This is the content that *should* be in test_jcsy.txt
# Since we had issues updating the file, we'll define it here for the tests.

def _get_parsed_header_date_for_test(date_str_short: str) -> datetime.date | None:
    """
    Mimics the parse_header_date logic from jcsy_config.yaml for test setup.
    Input: "12DEC"
    Output: datetime.date object for 12th Dec of current year.
    """
    try:
        # Assumes format like 12DEC (len 5)
        if len(date_str_short) == 5:
            date_obj = datetime.datetime.strptime(date_str_short, '%d%b').date()
            date_obj = date_obj.replace(year=datetime.datetime.now().year)
            return date_obj
        # Add handling for DDMMMYY if needed, though current JCSY is DDMMM
        return None # Should align with whatever the actual parser supports
    except ValueError:
        return None

TEST_JCSY_INBOUND_CONTENT = """JCSY:CA0984/12DEC/LAX,I
FLT/ORIG   ARVL   BKD     CHK        UCK     NBRD       BAG
DL0738 /JFK       000/001 000/001+00 000/000 000/000+00 001/0016
AS2182 /LAS       001/000 001/000+00 000/000 000/000+00 002/0032
UA8283 /ORD       000/001 000/001+00 000/000 000/000+00 002/0032
AA3276 /PHL       000/001 000/000+00 000/001 000/000+00 000/0000
##TOTAL##         005/093 005/091+00 000/002 003/050+00 112/1811
"""

# Sample JCSY data for an OUTBOUND flight
# For PEK, O (Outbound from PEK)
# Date: 15th August of current year
current_year = datetime.date.today().year
outbound_flight_date_str = f"{current_year}-08-15"
outbound_flight_date_jcsy = f"15AUG"

TEST_JCSY_OUTBOUND_CONTENT = f"""JCSY:MU5183/{outbound_flight_date_jcsy}/PEK,O
FLT/DEST   DEPT   BKD     CHK        UCK     NBRD       BAG
CZ3101 /CAN       001/002 001/002+00 000/000 000/000+00 003/0060
CA1831 /SHA       000/005 000/005+00 000/000 000/000+00 005/0100
##TOTAL##         001/007 001/007+00 000/000 000/000+00 008/0160
"""


# --- Fixtures ---
@pytest.fixture(scope="function")
def db_instance():
    """
    Provides a clean in-memory FlightDatabase instance for each test function.
    Ensures the database schema is initialized.
    """
    # Use :memory: for a fresh DB each time, ensuring no cross-test contamination by default
    # For import_button's specific global `flight_db`, this approach needs careful handling
    # or modification of import_button.py to accept a db instance.
    # For now, we test the global instance, but ensure it's clean.

    # The import_button module initializes its own global `flight_db`.
    # We need to ensure this global instance is using a predictable, clean database.
    # One way is to control the db file it uses.
    test_db_name = "test_flights_import_button.db"
    test_db_path = os.path.join(project_root, "src", "database", test_db_name)

    # Ensure a clean state by deleting the test DB if it exists
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    # Temporarily override the global flight_db in import_button
    # This is a bit intrusive but necessary if import_button.py uses a hardcoded global db
    # A better long-term solution is dependency injection for flight_db in import_button.py
    from src.ui import import_button as ib
    original_flight_db = ib.flight_db

    # Create a new DB instance for testing
    ib.flight_db = FlightDatabase(db_name=test_db_name)
    ib.flight_db.initialize_database() # Ensure tables are created

    yield ib.flight_db # Provide this specific instance to tests

    # Teardown: close and remove the test database
    ib.flight_db.close()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    # Restore original flight_db if it was different
    ib.flight_db = original_flight_db


# --- Test Cases for import_jcsy_data ---

def test_import_inbound_jcsy_data_success(db_instance):
    """Test successful import of valid INBOUND JCSY data."""
    # Extract header info for cleanup and verification
    # JCSY:CA0984/12DEC/LAX,I
    header_airline = "CA"
    header_flight_no = "0984"
    raw_date_str = "12DEC"
    flight_date_obj = _get_parsed_header_date_for_test(raw_date_str)
    assert flight_date_obj is not None, f"Test helper _get_parsed_header_date_for_test failed for {raw_date_str}"
    header_flight_date_db = flight_date_obj.strftime('%Y-%m-%d')

    # Clean up any pre-existing data for this flight
    db_instance.delete_jcsy_flight_by_header(header_airline, header_flight_no, header_flight_date_db)

    result = import_jcsy_data(TEST_JCSY_INBOUND_CONTENT)

    assert result["status"] == "success"
    assert "Successfully imported JCSY data" in result["message"]
    jcsy_flight_id = result["message"].split("Master record ID: ")[1].split(".")[0]
    assert jcsy_flight_id is not None

    with db_instance as db:
        # Verify jcsy_flights table
        db.cursor.execute("SELECT * FROM jcsy_flights WHERE airline=? AND flight_number=? AND flight_date=?",
                            (header_airline, header_flight_no, header_flight_date_db))
        jcsy_header_row = db.cursor.fetchone()
        assert jcsy_header_row is not None
        assert jcsy_header_row["airline"] == header_airline
        assert jcsy_header_row["flight_number"] == header_flight_no
        assert jcsy_header_row["flight_date"] == header_flight_date_db
        assert jcsy_header_row["arrival_airport"] == "LAX" # Inbound
        assert jcsy_header_row["departure_airport"] is None
        assert jcsy_header_row["inbound_not"] == 1

        # Verify query_flights table (check one entry for brevity)
        # DL0738 /JFK ...
        db.cursor.execute("SELECT * FROM query_flights WHERE jcsy_flight_id=? AND airline=? AND flight_number=?",
                            (jcsy_header_row["id"], "DL", "0738"))
        query_flight_row = db.cursor.fetchone()
        assert query_flight_row is not None
        assert query_flight_row["departure_airport"] == "JFK" # Origin for this segment
        assert query_flight_row["arrival_airport"] == "LAX"   # Destination from header
        assert query_flight_row["flight_date"] == header_flight_date_db
        assert query_flight_row["booked_count_non_economy"] == 0
        assert query_flight_row["booked_count_economy"] == 1
        assert query_flight_row["checked_count_non_economy"] == 0
        assert query_flight_row["checked_count_economy"] == 1
        assert query_flight_row["check_count_infant"] == 0 # from +00
        assert query_flight_row["bags_count_piece"] == 1
        assert query_flight_row["bags_count_weight"] == 16
        assert query_flight_row["std_text"] == "" # Not in this JCSY format's flight lines, parser returns empty string

        # Check total number of query flights
        db.cursor.execute("SELECT COUNT(*) FROM query_flights WHERE jcsy_flight_id=?", (jcsy_header_row["id"],))
        count = db.cursor.fetchone()[0]
        assert count == 4 # DL0738, AS2182, UA8283, AA3276

def test_import_inbound_jcsy_data_idempotency(db_instance):
    """Test that importing the same INBOUND JCSY data twice doesn't duplicate or error."""
    header_airline = "CA"
    header_flight_no = "0984"
    raw_date_str = "12DEC"
    flight_date_obj = _get_parsed_header_date_for_test(raw_date_str)
    assert flight_date_obj is not None, f"Test helper _get_parsed_header_date_for_test failed for {raw_date_str}"
    header_flight_date_db = flight_date_obj.strftime('%Y-%m-%d')

    # Clean up before first import
    db_instance.delete_jcsy_flight_by_header(header_airline, header_flight_no, header_flight_date_db)

    result1 = import_jcsy_data(TEST_JCSY_INBOUND_CONTENT)
    assert result1["status"] == "success"
    jcsy_flight_id1 = int(result1["message"].split("Master record ID: ")[1].split(".")[0])

    # Attempt to import again
    # The current import_button.py logic will try to insert into jcsy_flights,
    # which has a UNIQUE constraint. This should result in a database error reported by import_jcsy_data.
    result2 = import_jcsy_data(TEST_JCSY_INBOUND_CONTENT)
    assert result2["status"] == "error" # Expecting an error due to unique constraint
    assert "UNIQUE constraint failed" in result2["message"] # Specific to SQLite

    # Verify that the original data is still there and no new data was partially added
    with db_instance as db:
        db.cursor.execute("SELECT COUNT(*) FROM jcsy_flights WHERE airline=? AND flight_number=? AND flight_date=?",
                            (header_airline, header_flight_no, header_flight_date_db))
        count_jcsy = db.cursor.fetchone()[0]
        assert count_jcsy == 1 # Still only one header

        db.cursor.execute("SELECT COUNT(*) FROM query_flights WHERE jcsy_flight_id=?", (jcsy_flight_id1,))
        count_query = db.cursor.fetchone()[0]
        assert count_query == 4 # Original query flights are still there

def test_import_outbound_jcsy_data_success(db_instance):
    """Test successful import of valid OUTBOUND JCSY data."""
    header_airline = "MU"
    header_flight_no = "5183"
    header_flight_date_db = outbound_flight_date_str # YYYY-MM-DD

    db_instance.delete_jcsy_flight_by_header(header_airline, header_flight_no, header_flight_date_db)
    result = import_jcsy_data(TEST_JCSY_OUTBOUND_CONTENT)

    assert result["status"] == "success"
    jcsy_flight_id = result["message"].split("Master record ID: ")[1].split(".")[0]

    with db_instance as db:
        db.cursor.execute("SELECT * FROM jcsy_flights WHERE id=?", (jcsy_flight_id,))
        jcsy_header_row = db.cursor.fetchone()
        assert jcsy_header_row is not None
        assert jcsy_header_row["airline"] == header_airline
        assert jcsy_header_row["flight_number"] == header_flight_no
        assert jcsy_header_row["flight_date"] == header_flight_date_db
        assert jcsy_header_row["departure_airport"] == "PEK" # Outbound
        assert jcsy_header_row["arrival_airport"] is None
        assert jcsy_header_row["inbound_not"] == 0 # 0 for Outbound 'O'

        # Verify a query flight (e.g., CZ3101 /CAN)
        db.cursor.execute("SELECT * FROM query_flights WHERE jcsy_flight_id=? AND airline=? AND flight_number=?",
                            (jcsy_flight_id, "CZ", "3101"))
        query_flight_row = db.cursor.fetchone()
        assert query_flight_row is not None
        assert query_flight_row["departure_airport"] == "PEK" # Origin from header
        assert query_flight_row["arrival_airport"] == "CAN"   # Destination for this segment
        assert query_flight_row["flight_date"] == header_flight_date_db
        assert query_flight_row["booked_count_economy"] == 2
        assert query_flight_row["std_text"] == "" # Not in this JCSY format, parser returns empty string

        db.cursor.execute("SELECT COUNT(*) FROM query_flights WHERE jcsy_flight_id=?", (jcsy_flight_id,))
        count = db.cursor.fetchone()[0]
        assert count == 2


def test_import_malformed_jcsy_data(db_instance):
    """Test import with malformed JCSY data."""
    malformed_content = "JCSY:GARBAGE_DATA"
    result = import_jcsy_data(malformed_content)
    assert result["status"] == "error"
    assert "Failed to parse JCSY header" in result["message"] # Or other relevant parser error

    malformed_content_no_flights = "JCSY:CA0984/12DEC/LAX,I" # Header ok, but no flight lines
    # Depending on parser leniency, this might be a success with 0 flights or an error.
    # The current JcsyParser seems to allow this.
    # We need to ensure the DB is clean for this specific test.
    header_airline = "CA"
    header_flight_no = "0984"
    raw_date_str = "12DEC" # Matches the date in malformed_content_no_flights
    flight_date_obj = _get_parsed_header_date_for_test(raw_date_str)
    assert flight_date_obj is not None, f"Test helper _get_parsed_header_date_for_test failed for {raw_date_str}"
    header_flight_date_db = flight_date_obj.strftime('%Y-%m-%d')
    db_instance.delete_jcsy_flight_by_header(header_airline, header_flight_no, header_flight_date_db)

    result = import_jcsy_data(malformed_content_no_flights)
    assert result["status"] == "success" # Header is valid, 0 flights processed
    assert "Processed 0 flight segments" in result["message"]
    jcsy_flight_id = result["message"].split("Master record ID: ")[1].split(".")[0]

    with db_instance as db:
        db.cursor.execute("SELECT COUNT(*) FROM query_flights WHERE jcsy_flight_id=?", (jcsy_flight_id,))
        count = db.cursor.fetchone()[0]
        assert count == 0


def test_import_jcsy_parser_not_initialized():
    """Test behavior when JcsyParser is not initialized (simulated)."""
    from src.ui import import_button as ib
    original_parser = ib.jcsy_parser
    ib.jcsy_parser = None # Simulate parser not being initialized

    result = import_jcsy_data("some text")
    assert result["status"] == "error"
    assert "JCSY Parser not initialized" in result["message"]

    ib.jcsy_parser = original_parser # Restore


def test_import_flight_db_not_initialized():
    """Test behavior when FlightDatabase is not initialized (simulated)."""
    from src.ui import import_button as ib
    original_db = ib.flight_db
    ib.flight_db = None # Simulate DB not being initialized

    result = import_jcsy_data(TEST_JCSY_INBOUND_CONTENT)
    assert result["status"] == "error"
    assert "Flight Database not initialized" in result["message"]

    ib.flight_db = original_db # Restore

# --- Test Cases for Helper Functions ---

@pytest.mark.parametrize("std_text, base_date_str, expected_str", [
    ("1000", "2023-01-15", "2023-01-15 10:00:00"),
    ("2359", "2023-01-15", "2023-01-15 23:59:00"),
    ("0000", "2023-01-15", "2023-01-15 00:00:00"),
    ("1000+1", "2023-01-15", "2023-01-16 10:00:00"), # Next day
    ("2300+2", "2023-01-30", "2023-02-01 23:00:00"), # Rolls over month
    ("0800+0", "2023-01-15", "2023-01-15 08:00:00"),
    ("100", None, None), # Invalid text
    (None, "2023-01-15", None),
    ("", "2023-01-15", None),
    ("ABCD", "2023-01-15", None),
    ("10:00", "2023-01-15", None), # Invalid format
    ("2400", "2023-01-15", None), # Invalid hour
    ("1060", "2023-01-15", None), # Invalid minute
    ("1000+A", "2023-01-15", None), # Invalid day offset
])
def test_parse_std_datetime(std_text, base_date_str, expected_str):
    base_date = datetime.datetime.strptime(base_date_str, '%Y-%m-%d').date() if base_date_str else None
    expected_dt = datetime.datetime.strptime(expected_str, '%Y-%m-%d %H:%M:%S') if expected_str else None

    assert parse_std_datetime(std_text, base_date) == expected_dt


@pytest.mark.parametrize("value_str, expected_int", [
    ("001", 1),
    ("100", 100),
    ("0", 0),
    ("000", 0),
    (None, 0),
    ("", 0),
    ("  ", 0),
    ("abc", 0), # Non-numeric
    ("10.5", 0), # Non-integer
    (123, 123), # Already an int
    ("0050", 50),
])
def test_safe_int_convert(value_str, expected_int):
    assert safe_int_convert(value_str) == expected_int

if __name__ == '__main__':
    # This allows running pytest from the command line on this file
    pytest.main()

print("tests/test_import_button.py created.")
