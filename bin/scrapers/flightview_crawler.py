import requests
from bs4 import BeautifulSoup
from datetime import date, datetime
from dataclasses import dataclass
from requests.exceptions import Timeout, RequestException


@dataclass
class return_structure:
    std: datetime = None
    atd: datetime = None
    etd: datetime = None
    sta: datetime = None
    ata: datetime = None
    eta: datetime = None


class FlightViewCrawler:
    def __init__(self):
        self.base_url = "https://www.flightview.com/flight-tracker"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.year = ""


    def _extract_time_from_table(self, table, time_label):
        """
        Get time from the table.
        Args:
            table: BeautifulSoup object of the table
            time_label: Label of the time to extract
        Returns:
            datetime object of the time
        """
        try:
            if not table:
                return None
            rows = table.find_all('tr')
            for row in rows:
                th = row.find('th')
                if th and time_label in th.get_text().strip():
                    td = row.find('td')
                    if td:
                        time_str = td.get_text().replace('\xa0', ' ').replace('&nbsp;', ' ').strip()
                        if not time_str or time_str == "N/A":
                            return None
                        # Parse the time and add the year from initialization
                        dt = datetime.strptime(time_str, '%I:%M %p, %B %d')
                        return dt.replace(year=self.year)
            return None
        except Exception as e:
            print(f"Extraction error for {time_label}: {str(e)}")
            return None


    def get_flight_info(self, airline, flight_number, flight_date: date, depapt=None, arrapt=None):
        """
        Get flight information from FlightView
        Args:
            airline: Airline code (e.g., 'CA')
            flight_number: Flight number without leading zeros (e.g., '984')
            date: Flight date in YYYYMMDD format
            depapt: Optional departure airport code (for specific search)
            arrapt: Arrival airport code, defaults to 'LAX'
        """
        try:
            self.year = flight_date.year
            # Construct URL based on whether depapt is provided and flight direction
            if depapt is None:
                url = f"{self.base_url}/{airline}/{flight_number}?date={flight_date.strftime('%Y%m%d')}&arrapt={arrapt}"
            elif arrapt is None:
                url = f"{self.base_url}/{airline}/{flight_number}?date={flight_date.strftime('%Y%m%d')}&depapt={depapt}"
            else:
                url = f"{self.base_url}/{airline}/{flight_number}?date={flight_date.strftime('%Y%m%d')}&depapt={depapt}&arrapt={arrapt}"
            print(f"FlightView URL: {url}")
            try:
                response = requests.get(url, headers=self.headers, timeout=5)
            except Timeout:
                print(f"Request timed out for flight {airline}{flight_number}")
                return None
            except RequestException as e:
                print(f"Network error for flight {airline}{flight_number}: {str(e)}")
                return None
            soup = BeautifulSoup(response.text, 'html.parser')
            # Get departure info table
            dep_table = soup.find('table', {'id': 'ffDepartureInfo'})
            dep_scheduled = self._extract_time_from_table(dep_table, 'Scheduled Time')
            dep_actual = self._extract_time_from_table(dep_table, 'Actual Time')
            dep_estimated = self._extract_time_from_table(dep_table, 'Estimated Time') 
            # Get arrival info table
            arr_table = soup.find('table', {'id': 'ffArrivalInfo'})
            arr_scheduled = self._extract_time_from_table(arr_table, 'Scheduled Time')
            arr_actual = self._extract_time_from_table(arr_table, 'Actual Time')
            arr_estimated = self._extract_time_from_table(arr_table, 'Estimated Time')
            return return_structure(
                std=dep_scheduled,
                atd=dep_actual,
                etd=dep_estimated,
                sta=arr_scheduled,
                ata=arr_actual,
                eta=arr_estimated
            )
        except requests.exceptions.RequestException as e:
            print(f"Network error for flight {airline}{flight_number}: {str(e)}")
            return None
        except Exception as e:
            print(f"Error scraping flight info: {str(e)}")
            return None 
        
