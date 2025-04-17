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

### 航班搜索能力
- 支持通过FlightStats和FlightView搜索航班信息
- 支持查看进港和出港航班列表（以LAX为主场机场）
- 显示航班元数据和详细信息，包括出发/到达时间
- 改进的航班状态提取
- 更准确的航班时间信息提取