# 此文件将包含 UI 按钮操作的函数
# 最初，它将包含"导入"按钮的函数

import sys
import os
import datetime
import sqlite3

# 将项目根目录添加到 Python 路径以允许直接导入
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from bin.config.jcsy_config import JcsyParser
from bin.database.flight_add import FlightAdd
from bin.database.flight_get import FlightGet
from bin.database.flight_db import FlightDatabase
from src.ui.refresh_button import refresh_button


def import_button(jcsy_content: str, config_path: str = 'jcsy_config.yaml') -> str:
    """
    导入 JCSY 格式字符串到数据库的主要函数
    参数：
        jcsy_content: JCSY 格式的字符串内容
        config_path: JCSY 配置文件路径
    返回操作结果的字符串描述
    """
    if not jcsy_content or not jcsy_content.strip():
        return "Error: No JCSY content provided"
    # 测试并确保数据库存在
    db = FlightDatabase()
    if not db.connection:
        # 如果连接失败，尝试重新初始化数据库
        db.initialize_database()
        db.connect()
        if not db.connection:
            return "Error: Failed to initialize database"
    # 初始化 FlightAdd 实例
    flight_add = FlightAdd(config_path)
    # 解析并添加 JCSY 内容到数据库
    flight_ids = flight_add.add_jcsy_content(jcsy_content)
    if not flight_ids:
        return "Error: No flights were imported"
    # 统计导入结果
    header_count = 1  # 总是有一个 header
    flight_segments_count = len(flight_ids) - header_count
    # 生成详细的结果报告
    report_lines = [f"Import completed successfully"]
    report_lines.append(f"  Header records: {header_count}")
    report_lines.append(f"  Flight segments: {flight_segments_count}")
    report_lines.append(f"  Total records: {len(flight_ids)}")
    # 显示导入的航班 ID
    if flight_ids:
        report_lines.append(f"  Imported flight IDs: {', '.join(map(str, flight_ids))}")
    # 自动刷新航班时间数据
    report_lines.append("")
    report_lines.append("Starting automatic flight time refresh...")
    refresh_result = refresh_button(jcsy_content)
    report_lines.append(refresh_result)
    return '\n'.join(report_lines)

