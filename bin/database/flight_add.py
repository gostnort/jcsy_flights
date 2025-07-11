from bin.database.flight_db import FlightDatabase
from bin.config.jcsy_config import JcsyParser
from datetime import datetime, date
from bin.database.flight_get import FlightGet
from bin.scrapers.flightview_crawler import FlightViewCrawler, return_structure
from bin.scrapers.flightstats_crawler import FlightStatsCrawler


class FlightAdd:
    """Repository for adding flight data to the database"""

    # Define the structure as a private class constant
    _UPDATE_FIELDS_STRUCTURE = {
        'table': str,
        'id': int,
        'flight_date': datetime,
        'departure_airport': str,
        'arrival_airport': str,
        'std': datetime,
        'etd': datetime,
        'atd': datetime,
        'sta': datetime,
        'eta': datetime,
        'ata': datetime
    }

    _JCSY_FLIGHT_REQUIRED_FIELDS = {
        'airline': str,
        'flight_number': str,
        'flight_date': date, 
        'departure_airport': str,
        'arrival_airport': str,
        'inbound_not': int,
        'std_text': str,
        'std': datetime,
        'etd': datetime,
        'atd': datetime,
        'sta': datetime,
        'eta': datetime,
        'ata': datetime,
        }

    _QUERY_FLIGHT_REQUIRED_FIELDS = {
        'jcsy_flight_id': int,
        'airline': str,
        'flight_number': str,
        'flight_date': date, 
        'departure_airport': str,
        'arrival_airport': str,
        'std_text': str,
        'std': datetime,
        'etd': datetime,
        'atd': datetime,
        'sta': datetime,
        'eta': datetime,
        'ata': datetime,
        'delayed': bool,
        'booked_count_non_economy': int,
        'booked_count_economy': int,
        'checked_count_non_economy': int,
        'checked_count_economy': int,
        'check_count_infant': int,
        'bags_count_piece': int,
        'bags_count_weight': int,
        }

    def __init__(self, config_path: str ):
        """Initialize with database connection and config parser"""
        # Use consistent database name from FlightDatabase
        self.db_name = FlightDatabase.DEFAULT_DB_NAME
        self.db = FlightDatabase(self.db_name)
        self.parser = JcsyParser(config_path)
        # Mapping from the db fields key to the parser fields as the value.
        self.HEADER_FIELDS = {
            'airline': 'header_airline',
            'flight_number': 'header_flight_number',
            'flight_date': 'header_flight_date',
            'inbound_not': 'inbound_not',
            # For JCSY format: if inbound_not=1 (inbound), header_airport is arrival
            # if inbound_not=0 (outbound), header_airport is departure
            # We'll handle this logic in add_jcsy_content method
        }
        self.QUERY_FLIGHT_FIELDS = {
            'airline': 'airline',
            'flight_number': 'flight_number',
            'flight_date': 'header_flight_date',
            'departure_airport': 'airport',
            'arrival_airport': '',
            'std_text': 'std_text',
            'booked_count_non_economy': 'booked_count_non_economy',
            'booked_count_economy': 'booked_count_economy',
            'checked_count_non_economy': 'checked_count_non_economy',
            'checked_count_economy': 'checked_count_economy',
            'check_count_infant': 'check_count_infant',
            'bags_count_piece': 'bags_count_piece',
            'bags_count_weight': 'bags_count_weight',
        }

    @property
    def UPDATE_FIELDS(self):
        """
        Read-only property that returns a copy of the update fields structure
        The corrent calling should be:
        copy_dict = {key: None for key in flight_add.UPDATE_FIELDS.keys()}
        """
        return self._UPDATE_FIELDS_STRUCTURE.copy()
    
    @property
    def JCSY_FLIGHT_REQUIRED_FIELDS(self):
        """
        Read-only property that returns a copy of the JCSY flight required fields structure
        """
        return self._JCSY_FLIGHT_REQUIRED_FIELDS.copy()
    

    @property
    def QUERY_FLIGHT_REQUIRED_FIELDS(self):
        """
        Read-only property that returns a copy of the query flight required fields structure
        """
        return self._QUERY_FLIGHT_REQUIRED_FIELDS.copy()


    def add_jcsy_content(self, jcsy_content:str) -> list[int]:
        parser_dict = self.parser.parse_content(jcsy_content)
        header_data_list = self._get_data_from_parser('jcsy_flights', self.HEADER_FIELDS, parser_dict)  
        if not header_data_list:
            raise ValueError("No header data parsed from JCSY content.")
        single_header_data_from_parser = header_data_list[0] # Data directly from parser
        flight_get = FlightGet(self.db_name)
        header_id = 0
        try:
            # Attempt to find the flight in the database using key info from parser output
            flight_id_list = flight_get.return_flight_id(
                'jcsy_flights',
                single_header_data_from_parser['airline'],
                single_header_data_from_parser['flight_number'],
                single_header_data_from_parser['flight_date'] 
            )
            if flight_id_list:
                header_id = flight_id_list[0]
        except (ValueError, IndexError, KeyError):
            # Flight not found or essential key data missing in parser output to perform lookup
            pass # Will proceed to insert if header_id remains 0
        # If flight was not found in DB, insert it using only parser data
        if header_id == 0:
            # At this stage, we insert with what the parser gives us.
            # Handle airport assignment based on inbound/outbound flag
            header_airport = single_header_data_from_parser.get('header_airport', '')
            inbound_flag = single_header_data_from_parser.get('inbound_not', 0)
            
            # Header flight airport is always departure_airport
            single_header_data_from_parser['departure_airport'] = header_airport
            single_header_data_from_parser['arrival_airport'] = ''  # Will be filled by individual flights
            
            # Remove the header_airport key as it's not a database field
            if 'header_airport' in single_header_data_from_parser:
                del single_header_data_from_parser['header_airport']
            
            # A minimal check for core identifiable info before trying to insert:
            if not (single_header_data_from_parser.get('airline') and 
                    single_header_data_from_parser.get('flight_number') and 
                    single_header_data_from_parser.get('flight_date')):
                raise ValueError("Essential identifying information (airline, flight_number, flight_date) missing from parsed header.")          
            # Add inbound_not if it's there, otherwise it should be nullable or have a default in DB
            # Add departure_airport if it's there
            # All other fields like arrival_airport, std, etd, atd, sta, eta, ata will be added 
            # by flight_maintain.py if not present in JCSY parsed output.
            header_id = self._add_flight_record('jcsy_flights', single_header_data_from_parser)
        if header_id == 0:
             raise Exception("Failed to obtain or create a valid header_id for JCSY content processing.")
        flight_ids=[]
        flight_ids.append(header_id)       
        flight_data_list = self._get_data_from_parser('query_flights', self.QUERY_FLIGHT_FIELDS, parser_dict)       
        for flight_dict in flight_data_list:
            flight_dict['jcsy_flight_id'] = header_id
            # Get the original header airport from the parsed data
            header_airport = parser_dict.get('header', {}).get('header_airport', '')
            inbound_flag = single_header_data_from_parser.get('inbound_not', 0)
            if inbound_flag == 1:
                # Inbound flight: header airport is arrival, individual airports are departures
                flight_dict['arrival_airport'] = header_airport  # LAX
                flight_dict['departure_airport'] = flight_dict.get('airport', '')  # Origin airport
            else:
                # Outbound flight: header airport is departure, individual airports are arrivals
                flight_dict['departure_airport'] = header_airport  # PEK
                flight_dict['arrival_airport'] = flight_dict.get('airport', '')  # Destination airport
            # Remove the 'airport' key as it's not a database field
            if 'airport' in flight_dict:
                del flight_dict['airport']
            for field in ['booked_count_non_economy', 'booked_count_economy',
                          'checked_count_non_economy', 'checked_count_economy',
                          'check_count_infant', 'bags_count_piece', 'bags_count_weight']:
                if field in flight_dict and flight_dict[field] is None:
                    flight_dict[field] = 0
            # Check for duplicate flight segment (same airline, flight_number, flight_date, departure_airport, arrival_airport)
            existing_flight_id = self._check_duplicate_flight_segment(flight_dict)
            if existing_flight_id:
                print(f"Skipping duplicate flight: {flight_dict.get('airline')}{flight_dict.get('flight_number')} {flight_dict.get('departure_airport')}-{flight_dict.get('arrival_airport')}")
                flight_ids.append(existing_flight_id)
            else:
                flight_ids.append(self._add_flight_record('query_flights', flight_dict))
        return flight_ids


    def _add_flight_record(self, table_name: str, flight_data: dict) -> int:
        if table_name not in ['jcsy_flights', 'query_flights']:
            raise ValueError(f"Invalid table name: {table_name}")
        valid_fields = {}
        if table_name == 'jcsy_flights':
            valid_fields= self.JCSY_FLIGHT_REQUIRED_FIELDS
        if table_name == 'query_flights':
            valid_fields= self.QUERY_FLIGHT_REQUIRED_FIELDS
        # Filter flight_data to include only valid fields for the table
        # and prepare for SQL insertion (e.g., convert datetime to string if needed)
        data_to_insert = {}
        for key, value in flight_data.items():
            if key in valid_fields:
                data_to_insert[key] = value
        if not data_to_insert:
            raise ValueError("No valid data provided for insertion.")
        columns = ', '.join(data_to_insert.keys())
        placeholders = ', '.join(['?' for _ in data_to_insert])
        query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
        try:
            with self.db: # Assuming self.db is your FlightDatabase instance
                self.db.cursor.execute(query, list(data_to_insert.values()))
                self.db.connection.commit()
                return self.db.cursor.lastrowid
        except Exception as e:
            # Consider more specific error handling or logging
            raise Exception(f"Failed to add record to {table_name}: {str(e)}")     


    def _get_data_from_parser(self, db_table, field_mapping, parsed_data):
        """
        Maps database field names to values from parser data
        Args:
            db_table: The database table name ('jcsy_flights' or 'query_flights')
            field_mapping: Dictionary that maps DB fields to parser fields
            parsed_data: Dictionary containing parsed data from the parser
            db_table: str, field_mapping: dict[str, str], parsed_data: dict[str, Any] -> list[dict[str, Any]]
        Returns:
            List of dictionaries with database field names as keys and parser values as values
        """
        result_list = []
        # For header data
        if db_table == 'jcsy_flights':
            header_data = parsed_data.get('header', {})
            if header_data:
                result = {}
                for db_field, parser_field in field_mapping.items():
                    if 'id' not in db_field and parser_field in header_data:
                        result[db_field] = header_data[parser_field]
                if result:
                    result_list.append(result)
        # For flight data
        elif db_table == 'query_flights':
            flight_data = parsed_data.get('flight', {})
            for flight in flight_data.values():
                result = {}
                for db_field, parser_field in field_mapping.items():
                    if 'id' not in db_field and parser_field in flight:
                        result[db_field] = flight[parser_field]
                if result:
                    result_list.append(result)
        return result_list


    def _check_duplicate_flight_segment(self, flight_dict: dict) -> int | None:
        """
        检查是否存在重复的航班段
        基于 airline, flight_number, flight_date, departure_airport, arrival_airport 判断重复
        返回已存在的航班ID，如果不存在则返回None
        """
        try:
            with self.db:
                query = """
                    SELECT id FROM query_flights 
                    WHERE airline = ? AND flight_number = ? AND flight_date = ? 
                    AND departure_airport = ? AND arrival_airport = ?
                """
                self.db.cursor.execute(query, (
                    flight_dict.get('airline'),
                    flight_dict.get('flight_number'),
                    flight_dict.get('flight_date'),
                    flight_dict.get('departure_airport'),
                    flight_dict.get('arrival_airport')
                ))
                result = self.db.cursor.fetchone()
                return result[0] if result else None
        except Exception as e:
            print(f"Error checking for duplicate flight: {e}")
            return None
        

    def update_flight(self, update_fields: dict):
        """
        Update the a flight id with the table name in the database if the value is not None.
        the table name and the flight id are required.
        Args:
            update_fields: The dictionary structure defined in the UPDATE_FIELDS property;
        """
        try:
            # Validate required fields
            if 'table' not in update_fields or 'id' not in update_fields:
                raise ValueError("Table name and flight ID are required")
            # Get the table name and ID
            table = update_fields['table']
            flight_id = update_fields['id']
            # Prepare update fields, excluding None values
            update_data = {}
            for field, value in update_fields.items():
                if field not in ['table', 'id'] and value is not None:
                    update_data[field] = value
            if not update_data:
                return  # No fields to update
            # Build the update query
            set_clause = ', '.join([f"{field} = ?" for field in update_data.keys()])
            query = f'''
                UPDATE {table}
                SET {set_clause}
                WHERE id = ?
            '''
            print(f"query: {query}")
            # Execute the update
            with self.db:
                self.db.cursor.execute(query, list(update_data.values()) + [flight_id])
                self.db.connection.commit()      
        except Exception as e:
            raise Exception(f"Failed to update flight times: {str(e)}")
        
