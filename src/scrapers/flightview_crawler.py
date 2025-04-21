import requests
from bs4 import BeautifulSoup
from datetime import datetime

class FlightViewScraper:
    def __init__(self):
        self.base_url = "https://www.flightview.com/flight-tracker"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def safe_extract_from_table(self, table, label):
        """
        Safely extract value from table row by label, handling special characters
        """
        try:
            if not table:
                return "N/A"
            rows = table.find_all('th')
            for row in rows:
                row_text = row.get_text().replace('\xa0', '').strip()
                if label in row_text:
                    value_cell = row.find_next('td')
                    if value_cell:
                        return value_cell.get_text().replace('\xa0', '').replace(' ', '').strip()
            return "N/A"
        except Exception as e:
            print(f"Extraction error for {label}: {str(e)}")
            return "N/A"

    def get_flight_info(self, airline, flight_number, date, is_arrival=True, depapt=None, arrapt="LAX"):
        """
        Get flight information from FlightView
        Args:
            airline: Airline code (e.g., 'CA')
            flight_number: Flight number without leading zeros (e.g., '984')
            date: Flight date in YYYYMMDD format
            is_arrival: Whether this is an arrival (True) or departure (False)
            depapt: Optional departure airport code (for specific search)
            arrapt: Arrival airport code, defaults to 'LAX'
        """
        try:
            # Construct URL based on whether depapt is provided and flight direction
            if depapt and not is_arrival:
                # Departure flight with specific departure airport
                url = f"{self.base_url}/{airline}/{flight_number}?date={date}&depapt={depapt}&arrapt={arrapt}"
            elif depapt and is_arrival:
                # Arrival flight with specific departure airport
                url = f"{self.base_url}/{airline}/{flight_number}?date={date}&depapt={depapt}&arrapt={arrapt}"
            elif is_arrival:
                # Generic arrival to arrapt
                url = f"{self.base_url}/{airline}/{flight_number}?date={date}&arrapt={arrapt}"
            else:
                # Generic departure from arrapt
                url = f"{self.base_url}/{airline}/{flight_number}?date={date}&depapt={arrapt}"
                
            print(f"FlightView URL: {url}")
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract the flight date from the page (could be different from requested date)
            flight_date_elem = soup.select_one('.fvDate')
            flight_date = date  # Default to requested date
            if flight_date_elem:
                try:
                    date_text = flight_date_elem.text.strip()
                    date_obj = datetime.strptime(date_text, "%A, %B %d, %Y")
                    flight_date = date_obj.strftime("%Y%m%d")
                except Exception as e:
                    print(f"Failed to parse flight date: {str(e)}")
            
            # Get status
            flight_status = soup.select_one('.flight-status')
            if not flight_status:
                print(f"Invalid response for flight {airline}{flight_number}")
                return None
                
            status = flight_status.text.strip()
            
            # Get departure info table
            dep_table = soup.find('table', {'id': 'ffDepartureInfo'})
            dep_scheduled = self.safe_extract_from_table(dep_table, 'Scheduled Time')
            dep_actual = self.safe_extract_from_table(dep_table, 'Actual Time')
            dep_terminal = self.safe_extract_from_table(dep_table, 'Terminal - Gate')
            
            # Get arrival info table
            arr_table = soup.find('table', {'id': 'ffArrivalInfo'})
            arr_scheduled = self.safe_extract_from_table(arr_table, 'Scheduled Time')
            arr_actual = self.safe_extract_from_table(arr_table, 'Actual Time')
            arr_estimated = self.safe_extract_from_table(arr_table, 'Estimated Time')
            arr_terminal = self.safe_extract_from_table(arr_table, 'Terminal - Gate')
            arr_baggage = self.safe_extract_from_table(arr_table, 'Baggage Claim')
            
            return {
                'status': status,
                'date': flight_date,  # Include actual flight date
                'departure': {
                    'scheduled': dep_scheduled,
                    'actual': dep_actual,
                    'terminal_gate': dep_terminal,
                    'status': status if not is_arrival else None
                },
                'arrival': {
                    'scheduled': arr_scheduled,
                    'actual': arr_actual,
                    'estimated': arr_estimated,
                    'terminal_gate': arr_terminal,
                    'baggage_claim': arr_baggage,
                    'status': status if is_arrival else None
                }
            }

        except requests.exceptions.RequestException as e:
            print(f"Network error for flight {airline}{flight_number}: {str(e)}")
            return None
        except Exception as e:
            print(f"Error scraping flight info: {str(e)}")
            return None 