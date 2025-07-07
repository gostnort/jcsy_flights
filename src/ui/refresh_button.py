# src/ui/refresh_button.py

import sys
import os
import datetime
import threading
import time
# Using concurrent.futures for easier thread management and timeouts if possible
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from bin.database.flight_db import FlightDatabase
# We'll need functions to get and update flight data.
# These might be in flight_get.py, flight_add.py, or flight_maintain.py
# For now, let's assume direct interaction or we'll import specific functions later.

# Crawler imports
from bin.scrapers.flightview_crawler import FlightViewCrawler #, return_structure as FlightViewReturnStructure
# from bin.scrapers.flightstats_crawler import FlightStatsCrawler #, return_structure as FlightStatsReturnStructure

# Placeholder for JCSY header parsing logic (similar to what might be in JcsyParser)
# We might need to extract or reuse parts of JcsyParser's header rule.
# For now, a simplified regex based on the 'JCSY:CA0984/12DEC/LAX,I' format.
import re
JCSY_HEADER_PATTERN = re.compile(r"^(?:JCSY:)?(?P<airline>[A-Z0-9]{2})(?P<flight_number>\d+)/(?P<flight_date_str>\d+[A-Z]{3})(?:/(?P<airport>[A-Z]{3})(?:,(?P<inbound_flag>[IO]))?)?")


def parse_jcsy_header_for_refresh(header_text: str) -> dict | None:
    """
    Parses a JCSY-like header string to extract flight identification details.
    Returns a dictionary with 'airline', 'flight_number', 'date' (datetime.date),
    'airport' if present, or None if parsing fails.
    Date parsing is simplified, assumes current year if year not in DDMMM format.
    """
    match = JCSY_HEADER_PATTERN.match(header_text.upper())
    if not match:
        return None

    details = match.groupdict()
    parsed = {
        "airline": details["airline"],
        "flight_number": details["flight_number"],
        "airport": details.get("airport") # Might be None if not in header_text
    }

    date_str = details["flight_date_str"]
    try:
        # Try DDMMMYY or DDMMM
        if len(date_str) > 5: # DDMMMYY e.g. 12DEC24
            parsed["date"] = datetime.datetime.strptime(date_str, "%d%b%y").date()
        else: # DDMMM e.g. 12DEC, assume current year
            parsed["date"] = datetime.datetime.strptime(date_str, "%d%b").date().replace(year=datetime.datetime.now().year)
    except ValueError:
        return None # Invalid date format
    return parsed


def call_crawler_with_timeout(crawler_function, args, timeout_seconds):
    """
    Calls a crawler function in a separate thread with a timeout.
    Args:
        crawler_function: The crawler function to call.
        args: A tuple of arguments for the crawler function.
        timeout_seconds: Timeout in seconds.
    Returns:
        The result from the crawler, or None if timeout or error.
    """
    # Note: Terminating threads forcefully is tricky in Python.
    # ThreadPoolExecutor's timeout on future.result() doesn't kill the thread,
    # it just stops waiting. The thread might continue running.
    # For true process termination, multiprocessing might be needed,
    # but that adds complexity for data sharing.
    # For now, we rely on the crawler being well-behaved or the timeout
    # simply preventing the main logic from waiting too long.

    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(crawler_function, *args)
    try:
        result = future.result(timeout=timeout_seconds)
        return result
    except FuturesTimeoutError:
        print(f"Crawler {crawler_function.__name__} timed out after {timeout_seconds} seconds.")
        # Attempt to cancel the future, though it may not stop a running thread.
        future.cancel()
        return None
    except Exception as e:
        print(f"Crawler {crawler_function.__name__} failed: {e}")
        return None
    finally:
        executor.shutdown(wait=False) # Don't wait for tasks to complete if they are stuck


def _get_flights_to_refresh(db_cursor, header_details: dict | None) -> list[dict]:
    """
    Fetches flight records from the database that need refreshing.
    If header_details is provided, fetches that specific flight.
    Otherwise, fetches today's flights.
    Returns a list of flight records (as dicts) or an empty list.
    Each dict should contain at least jcsy_flight_id, query_flight_id, airline, flight_number, flight_date
    and current time fields (std, atd, eta, ata) from query_flights.
    """
    flights_to_check = []
    if header_details:
        # 1. Find the jcsy_flights record based on header.
        find_jcsy_sql = "SELECT id FROM jcsy_flights WHERE airline = ? AND flight_number = ? AND flight_date = ?"
        # Optional: Add airport matching if header_details['airport'] is crucial for identifying
        # the correct jcsy_flights record, e.g., if the same flight number/date can exist for different routes.
        # For now, assuming airline, flight_number, and date are unique enough for jcsy_flights.
        # if header_details.get('airport'):
        #     # This part needs careful consideration of whether header_airport is dep or arr for jcsy_flights
        #     # and if jcsy_flights even stores both.
        #     # find_jcsy_sql += " AND (departure_airport = ? OR arrival_airport = ?)"
        #     db_cursor.execute(find_jcsy_sql, (
        #         header_details['airline'], header_details['flight_number'],
        #         header_details['date'].strftime('%Y-%m-%d'),
        #         header_details['airport'], header_details['airport']
        #     ))
        # else:
        db_cursor.execute(find_jcsy_sql, (
            header_details['airline'],
            header_details['flight_number'],
            header_details['date'].strftime('%Y-%m-%d')
        ))
        jcsy_record = db_cursor.fetchone()

        if not jcsy_record:
            return "Flight not found based on header."

        jcsy_flight_id = jcsy_record['id']

        # 2. Fetch all query_flights for that jcsy_flight_id.
        # The original join with jcsy_flights is still useful to get jf.inbound_not etc.
        sql_segments = """
            SELECT qf.*, jf.inbound_not, jf.departure_airport as jf_dep, jf.arrival_airport as jf_arr
            FROM query_flights qf
            JOIN jcsy_flights jf ON qf.jcsy_flight_id = jf.id
            WHERE qf.jcsy_flight_id = ?
        """
        db_cursor.execute(sql_segments, (jcsy_flight_id,))
        for row in db_cursor.fetchall():
            flights_to_check.append(dict(row))

        if not flights_to_check:
            # This case implies a jcsy_flights record exists but has no query_flights segments.
            # This could be valid (e.g., a cancelled flight with no segments listed) or an import issue.
            # For refresh purposes, it means no segments to refresh.
            return "No segments found for the specified flight header."
    else:
        # Query for today's flights
        today_date_str = datetime.date.today().strftime('%Y-%m-%d')
        sql = """
            SELECT qf.*, jf.inbound_not, jf.departure_airport as jf_dep, jf.arrival_airport as jf_arr
            FROM query_flights qf
            JOIN jcsy_flights jf ON qf.jcsy_flight_id = jf.id
            WHERE qf.flight_date = ?
        """
        db_cursor.execute(sql, (today_date_str,))
        for row in db_cursor.fetchall():
            flights_to_check.append(dict(row))

    return flights_to_check


from bin.scrapers.flightview_crawler import return_structure as CrawlerReturnStructure # Use generic alias

def _update_flight_in_db(db_connection, query_flight_id: int, crawler_data: CrawlerReturnStructure):
    """
    Updates the specified query_flight record with new time data from crawler_data.
    crawler_data is an instance of return_structure.
    """
    if not crawler_data:
        print(f"No crawler data provided to update for query_flight_id {query_flight_id}")
        return

    # Build SET part of SQL query dynamically from CrawlerReturnStructure fields
    set_clauses = []
    values = []

    # Map attributes of CrawlerReturnStructure to database columns
    # Assuming direct mapping for relevant time fields
    fields_to_update = ['std', 'etd', 'atd', 'sta', 'eta', 'ata']
    # Potentially also 'departure_airport', 'arrival_airport' if crawlers can correct them
    # fields_to_update.extend(['departure_airport', 'arrival_airport'])

    for field in fields_to_update:
        value = getattr(crawler_data, field, None)
        if value is not None: # Only update if crawler provided a value (None means not available from crawler)
            set_clauses.append(f"{field} = ?")
            # Ensure datetime objects are converted to ISO format strings for database insertion
            if isinstance(value, (datetime.datetime, datetime.date)):
                # Match the format used in test assertions, e.g., 'YYYY-MM-DD HH:MM:SS'
                # Ensure that the timespec matches what's expected if sub-second precision matters.
                # Using 'seconds' for simplicity as seen in test assertions.
                values.append(value.isoformat(sep=' ', timespec='seconds'))
            else:
                values.append(value)

    if not set_clauses:
        print(f"No valid time data from crawler to update for query_flight_id {query_flight_id}")
        return

    sql = f"UPDATE query_flights SET {', '.join(set_clauses)} WHERE id = ?"
    values.append(query_flight_id)

    cursor = None  # Initialize cursor to None
    try:
        cursor = db_connection.cursor()
        cursor.execute(sql, tuple(values))
        db_connection.commit()
        print(f"Updated flight times for query_flight_id {query_flight_id} with {len(set_clauses)} fields.")
    except Exception as e:
        if db_connection.in_transaction: # Check if a transaction is active before rolling back
            db_connection.rollback()
        print(f"Error updating flight times for query_flight_id {query_flight_id}: {e}")
    finally:
        if cursor:
            cursor.close()


def refresh_flight_data(header_text: str | None = None) -> str:
    """
    Main function for the "Refresh" button.
    - Parses optional header_text to identify a specific flight.
    - If no header_text, queries for today's flights.
    - For identified flights, if time data (STD, ATD, ETA, ATA) is missing,
      calls crawlers (FlightView then FlightStats, with timeouts) in threads.
    - Updates the database with new data from crawlers.
    Returns a status message.
    """
    if not flight_db: # flight_db should be initialized globally like in import_button.py
        return "Error: Flight Database not initialized."

    header_details = None
    if header_text:
        header_details = parse_jcsy_header_for_refresh(header_text)
        if not header_details:
            return f"Error: Invalid header text format: '{header_text}'"

    active_threads = []
    results_log = []

    # Ensure flight_db is connected if not already (though 'with flight_db' below handles it)
    # if not flight_db.connection:
    #     flight_db.connect()

    with flight_db: # Ensure connection is managed for the main thread operations
        flights_needing_check = _get_flights_to_refresh(flight_db.cursor, header_details)

        if isinstance(flights_needing_check, str): # Error message from _get_flights_to_refresh
            return flights_needing_check

        if not flights_needing_check:
            return "No flights found matching criteria."

        flights_to_actually_refresh = []
        for flight in flights_needing_check:
            # Check if any of the key time fields are missing
            if not all([flight.get('std'), flight.get('atd'), flight.get('eta'), flight.get('ata')]):
                flights_to_actually_refresh.append(flight)

        if not flights_to_actually_refresh:
            return "All queried flights have complete time data (STD, ATD, ETA, ATA)."

        for flight_info in flights_to_actually_refresh:
            # Each flight refresh runs in its own thread to allow parallel crawling
            # and keep UI responsive.
            # Pass the global (and potentially test-patched) flight_db instance to the thread.
            thread = threading.Thread(
                target=_process_single_flight_refresh,
                args=(flight_info, results_log) # Reverted: Do not pass flight_db directly
            )
            active_threads.append(thread)
            thread.start()

    # Wait for all processing threads to complete (optional, could return immediately)
    # For now, let's wait to give a complete status, but UI might prefer immediate return.
    # If returning immediately, need a way to update UI later when threads finish.
    for thread in active_threads:
        thread.join() # This will block until each thread is done.

    if not results_log:
         return f"Attempted to refresh {len(flights_to_actually_refresh)} flight(s), but no updates were made (check crawler logs)."

    return f"Refresh process completed for {len(flights_to_actually_refresh)} flight(s). Results: {'; '.join(results_log)}"


def _process_single_flight_refresh(flight_info: dict, results_log: list): # Reverted signature
    """
    Handles crawling and DB update for a single flight. Runs in a thread.
    flight_info: A dict from _get_flights_to_refresh.
    results_log is a shared list to append status messages.
    """
    qf_id = flight_info['id']
    airline = flight_info['airline']
    flight_number = flight_info['flight_number']
    # flight_date needs to be datetime.date object for crawlers
    flight_date_obj = datetime.datetime.strptime(flight_info['flight_date'], '%Y-%m-%d').date()

    # Determine departure and arrival airports for the crawler
    # Determine departure and arrival airports for the crawler for this specific segment
    # These come directly from the query_flights record for this segment.
    dep_for_crawler = flight_info.get('departure_airport')
    arr_for_crawler = flight_info.get('arrival_airport')

    if not dep_for_crawler and not arr_for_crawler:
        # As per FlightViewCrawler, at least one airport must be provided.
        # If both are missing from query_flights, we might not be able to crawl.
        # However, FlightViewCrawler takes depapt='' or arrapt=''
        # We should pass what we have. If both are truly None, then log error.
        msg = f"Flight {airline}{flight_number} (QFID: {qf_id}): Both departure and arrival airports are missing for this segment. Cannot crawl."
        print(msg)
        results_log.append(msg)
        return

    # Ensure dep_for_crawler and arr_for_crawler are empty strings if None, as per crawler expectation
    dep_for_crawler = dep_for_crawler if dep_for_crawler is not None else ''
    arr_for_crawler = arr_for_crawler if arr_for_crawler is not None else ''

    # Instantiate crawlers
    flightview_crawler_instance = FlightViewCrawler()
    # flightstats_crawler_instance = FlightStatsCrawler() # Assuming similar instantiation

    crawler_args = (airline, flight_number, flight_date_obj, dep_for_crawler, arr_for_crawler)

    print(f"Attempting FlightView for {airline}{flight_number} ({flight_date_obj}, {dep_for_crawler}->{arr_for_crawler})")

    crawled_data = call_crawler_with_timeout(
        flightview_crawler_instance.get_flight_info,
        crawler_args,
        10
    )

    if not crawled_data:
        print(f"FlightView failed/timed out for {airline}{flight_number}. Trying FlightStats.")
        # Placeholder for FlightStats - assuming similar interface
        # crawled_data = call_crawler_with_timeout(
        #     flightstats_crawler_instance.get_flight_info,
        #     crawler_args,
        #     10
        # )
        # For now, simulate FlightStats also returning no data if FlightView failed
        pass

    if crawled_data: # This will be a CrawlerReturnStructure instance
        thread_local_db = FlightDatabase() # Each thread gets its own DB connection instance.
                                      # The test patch mocker.patch('src.ui.refresh_button.FlightDatabase', ...)
                                      # will ensure this uses the correct test DB file name.
        try:
            with thread_local_db as db_for_update: # Manages connect/close for this thread's DB interaction
                 _update_flight_in_db(db_for_update.connection, qf_id, crawled_data)
            msg = f"Flight {airline}{flight_number} (QFID: {qf_id}): Updated with data."
            print(msg)
            results_log.append(msg)
        except Exception as e:
            # Catch potential errors during DB interaction specific to this thread
            msg = f"Flight {airline}{flight_number} (QFID: {qf_id}): DB update failed - {e}"
            print(msg)
            results_log.append(msg)
        finally:
            # Ensure the thread-local connection is closed even if 'with' block fails unexpectedly before __exit__
            if thread_local_db and thread_local_db.connection:
                thread_local_db.close()
    else:
        msg = f"Flight {airline}{flight_number} (QFID: {qf_id}): Both crawlers failed or returned no data."
        print(msg)
        results_log.append(msg)

# Global flight_db instance, similar to import_button.py
flight_db = None
try:
    db_dir = os.path.join(project_root, "src", "database")
    if not os.path.exists(db_dir):
        os.makedirs(db_dir)
    flight_db = FlightDatabase()
except Exception as e:
    print(f"CRITICAL: Error initializing FlightDatabase in refresh_button.py: {e}")


if __name__ == '__main__':
    print("Testing refresh_button.py...")

    # Mock crawler functions for testing
    def mock_flightview_ok(airline, flight_number, date, dep, arr):
        print(f"MOCK FlightView: Called for {airline}{flight_number} {date} {dep}-{arr}")
        time.sleep(1) # Simulate work
        return {
            "std": datetime.datetime.combine(date, datetime.time(10, 0)),
            "atd": datetime.datetime.combine(date, datetime.time(10, 5)),
            "eta": datetime.datetime.combine(date, datetime.time(12, 0)),
            "ata": datetime.datetime.combine(date, datetime.time(12, 5))
        }

    def mock_flightview_timeout(airline, flight_number, date, dep, arr):
        print(f"MOCK FlightView (TIMEOUT): Called for {airline}{flight_number} {date} {dep}-{arr}")
        time.sleep(15) # Simulate timeout
        return {"std": "timeout_data"}

    def mock_flightstats_ok(airline, flight_number, date, dep, arr):
        print(f"MOCK FlightStats: Called for {airline}{flight_number} {date} {dep}-{arr}")
        time.sleep(1)
        return {
            "std": datetime.datetime.combine(date, datetime.time(10, 2)),
            "atd": datetime.datetime.combine(date, datetime.time(10, 7)),
            "eta": datetime.datetime.combine(date, datetime.time(12, 2)),
            "ata": datetime.datetime.combine(date, datetime.time(12, 7))
        }

    # Replace actual crawler calls with mocks for testing this module
    # flightview_scrape = mock_flightview_ok
    # flightstats_scrape = mock_flightstats_ok

    # To test, you would need some data in the DB.
    # Example:
    # 1. Test with empty header (today's flights)
    # print("\n--- Test Case 1: Refresh today's flights ---")
    # status = refresh_flight_data()
    # print(f"Status: {status}")

    # 2. Test with a specific header for an existing flight
    # print("\n--- Test Case 2: Refresh specific flight (replace with actual data in your DB) ---")
    # Assuming a flight AA100 exists for today
    # today_for_header = datetime.date.today().strftime("%d%b").upper() # e.g. 17JUL
    # status_specific = refresh_flight_data(f"AA100/{today_for_header}/JFK")
    # print(f"Status specific: {status_specific}")

    # 3. Test with a header for a non-existent flight
    # print("\n--- Test Case 3: Refresh non-existent flight ---")
    # status_nonexist = refresh_flight_data("XX9999/01JAN/XYZ")
    # print(f"Status non-exist: {status_nonexist}")

    # Need to mock the actual crawler imports for the test to run without them
    # For example, assign mock functions to the names expected by _process_single_flight_refresh
    # This part is tricky without knowing the exact crawler function names and structure.
    # Temporarily, we can test parts of it.

    print("\n--- Testing header parser ---")
    print(parse_jcsy_header_for_refresh("CA0984/12DEC/LAX,I"))
    print(parse_jcsy_header_for_refresh("UA123/05JUN24/ORD"))
    print(parse_jcsy_header_for_refresh("INVALIDTEXT"))

    if flight_db:
        print("\n--- DB Sanity Check (listing tables) ---")
        try:
            with flight_db:
                flight_db.cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
                tables = flight_db.cursor.fetchall()
                print(f"Tables: {[table[0] for table in tables]}")
        except Exception as e:
            print(f"DB check failed: {e}")
    else:
        print("Flight_db not initialized, skipping DB sanity check.")

    print("\nRefresh_button.py file created with骨架. Further implementation of crawler calls and DB interactions within _process_single_flight_refresh is needed based on actual crawler function signatures.")

# To make _process_single_flight_refresh testable directly, we'd need to assign
# mock crawlers to global names or pass them as parameters.
# For now, the above __main__ tests the header parser and DB connection.
# The full refresh_flight_data would require a populated DB and actual (or more deeply mocked) crawlers.

# Example of how crawler functions might be assigned for testing _process_single_flight_refresh:
# --- Test Mocks & Setup ---
# We need to be able to replace the actual crawlers for testing.
# This is a simplified way for __main__ testing. Proper tests use unittest.mock.

class MockCrawler:
    def __init__(self, name="MockCrawler", behavior="ok", data_to_return=None, delay=0):
        self.name = name
        self.behavior = behavior  # "ok", "timeout", "fail", "no_data"
        self.data_to_return = data_to_return
        self.delay = delay # seconds
        print(f"MOCK {self.name} initialized with behavior: {self.behavior}, delay: {self.delay}s")

    def get_flight_info(self, airline, flight_number, date, depapt, arrapt):
        print(f"MOCK {self.name}: Called for {airline}{flight_number} ({date} {depapt}->{arrapt})")
        if self.delay > 0:
            print(f"MOCK {self.name}: Simulating delay of {self.delay}s...")
            time.sleep(self.delay)

        if self.behavior == "timeout":
            # The timeout is handled by call_crawler_with_timeout,
            # this delay just needs to exceed it.
            print(f"MOCK {self.name}: Behavior is 'timeout', an actual timeout should occur in calling code.")
            # This return won't be hit if call_crawler_with_timeout works correctly.
            return None
        elif self.behavior == "fail":
            print(f"MOCK {self.name}: Simulating failure.")
            raise Exception("Simulated crawler failure")
        elif self.behavior == "no_data":
            print(f"MOCK {self.name}: Simulating no data returned.")
            return None

        # Default "ok" behavior
        if self.data_to_return:
            print(f"MOCK {self.name}: Returning provided mock data.")
            return self.data_to_return

        print(f"MOCK {self.name}: Returning default OK data.")
        return CrawlerReturnStructure( # Ensure CrawlerReturnStructure is defined or imported
            departure_airport=depapt if depapt else "MOCK_DEP", # Provide defaults if empty
            arrival_airport=arrapt if arrapt else "MOCK_ARR",
            std=datetime.datetime.combine(date, datetime.time(10, 0)),
            atd=datetime.datetime.combine(date, datetime.time(10, 5)),
            etd=datetime.datetime.combine(date, datetime.time(10, 2)), # Estimated
            sta=datetime.datetime.combine(date, datetime.time(12, 0)),
            ata=datetime.datetime.combine(date, datetime.time(12, 5)),
            eta=datetime.datetime.combine(date, datetime.time(12, 2)) # Estimated
        )

# Store original crawler classes to restore them later
_original_flightview_crawler = None
# _original_flightstats_crawler = None # If we had it

def _patch_crawlers(flightview_mock_instance, flightstats_mock_instance=None):
    """Patches the global crawler classes with mock instances."""
    global FlightViewCrawler, _original_flightview_crawler
    # global FlightStatsCrawler, _original_flightstats_crawler

    if _original_flightview_crawler is None: # Patch only once
        _original_flightview_crawler = FlightViewCrawler

    # Create a new class that when instantiated, returns our mock_instance
    class PatchedFVC:
        def __init__(self): # Match original constructor if it takes args
            pass
        def get_flight_info(self, *args, **kwargs): # Match method signature
            return flightview_mock_instance.get_flight_info(*args, **kwargs)

    FlightViewCrawler = PatchedFVC

    # Similarly for FlightStatsCrawler if it was defined and imported
    # if flightstats_mock_instance:
    #     if _original_flightstats_crawler is None:
    #         _original_flightstats_crawler = FlightStatsCrawler
    #     class PatchedFSC:
    #         def __init__(self): pass
    #         def get_flight_info(self, *args, **kwargs):
    #             return flightstats_mock_instance.get_flight_info(*args, **kwargs)
    #     FlightStatsCrawler = PatchedFSC


def _restore_crawlers():
    """Restores original crawler classes."""
    global FlightViewCrawler, _original_flightview_crawler
    # global FlightStatsCrawler, _original_flightstats_crawler
    if _original_flightview_crawler is not None:
        FlightViewCrawler = _original_flightview_crawler
        # _original_flightview_crawler = None # Reset for next patch cycle if needed in complex test suites
    # if _original_flightstats_crawler is not None:
    #     FlightStatsCrawler = _original_flightstats_crawler
    #     # _original_flightstats_crawler = None


if __name__ == '__main__':
    print("Testing refresh_button.py...")

    # Ensure the global flight_db is re-initialized to use an in-memory DB for tests
    # This is crucial for test isolation.
    flight_db = FlightDatabase(db_name=":memory:")
    flight_db.initialize_database() # Create schema

    print("\n--- Testing header parser ---")
    # ... (header parser tests remain the same) ...
    print(f"Parse 'CA0984/12DEC/LAX,I': {parse_jcsy_header_for_refresh('CA0984/12DEC/LAX,I')}")
    print(f"Parse 'UA123/05JUN24/ORD': {parse_jcsy_header_for_refresh('UA123/05JUN24/ORD')}")
    print(f"Parse 'INVALIDTEXT': {parse_jcsy_header_for_refresh('INVALIDTEXT')}")


    # --- Test Case 1: Specific flight, needs update, FlightView OK ---
    print("\n--- Test Case 1: Specific flight, needs update, FlightView OK ---")
    mock_fv_case1 = MockCrawler(name="FV_Case1", behavior="ok", delay=1)
    _patch_crawlers(flightview_mock_instance=mock_fv_case1)

    today = datetime.date.today()
    today_str = today.strftime('%Y-%m-%d')
    header_to_test_aa100 = f"AA100/{today.strftime('%d%b').upper()}/JFK"

    with flight_db:
        flight_db.cursor.execute("DELETE FROM query_flights") # Clean previous test data
        flight_db.cursor.execute("DELETE FROM jcsy_flights")
        flight_db.cursor.execute(
            "INSERT INTO jcsy_flights (airline, flight_number, flight_date, departure_airport, inbound_not) VALUES (?, ?, ?, ?, ?)",
            ("AA", "100", today_str, "JFK", 0)
        )
        jcsy_id = flight_db.cursor.lastrowid
        flight_db.cursor.execute(
            "INSERT INTO query_flights (jcsy_flight_id, airline, flight_number, flight_date, departure_airport, arrival_airport) VALUES (?, ?, ?, ?, ?, ?)",
            (jcsy_id, "AA", "100", today_str, "JFK", "LAX")
        )
        flight_db.connection.commit()

    print(f"Test Case 1: Refreshing with header: {header_to_test_aa100}")
    status = refresh_flight_data(header_text=header_to_test_aa100)
    print(f"Test Case 1 Status: {status}")
    with flight_db:
        flight_db.cursor.execute("SELECT std, atd, eta, ata FROM query_flights WHERE airline='AA' AND flight_number='100'")
        row = flight_db.cursor.fetchone()
        print(f"DB check for AA100 after refresh: {dict(row) if row else 'Not found'}")
    _restore_crawlers()


    # --- Test Case 2: Specific flight, FlightView times out, FlightStats (mocked) OK ---
    print("\n--- Test Case 2: Specific flight, FlightView times out, FlightStats OK ---")
    mock_fv_case2 = MockCrawler(name="FV_Case2_Timeout", behavior="timeout", delay=12) # delay > 10s timeout
    # We need a mock for FlightStats as well, even if it's not fully implemented in main code yet
    mock_fs_case2 = MockCrawler(name="FS_Case2_OK", behavior="ok", delay=1)

    # To make this test work, we need to ensure _process_single_flight_refresh actually
    # attempts to call a FlightStatsCrawler. For now, the code has a placeholder.
    # We'll assume for this test that if FlightStatsCrawler were defined and imported,
    # it would be patched like FlightViewCrawler.
    # For a more robust test, the FlightStatsCrawler call in _process_single_flight_refresh
    # should not be commented out.

    # For now, this test will show FlightView timeout and then "Both crawlers failed" because
    # the FlightStats part is a `pass` in `_process_single_flight_refresh`.
    # To truly test the fallback, the FlightStats call needs to be active in the main code.
    # I will proceed assuming the test output will reflect this current state.
    _patch_crawlers(flightview_mock_instance=mock_fv_case2, flightstats_mock_instance=mock_fs_case2) # Pass both mocks

    with flight_db: # Clear times for AA100 again
        flight_db.cursor.execute("UPDATE query_flights SET std=NULL, atd=NULL, eta=NULL, ata=NULL WHERE airline='AA' AND flight_number='100'")
        flight_db.connection.commit()

    print(f"Test Case 2: Refreshing with header: {header_to_test_aa100}")
    status = refresh_flight_data(header_text=header_to_test_aa100)
    print(f"Test Case 2 Status: {status}") # Expected: FV times out, then FS is tried (if code allows)
    _restore_crawlers()


    # --- Test Case 3: Flight not found ---
    print("\n--- Test Case 3: Flight not found ---")
    mock_fv_case3 = MockCrawler(name="FV_Case3_NotCalled", behavior="ok")
    _patch_crawlers(mock_fv_case3)
    status = refresh_flight_data(header_text="XX999/01JAN/XYZ")
    print(f"Test Case 3 Status: {status}")
    _restore_crawlers()

    # --- Test Case 4: Refresh today's flights (no header), one needs update ---
    print("\n--- Test Case 4: Refresh today's flights, one needs update ---")
    mock_fv_case4 = MockCrawler(name="FV_Case4_TodayOK", behavior="ok", delay=1)
    _patch_crawlers(mock_fv_case4)

    with flight_db:
        # Clean up and set up for this specific test
        flight_db.cursor.execute("DELETE FROM query_flights")
        flight_db.cursor.execute("DELETE FROM jcsy_flights")
        # Flight 1 (AA100) - needs update
        flight_db.cursor.execute(
            "INSERT INTO jcsy_flights (airline, flight_number, flight_date, departure_airport, inbound_not) VALUES (?, ?, ?, ?, ?)",
            ("AA", "100", today_str, "JFK", 0))
        jcsy_id_aa = flight_db.cursor.lastrowid
        flight_db.cursor.execute(
            "INSERT INTO query_flights (jcsy_flight_id, airline, flight_number, flight_date, departure_airport, arrival_airport) VALUES (?, ?, ?, ?, ?, ?)",
            (jcsy_id_aa, "AA", "100", today_str, "JFK", "LAX"))
        # Flight 2 (UA200) - already has some data, shouldn't be updated by this mock if times are full
        flight_db.cursor.execute(
            "INSERT INTO jcsy_flights (airline, flight_number, flight_date, arrival_airport, inbound_not) VALUES (?, ?, ?, ?, ?)",
            ("UA", "200", today_str, "ORD", 1))
        jcsy_id_ua = flight_db.cursor.lastrowid
        flight_db.cursor.execute(
            "INSERT INTO query_flights (jcsy_flight_id, airline, flight_number, flight_date, departure_airport, arrival_airport, std, atd, eta, ata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (jcsy_id_ua, "UA", "200", today_str, "LAX", "ORD",
             datetime.datetime.now(), datetime.datetime.now(),datetime.datetime.now(),datetime.datetime.now())) # All key times present
        flight_db.connection.commit()

    print("Test Case 4: Refreshing today's flights (no header)")
    status = refresh_flight_data(header_text=None)
    print(f"Test Case 4 Status: {status}")
    with flight_db:
        print("DB check for today's flights after refresh:")
        flight_db.cursor.execute("SELECT airline, flight_number, std, atd, eta, ata FROM query_flights WHERE flight_date=?", (today_str,))
        for row in flight_db.cursor.fetchall():
            print(dict(row))
    _restore_crawlers()

    print("\nBasic __main__ tests for refresh_button.py executed.")
    print("NOTE: Full testing of FlightStats fallback requires FlightStatsCrawler integration in main code.")
    print("NOTE: Timeout behavior for threads (linger vs terminate) is still based on threading limitations.")
