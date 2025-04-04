### 设置虚拟环境
`python -m venv .venv`

### 激活虚拟环境
`./.venv/scripts/activate`

### 安装库
`pip install -r requirements.txt`

### 启动应用
#### 顺序处理版本（Sequential Processing Version）
`python main.py`

#### 并行处理版本（Parallel Processing Version）
`python parallel_main.py`

### 创建快捷方式
为了避免看到命令行窗口，快捷方式可以使用：
- 顺序处理版本: `pythonw.exe main.py`
- 并行处理版本: `pythonw.exe parallel_main.py`

### 版本特点
#### 顺序处理版本 (v0.3)
- 一次处理一个航班
- 每个结果需要手动接受或拒绝

#### 并行处理版本 (v0.4)
- 同时处理最多5个航班
- 自动接受结果
- 带有进度条的用户界面
- 显著提高处理速度

