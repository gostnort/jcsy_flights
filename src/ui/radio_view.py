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
        airline = parsed_header_data.get('header_airline_code')
        flight_number = parsed_header_data.get('header_flight_number')
        flight_date = parsed_header_data.get('header_flight_date')
        return self.flight_getter.return_flight_id('jcsy_flights',airline, flight_number, flight_date)
        

    def update_markdown_view(self):
        raw_text_from_editor = self.editor.toPlainText().strip()
        markdown_to_display = ""
        if raw_text_from_editor.startswith("JCSY:"):
            try:
                parser = JcsyParser("jcsy_config.yaml")
                parsed_data = parser.parse_content(raw_text_from_editor)
                header_dict_from_parser = parsed_data.get('header', {})
                header_flight_id = self._get_header_id_from_parsed_jcsy(header_dict_from_parser)
                markdown_formatter = MarkdownFormatter(header_flight_id)
                markdown_to_display = markdown_formatter.markdown
            except FileNotFoundError as e:
                # print(f"[ViewModeHandler] JCSY Config File Not Found: {e}") # Keep for now
                markdown_to_display = markdown.markdown(f"## Configuration Error\\nJCSY config file not found:({str(e)})\\n### Raw Input:\\n{raw_text_from_editor}", extensions=['tables'])
            except Exception as e:
                import traceback
                # print(f"[ViewModeHandler] Error processing JCSY: {e}\\n{traceback.format_exc()}") # Keep for now, but maybe make it conditional
                markdown_to_display = markdown.markdown(f"## Error Processing JCSY\\n`{str(e)}`\\n### Raw Input:\\n{raw_text_from_editor}", extensions=['tables'])
        else: # Does not start with JCSY:
            markdown_to_display = markdown.markdown(raw_text_from_editor, extensions=['tables'])
        self.viewer.setMarkdownText(markdown_to_display)
