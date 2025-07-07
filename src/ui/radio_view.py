import sys
import os
from datetime import datetime, date # 用于日期解析
import markdown # 用于基本 markdown 渲染
from bin.config.jcsy_config import JcsyParser
from bin.config.markdown_config import MarkdownFormatter
from bin.database.flight_get import FlightGet



class ViewModeHandler:
    def __init__(self, editor_widget, viewer_widget, flight_getter_instance):
        self.editor = editor_widget
        self.viewer = viewer_widget
        self.flight_getter = flight_getter_instance


    def _get_header_id_from_parsed_jcsy(self, parsed_header_data: dict) -> int | None:
        """解析 JCSY 头部数据，查询数据库获取航班 ID"""
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
                # print(f"[ViewModeHandler] JCSY 配置文件未找到: {e}") # 暂时保留
                markdown_to_display = markdown.markdown(f"## 配置错误\\nJCSY 配置文件未找到:({str(e)})\\n### 原始输入:\\n{raw_text_from_editor}", extensions=['tables'])
            except Exception as e:
                import traceback
                # print(f"[ViewModeHandler] 处理 JCSY 时出错: {e}\\n{traceback.format_exc()}") # 暂时保留，但可能使其有条件
                markdown_to_display = markdown.markdown(f"## 处理 JCSY 时出错\\n`{str(e)}`\\n### 原始输入:\\n{raw_text_from_editor}", extensions=['tables'])
        else: # 不以 JCSY 开头：
            markdown_to_display = markdown.markdown(raw_text_from_editor, extensions=['tables'])
        self.viewer.setMarkdownText(markdown_to_display)
