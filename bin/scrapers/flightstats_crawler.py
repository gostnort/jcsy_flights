import requests
from bs4 import BeautifulSoup
from datetime import datetime, date
import random
from bin.scrapers.flightview_crawler import return_structure
from requests.exceptions import Timeout, RequestException



class FlightStatsCrawler:
    def __init__(self):
        self.url_template = "https://www.flightstats.com/v2/flight-tracker/{airline}/{number}?year={year}&month={month}&date={date}"
        # Headers for requests method
        user_agents = [
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36"
        ]
        self.headers = {
            'User-Agent': random.choice(user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive'
        }
        self.year = ""
        self.month = ""
        self.day = ""
    

    def get_flight_info(self, airline, flight_number, flight_date: date):
        """
        Get flight information from FlightStats
        Args:
            airline: Airline code (e.g., 'AA')
            flight_number: Flight number (e.g., '123')
            flight_date: The date object date(YYYY, MM, DD)
        Returns:
            The structure with the flight details from the FlightViewCrawler.
        """
        try:
            self.year = flight_date.year
            self.month = flight_date.month
            self.day = flight_date.day
            # Build the URL
            url = self.url_template.format(
                airline=airline,
                number=flight_number,
                year=self.year,
                month=self.month,
                date=self.day
            )
            print(f"FlightStats URL: {url}")
            # Make the request with headers
            try:
                response = requests.get(url, headers=self.headers, timeout=5)
            except Timeout:
                print(f"Request timed out for flight {airline}{flight_number}")
                return None
            except RequestException as e:
                print(f"Network error for flight {airline}{flight_number}: {str(e)}")
                return None
            # Parse the HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            return self._parse_flight_data(soup)
        except Exception as e:
            print(f"Error getting flight info: {str(e)}")
            return None
    

    def _parse_flight_data(self, soup) -> return_structure:
        """
        Parse flight data from BeautifulSoup object.
        Args:
            soup: BeautifulSoup object of the flight data
        Returns:
            return_structure object with flight details
        """
        result = return_structure()
        dep_section = soup.find('div', string='Flight Departure Times')
        if dep_section:
            time_container = dep_section.find_next('div', class_=lambda x: x and 'TimeGroupContainer' in x)
            if time_container:
                std_elem = time_container.find('div', string='Scheduled')
                if std_elem:
                    time_div = std_elem.find_next('div')
                    if time_div:
                        std_time = time_div.contents[0].strip()
                        if std_time:#if the time not exists, datetime will raise an error.
                            result.std = datetime.strptime(std_time, '%H:%M').replace(year=self.year, month=self.month, day=self.day)
                atd_elem = time_container.find('div', string='Actual')
                if atd_elem:
                    time_div = atd_elem.find_next('div')
                    if time_div:
                        atd_time = time_div.contents[0].strip()
                        if atd_time:
                            result.atd = datetime.strptime(atd_time, '%H:%M').replace(year=self.year, month=self.month, day=self.day)
                etd_elem = time_container.find('div', string='Estimated')
                if etd_elem:
                    time_div = etd_elem.find_next('div')
                    if time_div:
                        etd_time = time_div.contents[0].strip()
                        if etd_time:
                            result.etd = datetime.strptime(etd_time, '%H:%M').replace(year=self.year, month=self.month, day=self.day)
        arr_section = soup.find('div', string='Flight Arrival Times')
        if arr_section:
            time_container = arr_section.find_next('div', class_=lambda x: x and 'TimeGroupContainer' in x)
            if time_container:
                sta_elem = time_container.find('div', string='Scheduled')
                if sta_elem:
                    time_div = sta_elem.find_next('div')
                    if time_div:
                        sta_time = time_div.contents[0].strip()
                        if sta_time:
                            result.sta = datetime.strptime(sta_time, '%H:%M').replace(year=self.year, month=self.month, day=self.day)
                ata_elem = time_container.find('div', string='Actual')
                if ata_elem:
                    time_div = ata_elem.find_next('div')
                    if time_div:
                        ata_time = time_div.contents[0].strip()
                        if ata_time:
                            result.ata = datetime.strptime(ata_time, '%H:%M').replace(year=self.year, month=self.month, day=self.day)
                eta_elem = time_container.find('div', string='Estimated')
                if eta_elem:
                    time_div = eta_elem.find_next('div')
                    if time_div:
                        eta_time = time_div.contents[0].strip()
                        if eta_time:
                            result.eta = datetime.strptime(eta_time, '%H:%M').replace(year=self.year, month=self.month, day=self.day)
        return result

