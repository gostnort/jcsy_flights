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
        Search for flight information using Google Custom Search
        """
        try:
            # Simple direct query format: AM782 GDL LAX "Gate Arrival" "PST"
            query = f"{flight_number} {origin} LAX \"Gate Arrival\" \"PST\""
            
            result = self.service.cse().list(
                q=query,
                cx=self.search_engine_id,
                num=1
            ).execute()

            if 'items' in result:
                return result['items'][0]
            return None

        except Exception as e:
            print(f"Error searching for flight {flight_number}: {str(e)}")
            return None
    
    def extract_arrival_time(self, search_result):
        if not search_result:
            return None
            
        snippet = search_result.get('snippet', '')
        
        # Look for time between "Gate Arrival. " and " PST"
        match = re.search(r'Gate Arrival\.\s+(\d{1,2}:\d{2}(?:AM|PM))\s+PST', snippet)
        if match:
            return match.group(1).strip()
            
        return None