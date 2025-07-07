# Test file for refresh_button.py
# This file will contain pytest tests for the refresh_flight_data functionality.

import pytest
import os
import datetime
import sys
import sqlite3
from unittest.mock import patch, MagicMock

# Add project root to sys.path to allow importing src modules
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Modules to be tested
from src.ui import refresh_button
from src.ui import import_button
from bin.database.flight_db import FlightDatabase
from bin.scrapers.flightview_crawler import return_structure as CrawlerReturnStructure # Used by mocks

# Path to the JCSY test data file
_TEST_DIR = os.path.dirname(__file__)
JCSY_TEST_DATA_FILE_PATH = os.path.abspath(os.path.join(_TEST_DIR, '..', 'test_jcsy.txt'))


@pytest.fixture(scope="function")
def jcsy_data_for_refresh_test() -> tuple[str, str, datetime.date]:
    """
    Loads JCSY data from test_jcsy.txt, replaces the date placeholder
    with tomorrow's date (DDMMM format), and returns the processed content,
    the raw DDMMM date string, and tomorrow's date object.
    """
    if not os.path.exists(JCSY_TEST_DATA_FILE_PATH):
        raise FileNotFoundError(f"Test data file not found: {JCSY_TEST_DATA_FILE_PATH}")

    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    tomorrow_date_str_ddmmm = tomorrow.strftime('%d%b').upper()  # e.g., 25JUL

    with open(JCSY_TEST_DATA_FILE_PATH, 'r') as f:
        template_content = f.read()

    processed_content = template_content.replace("{{FLIGHT_DATE}}", tomorrow_date_str_ddmmm)
    return processed_content, tomorrow_date_str_ddmmm, tomorrow

@pytest.fixture(scope="function")
def refresh_db_instance():
    """
    Provides a clean in-memory FlightDatabase instance for each test function.
    Ensures the database schema is initialized.
    Crucially, it patches the global flight_db instances in import_button and refresh_button.
    """
    test_db_name = f"test_flights_refresh_button_{os.urandom(4).hex()}.db"
    test_db_path = os.path.join(project_root, "src", "database", test_db_name)

    # Ensure a clean state by trying to delete if it somehow exists (it shouldn't with unique names)
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

    # Create a new DB instance for testing
    # We patch the actual global variables in the modules under test.
    # This is more direct than trying to re-assign ib.flight_db if the module was already loaded.

    # Initialize the test database
    db = FlightDatabase(db_name=test_db_name)
    db.initialize_database()

    # Patching globals in the modules
    # We need to ensure that import_button.py and refresh_button.py use our test DB
    # The modules might have already initialized their own flight_db when they were imported.
    # So, we directly patch those global variables within the modules.

    import_button_db_patcher = patch('src.ui.import_button.flight_db', db)
    refresh_button_db_patcher = patch('src.ui.refresh_button.flight_db', db)

    # Start the patches
    import_button_db_patcher.start()
    refresh_button_db_patcher.start()

    yield db  # Provide this specific instance to tests

    # Teardown: stop patches, close, and remove the test database
    import_button_db_patcher.stop()
    refresh_button_db_patcher.stop()

    db.close()
    if os.path.exists(test_db_path):
        os.remove(test_db_path)

def test_refresh_data_success(jcsy_data_for_refresh_test, refresh_db_instance, mocker):
    """
    Tests the successful refresh of flight data.
    1. Imports data for tomorrow.
    2. Mocks the crawler to return specific time data.
    3. Calls refresh_flight_data.
    4. Verifies that the database is updated with crawler data.
    """
    processed_jcsy_content, tomorrow_date_ddmmm, tomorrow_date_obj = jcsy_data_for_refresh_test
    db = refresh_db_instance

    # --- Arrange: Import data ---
    # The JCSY header in test_jcsy.txt is CA0984/.../LAX,I (from fixture)
    header_airline = "CA"
    header_flight_no = "0984" # Aligning with test_jcsy.txt content
    header_airport = "LAX"
    header_inbound_flag = "I" # Inbound

    import_result = import_button.import_jcsy_data(processed_jcsy_content)
    assert import_result["status"] == "success", f"Import failed: {import_result['message']}"
    jcsy_master_id = int(import_result["message"].split("Master record ID: ")[1].split(".")[0])

    # Verify import for a specific segment that will be refreshed (e.g., the first one: UA1123 /SFO from test_jcsy.txt)
    # For an inbound flight (LAX arrival), the segment "UA1123 /SFO" means UA1123 from SFO to LAX.
    segment_airline = "UA"
    segment_flight_no = "1123"
    segment_origin_airport = "SFO" # From the flight line
    segment_dest_airport = header_airport # From the header (LAX)

    with db: # Use the FlightDatabase instance as a context manager
        cursor = db.cursor # Access cursor from the instance
        cursor.execute("""
            SELECT id, departure_airport, arrival_airport, std, atd, eta, ata
            FROM query_flights
            WHERE jcsy_flight_id = ? AND airline = ? AND flight_number = ? AND flight_date = ?
        """, (jcsy_master_id, segment_airline, segment_flight_no, tomorrow_date_obj.strftime('%Y-%m-%d')))
        flight_segment_row = cursor.fetchone()
        assert flight_segment_row is not None, "Flight segment not found after import"
        assert flight_segment_row["departure_airport"] == segment_origin_airport
        assert flight_segment_row["arrival_airport"] == segment_dest_airport
        # Ensure time fields are initially NULL or not set, as per current import logic
        assert flight_segment_row["std"] is None
        assert flight_segment_row["atd"] is None
        assert flight_segment_row["eta"] is None
        assert flight_segment_row["ata"] is None
        query_flight_id_to_refresh = flight_segment_row["id"]

    # --- Arrange: Mock Crawler ---
    mock_crawler_data = CrawlerReturnStructure(
        departure_airport=segment_origin_airport, # BOS
        arrival_airport=segment_dest_airport,   # LAX
        std=datetime.datetime.combine(tomorrow_date_obj, datetime.time(10, 0)),
        atd=datetime.datetime.combine(tomorrow_date_obj, datetime.time(10, 5)),
        etd=datetime.datetime.combine(tomorrow_date_obj, datetime.time(10, 2)),
        sta=datetime.datetime.combine(tomorrow_date_obj, datetime.time(12, 0)),
        ata=datetime.datetime.combine(tomorrow_date_obj, datetime.time(12, 5)),
        eta=datetime.datetime.combine(tomorrow_date_obj, datetime.time(12, 2))
    )

    # We need to mock the *instance* of the crawler's get_flight_info method
    # The refresh_button.py instantiates FlightViewCrawler locally.
    # So, we patch the class itself to make its instances return a MagicMock for get_flight_info.

    # Instead of patching the class, it's often easier to patch the specific function
    # if it's imported directly or patch where it's looked up.
    # `refresh_button._process_single_flight_refresh` calls `flightview_crawler_instance.get_flight_info`
    # and `call_crawler_with_timeout` which takes the method.
    # Let's mock `FlightViewCrawler` constructor to return a mock instance,
    # or mock its `get_flight_info` method if the instance is accessible.

    # Simpler: `refresh_button` imports `FlightViewCrawler`. We can patch this imported name.
    # The `_patch_crawlers` in `refresh_button.py`'s `__main__` gives a hint.
    # We want `FlightViewCrawler().get_flight_info` to be our mock.

    mock_flightview_instance = MagicMock()
    mock_flightview_instance.get_flight_info.return_value = mock_crawler_data

    # Patch where FlightViewCrawler is instantiated or its methods are called.
    # In refresh_button.py: `flightview_crawler_instance = FlightViewCrawler()`
    # then `flightview_crawler_instance.get_flight_info`
    # So, we patch `src.ui.refresh_button.FlightViewCrawler`
    # to make its constructor return our `mock_flightview_instance`.
    mocker.patch('src.ui.refresh_button.FlightViewCrawler', return_value=mock_flightview_instance)

    # Patch FlightDatabase constructor in refresh_button module to use the test db name
    # This ensures threads spawned by refresh_button use the same physical database file.
    def mock_db_constructor_for_refresh(*args, **kwargs):
        # The refresh_db_instance IS the 'db' object in this test scope.
        # Its db_name attribute holds the unique filename used by the test fixture.
        return FlightDatabase(db_name=db.db_name)

    mocker.patch('src.ui.refresh_button.FlightDatabase', side_effect=mock_db_constructor_for_refresh)

    # If FlightStatsCrawler was active, we'd mock it too.
    # mock_flightstats_instance = MagicMock()
    # mock_flightstats_instance.get_flight_info.return_value = None # e.g. FlightView succeeded
    # mocker.patch('src.ui.refresh_button.FlightStatsCrawler', return_value=mock_flightstats_instance)


    # --- Act: Call refresh_flight_data ---
    # The JCSY header for refresh_flight_data needs to match the *main* flight from JCSY file
    # JCSY:CA0988/{{FLIGHT_DATE}}/LAX,I
    # The refresh logic in `_get_flights_to_refresh` uses this header to find the `jcsy_flights` record,
    # then finds associated `query_flights`.
    # The `parse_jcsy_header_for_refresh` expects airline, flight_number, flight_date_str, optionally airport.
    # For our test_jcsy.txt: CA0988, tomorrow_date_ddmmm, LAX
    refresh_header_text = f"{header_airline}{header_flight_no}/{tomorrow_date_ddmmm}/{header_airport}"

    # Ensure refresh_button's global flight_db is our test db (already handled by refresh_db_instance fixture)
    # print(f"Using DB for refresh: {refresh_button.flight_db.db_name}") # For debugging

    status_message = refresh_button.refresh_flight_data(header_text=refresh_header_text)
    print(f"Refresh status: {status_message}") # For debugging

    # --- Assert ---
    assert "Refresh process completed" in status_message
    assert "Updated with data" in status_message # Check for positive update message for the flight

    # Verify crawler was called correctly
    # The args for get_flight_info are: airline, flight_number, flight_date_obj, dep_for_crawler, arr_for_crawler
    # For the segment DL1728 from BOS to LAX (QFID: query_flight_id_to_refresh)
    # flight_date_obj is tomorrow_date_obj
    # dep_for_crawler is segment_origin_airport ('BOS')
    # arr_for_crawler is segment_dest_airport ('LAX')
    mock_flightview_instance.get_flight_info.assert_any_call(
        segment_airline,          # "DL"
        segment_flight_no,        # "1728"
        tomorrow_date_obj,
        segment_origin_airport,   # "BOS"
        segment_dest_airport      # "LAX"
    )
    # We can use assert_any_call if other segments from the JCSY might also be processed.
    # If we are sure only one is processed or want to check a specific one:
    # For this test, the JCSY file has multiple segments. The refresh logic might iterate.
    # Let's ensure it was called for our target segment.

    # Verify database update for the specific segment
    with db: # Use the FlightDatabase instance as a context manager
        cursor = db.cursor # Access cursor from the instance
        cursor.execute("""
            SELECT std, etd, atd, sta, eta, ata
            FROM query_flights WHERE id = ?
        """, (query_flight_id_to_refresh,))
        updated_row = cursor.fetchone()
        assert updated_row is not None, "Segment vanished after refresh attempt"

        # Timestamps in DB are strings (ISO format). Compare with the ISO format of mock_crawler_data.
        # These assertions should be outside the 'with db:' block if db is closed after it,
        # or ensure db is still usable. Here, updated_row is already fetched.
        assert updated_row["std"] == mock_crawler_data.std.isoformat(sep=' ', timespec='seconds')
        assert updated_row["atd"] == mock_crawler_data.atd.isoformat(sep=' ', timespec='seconds')
        assert updated_row["eta"] == mock_crawler_data.eta.isoformat(sep=' ', timespec='seconds')
        assert updated_row["ata"] == mock_crawler_data.ata.isoformat(sep=' ', timespec='seconds')
        assert updated_row["etd"] == mock_crawler_data.etd.isoformat(sep=' ', timespec='seconds')
        assert updated_row["sta"] == mock_crawler_data.sta.isoformat(sep=' ', timespec='seconds')


def test_refresh_flight_already_has_data(jcsy_data_for_refresh_test, refresh_db_instance, mocker):
    """
    Tests that if a flight already has complete time data, crawlers are not called.
    """
    processed_jcsy_content, tomorrow_date_ddmmm, tomorrow_date_obj = jcsy_data_for_refresh_test
    db = refresh_db_instance

    header_airline = "CA"
    header_flight_no = "0984" # Aligning with test_jcsy.txt content
    header_airport = "LAX"

    import_result = import_button.import_jcsy_data(processed_jcsy_content)
    assert import_result["status"] == "success"
    jcsy_master_id = int(import_result["message"].split("Master record ID: ")[1].split(".")[0])

    # Pick a segment, e.g., UA1123 from test_jcsy.txt
    segment_airline = "UA"
    segment_flight_no = "1123"
    tomorrow_str_ymd = tomorrow_date_obj.strftime('%Y-%m-%d')
    # Manually update this segment to have complete time data
    with db: # Use the FlightDatabase instance as a context manager
        cursor = db.cursor # Access cursor from the instance
        cursor.execute("""
            UPDATE query_flights
            SET std = ?, atd = ?, eta = ?, ata = ?
            WHERE jcsy_flight_id = ? AND airline = ? AND flight_number = ? AND flight_date = ?
        """, (
                datetime.datetime.combine(tomorrow_date_obj, datetime.time(10, 0)),
                datetime.datetime.combine(tomorrow_date_obj, datetime.time(10, 5)),
                datetime.datetime.combine(tomorrow_date_obj, datetime.time(12, 0)),
                datetime.datetime.combine(tomorrow_date_obj, datetime.time(12, 5)),
            jcsy_master_id, segment_airline, segment_flight_no, tomorrow_str_ymd
        ))
        db.connection.commit() # Correctly call commit on the connection object
        assert cursor.rowcount > 0, "Failed to pre-populate data for test segment"

    # Mock the crawler instance
    mock_flightview_instance = MagicMock()
    mocker.patch('src.ui.refresh_button.FlightViewCrawler', return_value=mock_flightview_instance)

    # Patch FlightDatabase in refresh_button to use the correct test db name in threads
    def mock_db_constructor_for_refresh(*args, **kwargs):
        return FlightDatabase(db_name=db.db_name)
    mocker.patch('src.ui.refresh_button.FlightDatabase', side_effect=mock_db_constructor_for_refresh)

    refresh_header_text = f"{header_airline}{header_flight_no}/{tomorrow_date_ddmmm}/{header_airport}"
    status_message = refresh_button.refresh_flight_data(header_text=refresh_header_text)

    print(f"Refresh status (already has data): {status_message}")

    # Assert that the crawler was NOT called for any flight in this JCSY group,
    # because the specific segment was updated, and others are also updated to simulate all having data.
    # For simplicity, we'll check the main one. If other segments were missing data, they might still be called.
    # The current `refresh_flight_data` returns "All queried flights have complete time data" if ALL are complete.
    # If some are complete and some are not, it will attempt to refresh the incomplete ones.
    # This test makes ALL segments complete to check the specific message.

    # To make sure ALL segments are complete for the specific header:
    with db: # Use the FlightDatabase instance as a context manager
        cursor = db.cursor # Access cursor from the instance
        cursor.execute("""
            UPDATE query_flights
            SET std = ?, atd = ?, eta = ?, ata = ?
            WHERE jcsy_flight_id = ? AND flight_date = ?
        """, (
            datetime.datetime.combine(tomorrow_date_obj, datetime.time(10, 0)),
            datetime.datetime.combine(tomorrow_date_obj, datetime.time(10, 5)),
            datetime.datetime.combine(tomorrow_date_obj, datetime.time(12, 0)),
            datetime.datetime.combine(tomorrow_date_obj, datetime.time(12, 5)),
            jcsy_master_id, tomorrow_str_ymd
        ))
        db.connection.commit() # Correctly call commit on the connection object

    # At this point, mock_flightview_instance.get_flight_info might have been called
    # for other segments if they were not complete.

    # Now, ensure ALL segments for this jcsy_master_id are complete
    with db:
        cursor = db.cursor
        cursor.execute("""
            UPDATE query_flights
            SET std = ?, atd = ?, eta = ?, ata = ?
            WHERE jcsy_flight_id = ? AND flight_date = ?
        """, (
            datetime.datetime.combine(tomorrow_date_obj, datetime.time(10, 0)),
            datetime.datetime.combine(tomorrow_date_obj, datetime.time(10, 5)),
            datetime.datetime.combine(tomorrow_date_obj, datetime.time(12, 0)),
            datetime.datetime.combine(tomorrow_date_obj, datetime.time(12, 5)),
            jcsy_master_id, tomorrow_str_ymd
        ))
        db.connection.commit()

    # Reset the mock before the call we want to assert for no calls
    mock_flightview_instance.reset_mock()

    status_message_all_updated = refresh_button.refresh_flight_data(header_text=refresh_header_text)
    print(f"Refresh status (all updated, after mock reset): {status_message_all_updated}")

    assert "All queried flights have complete time data" in status_message_all_updated
    mock_flightview_instance.get_flight_info.assert_not_called()


def test_refresh_flight_not_found_in_db(refresh_db_instance, mocker):
    """
    Tests that if a flight specified in header is not in DB, an error is returned.
    """
    db = refresh_db_instance # DB is clean due to fixture scope
    tomorrow = datetime.date.today() + datetime.timedelta(days=1)
    tomorrow_date_ddmmm = tomorrow.strftime('%d%b').upper()

    non_existent_header = f"XX9999/{tomorrow_date_ddmmm}/XYZ"

    mock_flightview_instance = MagicMock()
    mocker.patch('src.ui.refresh_button.FlightViewCrawler', return_value=mock_flightview_instance)

    # Patch FlightDatabase in refresh_button to use the correct test db name in threads
    def mock_db_constructor_for_refresh(*args, **kwargs):
        return FlightDatabase(db_name=db.db_name) # db is refresh_db_instance
    mocker.patch('src.ui.refresh_button.FlightDatabase', side_effect=mock_db_constructor_for_refresh)

    status_message = refresh_button.refresh_flight_data(header_text=non_existent_header)
    print(f"Refresh status (not found): {status_message}")

    assert "Flight not found based on header" in status_message or \
           "No flights found matching criteria" in status_message # Depending on how specific the query is
    mock_flightview_instance.get_flight_info.assert_not_called()


if __name__ == '__main__':
    pytest.main()
