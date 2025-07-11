#!/usr/bin/env python3
"""
测试脚本：从 test_jcsy.txt 读取 JCSY 字符串并调用 import_button() 完成整个数据处理流程
"""

import os
import sys
import datetime

# 将项目根目录添加到 Python 路径
project_root = os.path.abspath(os.path.dirname(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ui.import_button import import_button
from bin.database.flight_get import FlightGet


def main():
    """
    主函数：读取 JCSY 文件并执行导入和刷新流程
    """
    # 检查 test_jcsy.txt 文件是否存在
    test_file_path = os.path.join(project_root, 'test_jcsy.txt')
    if not os.path.exists(test_file_path):
        print("Error: test_jcsy.txt not found in the root directory")
        print(f"Expected path: {test_file_path}")
        return
    try:
        # 读取 JCSY 内容
        print("Reading JCSY content from test_jcsy.txt...")
        with open(test_file_path, 'r', encoding='utf-8') as f:
            jcsy_content = f.read()
        if not jcsy_content.strip():
            print("Error: test_jcsy.txt is empty")
            return
        print("JCSY content loaded successfully")
        # 替换 {{FLIGHT_DATE}} 为今天的日期
        today = datetime.date.today()
        today_ddmmm = today.strftime('%d%b').upper()
        jcsy_content = jcsy_content.replace("{{FLIGHT_DATE}}", today_ddmmm)
        print(f"Replaced {{FLIGHT_DATE}} with: {today_ddmmm}")
        print("-" * 50)
        print("Processed JCSY Content:")
        print(jcsy_content)
        print("-" * 50)
        # 调用 import_button 完成整个数据处理流程
        print("Starting import and refresh process...")
        print("=" * 50)
        result = import_button(jcsy_content)
        print("=" * 50)
        print("Final Result:")
        print(result)
        print("=" * 50)
        # 验证数据库中的导入结果
        print("Verifying database import...")
        print("-" * 50)
        verify_database_import(today)
        print("=" * 50)
        print("Test completed successfully!")
    except FileNotFoundError as e:
        print(f"File error: {e}")
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()


def verify_database_import(flight_date: datetime.date):
    """
    验证数据库中的导入结果
    查询并显示 header flight 和相关的 flights
    """
    try:
        flight_get = FlightGet()
        # 使用 return_flight_id 方法查询 header flight
        header_flight = flight_get.return_flight_id('jcsy_flights', 'CA', '1234', flight_date)
        if header_flight:
            header_id = header_flight['id']
            print(f"Header flight ID: {header_id}")
            # 使用 FlightGet 方法查询相关的 flight segments
            flight_ids = flight_get.return_related_flights_IDs('query_flights', header_id)
            print(f"Related flight segments: {len(flight_ids)}")
            for flight_id in flight_ids:
                flight_data = flight_get.return_flight_data('query_flights', flight_id)
                if flight_data:
                    print(f"  Segment ID: {flight_id}, {flight_data.get('airline')}{flight_data.get('flight_number')}")
                    print(f"    Route: {flight_data.get('departure_airport')} -> {flight_data.get('arrival_airport')}")
                    print(f"    STD: {flight_data.get('std')}, STA: {flight_data.get('sta')}")
                    print(f"    Booked: {flight_data.get('booked_count_economy')}/{flight_data.get('booked_count_non_economy')}")
                    print(f"    Checked: {flight_data.get('checked_count_economy')}/{flight_data.get('checked_count_non_economy')}")
                    print(f"    Bags: {flight_data.get('bags_count_piece')} pieces, {flight_data.get('bags_count_weight')} kg")
        else:
            print("No header flight found")
    except Exception as e:
        print(f"Database verification failed: {e}")


if __name__ == "__main__":
    main() 