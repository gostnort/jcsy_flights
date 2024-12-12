import re
from datetime import datetime
from googleapiclient.discovery import build

class FlightScraper:
    def __init__(self):
        """
        Initialize with Google Custom Search API credentials
        """
        self.api_key = "AIzaSyB6VOIk0l6xKGKKmhuaQF8mmduyBk1d5jg"
        self.search_engine_id = "21d9e739fcf6c4bdc"
        self.service = build("customsearch", "v1", developerKey=self.api_key)
    
    def format_flight_number(self, flight_number):
        """
        Format flight number by removing leading zeros after airline code
        Example: AM0782 -> AM782, UA0123 -> UA123
        """
        airline_code = flight_number[:2]
        flight_digits = flight_number[2:].lstrip('0')
        return f"{airline_code}{flight_digits}"
    
    def get_flight_list(self, text):
        flights = []
        for i, line in enumerate(text.split('\n')):
            if line.startswith('JCSY:') or line.startswith('FLT/') or line.startswith('##') or not line.strip():
                continue
                
            parts = line.split()
            if len(parts) < 2:
                continue
                
            flight_number = self.format_flight_number(parts[0].strip())
            origin = parts[1].strip().lstrip('/')
            
            flights.append({
                'number': flight_number,
                'origin': origin,
                'line': line,
                'index': i  # Store the original line index
            })
            
        return flights

    def search_flight_info(self, flight_number, origin):
        """
        Search for flight information using Google Custom Search on FlightAware
        """
        try:
            # Search FlightAware only
            query = f"{flight_number} LAX \"Landing\" \"Gate Arrival\""
            result = self.service.cse().list(
                q=query,
                cx=self.search_engine_id,
                num=1
            ).execute()

            return result['items'][0] if 'items' in result else None

        except Exception as e:
            print(f"Error searching for flight {flight_number}: {str(e)}")
            return None
    
    def extract_arrival_time(self, search_result):
        """
        Extract arrival times (ATA, STA, and Blocked) from FlightAware search result
        Returns a dictionary with all three times
        """
        if not search_result:
            return None

        snippet = search_result.get('snippet', '')
        times = {
            'ata': None,  # Actual Time of Arrival
            'sta': None,  # Scheduled Time of Arrival
            'blocked': None  # Gate Arrival Time
        }
        
        # Extract ATA (Landing time)
        ata_match = re.search(r'Landing\.\s+(\d{1,2}:\d{2}(?:AM|PM))\s+PST', snippet)
        if ata_match:
            times['ata'] = ata_match.group(1).strip()
            
        # Extract STA (Scheduled time)
        sta_match = re.search(r'Scheduled\s+(\d{1,2}:\d{2}(?:AM|PM))\s+PST', snippet)
        if sta_match:
            times['sta'] = sta_match.group(1).strip()
            
        # Extract Blocked (Gate Arrival time)
        blocked_match = re.search(r'Gate Arrival\.\s+(\d{1,2}:\d{2}(?:AM|PM))\s+PST', snippet)
        if blocked_match:
            times['blocked'] = blocked_match.group(1).strip()
            
        return times