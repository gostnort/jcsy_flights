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
        print("-" * 50)
        print("JCSY Content:")
        print(jcsy_content)
        print("-" * 50)
        # 替换 {{FLIGHT_DATE}} 为今天的日期
        today = datetime.date.today()
        today_ddmmm = today.strftime('%d%b').upper()
        jcsy_content = jcsy_content.replace("{{FLIGHT_DATE}}", today_ddmmm)
        print(f"Replaced {{FLIGHT_DATE}} with: {today_ddmmm}")
        print("-" * 50)
        # 调用 import_button 完成整个数据处理流程
        print("Starting import and refresh process...")
        print("=" * 50)
        result = import_button(jcsy_content)
        print("=" * 50)
        print("Final Result:")
        print(result)
        print("=" * 50)
        print("Test completed successfully!")
    except FileNotFoundError as e:
        print(f"File error: {e}")
    except Exception as e:
        print(f"Test failed with error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main() 