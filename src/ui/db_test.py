from src.database.flight_repository import FlightRepository
from src.database.flight_query import FlightQuery

def test_flight_repository(jcsy_data: str):
    """Test the FlightRepository class with JCSY data"""
    repo = FlightRepository()
    flight_ids = repo.process_jscy_content(jcsy_data)
    print(f"Processed {len(flight_ids)} flights")
    
def test_flight_query(main_flight_id: int):
    """Test the FlightQuery class with a specific flight ID"""
    query = FlightQuery()
    flight_data = query.get_flight_with_queries(main_flight_id)
    display_info = _display_flight_info(flight_data)
    print(display_info)

def test_search_main_flight(airline_flight_number: str, departure_date_mmddyy: str):
    """Test the search_main_flight function"""
    query = FlightQuery()
    flight_data = query.search_main_flight(airline_flight_number, departure_date_mmddyy)
    print(f"Flight data: {flight_data}")

def _display_flight_info(flight_data: dict) -> str:
    """
    Get and format flight information as a formatted string
    
    Args:
        main_flight_id: The ID of the main flight (jscy_flight_id)
        
    Returns:
        Formatted string with flight details
    """
    
    # Start building the output string
    output = []
    
    # Basic flight information
    airline = flight_data.get('airline', '')
    flight_number = flight_data.get('flight_number', '')
    is_arrival = flight_data.get('is_arrival', False)
    flight_type = "ARRIVAL" if is_arrival else "DEPARTURE"
    departure_airport = flight_data.get('departure_airport', '')
    arrival_airport = flight_data.get('arrival_airport', '')
    
    # Format date if available
    flight_date = flight_data.get('flight_date', '')
    if flight_date and len(flight_date) == 8:
        formatted_date = f"{flight_date[:4]}-{flight_date[4:6]}-{flight_date[6:8]}"
    else:
        formatted_date = flight_date
    
    output.append(f"Flight: {airline}{flight_number}")
    output.append(f"Date: {formatted_date}")
    output.append(f"Type: {flight_type}")
    output.append(f"Route: {departure_airport} → {arrival_airport}")
    
    # Time information
    output.append("\nTIME INFORMATION:")
    output.append(f"STD (Scheduled Departure): {flight_data.get('std', 'N/A')}")
    output.append(f"ETD (Estimated Departure): {flight_data.get('etd', 'N/A')}")
    output.append(f"ATD (Actual Departure): {flight_data.get('atd', 'N/A')}")
    output.append(f"STA (Scheduled Arrival): {flight_data.get('sta', 'N/A')}")
    output.append(f"ETA (Estimated Arrival): {flight_data.get('eta', 'N/A')}")
    output.append(f"ATA (Actual Arrival): {flight_data.get('ata', 'N/A')}")
    
    # Delayed status
    is_delayed = flight_data.get('delayed', 0) == 1
    output.append(f"Delayed: {'YES' if is_delayed else 'No'}")
    
    # Original JSCY line if available
    if flight_data.get('original_line'):
        output.append("\nORIGINAL JSCY LINE:")
        output.append(flight_data.get('original_line', ''))
    
    # Processed line if available and different
    if (flight_data.get('processed_line') and 
        flight_data.get('processed_line') != flight_data.get('original_line')):
        output.append("\nPROCESSED LINE:")
        output.append(flight_data.get('processed_line', ''))
    
    # Add query information if available
    if flight_data.get('queries'):
        output.append("\nQUERY HISTORY:")
        output.append("-" * 60)
        
        for i, query in enumerate(flight_data['queries']):
            output.append(f"Query #{i+1} (Source: {query.get('source', 'Unknown')})")
            output.append(f"  Timestamp: {query.get('query_timestamp', 'N/A')}")
            
            # Time fields for this query
            output.append("  Time Information:")
            output.append(f"    STD: {query.get('std', 'N/A')}")
            output.append(f"    ETD: {query.get('etd', 'N/A')}")
            output.append(f"    ATD: {query.get('atd', 'N/A')}")
            output.append(f"    STA: {query.get('sta', 'N/A')}")
            output.append(f"    ETA: {query.get('eta', 'N/A')}")
            output.append(f"    ATA: {query.get('ata', 'N/A')}")
            
            # Passenger and baggage information
            if any(key in query for key in ['booked_count_economy', 'booked_count_non_economy']):
                output.append("  Passenger Information:")
                output.append(f"    Economy: {query.get('booked_count_economy', 0)}")
                output.append(f"    Non-Economy: {query.get('booked_count_non_economy', 0)}")
                output.append(f"    Checked (Economy): {query.get('checked_count_economy', 0)}")
                output.append(f"    Checked (Non-Economy): {query.get('checked_count_non_economy', 0)}")
                output.append(f"    Infants: {query.get('check_count_infant', 0)}")
            
            if any(key in query for key in ['bags_count_piece', 'bags_count_weight']):
                output.append("  Baggage Information:")
                output.append(f"    Pieces: {query.get('bags_count_piece', 0)}")
                output.append(f"    Weight: {query.get('bags_count_weight', 0)} kg")
            
            output.append("-" * 40)
    
    # Final divider
    output.append("=" * 60)
    
    return "\n".join(output)    
    
    
    
