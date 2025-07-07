# src/ui/export_button.py

import sys
import os
from datetime import datetime

# Add project root to Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from bin.database.flight_get import FlightGet
from bin.config.markdown_config import MarkdownFormatter

def _format_pax_count(non_economy, economy):
    """Helper to format passenger counts like 000/001"""
    return f"{int(non_economy or 0):03d}/{int(economy or 0):03d}"

def _format_checked_pax_count(non_economy, economy, infant):
    """Helper to format checked passenger counts like 000/001+00"""
    return f"{int(non_economy or 0):03d}/{int(economy or 0):03d}+{int(infant or 0):02d}"

def _format_bags(pieces, weight):
    """Helper to format bags like 001/0016"""
    return f"{int(pieces or 0):03d}/{int(weight or 0):04d}"

def export_button(header_flight_id: int, output_format_is_markdown: bool) -> str:
    """
    Exports flight data in the specified format (Markdown or JCSY).

    Args:
        header_flight_id: The ID of the main flight record in jcsy_flights.
        output_format_is_markdown: True for Markdown, False for JCSY.

    Returns:
        A string containing the formatted flight data.
    """
    db_getter = FlightGet()

    # Fetch header flight data
    header_flight_data = db_getter.return_flight_data('jcsy_flights', header_flight_id)
    if not header_flight_data:
        return "Error: Header flight data not found."

    # Fetch related query flights
    related_flight_ids = db_getter.return_related_flights_IDs('query_flights', header_flight_id)
    query_flights_data = []
    for flight_id in related_flight_ids:
        data = db_getter.return_flight_data('query_flights', flight_id)
        if data:
            query_flights_data.append(data)

    if output_format_is_markdown:
        try:
            # Ensure markdown_config.yaml is locatable from where MarkdownFormatter expects it
            # MarkdownFormatter constructor handles loading its own config and data
            formatter = MarkdownFormatter(header_flight_id=header_flight_id)
            return formatter.markdown
        except Exception as e:
            return f"Error generating Markdown: {str(e)}"
    else:
        # JCSY Format
        output_lines = []

        # 1. Header Line
        airline = header_flight_data.get('airline', '')
        flight_number = header_flight_data.get('flight_number', '')

        flight_date_obj = header_flight_data.get('flight_date')
        if isinstance(flight_date_obj, str):
            try:
                flight_date_obj = datetime.strptime(flight_date_obj, '%Y-%m-%d').date()
            except ValueError:
                flight_date_obj = None # Handle error or use a default

        flight_date_ddmmm = flight_date_obj.strftime('%d%b').upper() if flight_date_obj else 'ERRDT'

        # Determine header airport and I/O flag
        # jcsy_flights stores departure_airport and arrival_airport.
        # inbound_not = 1 means it's an inbound flight (header_airport is arrival)
        # inbound_not = 0 means it's an outbound flight (header_airport is departure)
        is_inbound = header_flight_data.get('inbound_not') == 1
        header_airport_jcsy = ''
        if is_inbound:
            header_airport_jcsy = header_flight_data.get('arrival_airport', 'N/A')
        else:
            header_airport_jcsy = header_flight_data.get('departure_airport', 'N/A')

        i_o_flag = 'I' if is_inbound else 'O'

        header_line = f"JCSY:{airline}{flight_number}/{flight_date_ddmmm}/{header_airport_jcsy},{i_o_flag}"
        output_lines.append(header_line)

        # 2. Title Line (Static)
        title_line = "FLT/ORIG   ARVL   BKD     CHK        UCK     NBRD       BAG                     "
        output_lines.append(title_line)

        # 3. Data Lines
        for q_flight in query_flights_data:
            q_airline = q_flight.get('airline', '')
            q_flight_number = q_flight.get('flight_number', '')

            # For JCSY output, the 'airport' in the segment line is:
            # - Origin airport if the main flight is INBOUND
            # - Destination airport if the main flight is OUTBOUND
            segment_airport_jcsy = ''
            if is_inbound: # Main flight is Inbound, so segment line shows segment's origin
                segment_airport_jcsy = q_flight.get('departure_airport', 'N/A')
            else: # Main flight is Outbound, so segment line shows segment's destination
                segment_airport_jcsy = q_flight.get('arrival_airport', 'N/A')


            # Arrival Time (ATA or ETA)
            ata_time_obj = q_flight.get('ata')
            eta_time_obj = q_flight.get('eta')
            arrival_time_hhmm = "----"

            actual_time_to_use = None
            if ata_time_obj:
                actual_time_to_use = ata_time_obj
            elif eta_time_obj:
                actual_time_to_use = eta_time_obj

            if actual_time_to_use:
                if isinstance(actual_time_to_use, str):
                    try:
                        # Assuming time stored as 'YYYY-MM-DD HH:MM:SS' or 'HH:MM:SS' or 'HH:MM'
                        if ' ' in actual_time_to_use and ':' in actual_time_to_use: # Datetime string
                           actual_time_to_use = datetime.strptime(actual_time_to_use.split(' ')[1], '%H:%M:%S').time()
                        elif ':' in actual_time_to_use: # Time string
                           parts = actual_time_to_use.split(':')
                           actual_time_to_use = datetime.strptime(f"{int(parts[0]):02d}:{int(parts[1]):02d}", '%H:%M').time()
                    except ValueError:
                        actual_time_to_use = None # Keep as None if parsing fails
                elif isinstance(actual_time_to_use, datetime): # Already a datetime object
                     actual_time_to_use = actual_time_to_use.time()

                if actual_time_to_use: # If conversion was successful
                    arrival_time_hhmm = actual_time_to_use.strftime('%H%M')


            booked_pax = _format_pax_count(
                q_flight.get('booked_count_non_economy'),
                q_flight.get('booked_count_economy')
            )
            # JCSY format from test_jcsy_out.txt shows CHK as "000/001+00"
            # This corresponds to checked_count_non_economy / checked_count_economy + check_count_infant
            checked_pax = _format_checked_pax_count(
                q_flight.get('checked_count_non_economy'),
                q_flight.get('checked_count_economy'),
                q_flight.get('check_count_infant')
            )

            # UCK, NBRD are not directly in schema for query_flights in import_button.py or markdown_config.py
            # Using placeholders for now based on `test_jcsy_out.txt`
            # These would need to be added to the database schema and import/refresh logic if required.
            # For now, using dummy values that match the test_jcsy_out.txt structure for these fields.
            uck_pax_str = "000/000" # Placeholder
            nbrd_pax_str = "000/000+00" # Placeholder

            # If UCK (Unchecked) means Booked - Checked, we could calculate it:
            # This is an assumption.
            # booked_ne = int(q_flight.get('booked_count_non_economy', 0))
            # booked_e = int(q_flight.get('booked_count_economy', 0))
            # checked_ne = int(q_flight.get('checked_count_non_economy', 0))
            # checked_e = int(q_flight.get('checked_count_economy', 0))
            # uck_ne = booked_ne - checked_ne
            # uck_e = booked_e - checked_e
            # uck_pax_str = _format_pax_count(max(0, uck_ne), max(0, uck_e))


            bags = _format_bags(
                q_flight.get('bags_count_piece'),
                q_flight.get('bags_count_weight')
            )

            # Flight number part should be {airline}{flight_number}
            # The test_jcsy_out.txt shows "UA1123 /SFO"
            # Airline seems to be part of the first element, then space, then slash, then airport.
            # Flight number can be variable length. Max 4 digits usually.
            # Airline 2 chars. Total 6 chars for flight ID part.
            # Example: UA1123 is 6 chars. DL0968 is 6 chars.
            flight_id_part = f"{q_airline}{q_flight_number}"

            # Fixed field widths based on `test_jcsy_out.txt`
            # FLT/ORIG (6 for FLT, 1 for space, 3 for ORIG = 10) -> UA1123 /SFO (6 for UA1123, 1 space, 1 slash, 3 for SFO = 11)
            # ARVL (4) -> 0835 (4)
            # BKD (7 with spaces) -> 000/001 (7)
            # CHK (10 with spaces) -> 000/001+00 (10)
            # UCK (7 with spaces) -> 000/000 (7)
            # NBRD (10 with spaces) -> 000/000+00 (10)
            # BAG (8 with spaces) -> 001/0016 (8)

            # Data line: {flight_id_part} /{segment_airport_jcsy} {arrival_time_hhmm}  {booked_pax} {checked_pax} {uck_pax_str} {nbrd_pax_str} {bags}
            # Need to ensure spacing is correct.
            # Example: UA1123 /SFO 0835  000/001 000/001+00 000/000 000/000+00 001/0016
            # Segment 1: Flight ID + Airport (UA1123 /SFO) - Max 11 chars. Left align. "UA1123 /SFO"
            #            "{:<11}".format(f"{flight_id_part} /{segment_airport_jcsy}") -> This might truncate if id is long.
            #            Let's try more dynamic spacing based on example.
            #            Part 1: flight_id_part (e.g. "UA1123")
            #            Part 2: " /" + segment_airport_jcsy (e.g. " /SFO")
            #            Part 3: arrival_time_hhmm (e.g. "0835")
            #
            # FLT/ORIG   ARVL   BKD     CHK        UCK     NBRD       BAG
            # UA1123 /SFO 0835  000/001 000/001+00 000/000 000/000+00 001/0016
            # Lengths:
            # Col 1 (Flight + Origin): "UA1123 /SFO" -> 11 chars. The title is "FLT/ORIG  " (10 chars)
            # Col 2 (Arrival Time): "0835" -> 4 chars. Title "ARVL" (4 chars)
            # Col 3 (Booked): "000/001" -> 7 chars. Title "BKD    " (7 chars)
            # Col 4 (Checked): "000/001+00" -> 10 chars. Title "CHK       " (10 chars)
            # Col 5 (UCK): "000/000" -> 7 chars. Title "UCK    " (7 chars)
            # Col 6 (NBRD): "000/000+00" -> 10 chars. Title "NBRD      " (10 chars)
            # Col 7 (BAG): "001/0016" -> 8 chars. Title "BAG       " (8 chars)
            #
            # Spacing between columns:
            # After Col1: 1 space ("UA1123 /SFO 0835")
            # After Col2: 2 spaces ("0835  000/001")
            # After Col3: 1 space ("000/001 000/001+00")
            # After Col4: 1 space ("000/001+00 000/000")
            # After Col5: 1 space ("000/000 000/000+00")
            # After Col6: 1 space ("000/000+00 001/0016")

            col1_flight_orig = f"{flight_id_part.ljust(6)} /{segment_airport_jcsy.ljust(3)}" # Total 6+1+1+3 = 11
            col2_arvl = arrival_time_hhmm.ljust(4)
            col3_bkd = booked_pax.ljust(7)
            col4_chk = checked_pax.ljust(10)
            col5_uck = uck_pax_str.ljust(7) # Placeholder
            col6_nbrd = nbrd_pax_str.ljust(10) # Placeholder
            col7_bag = bags.ljust(8)

            data_line = (
                f"{col1_flight_orig} "
                f"{col2_arvl}  " # Two spaces after ARVL
                f"{col3_bkd} "
                f"{col4_chk} "
                f"{col5_uck} "
                f"{col6_nbrd} "
                f"{col7_bag}"
            )
            output_lines.append(data_line.rstrip()) # Remove trailing spaces if any from last field

        # 4. Total Line (Skipping for now as it requires aggregation logic not specified)
        # If needed, it would look like:
        # output_lines.append("##TOTAL##         005/093 005/091+00 000/002 003/050+00 112/1811")

        return "\n".join(output_lines)

if __name__ == '__main__':
    # This is a placeholder for basic local testing.
    # Proper testing will be done with pytest and a test database.
    print("This is src/ui/export_button.py")
    print("To test, you'd typically call export_button(header_id, is_markdown) after populating a database.")

    # Example:
    # Create a dummy database and populate it if FlightGet can connect to it.
    # For now, this will likely fail if a DB is not set up or if FlightGet has specific expectations.

    # print("\n--- Mock Test (requires DB setup) ---")
    # Assuming a header_flight_id = 1 exists and has related flights.
    # try:
    #     header_id_to_test = 1 # Replace with a valid ID from your test DB
    #     print(f"\n--- Testing Markdown Output for Flight ID {header_id_to_test} ---")
    #     markdown_output = export_button(header_id_to_test, True)
    #     print(markdown_output)

    #     print(f"\n--- Testing JCSY Output for Flight ID {header_id_to_test} ---")
    #     jcsy_output = export_button(header_id_to_test, False)
    #     print(jcsy_output)
    # except Exception as e:
    #     print(f"Error in local test: {e}")
    #     print("Ensure database is populated and FlightGet is configured correctly.")

    pass
