import sys
import os
from datetime import datetime, date # For date parsing
import markdown # For basic markdown rendering
from bin.config.jcsy_config import JcsyParser
from bin.config.markdown_config import MarkdownFormatter
from bin.database.flight_get import FlightGet



class ViewModeHandler:
    def __init__(self, editor_widget, viewer_widget, flight_getter_instance):
        self.editor = editor_widget
        self.viewer = viewer_widget
        self.flight_getter = flight_getter_instance


    def _get_header_id_from_parsed_jcsy(self, parsed_header_data: dict) -> int | None:
        """Parses JCSY header data, queries DB for flight ID."""
        if not self.flight_getter or not parsed_header_data:
            return None
        
        airline = parsed_header_data.get('header_airline_code')
        flight_number_str = parsed_header_data.get('header_flight_number')
        flight_date_str = parsed_header_data.get('header_flight_date')
        departure_airport = parsed_header_data.get('header_departure_airport')

        if not all([airline, flight_number_str, flight_date_str, departure_airport]):
            # print("Incomplete header data from JcsyParser for DB lookup in ViewModeHandler.") # Keep for now, or make optional
            return None

        try:
            day = int(flight_date_str[:2])
            month_str = flight_date_str[2:].upper()
            current_year = datetime.now().year 
            parsed_date_obj = datetime.strptime(f"{current_year}-{month_str}-{day:02d}", "%Y-%b-%d").date()
        except ValueError as e:
            # print(f"Could not parse date from JCSY header ('{flight_date_str}') in ViewModeHandler: {e}") # Keep for now
            return None

        # print("Placeholder: ViewModeHandler._get_header_id_from_parsed_jcsy would query DB here. Returning None.") # Keep for now
        return None # Placeholder

    def update_markdown_view(self):
        raw_text_from_editor = self.editor.toPlainText().strip()
        markdown_to_display = ""

        if not raw_text_from_editor:
            self.viewer.setMarkdownText("")
            return

        if raw_text_from_editor.startswith("JCSY:"):
            try:
                jcsy_config_name = "jcsy_i_config.yaml" # <<< Placeholder
                
                if hasattr(JcsyParser, '_load_config'): # Check for real parser
                    parser = JcsyParser(config_file=jcsy_config_name)
                    parsed_data = parser.parse_content(raw_text_from_editor)
                    header_dict_from_parser = parsed_data.get('header', {})

                    if header_dict_from_parser:
                        header_flight_id = self._get_header_id_from_parsed_jcsy(header_dict_from_parser)

                        if header_flight_id is not None and hasattr(MarkdownFormatter, '_load_config'):
                            formatter = MarkdownFormatter(header_flight_id=header_flight_id)
                            markdown_to_display = formatter.get_markdown()
                            if markdown_to_display.startswith("Error:"):
                                # print(f"[ViewModeHandler] MarkdownFormatter error: {markdown_to_display}") # Keep for now
                                markdown_to_display = markdown.markdown(f"## JCSY Formatting Error\\n```\\n{markdown_to_display}\\n```\\n### Raw Input:\\n{raw_text_from_editor}", extensions=['tables'])
                        else:
                            preview_header_info = ", ".join([f"{k}: {v}" for k,v in header_dict_from_parser.items()])
                            markdown_to_display = markdown.markdown(
                                f"## JCSY Data Preview (Flight ID Not Found or Formatter Issue)\\n"
                                f"**Parsed Header:** `{preview_header_info}`\\n\\n"
                                f"(Full table rendering requires this flight to be 'Imported' into the database to get a valid ID).\\n\\n"
                                f"### Raw Input:\\n```\\n{raw_text_from_editor}\\n```", extensions=['tables'])
                    else:
                        markdown_to_display = markdown.markdown(f"## JCSY Parsing Issue\\nCould not extract header data, though 'JCSY:' prefix was found.\\n### Raw Input:\\n{raw_text_from_editor}", extensions=['tables'])
                else: # JcsyParser is a dummy
                    markdown_to_display = markdown.markdown(f"## JCSY Parser Not Loaded\\nCannot process JCSY data.\\n### Raw Input:\\n{raw_text_from_editor}", extensions=['tables'])
            except FileNotFoundError as e:
                # print(f"[ViewModeHandler] JCSY Config File Not Found: {e}") # Keep for now
                markdown_to_display = markdown.markdown(f"## Configuration Error\\nJCSY config file not found: {jcsy_config_name}\\n({str(e)})\\n### Raw Input:\\n{raw_text_from_editor}", extensions=['tables'])

            except Exception as e:
                import traceback
                # print(f"[ViewModeHandler] Error processing JCSY: {e}\\n{traceback.format_exc()}") # Keep for now, but maybe make it conditional
                markdown_to_display = markdown.markdown(f"## Error Processing JCSY\\n`{str(e)}`\\n### Raw Input:\\n{raw_text_from_editor}", extensions=['tables'])
        else: # Does not start with JCSY:
            markdown_to_display = markdown.markdown(raw_text_from_editor, extensions=['tables'])
        
        self.viewer.setMarkdownText(markdown_to_display)
