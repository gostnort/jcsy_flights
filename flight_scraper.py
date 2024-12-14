import re
from datetime import datetime
from googleapiclient.discovery import build
from flightview_crawler import FlightViewScraper
from datetime import datetime, timedelta

class FlightScraper:
    def __init__(self):
        # FlightView related
        self.flightview_scraper = FlightViewScraper()
        self.flightview_date = None
        
        # FlightAware related (Google Search)
        self.flightaware_api_key = "AIzaSyB6VOIk0l6xKGKKmhuaQF8mmduyBk1d5jg"
        self.flightaware_search_id = "21d9e739fcf6c4bdc"
        self.flightaware_service = build("customsearch", "v1", developerKey=self.flightaware_api_key)
        
        # Standardized return structure
        self.search_result = {
            'ata': None,  # datetime object
            'sta': None,  # datetime object
            'snippet': None  # FlightAware snippet text
        }
    
    # Return the flight date in YYYYMMDD format from the JCSY line.
    # Examples:
    # JCSY:CA0984/11DEC24/LAX,I -> 20241211
    # JCSY:CA0984/11DEC/LAX,I -> {current_year}1211
    def parse_flight_date(self, text):
        """Parse date from JCSY line for FlightView format"""
        try:
            for line in text.split('\n'):
                if line.startswith('JCSY:'):
                    parts = line.split('/')
                    if len(parts) >= 2:
                        date_part = parts[1]  # "11DEC" or "11DEC24"
                        
                        if len(date_part) > 5:  # Has year
                            date_obj = datetime.strptime(date_part, "%d%b%y")
                            year = 2000 + date_obj.year % 100
                        else:
                            date_obj = datetime.strptime(date_part, "%d%b")
                            year = datetime.now().year
                        
                        self.flightview_date = date_obj.replace(year=year).strftime("%Y%m%d")
                        return self.flightview_date
            return None
        except Exception as e:
            print(f"Error parsing flight date: {str(e)}")
            return None
    
    # Format flight number by removing leading zeros.
    # Examples:
    # AM0782 -> AM782
    # UA0023 -> UA23
    def format_flight_number(self, flight_number):
        """Format flight number by removing leading zeros"""
        airline_code = flight_number[:2]
        flight_digits = flight_number[2:].lstrip('0')
        return f"{airline_code}{flight_digits}"
    
    # Parse the JCSY line and return a list of flights.
    # Each flight is a dictionary with the following keys:
    # - number: the flight number
    # - depapt: the departure airport
    # - line: the original JCSY line
    # - index: the index of the flight in the list
    def get_flight_list(self, text):
        self.parse_flight_date(text)
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
                'number': flight_number,
                'depapt': depapt,
                'line': line,
                'index': i
            })
            
        return flights

    # Search flight using flightview_crawler.
    # Return a dictionary with the following keys:
    # - ata: the actual arrival time
    # - sta: the scheduled arrival time
    def flightview_search(self, flight_number, depapt):
        """Search flight using FlightView"""
        try:
            airline = flight_number[:2]
            flight_num = flight_number[2:]
            flight_info = self.flightview_scraper.get_flight_info(
                airline, flight_num, self.flightview_date, depapt
            )
            if flight_info and flight_info.get('arrival'):
                arr_info = flight_info['arrival']
                if arr_info.get('scheduled') != "N/A" or arr_info.get('actual') != "N/A":
                    get_ata = arr_info.get('actual')
                    self.search_result['ata'] = self.split_for_datetime(get_ata, 0) if get_ata != "N/A" else None
                    get_sta = arr_info.get('scheduled')
                    self.search_result['sta'] = self.split_for_datetime(get_sta, 0) if get_sta != "N/A" else None
                    self.search_result['snippet'] = None  # FlightView doesn't use snippet
                    return self.search_result
            self.search_result = {'ata': None, 'sta': None, 'snippet': None}
            return None
        except Exception as e:
            print(f"FlightView error for {flight_number}: {str(e)}")
            self.search_result = {'ata': None, 'sta': None, 'snippet': None}
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
    def flightaware_search(self, flight_number):
        """Search flight using FlightAware (via Google)"""
        try:
            query = f"site:flightaware.com {flight_number} LAX \"Landing\" \"Gate Arrival\""
            result = self.flightaware_service.cse().list(
                q=query,
                cx=self.flightaware_search_id,
                num=1
            ).execute()

            if 'items' in result:
                return self.flightaware_extract_times(result['items'][0])
            self.search_result = {'ata': None, 'sta': None, 'snippet': None}
            return None
        except Exception as e:
            print(f"FlightAware error for {flight_number}: {str(e)}")
            self.search_result = {'ata': None, 'sta': None, 'snippet': None}
            return None
    
    # Extract times from FlightAware search result.
    # Return a dictionary with the following keys:
    # - ata: the actual arrival time
    # - sta: the scheduled arrival time
    def flightaware_extract_times(self, search_result):
        """Extract times from FlightAware search result"""
        if not search_result:
            self.search_result = {'ata': None, 'sta': None, 'snippet': None}
            return None

        snippet = search_result.get('snippet', '')
        # Store the snippet in search_result
        self.search_result['snippet'] = snippet
        
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

    def search_flight_info(self, flight_number, origin):
        """Main search function trying FlightView first, then FlightAware"""
        # Reset search result
        self.search_result = {'ata': None, 'sta': None, 'snippet': None}
        
        # Try FlightView first
        result = self.flightview_search(flight_number, origin)
        if result:
            return result

        # Fallback to FlightAware
        print(f"Falling back to FlightAware for {flight_number}")
        return self.flightaware_search(flight_number)
