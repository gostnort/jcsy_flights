### 设置虚拟环境
`python -m venv .venv`

### 激活虚拟环境
`./.venv/scripts/activate`

### 安装库
`pip install -r requirements.txt`

### 启动窗口
`python main.py`

### 创建快捷方式
为了避免看到命令行窗口，快捷方式可以使用
`pythonw.exe main.py`

## 新功能

### 版本 0.51
- 代码格式标准化：
  - 类之间保持3个空行
  - 函数之间保持2个空行
  - 函数内部没有空行，使用中文注释分隔逻辑块
- 重构数据库操作：
  - 使用 FlightAdd.add_jcsy_content() 替代直接 SQL 操作
  - 使用 FlightAdd.update_flight() 更新航班信息
  - 使用 FlightGet 类方法获取航班数据
- 翻译所有注释为中文
- 改进代码结构和导入组织

### 航班搜索能力
- 支持通过FlightStats和FlightView搜索航班信息
- 支持查看进港和出港航班列表（以LAX为主场机场）
- 显示航班元数据和详细信息，包括出发/到达时间
- 改进的航班状态提取
- 更准确的航班时间信息提取