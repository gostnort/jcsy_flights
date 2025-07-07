# src/ui/refresh_button.py

import sys
import os
import datetime
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
# 数据库导入
from bin.database.flight_add import FlightAdd
from bin.database.flight_get import FlightGet
# 爬虫导入
from bin.scrapers.flightview_crawler import FlightViewCrawler
from bin.scrapers.flightview_crawler import return_structure as CrawlerReturnStructure

# 将项目根目录添加到 Python 路径
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
# JCSY 头部解析逻辑的占位符（类似于 JcsyParser 中的内容）
# 基于 'JCSY:CA0984/12DEC/LAX,I' 格式的简化正则表达式
JCSY_HEADER_PATTERN = re.compile(r"^(?:JCSY:)?(?P<airline>[A-Z0-9]{2})(?P<flight_number>\d+)/(?P<flight_date_str>\d+[A-Z]{3})(?:/(?P<airport>[A-Z]{3})(?:,(?P<inbound_flag>[IO]))?)?")


def parse_jcsy_header_for_refresh(header_text: str) -> dict | None:
    """
    解析类似 JCSY 的头部字符串以提取航班识别详情
    返回包含 'airline'、'flight_number'、'date'（datetime.date）、
    'airport'（如果存在）的字典，如果解析失败则返回 None
    日期解析已简化，如果年份不在 DDMMM 格式中则假设为当前年份
    """
    match = JCSY_HEADER_PATTERN.match(header_text.upper())
    if not match:
        return None
    # 获取匹配的详细信息
    details = match.groupdict()
    parsed = {
        "airline": details["airline"],
        "flight_number": details["flight_number"],
        "airport": details.get("airport") # 如果不在 header_text 中可能为 None
    }
    # 解析日期字符串
    date_str = details["flight_date_str"]
    try:
        # 尝试 DDMMMYY 或 DDMMM
        if len(date_str) > 5: # DDMMMYY 例如 12DEC24
            parsed["date"] = datetime.datetime.strptime(date_str, "%d%b%y").date()
        else: # DDMMM 例如 12DEC，假设为当前年份
            parsed["date"] = datetime.datetime.strptime(date_str, "%d%b").date().replace(year=datetime.datetime.now().year)
    except ValueError:
        return None # 无效的日期格式
    return parsed


def call_crawler_with_timeout(crawler_function, args, timeout_seconds):
    """
    在单独的线程中调用爬虫函数并设置超时
    参数：
        crawler_function: 要调用的爬虫函数
        args: 爬虫函数的参数元组
        timeout_seconds: 超时秒数
    返回：
        来自爬虫的结果，如果超时或错误则返回 None
    """
    # 注意：在 Python 中强制终止线程很棘手
    # ThreadPoolExecutor 在 future.result() 上的超时不会杀死线程，
    # 它只是停止等待。线程可能会继续运行
    # 对于真正的进程终止，可能需要多进程，
    # 但这增加了数据共享的复杂性
    # 现在，我们依赖爬虫表现良好或超时
    # 只是防止主逻辑等待太久
    # 创建线程池执行器
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(crawler_function, *args)
    try:
        result = future.result(timeout=timeout_seconds)
        return result
    except FuturesTimeoutError:
        print(f"爬虫 {crawler_function.__name__} 在 {timeout_seconds} 秒后超时")
        # 尝试取消 future，虽然它可能不会停止正在运行的线程
        future.cancel()
        return None
    except Exception as e:
        print(f"爬虫 {crawler_function.__name__} 失败: {e}")
        return None
    finally:
        executor.shutdown(wait=False) # 如果任务卡住，不要等待任务完成


def _get_flights_to_refresh(header_details: dict | None) -> list[dict]:
    """
    从数据库获取需要刷新的航班记录
    如果提供了 header_details，则获取该特定航班
    否则，获取今天的航班
    返回航班记录列表（作为字典）或错误消息字符串
    """
    flights_to_check = []
    # 初始化数据库访问类
    flight_get = FlightGet()
    # 检查是否有特定航班需要刷新
    if header_details:
        # 使用 flight_get.return_flight_id 查找航班 ID
        jcsy_flight_id_row = flight_get.return_flight_id(
            'jcsy_flights',
            header_details['airline'],
            header_details['flight_number'],
            header_details['date']
        )
        # 检查是否找到记录
        if not jcsy_flight_id_row:
            return "基于头部未找到航班"
        # 获取航班 ID
        jcsy_flight_id = jcsy_flight_id_row[0]
        # 使用 flight_get.return_related_flights_IDs 获取关联的航班段
        flight_ids = flight_get.return_related_flights_IDs('query_flights', jcsy_flight_id)
        # 检查是否找到段
        if not flight_ids:
            return "未找到指定航班头部的段"
        # 获取每个航班段的详细信息
        for flight_id in flight_ids:
            flight_data = flight_get.return_flight_data('query_flights', flight_id)
            if flight_data:
                # 添加主航班信息
                jcsy_flight_data = flight_get.return_flight_data('jcsy_flights', jcsy_flight_id)
                if jcsy_flight_data:
                    flight_data['inbound_not'] = jcsy_flight_data.get('inbound_not')
                    flight_data['jf_dep'] = jcsy_flight_data.get('departure_airport')
                    flight_data['jf_arr'] = jcsy_flight_data.get('arrival_airport')
                flights_to_check.append(flight_data)
    else:
        # 查询今天的航班
        today_date = datetime.date.today()
        # 获取所有今天的主航班记录
        flight_get.db.connect()
        flight_get.db.cursor.execute(
            'SELECT id FROM jcsy_flights WHERE flight_date = ?',
            (today_date.strftime('%Y-%m-%d'),)
        )
        jcsy_flights = flight_get.db.cursor.fetchall()
        # 对于每个主航班，获取关联的航班段
        for jcsy_flight_row in jcsy_flights:
            jcsy_flight_id = jcsy_flight_row[0]
            flight_ids = flight_get.return_related_flights_IDs('query_flights', jcsy_flight_id)
            for flight_id in flight_ids:
                flight_data = flight_get.return_flight_data('query_flights', flight_id)
                if flight_data:
                    # 添加主航班信息
                    jcsy_flight_data = flight_get.return_flight_data('jcsy_flights', jcsy_flight_id)
                    if jcsy_flight_data:
                        flight_data['inbound_not'] = jcsy_flight_data.get('inbound_not')
                        flight_data['jf_dep'] = jcsy_flight_data.get('departure_airport')
                        flight_data['jf_arr'] = jcsy_flight_data.get('arrival_airport')
                    flights_to_check.append(flight_data)
    # 返回需要检查的航班列表
    return flights_to_check


def _update_flight_in_db(query_flight_id: int, crawler_data: CrawlerReturnStructure):
    """
    使用来自 crawler_data 的新时间数据更新指定的 query_flight 记录
    使用 FlightAdd.update_flight 方法而不是直接 SQL
    """
    if not crawler_data:
        print(f"没有为 query_flight_id {query_flight_id} 提供爬虫数据来更新")
        return
    # 初始化 FlightAdd 类
    flight_add = FlightAdd()
    # 准备更新字段
    update_fields = {
        'table': 'query_flights',
        'id': query_flight_id
    }
    # 将 CrawlerReturnStructure 的属性映射到数据库列
    fields_to_update = ['std', 'etd', 'atd', 'sta', 'eta', 'ata']
    # 添加有值的字段到更新字典
    for field in fields_to_update:
        value = getattr(crawler_data, field, None)
        if value is not None:
            update_fields[field] = value
    # 检查是否有字段需要更新
    if len(update_fields) <= 2:  # 只有 table 和 id
        print(f"没有有效数据要更新 query_flight_id {query_flight_id}")
        return
    # 使用 FlightAdd.update_flight 方法更新数据库
    try:
        flight_add.update_flight(update_fields)
        print(f"成功更新 query_flight_id {query_flight_id} 的 {len(update_fields) - 2} 个字段")
    except Exception as e:
        print(f"更新 query_flight_id {query_flight_id} 时出错: {e}")


def refresh_flight_data(header_text: str | None = None) -> str:
    """
    刷新航班数据的主要函数
    如果提供了 header_text，则刷新特定航班
    否则刷新今天的航班
    返回操作结果的字符串描述
    """
    try:
        # 解析头部（如果提供）
        header_details = None
        if header_text:
            header_details = parse_jcsy_header_for_refresh(header_text)
            if not header_details:
                return f"无法解析头部文本: {header_text}"
        # 获取需要刷新的航班
        flights_to_refresh = _get_flights_to_refresh(header_details)
        if isinstance(flights_to_refresh, str): # 错误消息
            return flights_to_refresh
        # 检查是否有航班需要刷新
        if not flights_to_refresh:
            return "没有找到需要刷新的航班"
        # 处理每个航班
        results_log = []
        for flight_info in flights_to_refresh:
            _process_single_flight_refresh(flight_info, results_log)
        # 汇总结果
        success_count = sum(1 for result in results_log if result.get('status') == 'success')
        total_count = len(results_log)
        return f"刷新完成: {success_count}/{total_count} 个航班成功更新"
    except Exception as e:
        return f"刷新过程中出错: {str(e)}"


def _process_single_flight_refresh(flight_info: dict, results_log: list):
    """
    处理单个航班的刷新
    更新 results_log 列表而不是返回结果
    """
    flight_id = flight_info.get('id')
    airline = flight_info.get('airline')
    flight_number = flight_info.get('flight_number')
    flight_date = flight_info.get('flight_date')
    departure_airport = flight_info.get('departure_airport')
    arrival_airport = flight_info.get('arrival_airport')
    # 检查必要信息是否存在
    if not all([flight_id, airline, flight_number, flight_date]):
        results_log.append({
            'status': 'error',
            'flight_id': flight_id,
            'message': '缺少必要的航班信息'
        })
        return
    # 尝试从 FlightView 获取数据
    try:
        crawler = FlightViewCrawler()
        crawler_data = call_crawler_with_timeout(
            crawler.get_flight_info,
            (airline, flight_number, flight_date, departure_airport, arrival_airport),
            30 # 30 秒超时
        )
        # 检查爬虫是否返回数据
        if crawler_data:
            # 更新数据库
            _update_flight_in_db(flight_id, crawler_data)
            results_log.append({
                'status': 'success',
                'flight_id': flight_id,
                'message': f'成功从 FlightView 更新 {airline}{flight_number}'
            })
        else:
            results_log.append({
                'status': 'error',
                'flight_id': flight_id,
                'message': f'无法从 FlightView 获取 {airline}{flight_number} 的数据'
            })
    except Exception as e:
        results_log.append({
            'status': 'error',
            'flight_id': flight_id,
            'message': f'处理 {airline}{flight_number} 时出错: {str(e)}'
        })
