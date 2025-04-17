from flight_scraper import FlightScraper
from flights_dispatch import FlightProcessor # Import FlightProcessor
from datetime import datetime
import os

def print_flight_info(title, flight_info, original_line):
    """Print flight information in a formatted way"""
    print(f"\n{title}: (Original: {original_line.strip()})")
    print("-" * 60)
    if not flight_info or (flight_info.get('sta') is None and flight_info.get('ata') is None):
        print("No valid time information found")
        # Optionally print snippet if available even without times
        if flight_info and flight_info.get('snippet'):
             print(f"Status Snippet: {flight_info['snippet']}")
        return

    # Print available info
    sta = flight_info.get('sta')
    ata = flight_info.get('ata')
    snippet = flight_info.get('snippet')
    is_yesterday = flight_info.get('is_yesterday', False)
    
    print(f"Scheduled Arrival (STA): {sta.strftime('%Y-%m-%d %H:%M') if sta else 'N/A'}")
    print(f"Actual/Estimated Arrival (ATA): {ata.strftime('%Y-%m-%d %H:%M') if ata else 'N/A'}")
    if snippet:
        print(f"Status Snippet: {snippet}")
    if is_yesterday:
        print("Note: Information pertains to the previous day.")

# Mock MainWindow class to hold the FlightScraper instance
class MockMainWindow:
    def __init__(self, list_type='arrival', home_airport='LAX'):
        try:
            self.flight_scraper = FlightScraper(list_type=list_type, home_airport=home_airport)
        except ValueError as ve:
            print(f"Error initializing scraper in MockMainWindow: {ve}")
            self.flight_scraper = None # Indicate failure

def main():
    # Define the path to the JCSY file
    jcsy_file_path = "JCSY.txt"
    
    # Check if the JCSY file exists
    if not os.path.exists(jcsy_file_path):
        print(f"Error: JCSY file not found at {jcsy_file_path}")
        return
        
    # Read the JCSY file content
    try:
        with open(jcsy_file_path, 'r') as f:
            jcsy_text = f.read()
    except Exception as e:
        print(f"Error reading JCSY file: {e}")
        return
        
    # --- Configuration --- 
    # Set list type ('arrival' or 'departure') and the home airport code
    config_list_type = 'arrival' 
    config_home_airport = 'LAX'    
    # ---------------------
    
    # Create Mock MainWindow which holds the scraper
    mock_window = MockMainWindow(list_type=config_list_type, home_airport=config_home_airport)
    if not mock_window.flight_scraper: # Check if scraper initialized correctly
        return
        
    # Create an instance of FlightProcessor, passing the mock window
    processor = FlightProcessor(mock_window)
        
    # Start processing - this parses JCSY and populates flights_to_process
    if not processor.start_processing(jcsy_text):
        print("Failed to start processing JCSY text.")
        return
        
    # Check if JCSY parsing within start_processing was successful
    if not mock_window.flight_scraper.flightview_date:
        print("Failed to initialize scraper date from JCSY file via processor. Exiting.")
        return
        
    print(f"\n--- Testing FlightProcessor ({processor.main_window.flight_scraper.list_type.capitalize()} List for {processor.main_window.flight_scraper.HOME_AIRPORT}) --- ")
    print(f"Using Flight Date: {processor.main_window.flight_scraper.flightview_date}")
    print("------------------------------------------------------------")

    # Manually iterate and process flights (simulating worker execution)
    if not processor.flights_to_process:
        print("No flights found in the JCSY file list to process.")
        return
        
    print(f"Found {len(processor.flights_to_process)} flights to process.")
    
    processed_results = []
    for flight in processor.flights_to_process:
        title = f"{flight['airline']}{flight['number']} ({flight['depapt']} -> {flight['arrapt']})"
        print(f"\nProcessing {title}...")
        
        # Directly call the search function (instead of using QThread)
        try:
            result = mock_window.flight_scraper.search_flight_info(flight)
            processed_results.append({'title': title, 'result': result, 'line': flight['line']})
            # In a real app, this result would come via signal
            print_flight_info(title, result, flight['line'])
        except Exception as e:
            print(f"Error processing flight {title}: {e}")
            processed_results.append({'title': title, 'result': None, 'line': flight['line'], 'error': str(e)})
            print_flight_info(title, None, flight['line'])
            
    print("\n--- Processing Complete ---")
    # Here you could potentially verify the processed_results list if needed

if __name__ == "__main__":
    main() 