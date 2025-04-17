import re
from datetime import datetime
from flightview_crawler import FlightViewScraper
from flightstats_crawler import FlightStatsScraper
from datetime import datetime, timedelta

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
            
        print(f"No information found for {a_flight['airline']}{a_flight['number']}")
        return result

    def split_for_datetime(self, OrigStr:str, ViewOrStats:int, base_date_str: str) -> datetime:
        """Parse datetime string from different formats
        ViewOrStats: 0 for FlightView (12:34AM,DEC11), 1 for FlightStats (10:35 PDT)
        """
        if not OrigStr or OrigStr == 'N/A':
            return None
            
        base_date_obj = datetime.strptime(base_date_str, "%Y%m%d")
        year = base_date_obj.year
        
        try:
            if ViewOrStats == 0:
                time_part, date_part = OrigStr.split(',')
                full_date_str = f"{date_part},{year}"
                temp_date = datetime.strptime(full_date_str, "%b%d,%Y")
                # Simple check for year wrap: if parsed date is much earlier than base date
                if (base_date_obj - temp_date).days > 180: 
                   year += 1
                   full_date_str = f"{date_part},{year}" 
                # If parsed date is much later than base date
                elif (temp_date - base_date_obj).days > 180:
                    year -= 1
                    full_date_str = f"{date_part},{year}"
                   
                datetime_str = f"{time_part},{full_date_str}"
                result = datetime.strptime(datetime_str, "%I:%M%p,%b%d,%Y")
            
            elif ViewOrStats == 1:
                time_str = OrigStr.split()[0] if ' ' in OrigStr else OrigStr
                time_obj = datetime.strptime(time_str, "%H:%M")
                result = base_date_obj.replace(hour=time_obj.hour, minute=time_obj.minute, second=0, microsecond=0)
            
            return result
        except Exception as e:
             print(f"Error parsing datetime string '{OrigStr}' with format {ViewOrStats} for date {base_date_str}: {e}")
             return None

    def _search_with_provider(self, a_flight:dict, use_flightview:bool):
        """Search flight using specified provider and handle date adjustments"""
        try:
            if not self.flightview_date or (use_flightview and not self.HOME_AIRPORT):
                print("Required parameters not set.")
                return {'display_time': '----', 'console_msg': None, 'sta': None, 'ata': None, 'std': None, 'atd': None}

            # Get flight info for current date
            try:
                if use_flightview:
                    flight_info = self.flightview_crawler.get_flight_info(
                        a_flight['airline'],
                        a_flight['number'],
                        self.flightview_date,
                        arrapt=a_flight.get('arrapt'),
                        depapt=a_flight.get('depapt')
                    )
                else:
                    flight_info = self.flightstats_crawler.get_flight_info(
                        a_flight['airline'],
                        a_flight['number'],
                        self.flightview_date
                    )
            except Exception as e:
                if use_flightview:
                    print(f"FlightView error, will try FlightStats: {str(e)}")
                    return {'display_time': '----', 'console_msg': str(e), 'sta': None, 'ata': None, 'std': None, 'atd': None}
                else:
                    print(f"FlightStats error: {str(e)}")
                    return {'display_time': '----', 'console_msg': f"Error: {str(e)}", 'sta': None, 'ata': None, 'std': None, 'atd': None}

            result = self._process_flight_info(flight_info, self.flightview_date, use_flightview)
            if result['display_time'] != '----' or result['console_msg']:
                return result

            # If no result found, check if we need to search on a different date
            search_date = self._get_search_date(a_flight)
            if search_date and search_date != self.flightview_date:
                print(f"Trying search on {search_date}...")
                try:
                    if use_flightview:
                        flight_info = self.flightview_crawler.get_flight_info(
                            a_flight['airline'],
                            a_flight['number'],
                            search_date,
                            arrapt=a_flight.get('arrapt'),
                            depapt=a_flight.get('depapt')
                        )
                    else:
                        flight_info = self.flightstats_crawler.get_flight_info(
                            a_flight['airline'],
                            a_flight['number'],
                            search_date
                        )
                except Exception as e:
                    if use_flightview:
                        print(f"FlightView error on alternative date, will try FlightStats: {str(e)}")
                        return {'display_time': '----', 'console_msg': str(e), 'sta': None, 'ata': None, 'std': None, 'atd': None}
                    else:
                        print(f"FlightStats error on alternative date: {str(e)}")
                        return {'display_time': '----', 'console_msg': f"Error: {str(e)}", 'sta': None, 'ata': None, 'std': None, 'atd': None}
                        
                return self._process_flight_info(flight_info, search_date, use_flightview)

            return result

        except Exception as e:
            print(f"Search error: {str(e)}")
            return {'display_time': '----', 'console_msg': f"Error: {str(e)}", 'sta': None, 'ata': None, 'std': None, 'atd': None}

    def _process_flight_info(self, flight_info, date_str:str, use_flightview:bool):
        """Process flight info from either provider and return standardized result"""
        result = {
            'display_time': '----',  # Default display time
            'console_msg': None,     # Console message for UI label
            'sta': None,             # Keep original times for comparison
            'ata': None,
            'std': None,
            'atd': None,
            'is_another_day': 0      # -1 for yesterday, +1 for tomorrow
        }
        
        if not flight_info:
            result['console_msg'] = "No flight information available"
            return result
            
        # Store status message if available
        if use_flightview and flight_info.get('status'):
            result['console_msg'] = flight_info.get('status')
            
        # Process arrival times
        if flight_info.get('arrival'):
            arr_info = flight_info['arrival']
            
            sta = arr_info.get('scheduled')
            if sta and sta != "N/A":
                result['sta'] = self.split_for_datetime(sta, 0 if use_flightview else 1, date_str)
                print(f"STA parsed: {result['sta']}")  # Debug log
                
            ata = arr_info.get('actual')
            if not ata or ata == "N/A":
                ata = arr_info.get('estimated')
            if ata and ata != "N/A":
                result['ata'] = self.split_for_datetime(ata, 0 if use_flightview else 1, date_str)
                print(f"ATA parsed: {result['ata']}")  # Debug log
                
        # Process departure times
        if flight_info.get('departure'):
            dep_info = flight_info['departure']
            
            std = dep_info.get('scheduled')
            if std and std != "N/A":
                result['std'] = self.split_for_datetime(std, 0 if use_flightview else 1, date_str)
                print(f"STD parsed: {result['std']}")  # Debug log
                
            atd = dep_info.get('actual')
            if not atd or atd == "N/A":
                atd = dep_info.get('estimated')
            if atd and atd != "N/A":
                result['atd'] = self.split_for_datetime(atd, 0 if use_flightview else 1, date_str)
                print(f"ATD parsed: {result['atd']}")  # Debug log
        
        # Format display time based on list type
        if self.list_type == 'arrival':
            if result['ata']:
                base_time = self._to_output_display_time(result['ata'])
                # Add 'd' prefix if delayed
                if result['sta'] and result['ata'] > result['sta']:
                    print(f"Flight is delayed: ATA {result['ata']} > STA {result['sta']}")
                    base_time = 'd' + base_time
                # Get alternative day info
                if result['sta']:
                    base_date = datetime.strptime(date_str, "%Y%m%d").date()
                    sta_date = result['sta'].date()
                    if sta_date < base_date:
                        result['is_another_day'] = -1
                        base_time += '-'
                    elif sta_date > base_date:
                        result['is_another_day'] = 1
                        base_time += '+'
                result['display_time'] = base_time
        else:  # departure
            if result['atd']:
                base_time = self._to_output_display_time(result['atd'])
                # Add 'd' prefix if delayed
                if result['std'] and result['atd'] > result['std']:
                    print(f"Flight is delayed: ATD {result['atd']} > STD {result['std']}")
                    base_time = 'd' + base_time
                # Get alternative day info
                if result['std']:
                    base_date = datetime.strptime(date_str, "%Y%m%d").date()
                    std_date = result['std'].date()
                    if std_date < base_date:
                        result['is_another_day'] = -1
                        base_time += '-'
                    elif std_date > base_date:
                        result['is_another_day'] = 1
                        base_time += '+'
                result['display_time'] = base_time
            elif result['std']:
                base_time = self._to_output_display_time(result['std']) + '*'
                # Get alternative day info for STD
                base_date = datetime.strptime(date_str, "%Y%m%d").date()
                std_date = result['std'].date()
                if std_date < base_date:
                    result['is_another_day'] = -1
                    base_time += '-'
                elif std_date > base_date:
                    result['is_another_day'] = 1
                    base_time += '+'
                result['display_time'] = base_time
                
        return result
        
    def _to_output_display_time(self, dt):
        """Format datetime into display string"""
        if not dt:
            return '----'
        return dt.strftime("%H%M")

    def _get_search_date(self, a_flight:dict):
        """Determine if we need to search on a different date"""
        try:
            # Need main flight times for comparison
            if not self.jcsy_departure_time or (self.list_type == 'departure' and not self.jcsy_arrival_time):
                return self.flightview_date

            # Get flight departure time
            flight_info = self.flightstats_crawler.get_flight_info(
                a_flight['airline'],
                a_flight['number'],
                self.flightview_date
            )
            
            if not flight_info or not flight_info.get('departure'):
                return self.flightview_date
                
            dep_time_str = flight_info['departure'].get('scheduled')
            if not dep_time_str or dep_time_str == "N/A":
                return self.flightview_date
                
            flight_dep_time = self.split_for_datetime(dep_time_str, 1, self.flightview_date)
            if not flight_dep_time:
                return self.flightview_date
            
            base_date = datetime.strptime(self.flightview_date, "%Y%m%d")
            
            if self.list_type == 'arrival':
                # For arrivals: check departure time difference
                if flight_dep_time > self.jcsy_departure_time:
                    return (base_date - timedelta(days=1)).strftime("%Y%m%d")
            else:
                # For departures: check against arrival time
                if flight_dep_time < self.jcsy_arrival_time:
                    return (base_date + timedelta(days=1)).strftime("%Y%m%d")
                    
            return self.flightview_date
                    
        except Exception as e:
            print(f"Error determining search date: {str(e)}")
            return self.flightview_date

