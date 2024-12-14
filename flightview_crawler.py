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
            # Find row by partial text match and handle special characters
            rows = table.find_all('th')
            for row in rows:
                # Clean and compare text
                row_text = row.get_text().replace('\xa0', '').strip()
                if label in row_text:
                    value_cell = row.find_next('td')
                    if value_cell:
                        # Clean the value text (remove non-breaking spaces and regular spaces)
                        return value_cell.get_text().replace('\xa0', '').replace(' ', '').strip()
            return "N/A"
        except Exception as e:
            print(f"Extraction error for {label}: {str(e)}")
            return "N/A"

    def get_flight_info(self, airline, flight_number, date, depapt):
        try:
            # Construct URL and get data from website
            url = f"{self.base_url}/{airline}/{flight_number}?date={date}&depapt={depapt}"
            response = requests.get(url, headers=self.headers)
            response.raise_for_status()
            # Save raw HTML content for debugging
            #with open('debug_response.html', 'w', encoding='utf-8') as f:
            #    f.write(response.text)
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser') 
            # Save parsed content for debugging
            #with open('debug_parsed.txt', 'w', encoding='utf-8') as f:
            #    f.write(soup.prettify()) 
            # Get status
            flight_status = soup.select_one('.flight-status')
            if not flight_status:  # If can't find status, page might be error page
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
            arr_terminal = self.safe_extract_from_table(arr_table, 'Terminal - Gate')
            arr_baggage = self.safe_extract_from_table(arr_table, 'Baggage Claim')
            return {
                'status': status,
                'departure': {
                    'scheduled': dep_scheduled,
                    'actual': dep_actual,
                    'terminal_gate': dep_terminal
                },
                'arrival': {
                    'scheduled': arr_scheduled,
                    'actual': arr_actual,
                    'terminal_gate': arr_terminal,
                    'baggage_claim': arr_baggage
                }
            }

        except requests.exceptions.RequestException as e:
            print(f"Network error for flight {airline}{flight_number}: {str(e)}")
            return None
        except Exception as e:
            print(f"Error scraping flight info: {str(e)}")
            return None

# Example usage:
if __name__ == "__main__":
    scraper = FlightViewScraper()
    flight_info = scraper.get_flight_info('JL', '12', '20241212', 'HND')
    if flight_info:
        print(flight_info)
    else:
        print("Failed to get flight information")
