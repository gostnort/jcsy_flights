import sys # 用于路径操作
import os  # 用于路径操作
import time
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QHBoxLayout,
                               QRadioButton, QButtonGroup, QStackedWidget,
                               QPushButton, QFrame, QLabel, QSizePolicy, QApplication)
from PySide6.QtCore import (Qt, QRect, QEvent, QPoint, Signal, 
                          QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QTimer, QObject)
from PySide6.QtGui import QFont, QCursor, QPalette, QMouseEvent
from bin.database.flight_get import FlightGet
from bin.processors.radio_view import ViewModeHandler # 添加导入

_EDIT_FONT = QFont("Courier New", 11)
_VIEW_FONT = QFont("Courier New", 11)
_TABLE_CSS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "table_styles.css")# 来自外部文件的表格边框默认 CSS
_RADIO_HEIGHT = 20


class MarkdownViewer(QTextEdit):
    def __init__(self):
        super().__init__()
        # 使查看器只读 - 这意味着用户无法编辑文本但仍可以选择和复制
        self.setReadOnly(True)
        # 使用与编辑器相同的字体以保持一致性 - 更新的字体
        self.setFont(_VIEW_FONT)
        self.setFrameStyle(QFrame.NoFrame) # 移除边框
        try:
            with open(_TABLE_CSS_FILE, "r") as f:
                table_css = f.read()
            self.document().setDefaultStyleSheet(table_css)
        except FileNotFoundError as e:
            print(f"警告: 在 {_TABLE_CSS_FILE} 未找到 CSS 文件。表格样式将不会应用。\n {e}")
            # 可选地，如果文件很关键，在这里定义内联备用 CSS
            fallback_css = """ 
            table { border-collapse: collapse; border: 1px solid black; } 
            th, td { border: 1px solid black; padding: 4px; text-align: left; } 
            th { background-color: #f0f0f0; } 
            """ 
            self.document().setDefaultStyleSheet(fallback_css) 


    def setMarkdownText(self, text):
        # 实际的 markdown 渲染现在由 ViewModeHandler 处理
        # 此方法只是设置给它的 HTML 内容
        self.setHtml(text)



class ControlPanel(QFrame):
    modeChanged = Signal(int)  # 用于编辑/查看模式
    EXPANDED_WIDTH = 150
    COLLAPSED_WIDTH = 45

    def __init__(self, parent=None):
        super().__init__(parent)
        control_panel_layout = QVBoxLayout(self)
        control_panel_layout.setContentsMargins(5, 5, 5, 5) # 为折叠状态减少边距
        control_panel_layout.setSpacing(8) # 为更紧密的折叠外观减少间距
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("ControlPanel")
        #self.setStyleSheet("ControlPanel { border-left: 1px solid palette(mid); background-color: palette(window); }") # 可选样式
        self._is_expanded = False # 开始折叠
        self.expanded_width = self.EXPANDED_WIDTH
        self.collapsed_width = self.COLLAPSED_WIDTH
        self.animation_duration = 250 # 毫秒
        # 单选按钮布局
        self.radio_layout_widget = QWidget()
        radio_layout = QVBoxLayout(self.radio_layout_widget)
        radio_layout.setContentsMargins(0,0,0,0) # 上、左、右、下
        self.edit_mode_radio = QRadioButton("编辑")
        self.edit_mode_radio.setFixedHeight(_RADIO_HEIGHT)
        self.view_mode_radio = QRadioButton("查看")
        self.view_mode_radio.setFixedHeight(_RADIO_HEIGHT)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.edit_mode_radio, 0)
        self.mode_group.addButton(self.view_mode_radio, 1)
        self.edit_mode_radio.setChecked(True)
        radio_layout.addWidget(self.edit_mode_radio)
        radio_layout.addWidget(self.view_mode_radio)
        radio_layout.addStretch()
        control_panel_layout.addWidget(self.radio_layout_widget) # 折叠时将被隐藏
        control_panel_layout.addStretch(1) # 这将把单选按钮向上推，操作按钮向下推
        # 连接 modeChanged 信号以发出 modeChanged 信号
        self.mode_group.idClicked.connect(self.modeChanged.emit)
        # 按钮
        self.action_buttons_widget = QWidget() # 用于容纳操作按钮的小部件
        action_buttons_layout = QVBoxLayout(self.action_buttons_widget)
        action_buttons_layout.setContentsMargins(0,0,0,0)
        action_buttons_layout.setSpacing(2)
        self.btn_import = QPushButton("导入")
        self.btn_fresh = QPushButton("刷新")
        self.btn_output = QPushButton("输出")
        self.btn_print = QPushButton("打印")
        self.action_buttons_list = [self.btn_import, self.btn_fresh, self.btn_output, self.btn_print]
        self._button_original_texts = {btn: btn.text() for btn in self.action_buttons_list}
        self._radio_original_texts = {self.edit_mode_radio: self.edit_mode_radio.text(), self.view_mode_radio: self.view_mode_radio.text()}
        # 定义按钮的折叠宽度
        for btn in self.action_buttons_list:
            action_buttons_layout.addWidget(btn)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(30) # 折叠时更小的按钮
            btn.setMinimumWidth(self.collapsed_width - 10) # 确保它们适合折叠宽度
        control_panel_layout.addWidget(self.action_buttons_widget) # 在底部添加操作按钮容器
        # 动画
        self.animation_group = QParallelAnimationGroup(self)
        self.min_width_anim = QPropertyAnimation(self, b"minimumWidth")
        self.max_width_anim = QPropertyAnimation(self, b"maximumWidth")
        for anim in [self.min_width_anim, self.max_width_anim]:
            anim.setDuration(self.animation_duration)
            anim.setEasingCurve(QEasingCurve.InOutQuad)
            self.animation_group.addAnimation(anim)
        self.animation_group.finished.connect(self._post_animation_update)
        #self._update_visual_state_immediately() # 正确设置初始折叠状态


    def mousePressEvent(self, event: QEvent):
        super().mousePressEvent(event) # 首先传递给子项
        if event.isAccepted(): return


    def animate_expand(self):
        # 检查动画是否已经在运行，或者如果它已经在展开宽度，因为我们不想再次动画它
        if self._is_expanded and (self.animation_group.state() == QParallelAnimationGroup.Running and self.min_width_anim.endValue() == self.expanded_width):
            return
        if self._is_expanded and self.animation_group.state() == QParallelAnimationGroup.Stopped:
            return
        self._is_expanded = True
        # 将宽度动画到展开宽度
        self.min_width_anim.setStartValue(self.width())
        self.min_width_anim.setEndValue(self.expanded_width)
        self.max_width_anim.setStartValue(self.width())
        self.max_width_anim.setEndValue(self.expanded_width)
        self.animation_group.start()


    def animate_collapse(self):
        if not self._is_expanded and (self.animation_group.state() == QParallelAnimationGroup.Running and self.min_width_anim.endValue() == self.collapsed_width):
            return
        if not self._is_expanded and self.animation_group.state() == QParallelAnimationGroup.Stopped:
            return
        self._is_expanded = False
        self._update_content_visibility_and_text(False) # 在动画前隐藏内容
        self.min_width_anim.setStartValue(self.width())
        self.min_width_anim.setEndValue(self.collapsed_width)
        self.max_width_anim.setStartValue(self.width())
        self.max_width_anim.setEndValue(self.collapsed_width)
        self.animation_group.start()


    def _post_animation_update(self):
        current_target_width = self.expanded_width if self._is_expanded else self.collapsed_width
        self.setFixedWidth(current_target_width)
        if self._is_expanded:
            self._update_content_visibility_and_text(True)
        else: # 折叠状态
            self._update_content_visibility_and_text(False)


    def _update_content_visibility_and_text(self, expanded):
        #self.radio_layout_widget.setVisible(expanded)
        # 操作按钮小部件始终可见，其内容（文本）会改变
        if not self.action_buttons_widget.isVisible(): self.action_buttons_widget.show()
        for btn in self.action_buttons_list:
            original_text = self._button_original_texts.get(btn, "")
            if expanded:
                btn.setText(original_text)
                btn.setToolTip("")
            else:
                btn.setText("")
                btn.setToolTip(original_text)
        for radio, text in self._radio_original_texts.items():
            radio.setText(text if expanded else "")


    def _update_visual_state_immediately(self): # 用于初始设置
        self.setFixedWidth(self.expanded_width if self._is_expanded else self.collapsed_width)
        # 此调用现在将正确设置操作按钮（可见但无文本）
        # 并为初始折叠状态隐藏 radio_layout_widget
        self._update_content_visibility_and_text(self._is_expanded)



class Window(QWidget):
    _WINDOW_WIDTH = 800
    _WINDOW_HEIGHT = 600
    _EDIT_MODE = 0
    _VIEW_MODE = 1
    _HOVER_CHECK_INTERVAL = 0.1 # 悬停检查之间的秒数 - 调整回 0.1 秒

    def __init__(self):
        super().__init__()
        self._last_hover_check_time = 0 # 初始化悬停检查时间
        self.setWindowTitle("JCSY 航班 0.5")
        screen = QApplication.primaryScreen()
        # 默认在屏幕右下角开始位置
        self.setGeometry(screen.availableGeometry().x() + screen.availableGeometry().width() - self._WINDOW_WIDTH, 
                  screen.availableGeometry().y() + screen.availableGeometry().height() - self._WINDOW_HEIGHT,
                  self._WINDOW_WIDTH,
                  self._WINDOW_HEIGHT)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        # 控制面板
        self.control_panel = ControlPanel(self)
        main_layout.addWidget(self.control_panel)
        # 堆叠小部件用于编辑器和查看器
        self.stacked_widget = QStackedWidget()
        # 编辑器
        self.editor = QTextEdit()
        self.editor.setFont(_EDIT_FONT)
        self.editor.setFrameStyle(QFrame.NoFrame)
        self.stacked_widget.addWidget(self.editor)
        # 查看器
        self.viewer = MarkdownViewer()
        self.stacked_widget.addWidget(self.viewer)
        main_layout.addWidget(self.stacked_widget)
        # 连接信号
        self.control_panel.modeChanged.connect(self._handle_mode_change)
        # 连接按钮信号
        self.control_panel.btn_import.clicked.connect(self._handle_import)
        self.control_panel.btn_fresh.clicked.connect(self._handle_fresh)
        self.control_panel.btn_output.clicked.connect(self._handle_output)
        self.control_panel.btn_print.clicked.connect(self._handle_print)
        # 设置初始模式
        self.stacked_widget.setCurrentIndex(self._EDIT_MODE)
        # 安装事件过滤器以检测鼠标悬停
        self.installEventFilter(self)
        # 初始化 ViewModeHandler
        self.flight_getter = FlightGet()
        self.view_mode_handler = ViewModeHandler(self.editor, self.viewer, self.flight_getter)
        # 设置初始视觉状态
        self.control_panel._update_visual_state_immediately()


    def _handle_mode_change(self, mode_id):
        """处理模式更改"""
        if mode_id == self._EDIT_MODE:
            self.stacked_widget.setCurrentIndex(self._EDIT_MODE)
        else: # 查看模式
            self.stacked_widget.setCurrentIndex(self._VIEW_MODE)
            # 更新 markdown 视图
            self.view_mode_handler.update_markdown_view()


    def _check_hover_and_trigger_panel_state(self, pos_in_window: QPoint):
        """检查鼠标位置并触发面板状态"""
        current_time = time.time()
        if current_time - self._last_hover_check_time < self._HOVER_CHECK_INTERVAL:
            return # 限制检查频率
        self._last_hover_check_time = current_time
        # 检查鼠标是否在控制面板区域
        panel_rect = self.control_panel.geometry()
        if panel_rect.contains(pos_in_window):
            if not self.control_panel._is_expanded:
                self.control_panel.animate_expand()
        else:
            if self.control_panel._is_expanded:
                self.control_panel.animate_collapse()


    def _handle_import(self):
        """处理导入按钮点击"""
        print("导入按钮被点击")


    def _handle_fresh(self):
        """处理刷新按钮点击"""
        print("刷新按钮被点击")


    def _handle_output(self):
        """处理输出按钮点击"""
        print("输出按钮被点击")


    def _handle_print(self):
        """处理打印按钮点击"""
        print("打印按钮被点击")


    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """事件过滤器以检测鼠标移动"""
        if event.type() == QEvent.MouseMove:
            mouse_event = QMouseEvent(event)
            self._check_hover_and_trigger_panel_state(mouse_event.pos())
        return super().eventFilter(watched, event)



        