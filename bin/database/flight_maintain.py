import time
from datetime import datetime, timedelta, date

# Assuming these paths are correct relative to where flight_maintain.py will be
# or that PYTHONPATH is set up.
from database.flight_get import FlightGet
from database.flight_add import FlightAdd # For FlightAdd.update_flight
from scrapers.flightview_crawler import FlightViewCrawler, return_structure as CrawlerReturnStructure
from scrapers.flightstats_crawler import FlightStatsCrawler

# Spacing: 3 lines between classes
# Spacing: 2 lines between functions
# Spacing: No empty lines in function except comments


class FlightMaintainer:


    def __init__(self, db_name="flights.db", config_path='jcsy_config.yaml'):
        self.flight_get = FlightGet(db_name=db_name)
        self.flight_add = FlightAdd(config_path=config_path)
        self.fv_crawler = FlightViewCrawler()
        self.fs_crawler = FlightStatsCrawler()
        # flight_schedule stores: {'id': int, 'table': str, 'next_run': datetime}
        self.flight_schedule = [] 
        self.default_scan_interval_seconds = 300 # For discovering new "today's flights"
        self.min_time_before_std_sta_for_etd_eta = timedelta(hours=2)
        self.post_ata_check_delay = timedelta(hours=1)
        self.retry_delay_on_crawler_failure = timedelta(minutes=15)
        self.max_sleep_interval = 60 # Max sleep time in the run loop


    def _fetch_flight_details_from_db(self, flight_id: int, table_name: str) -> dict | None:
        try:
            # Ensure the database connection is open for this operation if FlightGet uses context manager internally
            # If FlightGet.db is a managed connection, this is fine.
            # Otherwise, self.flight_get.db.connect() might be needed if it can be closed.
            with self.flight_get.db: 
                flight_row = self.flight_get.return_flight_data(table_name, flight_id)
            if flight_row:
                return dict(flight_row) # Convert sqlite3.Row to dict
            return None
        except Exception as e:
            print(f"[{datetime.now()}] Error fetching flight details for {table_name} ID {flight_id} from DB: {e}")
            return None


    def _calculate_next_run_time(self, flight_details: dict) -> datetime | None:
        now = datetime.now()
        # Assuming flight_details directly provides datetime objects or None for time fields
        atd = flight_details.get('atd')
        ata = flight_details.get('ata')
        etd = flight_details.get('etd')
        eta = flight_details.get('eta')
        std = flight_details.get('std')
        sta = flight_details.get('sta')
        if atd and ata:
            if ata > now - self.post_ata_check_delay: # Check once more after ATA
                return ata + self.post_ata_check_delay
            return None # Flight is complete for monitoring
        if not atd: # Not departed
            next_check = None
            if etd and etd > now:
                next_check = etd
            elif std:
                # Check for ETD starting min_time_before_std_sta_for_etd_eta before STD
                etd_check_trigger = std - self.min_time_before_std_sta_for_etd_eta
                if etd_check_trigger > now: # If trigger time is in the future
                    next_check = etd_check_trigger
                # If trigger time is past, or STD is near/past, use STD (if future) or now
                else:
                    next_check = std if std > now else now 
            return next_check if next_check else now + self.retry_delay_on_crawler_failure
        if atd and not ata: # Departed but not arrived
            next_check = None
            if eta and eta > now:
                next_check = eta
            elif sta:
                # Check for ETA starting min_time_before_std_sta_for_etd_eta before STA
                eta_check_trigger = sta - self.min_time_before_std_sta_for_etd_eta
                if eta_check_trigger > now:
                    next_check = eta_check_trigger
                else:
                    next_check = sta if sta > now else now
            return next_check if next_check else now + self.retry_delay_on_crawler_failure
        return None # Default case, should ideally not be reached


    def _add_or_update_flight_in_monitor(self, flight_id: int, table_name: str, initial_details: dict = None):
        details_for_calc = initial_details
        if not details_for_calc:
            details_for_calc = self._fetch_flight_details_from_db(flight_id, table_name)
        if not details_for_calc:
            print(f"[{datetime.now()}] Could not fetch details for {table_name} ID {flight_id}. Cannot schedule.")
            return
        next_run = self._calculate_next_run_time(details_for_calc)
        existing_entry_index = -1
        for i, entry in enumerate(self.flight_schedule):
            if entry['id'] == flight_id and entry['table'] == table_name:
                existing_entry_index = i
                break
        if next_run:
            new_entry = {'id': flight_id, 'table': table_name, 'next_run': next_run}
            if existing_entry_index != -1:
                self.flight_schedule[existing_entry_index] = new_entry
            else:
                self.flight_schedule.append(new_entry)
            print(f"[{datetime.now()}] Scheduled/Updated: {table_name} ID {flight_id} for {next_run}")
        else:
            if existing_entry_index != -1:
                self.flight_schedule.pop(existing_entry_index)
            print(f"[{datetime.now()}] Flight {table_name} ID {flight_id} considered complete. Removed from monitor.") 
        self.flight_schedule.sort(key=lambda x: x['next_run'] if x['next_run'] else datetime.max)


    def _discover_flights_from_database(self, for_date: date = None, specific_header_id: int = None) -> list[dict]:
        """ 
        Discovers flights from the database that may need monitoring.
        Returns a list of full flight detail dictionaries.
        NOTE: This method needs actual DB query implementations. 
              FlightGet might need new methods for these specific queries.
        """
        discovered_flight_details = []
        with self.flight_get.db: # Manage DB connection
            if specific_header_id is not None:
                print(f"[{datetime.now()}] Discovering specific header flight ID {specific_header_id} and related.")
                header_details = self._fetch_flight_details_from_db(specific_header_id, 'jcsy_flights')
                if header_details and (not header_details.get('atd') or not header_details.get('ata')):
                    discovered_flight_details.append(header_details)
                # Fetch related query flights
                related_ids = self.flight_get.return_related_flights_IDs('query_flights', specific_header_id) # Assuming table name is not used here by FlightGet
                for q_id in related_ids:
                    query_details = self._fetch_flight_details_from_db(q_id, 'query_flights')
                    if query_details and (not query_details.get('atd') or not query_details.get('ata')):
                        discovered_flight_details.append(query_details)
            elif for_date is not None: # Restored elif for exclusive logic
                print(f"[{datetime.now()}] Discovering flights for date {for_date} needing updates.")
                date_str = for_date.strftime('%Y-%m-%d')
                for table_name in ['jcsy_flights', 'query_flights']:
                    # ---- START PLACEHOLDER DB QUERY ----
                    # This section requires new methods in FlightGet or direct SQL execution.
                    # Example:
                    # flight_ids_to_check = self.flight_get.get_flight_ids_for_monitoring(table_name, date_str)
                    print(f"Conceptual: Querying {table_name} for flights on {date_str} with missing ATD/ATA.")
                    flight_ids_to_check = [] # Simulate no flights found to avoid errors
                    # ---- END PLACEHOLDER DB QUERY ----
                    for flight_id in flight_ids_to_check:
                        details = self._fetch_flight_details_from_db(flight_id, table_name)
                        if details: # Ensure details were fetched
                            discovered_flight_details.append(details)
            else: # Restored else for the case where neither is provided
                print(f"[{datetime.now()}] No discovery criteria specified for discover_flights_from_database.")
        return discovered_flight_details


    def monitor_todays_flights(self):
        print(f"[{datetime.now()}] Initiating monitoring for today's flights.")
        today = date.today()
        discovered_flights = self._discover_flights_from_database(for_date=today)
        for flight_detail_dict in discovered_flights:
            self._add_or_update_flight_in_monitor(flight_detail_dict['id'], flight_detail_dict['table'], initial_details=flight_detail_dict)
        if not discovered_flights:
            print(f"[{datetime.now()}] No new active flights found for today: {today}")


    def monitor_specific_header_flight(self, header_flight_id: int):
        print(f"[{datetime.now()}] Initiating monitoring for specific header flight ID {header_flight_id}.")
        discovered_flights = self._discover_flights_from_database(specific_header_id=header_flight_id)
        for flight_detail_dict in discovered_flights:
            self._add_or_update_flight_in_monitor(flight_detail_dict['id'], flight_detail_dict['table'], initial_details=flight_detail_dict)
        if not discovered_flights:
            print(f"[{datetime.now()}] No active flights found for header ID {header_flight_id} or its related query flights.")


    def _run_crawlers_for_flight(self, flight_details: dict) -> CrawlerReturnStructure | None:
        flight_date_obj = flight_details.get('flight_date')
        airline = flight_details.get('airline')
        flight_no = flight_details.get('flight_number')
        dep_apt = flight_details.get('departure_airport')
        arr_apt = flight_details.get('arrival_airport')
        if isinstance(flight_date_obj, str):
            flight_date_obj = datetime.strptime(flight_date_obj, '%Y-%m-%d').date()
        elif isinstance(flight_date_obj, datetime):
            flight_date_obj = flight_date_obj.date()
        if not isinstance(flight_date_obj, date):
            print(f"[{datetime.now()}] flight_date not a valid date object: {flight_date_obj}"); return None
        crawler_data = None
        crawler_data = self.fv_crawler.get_flight_info(airline, flight_no, flight_date_obj, depapt=dep_apt or '', arrapt=arr_apt or '')
        if not crawler_data:
            print(f"[{datetime.now()}] FlightView failed/insufficient data. Attempting FlightStats for {airline}{flight_no}")
            crawler_data = self.fs_crawler.get_flight_info(airline, flight_no, flight_date_obj)  
        return crawler_data


    def _process_due_flights(self):
        now = datetime.now()
        processed_this_cycle = False  
        for i in range(len(self.flight_schedule) -1, -1, -1): # Iterate backwards for safe removal/modification
            flight_entry = self.flight_schedule[i]
            if flight_entry['next_run'] and flight_entry['next_run'] <= now:
                processed_this_cycle = True
                flight_id = flight_entry['id']
                table_name = flight_entry['table']
                print(f"[{datetime.now()}] Processing {table_name} ID {flight_id} scheduled for {flight_entry['next_run']}")

                current_details = self._fetch_flight_details_from_db(flight_id, table_name)
                if not current_details:
                    print(f"[{datetime.now()}] Failed to fetch details for {table_name} ID {flight_id}. Removing from schedule.")
                    self.flight_schedule.pop(i) # Remove if details can't be fetched
                    continue
                crawler_output = self._run_crawlers_for_flight(current_details)
                update_made_to_db = False
                if crawler_output:
                    update_payload = {'table': table_name, 'id': flight_id}
                    fields_from_crawler = ['departure_airport', 'arrival_airport', 'std', 'atd', 'etd', 'sta', 'ata', 'eta']
                    has_new_data = False
                    for field in fields_from_crawler:
                        crawler_value = getattr(crawler_output, field, None)
                        if crawler_value is not None:
                            update_payload[field] = crawler_value
                            # Check if this is actually different from DB to avoid empty updates
                            # For simplicity, we update if crawler provided it.
                            # More robust: compare crawler_value with current_details[field]
                            has_new_data = True                     
                    if has_new_data:
                        try:
                            print(f"[{datetime.now()}] Updating DB for {table_name} ID {flight_id}")
                            self.flight_add.update_flight(update_payload)
                            update_made_to_db = True
                        except Exception as e:
                            print(f"[{datetime.now()}] Error updating DB for {table_name} ID {flight_id}: {e}")
                    else:
                        print(f"[{datetime.now()}] No new updatable data from crawlers for {table_name} ID {flight_id}")
                else:
                    print(f"[{datetime.now()}] Crawlers returned no data for {table_name} ID {flight_id}.")               
                # Regardless of crawler success, flight needs re-evaluation for scheduling
                # Fetch fresh details if DB was updated, or use current if not, to decide next run time.
                details_for_reschedule = self._fetch_flight_details_from_db(flight_id, table_name) if update_made_to_db else current_details
                if details_for_reschedule:
                     # This call will update the entry in self.flight_schedule or remove it
                    self._add_or_update_flight_in_monitor(flight_id, table_name, initial_details=details_for_reschedule)
                else:
                    # If somehow details are gone after trying to update, remove from schedule
                    print(f"[{datetime.now()}] Could not get details for {table_name} ID {flight_id} post-processing. Removing.")
                    self.flight_schedule.pop(i) # Pop the original entry if it can't be re-evaluated           
        if processed_this_cycle:
            self.flight_schedule.sort(key=lambda x: x['next_run'] if x['next_run'] else datetime.max)
            if self.flight_schedule and self.flight_schedule[0]['next_run'] is not None:
                print(f"[{datetime.now()}] Processed due flights. Next check: {self.flight_schedule[0]['next_run']}")
            else:
                print(f"[{datetime.now()}] Processed due flights. Schedule now empty or all flights complete.")


    def run(self):
        # Initial scan for today's flights to populate the schedule - runs only once at startup
        self.monitor_todays_flights()
        while True:
            now = datetime.now()
            # Removed periodic discovery of today's flights as per requirements
            # monitor_todays_flights should only run once at startup
            
            if not self.flight_schedule or self.flight_schedule[0]['next_run'] is None:
                wait_time = self.max_sleep_interval  # Just wait the max interval if nothing to process
                if self.flight_schedule and self.flight_schedule[0]['next_run'] is None:
                    print(f"[{now}] All monitored flights appear complete. Waiting for new triggers.")
                else:
                    print(f"[{now}] No flights in monitor. Waiting for new triggers.")
                time.sleep(wait_time)
                continue
            next_run_time = self.flight_schedule[0]['next_run']
            if next_run_time <= now:
                self._process_due_flights() # This will re-sort the schedule
            else:
                sleep_duration = (next_run_time - now).total_seconds()
                actual_sleep = min(max(1, sleep_duration), self.max_sleep_interval)
                print(f"[{datetime.now()}] Next check at {next_run_time}. Sleeping for {actual_sleep:.2f}s.")
                time.sleep(actual_sleep)

# --- End of FlightMaintainer class ---


# Example of how to run (optional, for testing)
if __name__ == '__main__':
    print("Starting FlightMaintainer example...")
    
    # Ensure DB path and config path are correct or adjust as needed
    # For this example to run meaningfully, the DB should exist and be connectable.
    # The jcsy_config.yaml is needed for FlightAdd initialization.
    try:
        maintainer = FlightMaintainer(db_name="flights.db") 

        # To test effectively:
        # 1. Populate 'flights.db' with test data:
        #    - Flights for today missing ATD/ATA.
        #    - A specific header flight (e.g., ID 1) with related query flights also needing updates.
        # 2. Ensure `FlightGet` can query these (especially new methods for `discover_flights_from_database`).
        #    The current `discover_flights_from_database` has PLACEHOLDER DB queries.
        #    You MUST implement the actual SQL queries there or in `FlightGet` for it to find flights.

        # Example: Manually trigger monitoring for a specific header flight ID (if it exists in DB)
        # print("Attempting to monitor specific header flight ID 1 (ensure it exists and needs updates)...")
        # maintainer.monitor_specific_header_flight(1) 

        # The run loop will then periodically call monitor_todays_flights().
        maintainer.run()

    except FileNotFoundError as e:
        print(f"ERROR: Config file not found. Ensure 'jcsy_config.yaml' exists or path is correct. Details: {e}")    
    except Exception as e:
        print(f"An error occurred in FlightMaintainer setup or main loop: {e}")
        import traceback
        traceback.print_exc()
