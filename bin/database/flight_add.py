from typing import Dict, Any, Optional, List
from bin.database.flight_db import FlightDatabase
from bin.config.config_parser import JcsyParser


class FlightAdd:
    """Repository for adding flight data to the database"""


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
    

    def _get_data_from_parser(self, db_table: str, field_mapping: Dict[str, str], parsed_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Maps database field names to values from parser data
        Args:
            db_table: The database table name ('jscy_flights' or 'query_flights')
            field_mapping: Dictionary that maps DB fields to parser fields
            parsed_data: Dictionary containing parsed data from the parser
        Returns:
            List of dictionaries with database field names as keys and parser values as values
        """
        result_list = []
        # For header data
        if db_table == 'jscy_flights':
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
                header_data = self._get_data_from_parser('jscy_flights', self.HEADER_FIELDS, parsed_data)
                if header_data:
                    query = f'''
                        INSERT INTO jscy_flights (
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
                    flight['jscy_flight_id'] = header_flight_id
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
        
