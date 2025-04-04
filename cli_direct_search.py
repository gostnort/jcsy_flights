from flight_scraper import FlightScraper
import sys
from datetime import datetime

def format_time(dt):
    """Format datetime to display time"""
    if dt is None:
        return "--:--"
    return dt.strftime("%I:%M%p")

def process_flight(flight, scraper):
    """Process a single flight and print results"""
    print(f"\nProcessing: {flight['airline']}{flight['number']} from {flight['depapt']}")
    print(f"Original line: {flight['line']}")
    
    result = scraper.search_flight_info(flight)
    
    if result:
        ata_str = format_time(result.get('ata'))
        sta_str = format_time(result.get('sta'))
        
        is_delayed = False
        if result.get('ata') and result.get('sta'):
            is_delayed = result['ata'] > result['sta']
        
        print(f"Scheduled Arrival Time (STA): {sta_str}")
        print(f"Actual Arrival Time (ATA): {ata_str}")
        
        if is_delayed:
            print("Status: DELAYED")
        elif result.get('ata'):
            print("Status: ON TIME")
        
        if result.get('snippet'):
            print(f"Flight info: {result['snippet']}")
        
        if result.get('is_yesterday'):
            print("Note: This flight was from yesterday")
            
        # Create replacement line with STA and ATA appended
        processed_line = flight['line']
        if result.get('sta') or result.get('ata'):
            # Append STA and ATA at the end of the line
            processed_line += f" | STA:{sta_str} ATA:{ata_str}"
            if is_delayed:
                processed_line += " [DELAYED]"
        
        return processed_line
    else:
        print("No results found for this flight")
        return flight['line']  # Return original line unchanged

def main():
    # Read JCSY.TXT file
    try:
        with open("JCSY.TXT", "r") as f:
            text = f.read()
    except Exception as e:
        print(f"Error reading JCSY.TXT: {str(e)}")
        return

    print("Processing flight data from JCSY.TXT...")
    
    # Initialize the flight scraper
    scraper = FlightScraper()
    
    # Parse the text to get flight list
    scraper.parse_jcsy_line(text)
    flights = scraper.get_flight_list(text)
    
    if not flights:
        print("No flights found in JCSY.TXT")
        return
    
    # Prepare output lines
    original_lines = text.splitlines()
    processed_lines = original_lines.copy()
    
    # Check if we need manual STD input
    if 'std' not in scraper.jcsy_flight:
        print("JCSY flight departure time not found. Please enter manually.")
        time_str = input("Enter JCSY flight departure time (24-hour format, e.g., 2220 for 10:20 PM): ")
        if len(time_str) != 4 or not time_str.isdigit():
            print("Invalid input format. Please use 24-hour format (e.g., 2220 for 10:20 PM)")
            return
        else:
            scraper.jcsy_flight['std'] = scraper.set_4digit_time(time_str)
        
        if not scraper.jcsy_flight['std']:
            print("Failed to set departure time. Please try again.")
            return
    
    print(f"Processing {len(flights)} flights...")
    
    # Process each flight
    for i, flight in enumerate(flights):
        processed_line = process_flight(flight, scraper)
        
        # Update the line in processed_lines
        line_index = flight['row'] - 1  # Convert 1-based to 0-based index
        if 0 <= line_index < len(processed_lines):
            processed_lines[line_index] = processed_line
        
        print(f"Progress: {i+1}/{len(flights)}")
    
    # Save processed result
    output_filename = "JCSY_PROCESSED.TXT"
    with open(output_filename, "w") as f:
        f.write('\n'.join(processed_lines))
    
    print(f"\nProcessing complete. Results saved to {output_filename}")

if __name__ == "__main__":
    main() 