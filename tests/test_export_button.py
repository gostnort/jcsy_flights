# tests/test_export_button.py

import pytest
import os
import sys
from datetime import datetime, date, timedelta, time
import sqlite3

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.export_button import export_button
from src.ui.import_button import import_jcsy_data, jcsy_parser as global_jcsy_parser, flight_db as global_import_flight_db
from src.ui.refresh_button import refresh_flight_data, flight_db as global_refresh_flight_db, FlightViewCrawler, CrawlerReturnStructure
from bin.database.flight_db import FlightDatabase
from bin.database.flight_get import FlightGet

# Store original global db instances from import/refresh modules
original_global_import_flight_db = global_import_flight_db
original_global_refresh_flight_db = global_refresh_flight_db

@pytest.fixture(scope="function")
def setup_test_db():
    """
    Sets up an in-memory SQLite database for testing, populates schema,
    and handles teardown.
    Also patches the global DB instances in import_button and refresh_button.
    """
    # Use a new in-memory database for each test function
    test_db = FlightDatabase(db_name=":memory:")
    test_db.initialize_database() # Create tables

    # Explicitly clear tables to ensure a completely fresh state for each test
    # This helps if :memory: DB + initialize_database isn't perfectly isolating across some internal calls
    # or if other modules might interact with a shared :memory: instance name if that were the case.
    with test_db as db: # Use context manager to ensure connection is active
        cursor = db.connection.cursor()
        try:
            cursor.execute("DELETE FROM query_flights")
            cursor.execute("DELETE FROM jcsy_flights")
            # Add other tables if they exist and need clearing, e.g., from flight_add or flight_maintain
            # For now, these are the main ones related to import/export.
            db.connection.commit()
        finally:
            cursor.close()

    # Patch the global db instances in the modules we're testing indirectly
    sys.modules['src.ui.import_button'].flight_db = test_db
    sys.modules['src.ui.refresh_button'].flight_db = test_db

    # Ensure FlightGet uses this test_db if it were to instantiate its own FlightDatabase
    # This might require FlightGet to accept a db_name or connection, or be refactored for DI.
    # For now, export_button instantiates FlightGet without params, so it will use its default.
    # This is a potential issue: FlightGet in export_button might use a different DB instance.
    # To fix this, FlightGet should ideally take a connection or FlightDatabase instance.
    # Workaround: We can re-initialize FlightGet's internal DB if it's module-level,
    # or rely on the fact that FlightGet() will also create an in-memory DB if default is :memory:
    # For this test, we will ensure FlightGet is also patched or its default is in-memory.
    # The FlightDatabase class, if its default db_name is ":memory:", might make this simpler.
    # Let's assume FlightGet() will use the same :memory: context if not specified,
    # or we can try to patch its internal _db if needed.
    # For now, we'll proceed and address if FlightGet doesn't see the data.

    yield test_db # Provide the db to the test

    test_db.close()

    # Restore original global db instances
    sys.modules['src.ui.import_button'].flight_db = original_global_import_flight_db
    sys.modules['src.ui.refresh_button'].flight_db = original_global_refresh_flight_db


# --- Mocking for Refresh Button ---
class MockFlightViewCrawler(FlightViewCrawler):
    def __init__(self, data_to_return=None):
        super().__init__() # In case the parent __init__ does something important
        self.data_to_return = data_to_return
        self.called_with_args = None

    def get_flight_info(self, airline, flight_number, flight_date, depapt, arrapt):
        self.called_with_args = (airline, flight_number, flight_date, depapt, arrapt)
        if self.data_to_return:
            # Check if the call matches expected flight for this data
            if self.data_to_return.get("match_criteria"):
                match = self.data_to_return["match_criteria"]
                if (match["airline"] == airline and
                    match["flight_number"] == flight_number and
                    match["flight_date"] == flight_date):
                    return self.data_to_return["data"]
            else: # Generic mock data for any call
                return self.data_to_return["data"]
        return None # Default: no data found


@pytest.fixture
def mock_crawlers(monkeypatch):
    """Fixture to mock crawlers used by refresh_flight_data."""
    mock_data_map = {} # flight_key -> CrawlerReturnStructure

    def get_mock_data_for_flight(airline, flight_number, flight_date_obj):
        key = (airline, flight_number, flight_date_obj.strftime('%Y-%m-%d'))
        return mock_data_map.get(key)

    # This will be our new FlightViewCrawler class for the duration of the test
    class PatchedFlightViewCrawler(FlightViewCrawler):
        def get_flight_info(self, airline, flight_number, flight_date_obj, depapt, arrapt):
            # print(f"MOCK PatchedFlightViewCrawler: Called for {airline}{flight_number} on {flight_date_obj}")
            data = get_mock_data_for_flight(airline, flight_number, flight_date_obj)
            if data:
                # print(f"MOCK PatchedFlightViewCrawler: Found mock data for {airline}{flight_number}")
                return data
            # print(f"MOCK PatchedFlightViewCrawler: No mock data for {airline}{flight_number}")
            return None

    monkeypatch.setattr(sys.modules['src.ui.refresh_button'], 'FlightViewCrawler', PatchedFlightViewCrawler)
    # If FlightStatsCrawler was active, it would be patched here too.

    # Return a way for the test to set mock data
    return mock_data_map


# --- Test Data ---
TEST_JCSY_INPUT_TEMPLATE = """JCSY:CA0984/{{FLIGHT_DATE_DDMMM}}/LAX,I
FLT/ORIG   ARVL   BKD     CHK        UCK     NBRD       BAG
UA1123 /SFO       000/001 000/001+00 000/000 000/000+00 001/0016
AA2400 /DFW       001/000 001/000+00 000/000 000/000+00 002/0032
DL0968 /SEA       000/001 000/001+00 000/000 000/000+00 002/0032
UA0267 /ORD       000/001 000/000+00 000/001 000/000+00 000/0000
"""

# Expected JCSY output structure, will be filled dynamically
EXPECTED_JCSY_OUTPUT_TEMPLATE = """JCSY:CA0984/{flight_date_ddmmm}/LAX,I
FLT/ORIG   ARVL   BKD     CHK        UCK     NBRD       BAG
UA1123 /SFO {ua1123_time}  000/001 000/001+00 000/000 000/000+00 001/0016
AA2400 /DFW {aa2400_time}  001/000 001/000+00 000/000 000/000+00 002/0032
DL0968 /SEA {dl0968_time}  000/001 000/001+00 000/000 000/000+00 002/0032
UA0267 /ORD {ua0267_time}  000/001 000/000+00 000/000 000/000+00 000/0000"""


def test_export_button_logic(setup_test_db, mock_crawlers):
    """
    Tests the export_button function for both Markdown and JCSY formats.
    """
    test_db = setup_test_db # Get the initialized in-memory DB

    # 1. Data Preparation
    # Determine dates for testing
    test_flight_date = date.today()
    flight_date_ddmmm = test_flight_date.strftime("%d%b").upper()
    flight_date_db_format = test_flight_date.strftime("%Y-%m-%d")

    # Prepare JCSY input by replacing placeholder
    jcsy_input_data = TEST_JCSY_INPUT_TEMPLATE.replace("{{FLIGHT_DATE_DDMMM}}", flight_date_ddmmm)

    # Call import_jcsy_data
    import_result = import_jcsy_data(jcsy_input_data)
    assert import_result["status"] == "success", f"Import failed: {import_result['message']}"

    # Get the header_flight_id from the import result (it's part of the message)
    # "Successfully imported JCSY data. Master record ID: {jcsy_flight_id}. ..."
    try:
        header_flight_id = int(import_result["message"].split("Master record ID: ")[1].split(".")[0])
    except (IndexError, ValueError) as e:
        pytest.fail(f"Could not extract header_flight_id from import message: {import_result['message']} - {e}")

    # Manually update ETA/ATA times in the database for specific segments
    # to test the export logic for time fields.
    # UA1123: Only ETA
    # AA2400: Only ATA
    # DL0968: Both ETA and ATA (ATA should be preferred)
    # UA0267: Neither ETA nor ATA (should show '----' or similar)

    eta_ua1123 = datetime.combine(test_flight_date, time(8, 30)) # 08:30
    ata_aa2400 = datetime.combine(test_flight_date, time(8, 55)) # 08:55 (suppose STA was 08:50)
    eta_dl0968 = datetime.combine(test_flight_date, time(9, 5))  # 09:05
    ata_dl0968 = datetime.combine(test_flight_date, time(9, 10)) # 09:10 (this should be used)

    with test_db as db: # Use the FlightDatabase instance as the context manager
        # The connection is managed by test_db's __enter__ and __exit__
        cursor = db.connection.cursor() # Obtain cursor from the active connection
        # Find the query_flight IDs first (safer than assuming order)
        # This is important because IDs are auto-incrementing and can vary.
        def get_qf_id(airline, flight_num):
            cursor.execute(
                "SELECT id FROM query_flights WHERE airline=? AND flight_number=? AND flight_date=?",
                (airline, flight_num, flight_date_db_format)
            )
            res = cursor.fetchone()
            assert res, f"Could not find query_flight for {airline}{flight_num}"
            return res[0]

        qf_id_ua1123 = get_qf_id("UA", "1123")
        qf_id_aa2400 = get_qf_id("AA", "2400")
        qf_id_dl0968 = get_qf_id("DL", "0968")
        qf_id_ua0267 = get_qf_id("UA", "0267") # For no times

        cursor.execute("UPDATE query_flights SET eta = ? WHERE id = ?", (eta_ua1123.isoformat(sep=' '), qf_id_ua1123))
        cursor.execute("UPDATE query_flights SET ata = ? WHERE id = ?", (ata_aa2400.isoformat(sep=' '), qf_id_aa2400))
        cursor.execute("UPDATE query_flights SET eta = ?, ata = ? WHERE id = ?", (eta_dl0968.isoformat(sep=' '), ata_dl0968.isoformat(sep=' '), qf_id_dl0968))
        # For UA0267, ensure times are NULL (they should be by default from import if not in JCSY)
        cursor.execute("UPDATE query_flights SET eta = NULL, ata = NULL WHERE id = ?", (qf_id_ua0267,))
        db.connection.commit() # Commit on the connection from the context-managed db instance
        cursor.close() # Explicitly close cursor

    # 2. Call refresh_flight_data (optional, but good for completeness)
    # Mock crawler data for refresh_flight_data. Let's say we want to refresh UA0267
    # and give it an ETA time via crawler.
    eta_ua0267_refreshed = datetime.combine(test_flight_date, time(9, 25)) # 09:25

    # Structure the mock data for the mock_crawlers fixture
    mock_crawlers[( "UA", "0267", flight_date_db_format )] = CrawlerReturnStructure(
        departure_airport="ORD", # Not strictly needed for this test's time focus
        arrival_airport="LAX",   # Not strictly needed
        std=None, atd=None, etd=None, # Not providing these via refresh
        sta=None,
        eta=eta_ua0267_refreshed, # This is what we want refresh to update
        ata=None
    )

    # Call refresh for the main flight. This should trigger refresh for its segments.
    # The header for refresh_flight_data is like "CA0984/DDMMM/LAX"
    refresh_header_text = f"CA0984/{flight_date_ddmmm}/LAX"
    refresh_status = refresh_flight_data(header_text=refresh_header_text)
    # print(f"Refresh status: {refresh_status}") # For debugging
    assert "Error" not in refresh_status, f"Refresh failed: {refresh_status}"
    # assert "Updated with data" in refresh_status or "No flights found matching criteria" in refresh_status or "complete time data" in refresh_status

    # Verify that UA0267's ETA was updated by refresh
    with test_db as db: # Use the FlightDatabase instance as the context manager
        cursor = db.connection.cursor() # Obtain cursor from the active connection
        try:
            cursor.execute("SELECT eta FROM query_flights WHERE id = ?", (qf_id_ua0267,))
            refreshed_eta_val = cursor.fetchone()[0]
            # print(f"Refreshed ETA for UA0267: {refreshed_eta_val}") # Debug
            assert refreshed_eta_val is not None, "Refresh did not update ETA for UA0267"
            # The value stored is a string, convert it back to datetime for comparison
            assert datetime.fromisoformat(refreshed_eta_val).time() == eta_ua0267_refreshed.time(), \
                "Refresh updated UA0267 ETA to an unexpected value."
        finally:
            cursor.close()


    # 3. Test Markdown Export
    markdown_output = export_button(header_flight_id, output_format_is_markdown=True)
    # print("\n--- Markdown Output ---")
    # print(markdown_output)
    assert "Error" not in markdown_output, f"Markdown export returned an error: {markdown_output}"
    # Markdown uses YYYY-MM-DD for date, and currently header_departure_airport might be None for inbound
    # For now, let's check the part that should be stable, and address airport display in MarkdownFormatter separately.
    # The date in markdown is flight_date_db_format (YYYY-MM-DD)
    # The airport in markdown header should now be LAX due to _get_header_station_airport
    expected_markdown_header_part = f"## JCSY:CA0984/{flight_date_db_format}/LAX,I" # Expecting LAX
    assert expected_markdown_header_part in markdown_output, \
        f"Expected Markdown header part '{expected_markdown_header_part}' not found in '{markdown_output}'"
    assert "Flight Number|Airport|Delay Mins|Booked Pax|Checked Pax|Bags/Weight" in markdown_output # Check table header
    assert "UA1123" in markdown_output # Check one of the flights is present

    # 4. Test JCSY Export
    jcsy_output = export_button(header_flight_id, output_format_is_markdown=False)
    # print("\n--- JCSY Output ---")
    # print(jcsy_output)
    assert "Error" not in jcsy_output, f"JCSY export returned an error: {jcsy_output}"

    # Construct expected JCSY output string
    # Times for JCSY output:
    # UA1123: ETA 08:30 -> "0830"
    # AA2400: ATA 08:55 -> "0855"
    # DL0968: ATA 09:10 (preferred over ETA 09:05) -> "0910"
    # UA0267: ETA from refresh 09:25 -> "0925"

    expected_jcsy_str = EXPECTED_JCSY_OUTPUT_TEMPLATE.format(
        flight_date_ddmmm=flight_date_ddmmm,
        ua1123_time=eta_ua1123.strftime("%H%M"),
        aa2400_time=ata_aa2400.strftime("%H%M"),
        dl0968_time=ata_dl0968.strftime("%H%M"), # ATA is preferred
        ua0267_time=eta_ua0267_refreshed.strftime("%H%M") # From refresh
    )

    # Normalizing whitespace for comparison, as trailing spaces might differ slightly.
    # Split into lines, strip each line, then rejoin.
    normalized_expected = "\n".join([line.strip() for line in expected_jcsy_str.splitlines()])
    normalized_actual = "\n".join([line.strip() for line in jcsy_output.splitlines()])

    # print("\n--- Expected JCSY (Normalized) ---")
    # print(normalized_expected)
    # print("\n--- Actual JCSY (Normalized) ---")
    # print(normalized_actual)

    assert normalized_actual == normalized_expected, "JCSY output does not match expected structure or content."

    # Final check: Ensure FlightGet used by export_button saw the test data.
    # If export_button produced meaningful output (not just "Error: Header flight data not found"),
    # it implies FlightGet was able to access the data from header_flight_id.
    # This is implicitly tested by the assertions above.


# Example of running pytest from command line:
# python -m pytest tests/test_export_button.py
if __name__ == '__main__':
    # This allows running the test file directly for debugging,
    # though it's better to use pytest runner.
    pytest.main([__file__])

# Small self-correction:
# `export_button` instantiates `FlightGet` locally. If `FlightDatabase`'s default constructor
# (called by `FlightGet` if `FlightGet` doesn't take a db instance/name)
# also defaults to `:memory:`, then during a single test run, it *might* access the same
# in-memory DB if SQLite's :memory: behavior is consistent across instances within the same process
# for unnamed :memory: DBs.
# However, a named in-memory DB like "file::memory:?cache=shared" or passing the connection/db_instance
# explicitly is much safer for ensuring `FlightGet` uses the test-specific DB.
# The current `FlightDatabase` uses `sqlite3.connect(self.db_name, detect_types=...)`.
# If `db_name` is simply ":memory:", each connect creates a *new* in-memory DB.
# This means `FlightGet()` inside `export_button` will NOT see data prepared by `setup_test_db`
# unless `FlightDatabase`'s default `db_name` is changed or `FlightGet` is refactored.

# To fix this for the test:
# 1. Modify `FlightDatabase` default to a shareable in-memory DB (e.g. "file:testflights?mode=memory&cache=shared")
#    AND ensure `FlightGet` uses this same default.
# 2. OR Refactor `FlightGet` to accept a `FlightDatabase` instance or connection string. (Best long-term)
# 3. OR Monkeypatch `FlightGet` itself in the test to use the `test_db` connection.

# For now, I will assume that if `FlightDatabase.DEFAULT_DB_NAME` was changed to ":memory:"
# or if `FlightGet` is modified to take a `db_name` parameter which is then set to ":memory:",
# the test would work as intended. If the test fails due to `FlightGet` not finding data,
# this will be the primary area to investigate and refactor.
# The test structure assumes `FlightGet` in `export_button` will somehow access the same in-memory DB.
# The current `FlightDatabase` has `DEFAULT_DB_NAME = "flights.db"`.
# `FlightGet` instantiates `FlightDatabase()` so it will try to use `flights.db`.
# This test WILL FAIL as `export_button`'s `FlightGet` won't see the in-memory data.

# Quick Patch Strategy for the test to work without refactoring FlightGet:
# We can monkeypatch `bin.database.flight_get.FlightDatabase` to make its instances
# use the test_db's connection.

@pytest.fixture(autouse=True) # Apply to all tests in this file
def patch_flight_get_db_access(monkeypatch, setup_test_db):
    """
    Ensures that any FlightGet instance created during the test
    uses the connection from the setup_test_db fixture.
    """

    # setup_test_db IS the FlightDatabase instance from the fixture
    db_instance_from_fixture = setup_test_db

    class PatchedFlightGetWithClosure(FlightGet):
        # Capture the db_instance_from_fixture from the outer scope of the fixture.
        # This specific instance will be used by all FlightGet() instantiations during one test.
        _shared_db_instance = db_instance_from_fixture

        def __init__(self, db_name=None): # Match original signature (though db_name won't be used)
            # Instead of FlightGet's normal __init__ which creates a new FlightDatabase,
            # we assign our shared (test-specific) FlightDatabase instance.
            self._db = PatchedFlightGetWithClosure._shared_db_instance
            self.db = PatchedFlightGetWithClosure._shared_db_instance # For consistency

            # Original FlightGet also initializes self.db_name and self._cursor,
            # but these might not be strictly necessary if all methods use self._db correctly.
            # If FlightGet's methods rely on self.db_name or an internally managed self._cursor,
            # those would need to be handled or methods overridden.
            # For now, this direct assignment of self._db is the core fix.
            self.db_name = self._db.db_name # Behave like original
            self._cursor = None # Behave like original

    monkeypatch.setattr(sys.modules['src.ui.export_button'], 'FlightGet', PatchedFlightGetWithClosure)
    monkeypatch.setattr(sys.modules['bin.config.markdown_config'], 'FlightGet', PatchedFlightGetWithClosure)

    yield

    # Monkeypatch is automatically undone after the test.
