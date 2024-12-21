import re
from datetime import datetime
from googleapiclient.discovery import build
from flightview_crawler import FlightViewScraper
from datetime import datetime, timedelta

class FlightScraper:
    def __init__(self):
        # FlightView related
        self.flightview_crawler = FlightViewScraper()
        self.flightview_date = None
        self.jcsy_flight = {}
        
        # FlightAware related (Google Search)
        self.flightaware_api_key = "AIzaSyB6VOIk0l6xKGKKmhuaQF8mmduyBk1d5jg"
        self.flightaware_search_id = "21d9e739fcf6c4bdc"
        self.flightaware_service = build("customsearch", "v1", developerKey=self.flightaware_api_key)
        
        # Standardized return structure
        self.search_result = {
            'ata': None,  # datetime object
            'sta': None,  # datetime object
            'snippet': None,  # FlightAware snippet text
            'is_yesterday': False  # Flag to indicate if the flight is yesterday's
        }
    
    # Processing the JCSY line and extract flight info.
    # Get the flightview_date and jcsy_flight from 'JCSY:CA0984/11DEC24/LAX,I'
    # To datetime object is 20241211 and jcsy_flight is {'airline': 'CA', 'number': '984'}
    def parse_jcsy_line(self, text):
        """Parse date and JCSY flight info from JCSY line"""
        try:
            for line in text.split('\n'):
                if line.startswith('JCSY:'):
                    parts = line.split('/')
                    if len(parts) >= 2:
                        # Get flight info from first part
                        section_1 = parts[0]  # "JCSY:CA0984"
                        flight_number = re.match(r'JCSY:(\w+)', section_1).group(1)
                        self.jcsy_flight = self.format_flight_number(flight_number)
                        
                        # Get date from second part
                        date_part = parts[1]  # "11DEC" or "11DEC24"
                        if len(date_part) > 5:  # Has year
                            date_obj = datetime.strptime(date_part, "%d%b%y")
                            year = 2000 + date_obj.year % 100
                        else:
                            date_obj = datetime.strptime(date_part, "%d%b")
                            year = datetime.now().year
                        
                        self.flightview_date = date_obj.replace(year=year).strftime("%Y%m%d")
                        self.jcsy_flight['departure'] = re.match(r'[A-Z]+', parts[2]).group(0) if len(parts) > 2 else None  # 'LAX' if available
                        # Get JCSY flight scheduled departure time
                        jcsy_info = self.flightview_crawler.get_flight_info(
                            self.jcsy_flight['airline'],
                            self.jcsy_flight['number'],
                            self.flightview_date,
                            depapt=self.jcsy_flight['departure']
                        )
                        if jcsy_info and jcsy_info['departure']['scheduled'] != "N/A":
                            self.jcsy_flight['std'] = jcsy_info['departure']['scheduled']
                            self.jcsy_flight['std'] = self.split_for_datetime(self.jcsy_flight['std'], 0)
                        else:
                            # Signal that we need manual input
                            raise ValueError("Could not get JCSY flight departure time automatically")
                        return None
        except Exception as e:
            print(f"Error parsing flight date: {str(e)}")
            return None
    
    # Format flight number by removing leading zeros.
    # Examples:
    # AM0782 -> {'airline': 'AM', 'number': '782'}
    # UA0023 -> {'airline': 'UA', 'number': '23'}
    def format_flight_number(self, flight_number):
        """Format flight number by removing leading zeros"""
        airline_code = flight_number[:2]
        flight_digits = flight_number[2:].lstrip('0')
        return {'airline': airline_code, 'number': flight_digits}
    
    # Parse the JCSY line and return a list of flights.
    # Each flight is a dictionary with the following keys:
    # - number: the flight number
    # - depapt: the departure airport
    # - line: the original JCSY line
    # - row: the line number of the flight in the JCSY.
    def get_flight_list(self, text):
        self.parse_jcsy_line(text)
        if not self.flightview_date:
            print("Could not determine flight date")
            return []
            
        flights = []
        for i, line in enumerate(text.split('\n')):
            if line.startswith('JCSY:') or line.startswith('FLT/') or line.startswith('##') or not line.strip():
                continue
                
            parts = line.split()
            if len(parts) < 2:
                continue
                
            flight_number = self.format_flight_number(parts[0].strip())
            depapt = parts[1].strip().lstrip('/')
            flights.append({
                'airline': flight_number['airline'],
                'number': flight_number['number'],
                'depapt': depapt,
                'line': line,
                'row': i+1
            })
        return flights

    # Search flight using flightview_crawler.
    # Return a dictionary with the following keys:
    # - ata: the actual arrival time
    # - sta: the scheduled arrival time
    def flightview_search(self, a_flight:dict):
        """Search flight using FlightView"""
        try:
            # Try current date first
            result = self._try_date_search(a_flight, self.flightview_date)
            if result == None:
                result = self._try_date_search(a_flight, self.flightview_date,depapt=a_flight['depapt'])  
            if result and result['sta']:  # Need to check if result exists and has sta
                if self.jcsy_flight['std'] < result['sta']:
                    yesterday = (datetime.strptime(self.flightview_date, "%Y%m%d") - timedelta(days=1)).strftime("%Y%m%d")
                    result = self._try_date_search(a_flight, yesterday)
                    if result:
                        self.search_result['is_yesterday'] = True  # Mark as yesterday's flight
                        return self.search_result
                else:
                    return result

            self.search_result = {'ata': None, 'sta': None, 'snippet': None, 'is_yesterday': False}
            return None
        except Exception as e:
            print(f"FlightView error for {a_flight['airline']}{a_flight['number']}: {str(e)}")
            self.search_result = {'ata': None, 'sta': None, 'snippet': None, 'is_yesterday': False}
            return None

    def _try_date_search(self, a_flight:dict, search_date:str,depapt=None):
        """Helper function to search flight with specific date"""
        try:
            flight_info = self.flightview_crawler.get_flight_info(
                a_flight['airline'],
                a_flight['number'],
                search_date,
                depapt=depapt
            )
            if flight_info and flight_info.get('arrival'):
                arr_info = flight_info['arrival']
                if arr_info.get('scheduled') != "N/A":
                    get_ata = arr_info.get('actual')
                    if get_ata == "N/A":  # If no actual time, try estimated
                        get_ata = arr_info.get('estimated')
                    self.search_result['ata'] = self.split_for_datetime(get_ata, 0) if get_ata != "N/A" else None
                    get_sta = arr_info.get('scheduled')
                    self.search_result['sta'] = self.split_for_datetime(get_sta, 0) if get_sta != "N/A" else None
                    self.search_result['snippet'] = None
                    self.search_result['is_yesterday'] = False
                    return self.search_result
            return None
        except Exception as e:
            print(f"FlightView date search error for {a_flight['airline']}{a_flight['number']}: {str(e)}")
            return None

    # Param is notifing which format of the original string.
    # 0: 12:34AM,DEC11 from FlightView
    # 1: '12:34AM' or '12:34AM +1' from FlightAware
    def split_for_datetime(self,OrigStr:str,ViewOrAware:int) -> datetime:
        if ViewOrAware == 0:
            # 12:34AM,DEC11 -> 12:34AM,DEC11,2024 -> datetime_obj
            result = datetime.strptime(OrigStr + ',' + self.flightview_date[0:4], "%I:%M%p,%b%d,%Y")
        elif ViewOrAware == 1:
            if OrigStr[-1].isdigit():
                # 12:34AM +1 -> 12:34AM,20241211 -> datetime_obj + N day
                time_str = OrigStr[0:7]
                result = datetime.strptime(time_str + ',' + self.flightview_date, "%I:%M%p,%Y%m%d")
                day_diff = int(OrigStr[-1])
                result += timedelta(days=day_diff)
            else:
                # 12:34AM -> 12:34AM,20241211 -> datetime_obj
                result = datetime.strptime(OrigStr + ',' + self.flightview_date, "%I:%M%p,%Y%m%d")
        return result


    # Search flight using FlightAware (via Google).
    # Return a dictionary with the following keys:
    # - ata: the actual arrival time
    # - sta: the scheduled arrival time
    def flightaware_search(self, a_flight:dict):
        """Search flight using FlightAware (via Google)"""
        try:
            full_number = f"{a_flight['airline']}{a_flight['number']}"
            query = f"site:flightaware.com {full_number} LAX \"Landing\" \"Gate Arrival\""
            result = self.flightaware_service.cse().list(
                q=query,
                cx=self.flightaware_search_id,
                num=1
            ).execute()

            if 'items' in result:
                return self.flightaware_extract_times(result['items'][0])
            self.search_result = {'ata': None, 'sta': None, 'snippet': None, 'is_yesterday': False}
            return None
        except Exception as e:
            print(f"FlightAware error for {a_flight['airline']}{a_flight['number']}: {str(e)}")
            self.search_result = {'ata': None, 'sta': None, 'snippet': None, 'is_yesterday': False}
            return None
    
    # Extract times from FlightAware search result.
    # Return a dictionary with the following keys:
    # - ata: the actual arrival time
    # - sta: the scheduled arrival time
    def flightaware_extract_times(self, search_result):
        """Extract times from FlightAware search result"""
        if not search_result:
            self.search_result = {'ata': None, 'sta': None, 'snippet': None, 'is_yesterday': False}
            return None

        snippet = search_result.get('snippet', '')
        # Store the snippet in search_result
        self.search_result['snippet'] = snippet
        self.search_result['is_yesterday'] = False  # FlightAware results are always current date
        
        # Extract ATA (Landing time) with possible day offset
        ata_match = re.search(r'Landing\.\s+(\d{1,2}:\d{2}(?:AM|PM))\s+PST(?:\s+\(([+]\d+)\))?', snippet)
        if ata_match:
            time_str = ata_match.group(1).strip()
            if ata_match.group(2):  # If day offset exists
                time_str += " " + ata_match.group(2)  # Add offset to time string
            self.search_result['ata'] = self.split_for_datetime(time_str, 1)
            
        # Extract STA (Scheduled time) with possible day offset
        sta_match = re.search(r'Scheduled\s+(\d{1,2}:\d{2}(?:AM|PM))\s+PST(?:\s+\(([+]\d+)\))?', snippet)
        if sta_match:
            time_str = sta_match.group(1).strip()
            if sta_match.group(2):  # If day offset exists
                time_str += " " + sta_match.group(2)  # Add offset to time string
            self.search_result['sta'] = self.split_for_datetime(time_str, 1)
            
        return self.search_result if (self.search_result['ata'] or self.search_result['sta']) else None

    # Return search_result.
    def search_flight_info(self, a_flight:dict):
        """Main search function trying FlightView first, then FlightAware"""
        # Reset search result
        self.search_result = {'ata': None, 'sta': None, 'snippet': None, 'is_yesterday': False}
        
        # Try FlightView first
        result = self.flightview_search(a_flight)
        if result:
            return result

        # Fallback to FlightAware
        print(f"Falling back to FlightAware for {a_flight['airline']}{a_flight['number']}")
        result = self.flightaware_search(a_flight)
        if result:
            return result
            
        # If no results found, return empty search_result instead of None
        return self.search_result

    def set_4digit_time(self, time_str):
        """Return a datetime object with the current flight date and 24 hour time"""
        from datetime import datetime
        time_24_plus_date = time_str[:2]+':'+time_str[2:] + ',' + self.flightview_date
        return datetime.strptime(time_24_plus_date, '%H:%M,%Y%m%d') if time_24_plus_date else None
