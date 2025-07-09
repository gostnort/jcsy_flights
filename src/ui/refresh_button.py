# src/ui/refresh_button.py
import os
import sys
import datetime
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from threading import Lock
from bin.database.flight_add import FlightAdd
from bin.database.flight_get import FlightGet
from bin.scrapers.flightview_crawler import FlightViewCrawler
from bin.scrapers.flightview_crawler import return_structure as FlightViewReturnStructure
from bin.scrapers.flightstats_crawler import FlightStatsScraper


def refresh_button(jcsy_text: str | None = None, max_workers: int = 3, timeout_seconds: int = 30) -> str:
    """
    刷新航班数据的主要函数
    如果提供了 header_text，则刷新特定航班，否则刷新今天的航班
    参数：
        jcsy_text: JCSY 头部文本，如果提供则刷新特定航班
        max_workers: 最大并发工作线程数
        timeout_seconds: 每个爬虫调用的超时时间
    返回操作结果的字符串描述
    """
    header_details = None
    if jcsy_text:
        header_details = _parse_jcsy_header_for_refresh(jcsy_text)
        if not header_details:
            return f"Failed to parse header text: {jcsy_text}"
    flights_to_refresh = _get_flights_to_refresh(header_details)
    if isinstance(flights_to_refresh, str):
        return flights_to_refresh
    if not flights_to_refresh:
        return "No flights found to refresh"
    print(f"Starting refresh of {len(flights_to_refresh)} flights using {max_workers} concurrent threads...")
    worker = FlightRefreshWorker(max_workers=max_workers, timeout_seconds=timeout_seconds)
    results = []
    for flight_info in flights_to_refresh:
        result = worker.process_single_flight(flight_info)
        results.append(result)
        print(f"Processing result: {result['status']} - {result['message']}")
    status_counts = {}
    for result in results:
        status = result.get('status', 'unknown')
        status_counts[status] = status_counts.get(status, 0) + 1
    report_lines = [f"Refresh completed: Processed {len(results)} flights"]
    for status, count in status_counts.items():
        status_names = {'success': 'Success', 'no_data': 'No Data', 'db_error': 'Database Error', 'error': 'Processing Error'}
        report_lines.append(f"  {status_names.get(status, status)}: {count} flights")
    successful_sources = [r.get('source') for r in results if r.get('status') == 'success' and r.get('source')]
    if successful_sources:
        source_counts = {}
        for source in successful_sources:
            source_counts[source] = source_counts.get(source, 0) + 1
        report_lines.append("Data source statistics:")
        for source, count in source_counts.items():
            source_names = {'flightview': 'FlightView', 'flightstats': 'FlightStats'}
            report_lines.append(f"  {source_names.get(source, source)}: {count} flights")
    return '\n'.join(report_lines)


def _parse_jcsy_header_for_refresh(jcsy_with_header_text: str) -> dict | None:
    """
    解析类似 JCSY 的头部字符串以提取航班识别详情
    返回包含 'airline'、'flight_number'、'date'（datetime.date）、
    'airport'（如果存在）的字典，如果解析失败则返回 None
    """
    if not jcsy_with_header_text:
        return None
    lines = jcsy_with_header_text.strip().split('\n')
    jcsy_line = None
    for line in lines:
        line = line.strip()
        if line and ('JCSY:' in line):
            jcsy_line = line
            break
    if not jcsy_line:
        return None
    JCSY_HEADER_PATTERN = re.compile(r"^(?:JCSY:)?(?P<airline>[A-Z0-9]{2})(?P<flight_number>\d+)/(?P<flight_date_str>\d+[A-Z]{3})(?:/(?P<airport>[A-Z]{3})(?:,(?P<inbound_flag>[IO]))?)?")
    match = JCSY_HEADER_PATTERN.match(jcsy_line.upper())
    if not match:
        return None
    details = match.groupdict()
    parsed = {"airline": details["airline"], "flight_number": details["flight_number"], "airport": details.get("airport")}
    date_str = details["flight_date_str"]
    if date_str == "{{FLIGHT_DATE}}":
        parsed["date"] = datetime.date.today()
    else:
        try:
            if len(date_str) > 5:
                parsed["date"] = datetime.datetime.strptime(date_str, "%d%b%y").date()
            else:
                parsed["date"] = datetime.datetime.strptime(date_str, "%d%b").date().replace(year=datetime.datetime.now().year)
        except ValueError:
            return None
    return parsed


def _get_flights_to_refresh(header_details: dict | None) -> list[dict]:
    """
    从数据库获取需要刷新的航班记录
    如果提供了 header_details，则获取该特定航班
    否则，获取今天的航班
    返回航班记录列表（作为字典）或错误消息字符串
    """
    flights_to_check = []
    flight_get = FlightGet()
    if header_details:
        jcsy_flight_id_row = flight_get.return_flight_id('jcsy_flights', header_details['airline'], header_details['flight_number'], header_details['date'])
        if not jcsy_flight_id_row:
            return "Flight not found based on header"
        jcsy_flight_id = jcsy_flight_id_row[0]
        flight_ids = flight_get.return_related_flights_IDs('query_flights', jcsy_flight_id)
        if not flight_ids:
            return "No segments found for specified flight header"
        for flight_id in flight_ids:
            flight_data = flight_get.return_flight_data('query_flights', flight_id)
            if flight_data:
                jcsy_flight_data = flight_get.return_flight_data('jcsy_flights', jcsy_flight_id)
                if jcsy_flight_data:
                    flight_data['inbound_not'] = jcsy_flight_data.get('inbound_not')
                    flight_data['jf_dep'] = jcsy_flight_data.get('departure_airport')
                    flight_data['jf_arr'] = jcsy_flight_data.get('arrival_airport')
                flights_to_check.append(flight_data)
    else:
        today_date = datetime.date.today()
        flight_get.db.connect()
        flight_get.db.cursor.execute('SELECT id FROM jcsy_flights WHERE flight_date = ?', (today_date.strftime('%Y-%m-%d'),))
        jcsy_flights = flight_get.db.cursor.fetchall()
        for jcsy_flight_row in jcsy_flights:
            jcsy_flight_id = jcsy_flight_row[0]
            flight_ids = flight_get.return_related_flights_IDs('query_flights', jcsy_flight_id)
            for flight_id in flight_ids:
                flight_data = flight_get.return_flight_data('query_flights', flight_id)
                if flight_data:
                    jcsy_flight_data = flight_get.return_flight_data('jcsy_flights', jcsy_flight_id)
                    if jcsy_flight_data:
                        flight_data['inbound_not'] = jcsy_flight_data.get('inbound_not')
                        flight_data['jf_dep'] = jcsy_flight_data.get('departure_airport')
                        flight_data['jf_arr'] = jcsy_flight_data.get('arrival_airport')
                    flights_to_check.append(flight_data)
    return flights_to_check


class FlightRefreshWorker:
    """
    航班刷新工作器，处理单个航班的爬虫调用和数据库更新
    使用线程池和超时机制来处理网络延迟
    """
    
    def __init__(self, max_workers=3, timeout_seconds=30):
        self.max_workers = max_workers
        self.timeout_seconds = timeout_seconds
        self.executor = ThreadPoolExecutor(max_workers=max_workers)
        self.results_lock = Lock()
        self.results = []
        self.flightview_crawler = FlightViewCrawler()
        self.flightstats_crawler = FlightStatsScraper()
        self.flight_add = FlightAdd()
        self.flight_get = FlightGet()
    
    def __del__(self):
        """清理资源"""
        if hasattr(self, 'executor'):
            self.executor.shutdown(wait=False)
    
    def call_crawler_with_timeout(self, crawler_function, args, timeout_seconds=None):
        """
        在单独的线程中调用爬虫函数并设置超时
        参数：
            crawler_function: 要调用的爬虫函数
            args: 爬虫函数的参数元组
            timeout_seconds: 超时秒数
        返回：
            来自爬虫的结果，如果超时或错误则返回 None
        """
        if timeout_seconds is None:
            timeout_seconds = self.timeout_seconds
        future = self.executor.submit(crawler_function, *args)
        try:
            result = future.result(timeout=timeout_seconds)
            return result
        except FuturesTimeoutError:
            print(f"Crawler {crawler_function.__name__} timed out after {timeout_seconds} seconds")
            future.cancel()
            return None
        except Exception as e:
            print(f"Crawler {crawler_function.__name__} failed: {e}")
            return None
    
    def get_flight_data_from_multiple_sources(self, flight_info):
        """
        从多个数据源获取航班数据，优先使用 FlightView，然后尝试 FlightStats
        参数：
            flight_info: 包含航班信息的字典
        返回：
            包含航班数据的字典或 None
        """
        airline = flight_info.get('airline')
        flight_number = flight_info.get('flight_number')
        flight_date = flight_info.get('flight_date')
        departure_airport = flight_info.get('departure_airport')
        arrival_airport = flight_info.get('arrival_airport')
        print(f"Attempting to get {airline}{flight_number} data from FlightView...")
        flightview_data = self.call_crawler_with_timeout(self.flightview_crawler.get_flight_info, (airline, flight_number, flight_date, departure_airport, arrival_airport), 20)
        if flightview_data and hasattr(flightview_data, 'std'):
            print(f"Successfully retrieved {airline}{flight_number} data from FlightView")
            return {'source': 'flightview', 'data': flightview_data, 'success': True}
        print(f"FlightView failed, attempting to get {airline}{flight_number} data from FlightStats...")
        try:
            date_str = flight_date.strftime('%Y%m%d') if isinstance(flight_date, datetime.date) else str(flight_date)
            flightstats_data = self.call_crawler_with_timeout(self.flightstats_crawler.get_flight_info, (airline, flight_number, date_str), 25)
            if flightstats_data:
                print(f"Successfully retrieved {airline}{flight_number} data from FlightStats")
                return {'source': 'flightstats', 'data': flightstats_data, 'success': True}
        except Exception as e:
            print(f"FlightStats call failed: {e}")
        print(f"Unable to retrieve {airline}{flight_number} data from any source")
        return {'source': 'none', 'data': None, 'success': False}
    
    def _update_flight_in_db(self, query_flight_id: int, crawler_result: dict):
        """
        使用来自爬虫的新时间数据更新指定的 query_flight 记录
        支持 FlightView 和 FlightStats 两种数据格式
        """
        if not crawler_result or not crawler_result.get('success'):
            print(f"No valid crawler data provided to update query_flight_id {query_flight_id}")
            return False
        source = crawler_result.get('source')
        data = crawler_result.get('data')
        update_fields = {'table': 'query_flights', 'id': query_flight_id}
        try:
            if source == 'flightview':
                fields_to_update = ['std', 'etd', 'atd', 'sta', 'eta', 'ata']
                for field in fields_to_update:
                    value = getattr(data, field, None)
                    if value is not None:
                        update_fields[field] = value
            elif source == 'flightstats':
                dep_info = data.get('departure', {})
                arr_info = data.get('arrival', {})
                field_mapping = {'scheduled': 'std', 'estimated': 'etd', 'actual': 'atd'}
                for fs_field, db_field in field_mapping.items():
                    value = dep_info.get(fs_field)
                    if value and value != 'N/A':
                        update_fields[db_field] = value
                field_mapping_arr = {'scheduled': 'sta', 'estimated': 'eta', 'actual': 'ata'}
                for fs_field, db_field in field_mapping_arr.items():
                    value = arr_info.get(fs_field)
                    if value and value != 'N/A':
                        update_fields[db_field] = value
            if len(update_fields) <= 2:
                print(f"No valid data to update query_flight_id {query_flight_id}")
                return False
            self.flight_add.update_flight(update_fields)
            print(f"Successfully updated {len(update_fields) - 2} fields for query_flight_id {query_flight_id} (source: {source})")
            return True
        except Exception as e:
            print(f"Error updating query_flight_id {query_flight_id}: {e}")
            return False
    
    def process_single_flight(self, flight_info: dict):
        """
        处理单个航班的刷新
        返回处理结果字典
        """
        flight_id = flight_info.get('id')
        airline = flight_info.get('airline')
        flight_number = flight_info.get('flight_number')
        if not all([flight_id, airline, flight_number]):
            return {'status': 'error', 'flight_id': flight_id, 'message': 'Missing required flight information', 'airline': airline, 'flight_number': flight_number}
        try:
            crawler_result = self.get_flight_data_from_multiple_sources(flight_info)
            if crawler_result.get('success'):
                update_success = self._update_flight_in_db(flight_id, crawler_result)
                if update_success:
                    return {'status': 'success', 'flight_id': flight_id, 'message': f'Successfully updated {airline}{flight_number} from {crawler_result["source"]}', 'airline': airline, 'flight_number': flight_number, 'source': crawler_result['source']}
                else:
                    return {'status': 'db_error', 'flight_id': flight_id, 'message': f'Data retrieved successfully but database update failed for {airline}{flight_number}', 'airline': airline, 'flight_number': flight_number}
            else:
                return {'status': 'no_data', 'flight_id': flight_id, 'message': f'Unable to retrieve data from any source for {airline}{flight_number}', 'airline': airline, 'flight_number': flight_number}
        except Exception as e:
            return {'status': 'error', 'flight_id': flight_id, 'message': f'Error processing {airline}{flight_number}: {str(e)}', 'airline': airline, 'flight_number': flight_number}


def test():
    """
    测试函数，调用 _parse_jcsy_header_for_refresh 并打印结果
    从根目录读取 test_jcsy.txt 作为测试用例
    """
    try:
        with open('test_jcsy.txt', 'r', encoding='utf-8') as f:
            test_string = f.read()
    except FileNotFoundError:
        print("test_jcsy.txt not found, please place it in the project root directory.")
        return
    # 替换 {{FLIGHT_DATE}} 为今天的 DDMMM 格式
    today = datetime.date.today()
    today_ddmmm = today.strftime('%d%b').upper()
    test_string = test_string.replace("{{FLIGHT_DATE}}", today_ddmmm)
    result = _parse_jcsy_header_for_refresh(test_string)
    print(result)


if __name__ == "__main__":
    # 运行测试
    test()