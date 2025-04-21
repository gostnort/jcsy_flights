import re
from datetime import datetime, timedelta
from src.scrapers.flightview_crawler import FlightViewScraper
from src.scrapers.flightstats_crawler import FlightStatsScraper

class FlightScraper:
    def __init__(self, list_type: str = 'arrival', home_airport: str = 'LAX'): # Default to arrival list, home LAX
        self.HOME_AIRPORT = home_airport
        # FlightView related
        self.flightview_crawler = FlightViewScraper()
        self.flightstats_crawler = FlightStatsScraper()
        
        # Configuration
        if list_type not in ['arrival', 'departure']:
            raise ValueError("list_type must be 'arrival' or 'departure'")
             
        self.list_type = list_type
        
        
        # These will be set by parse_jcsy_line
        self.flightview_date = None 
        self.jcsy_flight = {} # Stores JCSY main flight number
        self.jcsy_departure_time = None # Stores departure time of the main flight
        self.jcsy_arrival_time = None # Stores arrival time of the main flight
        
        # Standardized return structure used by search methods
        self.search_result = {
            'ata': None,  # datetime object
            'sta': None,  # datetime object
            'snippet': None,  # Flight status text
            'is_another_day': int  # Flag to indicate if the flight is day -1 or +1
        }
    
    # Processing the JCSY line and extract flight info.
    # Get the flightview_date and jcsy_flight from 'JCSY:CA0984/11DEC24/LAX,I'
    # flightview_date becomes 20241211
    # jcsy_flight becomes {'airline': 'CA', 'number': '984'}
    def parse_jcsy_line(self, text):
        """Parse date and main JCSY flight number from JCSY line"""
        try:
            for line in text.split('\n'):
                if line.startswith('JCSY:'):
                    parts = line.split('/')
                    # Now only requires JCSY:FLT/DATE - Airport is configured
                    if len(parts) >= 2: 
                        # Get flight info from first part
                        section_1 = parts[0]  # "JCSY:CA0984"
                        flight_number_match = re.match(r'JCSY:(\w+)', section_1)
                        if not flight_number_match:
                            continue
                        flight_number = flight_number_match.group(1)
                        # Store only airline/number, airport comes from config
                        self.jcsy_flight = self.format_flight_number(flight_number)
                        
                        # Get date from second part
                        date_part = parts[1]  # "11DEC" or "11DEC24"
                        if len(date_part) > 5:  # Has year
                            year_part = int(date_part[-2:])
                            year = 2000 + year_part if year_part < 70 else 1900 + year_part # Adjust century
                            date_str = date_part[:-2] + str(year)
                            date_obj = datetime.strptime(date_str, "%d%b%Y")
                        else:
                            date_obj = datetime.strptime(date_part, "%d%b")
                            year = datetime.now().year
                            if date_obj.month == 12 and datetime.now().month == 1:
                                year -= 1
                        self.flightview_date = date_obj.replace(year=year).strftime("%Y%m%d")
                        
                        # Get times for the main flight
                        self._get_main_flight_times()
                        
                        print(f"Parsed JCSY ({self.list_type} list): Date={self.flightview_date}, Main Flight={self.jcsy_flight['airline']}{self.jcsy_flight['number']}, Home Airport={self.HOME_AIRPORT}")
                        
                        return True # Successfully parsed JCSY line
            # If loop completes without finding JCSY line
            raise ValueError("JCSY line not found or invalid format (Requires at least JCSY:FLT/DATE)")
        except Exception as e:
            print(f"Error parsing JCSY line: {str(e)}")
            self.flightview_date = None
            self.jcsy_flight = {}
            self.jcsy_departure_time = None
            self.jcsy_arrival_time = None
            return False
    
    def _get_main_flight_times(self):
        """Get departure and arrival times for the main flight using FlightStats"""
        try:
            if not self.jcsy_flight or not self.flightview_date:
                print("Main flight or date not set, cannot get flight times.")
                return
            
            print(f"Getting times for main flight {self.jcsy_flight['airline']}{self.jcsy_flight['number']} on {self.flightview_date}...")
            flight_info = self.flightstats_crawler.get_flight_info(
                self.jcsy_flight['airline'],
                self.jcsy_flight['number'],
                self.flightview_date
            )
            
            if flight_info:
                # Get departure time
                if flight_info.get('departure'):
                    dep_info = flight_info['departure']
                    dep_time = dep_info.get('scheduled')
                    if dep_time and dep_time != "N/A":
                        self.jcsy_departure_time = self.split_for_datetime(dep_time, 1, self.flightview_date)
                        print(f"Main flight departure time: {self.jcsy_departure_time}")
                    else:
                        print("No scheduled departure time found for main flight.")
                
                # Get arrival time
                if flight_info.get('arrival'):
                    arr_info = flight_info['arrival']
                    arr_time = arr_info.get('scheduled')
                    if arr_time and arr_time != "N/A":
                        self.jcsy_arrival_time = self.split_for_datetime(arr_time, 1, self.flightview_date)
                        print(f"Main flight arrival time: {self.jcsy_arrival_time}")
                    else:
                        print("No scheduled arrival time found for main flight.")
            else:
                print("Could not get flight info for main flight.")
        except Exception as e:
            print(f"Error getting main flight times: {str(e)}")
    
    # Format flight number by removing leading zeros.
    # Examples:
    # AM0782 -> {'airline': 'AM', 'number': '782'}
    # UA0023 -> {'airline': 'UA', 'number': '23'}
    def format_flight_number(self, flight_number):
        """Format flight number by removing leading zeros"""
        airline_code = flight_number[:2]
        flight_digits = flight_number[2:].lstrip('0')
        return {'airline': airline_code, 'number': flight_digits}
    
    # Parse the text and return a list of flights.
    # Each flight is a dictionary with the following keys:
    # - airline, number: flight identifier
    # - depapt / arrapt: departure/arrival airports based on list_type & home_airport
    # - line: the original line
    # - row: the line number of the flight in the text.
    def get_flight_list(self, text):
        if not self.parse_jcsy_line(text):
            print("Could not parse JCSY line, cannot process flight list.")
            return []
            
        flights = []
        for i, line in enumerate(text.split('\n')): 
            # Skip header, comment, JCSY, or empty lines
            if line.startswith('JCSY:') or line.startswith('FLT/') or line.startswith('##') or not line.strip():
                continue
                
            parts = line.split()
            if len(parts) < 2:
                continue
                
            flight_number_str = parts[0].strip()
            if not re.match(r'^[A-Z0-9]{2,3}\d{1,4}$' , flight_number_str):
                print(f"Skipping invalid flight format on line {i+1}: {line}")
                continue
                
            flight_number = self.format_flight_number(flight_number_str)
            other_airport = parts[1].strip().lstrip('/')
            if not re.match(r'^[A-Z]{3}$' , other_airport):
                 print(f"Skipping invalid other airport on line {i+1}: {line}")
                 continue
                 
            flight_details = {
                'airline': flight_number['airline'],
                'number': flight_number['number'],
                'line': line,
                'row': i+1
            }
            
            # Assign airports based on list type and home airport
            if self.list_type == 'arrival':
                flight_details['depapt'] = other_airport # For arrivals, the listed airport is departure
                flight_details['arrapt'] = self.HOME_AIRPORT # Arrival is the home airport
            else: # departure list
                flight_details['depapt'] = self.HOME_AIRPORT # Departure is the home airport
                flight_details['arrapt'] = other_airport # For departures, the listed airport is arrival
                
            flights.append(flight_details)
        return flights

    def search_flight_info(self, a_flight:dict):
        """Main search function trying FlightView first, then FlightStats"""
        # Try FlightView first
        print(f"Searching FlightView for {a_flight['airline']}{a_flight['number']}...")
        result = self._search_with_provider(a_flight, use_flightview=True)
        if result['display_time'] != '----' or result['console_msg']:
            print(f"Found result on FlightView.")
            return result

        # Fallback to FlightStats
        print(f"No definitive result on FlightView, falling back to FlightStats for {a_flight['airline']}{a_flight['number']}...")
        result = self._search_with_provider(a_flight, use_flightview=False)
        if result['display_time'] != '----' or result['console_msg']:
            print(f"Found result on FlightStats.")
            return result
            
    def split_for_datetime(self, OrigStr:str, ViewOrStats:int, base_date_str: str) -> datetime:
        """Parse date and time string from FlightView or FlightStats"""
        # Check if OrigStr == "N/A"
        if OrigStr == "N/A":
            return None
            
        if ViewOrStats == 0:  # FlightView
            try:
                # FlightView format "07:08 AM"
                time_obj = datetime.strptime(OrigStr, "%I:%M %p")
                
                # Convert base_date_str YYYYMMDD to datetime
                base_date = datetime.strptime(base_date_str, "%Y%m%d")
                
                # Set the time on the base date
                result = base_date.replace(hour=time_obj.hour, minute=time_obj.minute)
                # print(f"Converted FlightView time {OrigStr} to {result}")
                return result
            except Exception as e:
                print(f"Error parsing FlightView time '{OrigStr}': {str(e)}")
                return None
                
        elif ViewOrStats == 1:  # FlightStats
            try:
                # FlightStats format: "2023-08-13T01:15:00.000" or "01:15"
                if 'T' in OrigStr:
                    # Already contains date information
                    result = datetime.strptime(OrigStr.split('.')[0], "%Y-%m-%dT%H:%M:%S")
                    # print(f"Converted FlightStats time {OrigStr} to {result}")
                    return result
                else:
                    # Time only format "01:15" - attach to base date
                    time_obj = datetime.strptime(OrigStr, "%H:%M")
                    
                    # Convert base_date_str YYYYMMDD to datetime
                    base_date = datetime.strptime(base_date_str, "%Y%m%d")
                    
                    # Set the time on the base date
                    result = base_date.replace(hour=time_obj.hour, minute=time_obj.minute)
                    # print(f"Converted FlightStats time {OrigStr} to {result}")
                    return result
            except Exception as e:
                print(f"Error parsing FlightStats time '{OrigStr}': {str(e)}")
                return None
        
        return None
            
    def _search_with_provider(self, a_flight:dict, use_flightview:bool):
        """Helper method to search for flight info using specified provider"""
        # Default empty response
        response = {'display_time': '----', 'is_yesterday': False, 'sta': None, 'ata': None, 'console_msg': None, 'snippet': None, 'date_str': None}
        
        try:
            # Get search date based on flight details
            date_str = self._get_search_date(a_flight)
            response['date_str'] = date_str
            
            if not date_str:
                return response
                
            if use_flightview:
                # Search with FlightView
                is_arrival = a_flight['arrapt'] == self.HOME_AIRPORT
                flight_info = self.flightview_crawler.get_flight_info(
                    a_flight['airline'], 
                    a_flight['number'],
                    date_str,
                    is_arrival
                )
            else:
                # Search with FlightStats
                flight_info = self.flightstats_crawler.get_flight_info(
                    a_flight['airline'], 
                    a_flight['number'],
                    date_str
                )
                
            # Process flight info
            if flight_info:
                response = self._process_flight_info(flight_info, date_str, use_flightview)
            else:
                response['console_msg'] = f"No flight info found for {a_flight['airline']}{a_flight['number']} on {date_str}"
                
            return response
        except Exception as e:
            print(f"Error in _search_with_provider: {str(e)}")
            response['console_msg'] = f"Error searching for flight: {str(e)}"
            return response
            
    def _process_flight_info(self, flight_info, date_str:str, use_flightview:bool):
        """Process flight info from FlightView or FlightStats"""
        # Default response
        response = {'display_time': '----', 'is_yesterday': False, 'sta': None, 'ata': None, 'console_msg': None, 'snippet': None, 'date_str': date_str}
        
        try:
            # For arrivals, we care about ATA
            # For departures, we care about ATD
            field_of_interest = 'arrival' if self.list_type == 'arrival' else 'departure'
            section = flight_info.get(field_of_interest, {})
            
            # Skip if no section found
            if not section:
                response['console_msg'] = f"No {field_of_interest} info found"
                return response
                
            # Get display info
            status = section.get('status', 'Unknown')
            response['snippet'] = status
            
            if use_flightview:
                # FlightView processing
                # Check if this is from a previous day
                flight_date = flight_info.get('date')
                if flight_date and flight_date != date_str:
                    # Different day flight
                    flight_date_obj = datetime.strptime(flight_date, "%Y%m%d")
                    search_date_obj = datetime.strptime(date_str, "%Y%m%d")
                    day_diff = (flight_date_obj - search_date_obj).days
                    
                    if day_diff != 0:
                        response['is_yesterday'] = True
                        response['console_msg'] = f"Flight is from {'previous' if day_diff < 0 else 'next'} day ({flight_date})"
                
                # Get times - scheduled and actual
                scheduled = section.get('scheduled')
                actual = section.get('actual')
                
                # Try to parse the times
                if scheduled and scheduled != "N/A":
                    sta_datetime = self.split_for_datetime(scheduled, 0, date_str) # 0 for FlightView
                    response['sta'] = sta_datetime
                    
                if actual and actual != "N/A":
                    ata_datetime = self.split_for_datetime(actual, 0, date_str) # 0 for FlightView
                    response['ata'] = ata_datetime
                    # Only use actual time for display if available
                    response['display_time'] = self._to_output_display_time(ata_datetime)
                elif scheduled and scheduled != "N/A":
                    # Fallback to scheduled time for display
                    response['display_time'] = self._to_output_display_time(response['sta'])
            else:
                # FlightStats processing
                # Check times
                scheduled = section.get('scheduled')
                actual = section.get('actual')
                estimated = section.get('estimated')
                
                # Check for day difference - not as reliable as FlightView
                status_lower = status.lower() if status else ""
                if "yesterday" in status_lower:
                    response['is_yesterday'] = True
                    response['console_msg'] = "Flight appears to be from yesterday (based on status)"
                    
                # Try to parse times
                if scheduled and scheduled != "N/A":
                    sta_datetime = self.split_for_datetime(scheduled, 1, date_str) # 1 for FlightStats
                    response['sta'] = sta_datetime
                    
                if actual and actual != "N/A":
                    ata_datetime = self.split_for_datetime(actual, 1, date_str) # 1 for FlightStats
                    response['ata'] = ata_datetime
                    # Only use actual time for display if available
                    response['display_time'] = self._to_output_display_time(ata_datetime)
                elif estimated and estimated != "N/A" and ("Estimated" in status or "Expected" in status):
                    # Use estimated time if available and flight not arrived/departed yet
                    estimated_datetime = self.split_for_datetime(estimated, 1, date_str) # 1 for FlightStats
                    response['display_time'] = self._to_output_display_time(estimated_datetime)
                elif scheduled and scheduled != "N/A":
                    # Fallback to scheduled time
                    response['display_time'] = self._to_output_display_time(response['sta'])
            
            return response
        except Exception as e:
            print(f"Error processing flight info: {str(e)}")
            response['console_msg'] = f"Error processing flight info: {str(e)}"
            return response
            
    def _to_output_display_time(self, dt):
        """Convert datetime to display string (HH:MM)"""
        if not dt:
            return '----'
        return dt.strftime('%H:%M')
        
    def _get_search_date(self, a_flight:dict):
        """Determine the appropriate search date based on flight details"""
        if not self.flightview_date:
            return None
            
        # Default to the date from the JCSY line
        search_date = self.flightview_date
        
        try:
            # Check if we need to adjust the date based on flight direction
            if not self.jcsy_departure_time or not self.jcsy_arrival_time:
                # Not enough info to adjust, use default date
                return search_date
                
            # Calculate if this flight is before or after the main JCSY flight
            main_time = self.jcsy_departure_time
            if self.list_type == 'arrival':
                main_time = self.jcsy_arrival_time
                
            # Convert to date objects for comparison
            main_date = datetime.strptime(self.flightview_date, "%Y%m%d")
            
            # Default return the main date
            return main_date.strftime("%Y%m%d")
        except Exception as e:
            print(f"Error determining search date: {str(e)}")
            return search_date 