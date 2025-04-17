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
        
        # Standardized return structure used by search methods
        self.search_result = {
            'ata': None,  # datetime object
            'sta': None,  # datetime object
            'snippet': None,  # Flight status text
            'is_yesterday': False  # Flag to indicate if the flight is yesterday's
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
                        
                        # No longer parsing airport from parts[2]
                        
                        print(f"Parsed JCSY ({self.list_type} list): Date={self.flightview_date}, Main Flight={self.jcsy_flight['airline']}{self.jcsy_flight['number']}, Home Airport={self.HOME_AIRPORT}")
                        
                        return True # Successfully parsed JCSY line
            # If loop completes without finding JCSY line
            raise ValueError("JCSY line not found or invalid format (Requires at least JCSY:FLT/DATE)")
        except Exception as e:
            print(f"Error parsing JCSY line: {str(e)}")
            self.flightview_date = None
            self.jcsy_flight = {}
            return False
    
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

    # Search flight using flightview_crawler.
    # Return a dictionary with the standardized search_result structure.
    def flightview_search(self, a_flight:dict):
        """Search flight using FlightView"""
        self._reset_search_result()
        
        # Check if date and configured home airport are set
        if not self.flightview_date or not self.HOME_AIRPORT:
             print("Flight date or Home Airport not set. Cannot search FlightView.")
             return self.search_result
             
        # Determine required arrapt and optional depapt for the FlightView query
        query_arrapt = a_flight.get('arrapt') # Should be set correctly in get_flight_list
        query_depapt = a_flight.get('depapt') # Use depapt if available in a_flight
        
        if not query_arrapt:
             # This case should ideally not happen if get_flight_list worked
             print(f"Arrival airport missing for flight {a_flight['airline']}{a_flight['number']}. Cannot search FlightView.")
             return self.search_result
             
        try:
            # Try current date first
            result_today = self._try_date_search(a_flight, self.flightview_date, query_arrapt, depapt=query_depapt)
            
            if result_today: 
                return result_today # Found on specified date

            # If not found today, try yesterday's date
            print(f"Flight {a_flight['airline']}{a_flight['number']} not found for {self.flightview_date} on FlightView, trying yesterday...")
            yesterday = (datetime.strptime(self.flightview_date, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
            result_yesterday = self._try_date_search(a_flight, yesterday, query_arrapt, depapt=query_depapt)
            
            if result_yesterday:
                self.search_result['is_yesterday'] = True
                return self.search_result

            # If not found on either date
            print(f"Flight {a_flight['airline']}{a_flight['number']} not found on FlightView for {self.flightview_date} or yesterday.")
            return self.search_result
            
        except Exception as e:
            print(f"FlightView search error for {a_flight['airline']}{a_flight['number']}: {str(e)}")
            return self.search_result

    def _try_date_search(self, a_flight:dict, search_date:str, arrival_airport:str, depapt=None):
        """Helper function to search flight with specific date, arrival, and optional departure airport"""
        try:
            flight_info = self.flightview_crawler.get_flight_info(
                a_flight['airline'],
                a_flight['number'],
                search_date,
                arrapt=arrival_airport, # Pass required arrival airport
                depapt=depapt          # Pass departure if available
            )
            
            # Reset result for this specific date attempt
            current_search_result = {'ata': None, 'sta': None, 'snippet': None, 'is_yesterday': False}
            
            if flight_info and flight_info.get('arrival'):
                arr_info = flight_info['arrival']
                current_search_result['snippet'] = flight_info.get('status')
                
                get_sta = arr_info.get('scheduled')
                if get_sta and get_sta != "N/A":
                    current_search_result['sta'] = self.split_for_datetime(get_sta, 0, search_date)
                
                get_ata = arr_info.get('actual')
                if not get_ata or get_ata == "N/A":
                    get_ata = arr_info.get('estimated')
                    
                if get_ata and get_ata != "N/A":
                     current_search_result['ata'] = self.split_for_datetime(get_ata, 0, search_date)
                     
                # If we found at least STA or ATA, update the main search result and return it
                if current_search_result['sta'] or current_search_result['ata']:
                    self.search_result.update(current_search_result) # Update the instance result
                    return self.search_result
                    
            return None
            
        except Exception as e:
            print(f"FlightView date search error for {a_flight['airline']}{a_flight['number']} on {search_date}: {str(e)}")
            return None

    # Param ViewOrStats notifies which format of the original string.
    # 0: 12:34AM,DEC11 from FlightView
    # 1: 10:35 PDT from FlightStats (ignoring timezone)
    # Param base_date_str is needed for context, esp. for ViewOrStats=0
    def split_for_datetime(self, OrigStr:str, ViewOrStats:int, base_date_str: str) -> datetime:
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
                # This might need refinement depending on edge cases
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

    # Search flight using FlightStats.
    # Return a dictionary with the standardized search_result structure.
    def flightstats_search(self, a_flight:dict):
        """Search flight using FlightStats"""
        self._reset_search_result()
        
        if not self.flightview_date:
             print("Flight date not set. Cannot search FlightStats.")
             return self.search_result

        # FlightStats search doesn't use depapt in its current implementation
        # query_depapt = a_flight.get('depapt') 

        try:
            # Try current date first
            flight_info = self.flightstats_crawler.get_flight_info(
                a_flight['airline'],
                a_flight['number'],
                self.flightview_date
                # depapt=query_depapt # Removed - not accepted by flightstats_crawler
            )
            
            if self._process_flightstats_info(flight_info, self.flightview_date):
                return self.search_result
            
            # Try yesterday's date if no result
            print(f"Flight {a_flight['airline']}{a_flight['number']} not found for {self.flightview_date} on FlightStats, trying yesterday...")
            yesterday = (datetime.strptime(self.flightview_date, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
            yesterday_info = self.flightstats_crawler.get_flight_info(
                a_flight['airline'],
                a_flight['number'],
                yesterday
                # depapt=query_depapt # Removed - not accepted by flightstats_crawler
            )
            
            if self._process_flightstats_info(yesterday_info, yesterday):
                self.search_result['is_yesterday'] = True
                return self.search_result
            
            print(f"Flight {a_flight['airline']}{a_flight['number']} not found on FlightStats for {self.flightview_date} or yesterday.")
            return self.search_result
            
        except Exception as e:
            print(f"FlightStats search error for {a_flight['airline']}{a_flight['number']}: {str(e)}")
            return self.search_result

    def _process_flightstats_info(self, flight_info, date_str):
        """Helper to process flight stats info and populate search_result"""
        if flight_info:
            # FlightStats doesn't reliably provide status, so we don't store snippet from it
            # self.search_result['snippet'] = flight_info.get('status') 
            
            arr_info = flight_info.get('arrival', {})
            
            sta = arr_info.get('scheduled')
            if sta and sta != 'N/A':
                self.search_result['sta'] = self.split_for_datetime(sta, 1, date_str)
            
            ata = arr_info.get('actual')
            if not ata or ata == 'N/A':
                ata = arr_info.get('estimated') # Fallback to estimated
            
            if ata and ata != 'N/A':
                self.search_result['ata'] = self.split_for_datetime(ata, 1, date_str)
            
            # Return True if we found either time
            if self.search_result['sta'] or self.search_result['ata']:
                return True
        return False
        
    def _reset_search_result(self):
        """Resets the search result structure"""
        self.search_result = {
            'ata': None, 
            'sta': None, 
            'snippet': None, 
            'is_yesterday': False
        }

    # Return search_result.
    def search_flight_info(self, a_flight:dict):
        """Main search function trying FlightView first, then FlightStats"""
        self._reset_search_result()
        
        # Try FlightView first
        print(f"Searching FlightView for {a_flight['airline']}{a_flight['number']}...")
        view_result = self.flightview_search(a_flight)
        # Check if view_result is not None and has valid times
        if view_result and (view_result.get('sta') or view_result.get('ata')):
             print(f"Found result on FlightView.")
             return view_result

        # Fallback to FlightStats
        print(f"No definitive result on FlightView, falling back to FlightStats for {a_flight['airline']}{a_flight['number']}...")
        stats_result = self.flightstats_search(a_flight)
        # Check if stats_result is not None and has valid times
        if stats_result and (stats_result.get('sta') or stats_result.get('ata')):
             print(f"Found result on FlightStats.")
             return stats_result
            
        # If no results found from either
        print(f"No information found for {a_flight['airline']}{a_flight['number']} on either service.")
        return self.search_result # Return empty (reset) result

    # This method seems unused and might be deprecated/incorrect
    # def set_4digit_time(self, time_str):
    #     """Return a datetime object with the current flight date and 24 hour time"""
    #     from datetime import datetime
    #     time_24_plus_date = time_str[:2]+':'+time_str[2:] + ',' + self.flightview_date
    #     return datetime.strptime(time_24_plus_date, '%H:%M,%Y%m%d') if time_24_plus_date else None
