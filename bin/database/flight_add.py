from bin.database.flight_db import FlightDatabase
from bin.config.config_parser import JcsyParser
from datetime import datetime


class FlightAdd:
    """Repository for adding flight data to the database"""

    # Define the structure as a private class constant
    _UPDATE_FIELDS_STRUCTURE = {
        'table': str,
        'id': int,
        'flight_date': datetime,
        'std': datetime,
        'etd': datetime,
        'atd': datetime,
        'sta': datetime,
        'eta': datetime,
        'ata': datetime
    }

    def __init__(self, config_path: str = 'jcsy_config.yaml'):
        """Initialize with database connection and config parser"""
        self.db = FlightDatabase()
        self.parser = JcsyParser(config_path)
        # Mapping from the db fields key to the parser fields as the value.
        self.HEADER_FIELDS = {
            'airline': 'header_airline',
            'flight_number': 'header_flight_number',
            'flight_date': 'header_flight_date',
            'is_arrival': 'is_arrival',
            'airport': 'header_airport',
        }
        self.QUERY_FLIGHT_FIELDS = {
            'airline': 'airline',
            'flight_number': 'flight_number',
            'flight_date': 'header_flight_date',
            'departure_airport': 'airport',
            'arrival_airport': 'header_airport',
            'std_text': 'std_text',
            'booked_count_non_economy': 'booked_count_non_economy',
            'booked_count_economy': 'booked_count_economy',
            'checked_count_non_economy': 'checked_count_non_economy',
            'checked_count_economy': 'checked_count_economy',
            'check_count_infant': 'check_count_infant',
            'bags_count_piece': 'bags_count_piece',
            'bags_count_weight': 'bags_count_weight',
        }
        self.HOME_AIRPORT = "LAX"

    @property
    def UPDATE_FIELDS(self):
        """
        Read-only property that returns a copy of the update fields structure
        The corrent calling should be:
        copy_dict = {key: None for key in flight_add.UPDATE_FIELDS.keys()}
        """
        return self._UPDATE_FIELDS_STRUCTURE.copy()

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


    def add_jcsy_content(self, content: str) -> None:   
        """
        Parse JCSY format content and add it to the database
        Args:
            content: Multi-line string of JCSY content  
        Raises:
            Exception: If parsing or database operations fail
        """
        try:
            # Parse the content using the configuration-driven parser
            parsed_data = self.parser.parse_content(content)
            with self.db:
                # Process header data
                header_data = self._get_data_from_parser('jcsy_flights', self.HEADER_FIELDS, parsed_data)
                if header_data:
                    query = f'''
                        INSERT INTO jcsy_flights (
                            {', '.join(header_data[0].keys())}
                        ) VALUES (
                            {', '.join(['?' for _ in header_data[0]])}
                        )
                    '''
                    self.db.cursor.execute(query, list(header_data[0].values()))
                    header_flight_id = self.db.cursor.lastrowid
                # Process flight data
                flight_data = self._get_data_from_parser('query_flights', self.QUERY_FLIGHT_FIELDS, parsed_data)
                print(f"\nflight_data: {flight_data}")
                for flight in flight_data:
                    # Add the header flight reference
                    flight['jcsy_flight_id'] = header_flight_id
                    # Set airports based on arrival/departure status
                    if not header_data[0].get('is_arrival'):
                        flight['departure_airport'] = self.HOME_AIRPORT
                        flight['arrival_airport'] = flight.get('airport', '')
                    # Convert numeric fields to 0 if None
                    for field in ['booked_count_non_economy', 'booked_count_economy', 
                                'checked_count_non_economy', 'checked_count_economy',
                                'check_count_infant', 'bags_count_piece', 'bags_count_weight']:
                        if field in flight and flight[field] is None:
                            flight[field] = 0
                    # Insert into query_flights table
                    query = f'''
                        INSERT INTO query_flights (
                            {', '.join(flight.keys())}
                        ) VALUES (
                            {', '.join(['?' for _ in flight])}
                        )
                    '''
                    self.db.cursor.execute(query, list(flight.values()))
                self.db.connection.commit()
        except Exception as e:
            raise Exception(f"Failed to add JCSY content: {str(e)}") 
        

    def update_flight_times(self, update_fields: dict):
        """
        Update the a flight id with the table name in the database if the value is not None.
        the table name and the flight id are required.
        Args:
            update_fields: The dictionary sample is showing in the __init__();
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
        
