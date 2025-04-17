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

### 航班搜索能力 (0.31 edition)
- 支持FlightView搜索航班信息; FlightStats作为备用
- 支持查看进港和出港航班列表（以LAX为主场机场）
- 命令行窗口会显示更加详细的信息，包括网址，出发/到达时间

### 多线程处理 (0.41版本)
- 使用最多5个并行线程同时处理多个航班查询
- 增加进度条显示处理进度

