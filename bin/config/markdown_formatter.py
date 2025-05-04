'''
Markdown formatter for flight data.

This module provides functions to convert flight data from the database
to a markdown format that can be rendered in the UI.
'''
from datetime import datetime, date
from typing import Dict, List, Union, Any, Callable
import yaml
import os
import re
from bin.database.flight_get import FlightGet

class MarkdownFormatter:
    """
    Class to convert flight data to markdown format for rendering in UI.
    """
    _FLIGHT_DATA_STRUCTURE = {
        'header_airline': str,
        'header_flight_number': str,
        'flight_date': date,
        'departure_airport': str,
        'is_arrival': int,
        'query_flights': list,
    }
    _QUERY_FLIGHT_DATA_STRUCTURE = {
        'airline': str,
        'flight_number': str,
        'flight_date': date,
        'departure_airport': str,
        'arrival_airport': str,
        'std': datetime,
        'etd': datetime,
        'atd': datetime,
        'sta': datetime,
        'eta': datetime,
        'ata': datetime,
        'booked_count_non_economy': int,
        'booked_count_economy': int,
        'checked_count_non_economy': int,
        'checked_count_economy': int,
        'check_count_infant': int,
        'bags_count_piece': int,
        'bags_count_weight': int, 
    }
    @property
    def FLIGHT_DATA_STRUCTURE(self):
        return self._FLIGHT_DATA_STRUCTURE.copy()
    @property
    def QUERY_FLIGHT_DATA_STRUCTURE(self):
        return self._QUERY_FLIGHT_DATA_STRUCTURE.copy()


    def __init__(self, header_flight_id: int):
        self.flight_data = {}
        self.db = FlightGet()
        src_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        config_path = os.path.join(src_dir, "bin", "config", "markdown_config.yaml")
        self.config = self._load_config(config_path)
        self._load_flight_data(header_flight_id)


    def _load_config(self, config_path):
        """Load the markdown formatting configuration from YAML."""
        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Error loading markdown config: {str(e)}")
            # Return a default config if loading fails
            return {
                'header': 'JCSY:{header_airline}{header_flight_number}/{flight_date}/{departure_airport},[header_I_O]',
                'fields': 'Flight Number|Airport|Delay Mins|Booked Pax|Checked Pax|Bags/Weight',
                'spaces': ':--------|:-----|:------|-------:|-----------:|--------:',
                'data': {
                    'Flight Number': '{airline}{flight_number}',
                    'Airport': '[judge_output_airport]',
                    'Delay Mins': '[delay_mins]',
                    'Booked Pax': '{booked_count_non_economy}/{booked_count_economy}',
                    'Checked Pax': '{checked_count_non_economy}/{checked_count_economy}+{check_count_infant}',
                    'Bags/Weight': '{bags_count_piece}/{bag_count_weight}'
                }
            }


    def _load_flight_data(self, header_flight_id):
        """
        Load flight data from the database.
        Args:
            header_flight_id: ID of the flight to load as header
        Returns:
            True if data was loaded successfully, False otherwise
        """
        try:
            # Get the header flight data
            header_data = self.db.return_flight_data('jcsy_flights', header_flight_id)
            if not header_data:
                return False
            related_flight_ids = self.db.return_related_flights_IDs('query_flights', header_flight_id)
            # Get related flights
            query_flights = []
            for flight_id in related_flight_ids:
                query_flights.append(self.db.return_flight_data('query_flights', flight_id))
            #Prepare query flights data.
            output_query_flights = []
            for flight in query_flights:
                # Create a new dictionary for each flight using the property method
                output_query_flight = self.QUERY_FLIGHT_DATA_STRUCTURE
                output_query_flight['airline'] = flight['airline']
                output_query_flight['flight_number'] = flight['flight_number']
                output_query_flight['flight_date'] = flight['flight_date']
                output_query_flight['departure_airport'] = flight['departure_airport']
                output_query_flight['arrival_airport'] = flight['arrival_airport']
                output_query_flight['std'] = flight['std']
                output_query_flight['etd'] = flight['etd']
                output_query_flight['atd'] = flight['atd']
                output_query_flight['sta'] = flight['sta']
                output_query_flight['eta'] = flight['eta']
                output_query_flight['ata'] = flight['ata']
                output_query_flight['booked_count_non_economy'] = flight['booked_count_non_economy']
                output_query_flight['booked_count_economy'] = flight['booked_count_economy']
                output_query_flight['checked_count_non_economy'] = flight['checked_count_non_economy']
                output_query_flight['checked_count_economy'] = flight['checked_count_economy']
                output_query_flight['check_count_infant'] = flight['check_count_infant']
                output_query_flight['bags_count_piece'] = flight['bags_count_piece']
                output_query_flight['bags_count_weight'] = flight['bags_count_weight']
                output_query_flights.append(output_query_flight)
            #Store the data with the header and query flights data.
            self.flight_data = {
                'header_airline': header_data['airline'],
                'header_flight_number': header_data['flight_number'],
                'flight_date': header_data['flight_date'],
                'departure_airport': header_data['departure_airport'],
                'is_arrival': header_data['is_arrival'],
                'query_flights': output_query_flights
            }
            return True
        except Exception as e:
            print(f"Error loading flight data: {str(e)}")
            return False


    def _substitute_fields(self, template, data_index=None):
        """
        Process template string by substituting fields and calling functions.
        Args:
            template: Template string containing placeholders
            data_index: Index of the query flight to use for data 
        Returns:
            Processed string with all substitutions applied
        """
        # Handle function calls [function_name]
        function_pattern = r'\[([^\]]+)\]'
        function_matches = re.findall(function_pattern, template)
        for func_name in function_matches:
            # Check if this function exists in the class
            if hasattr(self, func_name) and callable(getattr(self, func_name)):
                func = getattr(self, func_name)
                # Call function with or without data_index parameter
                if data_index is not None and 'query_flight_index' in func.__code__.co_varnames:
                    result = func(data_index)
                else:
                    result = func()
                # Replace function call with result
                template = template.replace(f"[{func_name}]", str(result))  
        # Handle field placeholders {field_name}
        if data_index is not None and 'query_flights' in self.flight_data:
            # Use query flight data for field substitution
            query_flight = self.flight_data.get('query_flights')[data_index]
            field_pattern = r'\{([^}]+)\}'
            field_matches = re.findall(field_pattern, template)
            for field_name in field_matches:
                field_value = query_flight.get(field_name, '')
                # Format date fields
                if field_name == 'flight_date' and isinstance(field_value, (date, datetime)):
                    if isinstance(field_value, datetime):
                        field_value = field_value.date()
                    field_value = field_value.strftime('%Y-%m-%d')
                # Format time fields
                elif field_name in ['std', 'etd', 'atd', 'sta', 'eta', 'ata'] and field_value:
                    field_value = field_value.strftime('%H:%M')
                # Replace placeholder with value
                template = template.replace(f"{{{field_name}}}", str(field_value))
        else:
            # Use header data for field substitution
            field_pattern = r'\{([^}]+)\}'
            field_matches = re.findall(field_pattern, template)
            for field_name in field_matches:
                field_value = self.flight_data.get(field_name, '')
                # Format date fields
                if field_name == 'flight_date' and isinstance(field_value, (date, datetime)):
                    if isinstance(field_value, datetime):
                        field_value = field_value.date()
                    field_value = field_value.strftime('%Y-%m-%d')
                # Replace placeholder with value
                template = template.replace(f"{{{field_name}}}", str(field_value))
        return template
    

    def header_I_O(self):
        """Return 'I' for arrival flights or 'O' for departure flights."""
        if self.flight_data.get('is_arrival') == 1:
            return 'I'
        else:
            return 'O'


    def judge_output_airport(self, query_flight_index):
        """Return the appropriate airport based on arrival/departure status."""
        if self.flight_data.get('is_arrival') == 1:
            return self.flight_data.get('query_flights')[query_flight_index].get('arrival_airport')
        else:
            return self.flight_data.get('query_flights')[query_flight_index].get('departure_airport')
        

    def delay_mins(self, query_flight_index):
        """Calculate and format delay minutes for the specified flight."""
        query_flight = self.flight_data.get('query_flights')[query_flight_index]
        if self.flight_data.get('is_arrival') == 1:
            return self._format_time_difference(query_flight.get('eta'), query_flight.get('sta'))
        else:
            return self._format_time_difference(query_flight.get('etd'), query_flight.get('atd'))


    def _format_time_difference(self, time1: datetime, time2: datetime) -> str:
        """
        Calculate and format the time difference between two timestamps.
        Args:
            time1: First datetime
            time2: Second datetime 
        Returns:
            Formatted string showing the time difference (e.g., "15m" or "2h5m")
            The minus time won't be shown(e.g., "").
        """
        # Calculate difference in minutes
        diff_seconds = (time1 - time2).total_seconds()
        diff_minutes = int(diff_seconds / 60)
        # Only show positive differences, return empty string for negative values
        if diff_minutes <= 0:
            return ""
        # Format the output (no sign needed since we only show positive values)
        if diff_minutes < 60:
            return f"{diff_minutes}m"
        else:
            hours = diff_minutes // 60
            minutes = diff_minutes % 60
            if minutes > 0:
                return f"{hours}h{minutes}m"
            else:
                return f"{hours}h"
    

    def format_markdown_header(self):
        """
        Format the flight header section as markdown.
        
        Returns:
            Formatted markdown header string
        """
        header_template = self.config.get('header', '')
        # Add the heading level ## if not in template
        if not header_template.startswith('#'):
            header_template = f"## {header_template}"
        # Substitute placeholders and function calls
        header = self._substitute_fields(header_template)
        return f"{header}\n\n"
    

    def format_markdown_table(self):
        """
        Format the flight data as a markdown table.
        
        Returns:
            Formatted markdown table string
        """
        # Get field names and alignment from config
        fields_line = self.config.get('fields', '')
        spaces_line = self.config.get('spaces', '')
        data_config = self.config.get('data', {})
        # Create table header
        table = f"{fields_line}\n{spaces_line}\n"
        # Process each flight in query_flights
        query_flights = self.flight_data.get('query_flights', [])
        for i, _ in enumerate(query_flights):
            row_cells = []
            # Process each field template
            for field_name, field_template in data_config.items():
                # Process template for this field
                cell_value = self._substitute_fields(field_template, i)
                row_cells.append(cell_value)
            # Join cells with pipe separator
            row = "|".join(row_cells)
            table += f"{row}\n"
        return table
    

    def get_markdown(self, flight_id=None):
        """
        Generate complete markdown for the specified flight or currently loaded data.
        
        Args:
            flight_id: Optional flight ID to load data for
            
        Returns:
            Formatted markdown string for the flight
        """
        # Load data if flight_id is provided
        if flight_id is not None:
            if not self._load_flight_data(flight_id):
                return f"Error: Could not load data for flight ID {flight_id}"
        # Check if we have data to format
        if not self.flight_data:
            return "Error: No flight data loaded"
        # Format the header and table
        markdown = self.format_markdown_header()
        markdown += self.format_markdown_table()
        return markdown

