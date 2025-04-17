import requests
from bs4 import BeautifulSoup
from datetime import datetime
import random

class FlightStatsScraper:
    def __init__(self):
        self.url_template = "https://www.flightstats.com/v2/flight-tracker/{airline}/{number}?year={year}&month={month}&date={date}"
        
        # Headers for requests method
        user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/92.0.4515.159 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
        ]
        self.headers = {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive'
        }
    
    def get_flight_info(self, airline, number, date_str):
        """
        Get flight information from FlightStats
        
        :param airline: Airline code (e.g., 'AA')
        :param number: Flight number (e.g., '123')
        :param date_str: Date string in format YYYYMMDD
        :param depapt: Departure airport (optional)
        :return: Dictionary with flight details or None if not found
        """
        try:
            # Convert date_str (YYYYMMDD) to year, month, day
            date_obj = datetime.strptime(date_str, "%Y%m%d")
            year = date_obj.year
            month = date_obj.month
            day = date_obj.day
            
            # Build the URL
            url = self.url_template.format(
                airline=airline,
                number=number,
                year=year,
                month=str(month).zfill(2),
                date=str(day).zfill(2)
            )
            
            print(f"Fetching data from: {url}")
            
            # Make the request with headers
            response = requests.get(url, headers=self.headers)
            if response.status_code != 200:
                print(f"Failed to load flight data: HTTP {response.status_code}")
                return None
            
            # Parse the HTML
            return self._parse_flight_data(html_content=response.text)
            
        except Exception as e:
            print(f"Error getting flight info: {str(e)}")
            return None
    
    def _parse_flight_data(self, html_content):
        """
        Parse flight data from HTML content
        
        :param html_content: HTML content of the FlightStats page
        :return: Dictionary with flight details or None if not valid
        """
        try:
            # Use BeautifulSoup for parsing
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Initialize result dictionary with just the essential fields
            result = {
                'departure': {
                    'scheduled': 'N/A',
                    'actual': 'N/A',
                    'estimated': 'N/A',
                    'airport': 'N/A'
                },
                'arrival': {
                    'scheduled': 'N/A',
                    'actual': 'N/A',
                    'estimated': 'N/A',
                    'airport': 'N/A'
                }
            }
            
            # Find the main ticket card sections
            ticket_cards = soup.find_all('div', class_=lambda c: c and c.startswith('ticket__TicketCard-'))
            
            if len(ticket_cards) >= 2:
                departure_card = ticket_cards[0]
                arrival_card = ticket_cards[1]
                
                # Extract Departure Info
                dep_airport_link = departure_card.find('a', class_=lambda c: c and c.startswith('ticket__AirportLink-'))
                if dep_airport_link:
                    result['departure']['airport'] = dep_airport_link.text.strip()
                
                dep_time_sections = departure_card.find_all('div', class_=lambda c: c and c.startswith('ticket__InfoSection-'))
                for section in dep_time_sections:
                    label = section.find('div', class_=lambda c: c and c.startswith('text-helper__TextHelper-'), string='Scheduled')
                    if label:
                        time_div = label.find_next_sibling('div')
                        if time_div:
                            result['departure']['scheduled'] = time_div.text.strip()
                            
                    label = section.find('div', class_=lambda c: c and c.startswith('text-helper__TextHelper-'), string='Actual')
                    if label:
                        time_div = label.find_next_sibling('div')
                        if time_div:
                            result['departure']['actual'] = time_div.text.strip()
                            
                    label = section.find('div', class_=lambda c: c and c.startswith('text-helper__TextHelper-'), string='Estimated')
                    if label:
                        time_div = label.find_next_sibling('div')
                        if time_div:
                            result['departure']['estimated'] = time_div.text.strip()
                
                # Extract Arrival Info
                arr_airport_link = arrival_card.find('a', class_=lambda c: c and c.startswith('ticket__AirportLink-'))
                if arr_airport_link:
                    result['arrival']['airport'] = arr_airport_link.text.strip()
                
                arr_time_sections = arrival_card.find_all('div', class_=lambda c: c and c.startswith('ticket__InfoSection-'))
                for section in arr_time_sections:
                    label = section.find('div', class_=lambda c: c and c.startswith('text-helper__TextHelper-'), string='Scheduled')
                    if label:
                        time_div = label.find_next_sibling('div')
                        if time_div:
                            result['arrival']['scheduled'] = time_div.text.strip()
                            
                    label = section.find('div', class_=lambda c: c and c.startswith('text-helper__TextHelper-'), string='Actual')
                    if label:
                        time_div = label.find_next_sibling('div')
                        if time_div:
                            result['arrival']['actual'] = time_div.text.strip()
                            
                    label = section.find('div', class_=lambda c: c and c.startswith('text-helper__TextHelper-'), string='Estimated')
                    if label:
                        time_div = label.find_next_sibling('div')
                        if time_div:
                            result['arrival']['estimated'] = time_div.text.strip()
              
            return result
            
        except Exception as e:
            print(f"Error parsing flight data: {str(e)}")
            return None

# Main section for testing
if __name__ == "__main__":
    # Create a scraper instance
    scraper = FlightStatsScraper()
    
    # Test with DL 0899
    flight_info = scraper.get_flight_info("DL", "0899", "20250416")
    
    if flight_info:
        print("\nFinal Flight Information:")
        print("-" * 40)
        
        print("\nDeparture:")
        dep_info = flight_info['departure']
        print(f"  Airport: {dep_info['airport']}")
        print(f"  Scheduled: {dep_info['scheduled']}")
        print(f"  Actual: {dep_info['actual']}")
        print(f"  Estimated: {dep_info['estimated']}")
        
        print("\nArrival:")
        arr_info = flight_info['arrival']
        print(f"  Airport: {arr_info['airport']}")
        print(f"  Scheduled: {arr_info['scheduled']}")
        print(f"  Actual: {arr_info['actual']}")
        print(f"  Estimated: {arr_info['estimated']}")
    else:
        print("Failed to retrieve flight information") 