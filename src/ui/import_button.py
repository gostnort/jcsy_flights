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


def parse_std_datetime(std_text: str, base_date: datetime.date) -> datetime.datetime | None:
    """
    解析 STD 文本（HHMM 或 HHMM+D）为 datetime 对象
    如果解析失败则返回 None
    """
    if not std_text or not base_date:
        return None
    try:
        # 提取时间部分
        time_str = std_text[:4]
        hour = int(time_str[:2])
        minute = int(time_str[2:])
        # 处理日期偏移
        day_offset = 0
        if len(std_text) > 4 and std_text[4] == '+':
            day_offset = int(std_text[5:])
        # 创建日期时间对象
        dt = datetime.datetime(base_date.year, base_date.month, base_date.day, hour, minute)
        dt += datetime.timedelta(days=day_offset)
        return dt
    except ValueError:
        return None # 无效格式


def safe_int_convert(value_str: str | None) -> int | None:
    """安全地将字符串（可能为 None 或空）转换为 int，去除前导零"""
    if value_str is None or not str(value_str).strip():
        return 0 # 如果为空或 None 则默认为 0
    try:
        # 解析器应该基于 YAML 处理 trim_leading_zeros
        # 但作为保护措施或如果直接传递值：
        cleaned_value = str(value_str).lstrip('0')
        if not cleaned_value: # 如果全是零，例如 "000"
            return 0
        return int(cleaned_value)
    except ValueError:
        return 0 # 如果转换失败则默认为 0


def import_jcsy_data(jcsy_text_content: str):
    """
    解析 JCSY 格式的文本内容并将其存储在数据库中
    使用 FlightAdd 类来处理数据库操作
    """
    try:
        # 使用 FlightAdd 类来处理 JCSY 内容导入
        flight_add = FlightAdd()
        # 调用 add_jcsy_content 方法，它会处理所有数据库操作
        flight_ids = flight_add.add_jcsy_content(jcsy_text_content)
        # 检查返回的航班 ID
        if not flight_ids:
            return {"status": "error", "message": "导入失败：未返回任何航班 ID"}
        # 第一个 ID 是主航班记录，其余是查询航班记录
        header_flight_id = flight_ids[0]
        query_flight_count = len(flight_ids) - 1
        # 返回成功状态和消息
        return {
            "status": "success",
            "message": f"成功导入 JCSY 数据。主记录 ID: {header_flight_id}。处理了 {query_flight_count} 个航班段。"
        }
    except ValueError as e:
        # 处理解析错误
        return {"status": "error", "message": f"解析错误: {str(e)}"}
    except Exception as e:
        # 处理其他错误
        return {"status": "error", "message": f"导入过程中出错: {str(e)}"}


def import_jcsy_data_legacy(jcsy_text_content: str):
    """
    解析 JCSY 格式的文本内容并将其存储在数据库中
    这是重构后的旧方法实现，使用 FlightAdd 类而不是直接 SQL
    """
    try:
        # 使用与新方法相同的 FlightAdd 类，但保持单独的函数以便向后兼容
        flight_add = FlightAdd(config_path="jcsy_config.yaml")
        # 调用相同的 add_jcsy_content 方法处理数据
        flight_ids = flight_add.add_jcsy_content(jcsy_text_content)
        # 检查返回的航班 ID
        if not flight_ids:
            return {"status": "error", "message": "导入失败：未返回任何航班 ID"}
        # 处理结果，与原始实现保持一致的返回格式
        header_flight_id = flight_ids[0]
        num_flights_processed = len(flight_ids) - 1
        # 返回成功状态和消息
        return {
            "status": "success",
            "message": f"成功导入 JCSY 数据。主记录 ID: {header_flight_id}。处理了 {num_flights_processed} 个航班段。"
        }
    except ValueError as e:
        # 处理解析错误
        return {"status": "error", "message": f"解析错误: {str(e)}"}
    except Exception as e:
        # 处理其他错误
        return {"status": "error", "message": f"导入过程中出错: {str(e)}"}


if __name__ == '__main__':
    print("测试 import_button.py...")
    # 测试数据
    test_jcsy_content = """
JCSY:UA123/15JAN/LAX,O
FLT/ORIG   ARVL   BKD     CHK        UCK     NBRD       BAG
UA123 /SFO 0835  000/001 000/001+00 000/000 000/000+00 001/0016
UA123 /ORD 1200  000/002 000/002+00 000/000 000/000+00 002/0032
"""
    print("测试 JCSY 导入（新方法）...")
    result = import_jcsy_data(test_jcsy_content)
    print(f"结果: {result}")
    print("\n测试 JCSY 导入（旧方法）...")
    legacy_result = import_jcsy_data_legacy(test_jcsy_content)
    print(f"旧方法结果: {legacy_result}")
    # 测试错误情况
    print("\n测试错误情况...")
    error_result = import_jcsy_data("无效的 JCSY 内容")
    print(f"错误结果: {error_result}")
