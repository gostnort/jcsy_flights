'''
This module will coorperate with the database and the web scraper to process the data.

The processor will be responsible for the following:
- Retrieving data from the database
- Sending and receiving data from the web scraper
- Storing data in the database

There is another multiprocessing class that will optimize the processing of the data.
'''
from bin.database.flight_db import FlightDatabase
from bin.database.flight_add import FlightAdd
from bin.database.flight_get import FlightGet
from bin.scrapers.flightview_crawler import FlightViewCrawler
from bin.scrapers.flightstats_crawler import FlightStatsCrawler
from datetime import datetime,date



class Processor:
    def __init__(self,main_flight_id):
        self.processing_dict = {}#Define the processing dictionary which keys are the qurey flight IDs and values are the processing status.
        self.status_dict = {#Define the status of the processing for the processing dictionary.
            'new':0,
            'processing':1,
            'completed':2,
            'error':3
        }
        self.flight_db = FlightDatabase()#Initialize the database connection from the FlightDatabase class.
        self.flight_add = FlightAdd()
        self.flight_get = FlightGet("flights.db")
        self.flight_view_crawler = FlightViewCrawler()
        self.flight_stats_crawler = FlightStatsCrawler()
        self.main_flight_id = main_flight_id
        self.header_flight_time = None
        self.is_arrival = self.flight_get.return_flight_data('jcsy_flights',self.main_flight_id)['is_arrival']


    def main_processor(self):
        try:
            self._update_header_times(self.main_flight_id)
            #Query the main flight related flights from the database with the 'new' status.
            self._get_query_flights(self.main_flight_id)#The result returns the processing_dict.
            #Query flights from the flightview crawler at first. 
            # - The status updates to 'processing' while getting a flight at the beginning.
            for flight_id in self.processing_dict:
                if self.processing_dict[flight_id] == self.status_dict['new']:
                    self.processing_dict[flight_id] = self.status_dict['processing']
                    self._update_query_times(flight_id)
            for flight_id in self.processing_dict:
                if self.processing_dict[flight_id] == self.status_dict['error']:
                    self._update_query_times(flight_id)
            return
        except Exception as e:
            print(e)
            return
    

    def _update_header_times(self):
        flight_info = self._get_flightview_info(self.main_flight_id,'jcsy_flights')
        if any(vars(flight_info).values()):
            self._update_flight_times(self.main_flight_id,flight_info,'jcsy_flights')
            if self.is_arrival == 1:
                self.header_flight_time = flight_info.get('std')
            else:
                self.header_flight_time = flight_info.get('sta')
            return
        flight_info = self._get_flightstats_info(self.main_flight_id,'jcsy_flights')
        if any(vars(flight_info).values()):
            self._update_flight_times(self.main_flight_id,flight_info,'jcsy_flights')
            if self.is_arrival == 1:
                self.header_flight_time = flight_info.get('std')
            else:
                self.header_flight_time = flight_info.get('sta')
        return
    

    def _update_query_times(self,query_flight_id):
        # The status updates to 'completed' after the flight times wrote to the database.
        # The status updates to 'error' while the flight is not processed.
        # Try FlightView function first
        if self._process_flight_info(query_flight_id, self._get_flightview_info):
            return
        # Try FlightStats function as fallback
        if self._process_flight_info(query_flight_id, self._get_flightstats_info):
            return
        # Mark as error if both sources failed
        self._mark_error(query_flight_id)
        return
    

    def _process_flight_info(self, query_flight_id, get_info_func):
        """
        Process flight information from a specific source.      
        Args:
            query_flight_id: ID of the query flight to update
            get_info_func: Function to get flight information 
        Returns:
            True if processing was successful, False otherwise
        """
        flight_info = get_info_func(query_flight_id)
        if any(vars(flight_info).values()):
            if self._update_flight_times(query_flight_id, flight_info, 'query_flights'):
                if self.is_arrival == 1:
                    if flight_info.get('std') > self.header_flight_time:
                        if get_info_func(query_flight_id, flight_date=self.header_flight_time.date()-1):
                            self._mark_completed(query_flight_id)
                else:
                    if flight_info.get('std') < self.header_flight_time:
                        if get_info_func(query_flight_id, flight_date=self.header_flight_time.date()+1):
                            self._mark_completed(query_flight_id)
                self._mark_completed(query_flight_id)
                return True
        return False


    def _update_flight_times(self,flight_id,flight_info,table) -> bool:
        result = False
        local_db_connection = FlightAdd()
        #Close the database connection after the update.
        #In the multiprocessing, the database connection will be closed automatically.
        #Because the parent garbage collector will not collect the child process.
        try:
            update_fields = local_db_connection.UPDATE_FIELDS
            update_fields['table'] = table
            update_fields['id'] = flight_id
            if flight_info.atd:
                update_fields['flight_date'] = flight_info.atd.date()
            else:
                update_fields['flight_date'] = flight_info.std.date()
            update_fields['std'] = flight_info.std
            update_fields['etd'] = flight_info.etd
            update_fields['atd'] = flight_info.atd
            update_fields['sta'] = flight_info.sta
            update_fields['eta'] = flight_info.eta
            update_fields['ata'] = flight_info.ata
            local_db_connection.update_flight_times(update_fields)
            if update_fields['flight_date'] != None:
                result = True
        finally:
            local_db_connection.db.close()
        return result


    def _get_query_flights(self, main_flight_id):
        #Query the main flight related flights from the database with the 'new' status.
        related_flight_ids = self.flight_get.return_related_flights_IDs('query_flights', main_flight_id)
        for flight_id in related_flight_ids:
            self.processing_dict[flight_id] = self.status_dict['new']
        return


    def _get_flightview_info(self, flight_id, table='query_flights',flight_date=None):
        flight_data = self.flight_get.return_flight_data(table, flight_id)
        if flight_date is None:
            flight_date = datetime.strptime(flight_data['flight_date'], '%Y-%m-%d').date()
        #Try the complete flight info first.
        flight_info = self.flight_view_crawler.get_flight_info(
            flight_data['airline'], 
            flight_data['flight_number'], 
            flight_date,
            flight_data['departure_airport'],
            flight_data['arrival_airport']
            )
        return flight_info
    

    def _get_flightstats_info(self, flight_id, table='query_flights',flight_date=None):
        flight_data = self.flight_get.return_flight_data(table, flight_id)
        if flight_date is None:
            flight_date = datetime.strptime(flight_data['flight_date'], '%Y-%m-%d').date()
        flight_info = self.flight_stats_crawler.get_flight_info(
            flight_data['airline'], 
            flight_data['flight_number'], 
            flight_date,
            )
        return flight_info
    

    def _mark_completed(self, flight_id):
        self.processing_dict[flight_id] = self.status_dict['completed']
        return
    

    def _mark_error(self, flight_id):
        self.processing_dict[flight_id] = self.status_dict['error']
        return
    
    