import sys # For path manipulation
import os  # For path manipulation
import time
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QTextEdit, QHBoxLayout,
                               QRadioButton, QButtonGroup, QStackedWidget,
                               QPushButton, QFrame, QLabel, QSizePolicy, QApplication)
from PySide6.QtCore import (Qt, QRect, QEvent, QPoint, Signal, 
                          QPropertyAnimation, QParallelAnimationGroup, QEasingCurve, QTimer, QObject)
from PySide6.QtGui import QFont, QCursor, QPalette, QMouseEvent
from bin.database.flight_get import FlightGet
from bin.processors.radio_view import ViewModeHandler # Added Import

_EDIT_FONT = QFont("Courier New", 11)
_VIEW_FONT = QFont("Courier New", 11)
_TABLE_CSS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "table_styles.css")# default CSS for table borders from external file
_RADIO_HEIGHT = 20


class MarkdownViewer(QTextEdit):
    def __init__(self):
        super().__init__()
        # Make viewer read-only - this means user can't edit text but can still select and copy
        self.setReadOnly(True)
        # Use the same font as the editor for consistency - UPDATED FONT
        self.setFont(_VIEW_FONT)
        self.setFrameStyle(QFrame.NoFrame) # Remove border
        try:
            with open(_TABLE_CSS_FILE, "r") as f:
                table_css = f.read()
            self.document().setDefaultStyleSheet(table_css)
        except FileNotFoundError as e:
            print(f"Warning: CSS file not found at {_TABLE_CSS_FILE}. Table styles will not be applied.\n {e}")
            # Optionally, define a fallback inline CSS here if the file is critical
            fallback_css = """ 
            table { border-collapse: collapse; border: 1px solid black; } 
            th, td { border: 1px solid black; padding: 4px; text-align: left; } 
            th { background-color: #f0f0f0; } 
            """ 
            self.document().setDefaultStyleSheet(fallback_css) 


    def setMarkdownText(self, text):
        # The actual markdown rendering is now handled by ViewModeHandler
        # This method just sets the HTML content given to it.
        self.setHtml(text)



class ControlPanel(QFrame):
    modeChanged = Signal(int)  # For Edit/View mode
    EXPANDED_WIDTH = 150
    COLLAPSED_WIDTH = 45

    def __init__(self, parent=None):
        super().__init__(parent)
        control_panel_layout = QVBoxLayout(self)
        control_panel_layout.setContentsMargins(5, 5, 5, 5) # Reduced margins for collapsed state
        control_panel_layout.setSpacing(8) # Reduced spacing for tighter collapsed look
        self.setFrameShape(QFrame.StyledPanel)
        self.setObjectName("ControlPanel")
        #self.setStyleSheet("ControlPanel { border-left: 1px solid palette(mid); background-color: palette(window); }") # Optional styling
        self._is_expanded = False # Start collapsed
        self.expanded_width = self.EXPANDED_WIDTH
        self.collapsed_width = self.COLLAPSED_WIDTH
        self.animation_duration = 250 # ms
        # radio layout
        self.radio_layout_widget = QWidget()
        radio_layout = QVBoxLayout(self.radio_layout_widget)
        radio_layout.setContentsMargins(0,0,0,0) # top, left, right, bottom
        self.edit_mode_radio = QRadioButton("Edit")
        self.edit_mode_radio.setFixedHeight(_RADIO_HEIGHT)
        self.view_mode_radio = QRadioButton("View")
        self.view_mode_radio.setFixedHeight(_RADIO_HEIGHT)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.edit_mode_radio, 0)
        self.mode_group.addButton(self.view_mode_radio, 1)
        self.edit_mode_radio.setChecked(True)
        radio_layout.addWidget(self.edit_mode_radio)
        radio_layout.addWidget(self.view_mode_radio)
        radio_layout.addStretch()
        control_panel_layout.addWidget(self.radio_layout_widget) # Will be hidden when collapsed
        control_panel_layout.addStretch(1) # This will push radios up and action buttons down
        # Connect modeChanged signal to emit modeChanged signal
        self.mode_group.idClicked.connect(self.modeChanged.emit)
        # Buttons
        self.action_buttons_widget = QWidget() # Widget to hold action buttons
        action_buttons_layout = QVBoxLayout(self.action_buttons_widget)
        action_buttons_layout.setContentsMargins(0,0,0,0)
        action_buttons_layout.setSpacing(2)
        self.btn_import = QPushButton("Import")
        self.btn_fresh = QPushButton("Fresh")
        self.btn_output = QPushButton("Output")
        self.btn_print = QPushButton("Print")
        self.action_buttons_list = [self.btn_import, self.btn_fresh, self.btn_output, self.btn_print]
        self._button_original_texts = {btn: btn.text() for btn in self.action_buttons_list}
        self._radio_original_texts = {self.edit_mode_radio: self.edit_mode_radio.text(), self.view_mode_radio: self.view_mode_radio.text()}
        # Define collapsed width for buttons
        for btn in self.action_buttons_list:
            action_buttons_layout.addWidget(btn)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumHeight(30) # Smaller buttons when collapsed
            btn.setMinimumWidth(self.collapsed_width - 10) # Ensure they fit collapsed width
        control_panel_layout.addWidget(self.action_buttons_widget) # Add action buttons container at the bottom
        # Animation
        self.animation_group = QParallelAnimationGroup(self)
        self.min_width_anim = QPropertyAnimation(self, b"minimumWidth")
        self.max_width_anim = QPropertyAnimation(self, b"maximumWidth")
        for anim in [self.min_width_anim, self.max_width_anim]:
            anim.setDuration(self.animation_duration)
            anim.setEasingCurve(QEasingCurve.InOutQuad)
            self.animation_group.addAnimation(anim)
        self.animation_group.finished.connect(self._post_animation_update)
        #self._update_visual_state_immediately() # Set initial collapsed state correctly


    def mousePressEvent(self, event: QEvent):
        super().mousePressEvent(event) # Pass to children first
        if event.isAccepted(): return


    def animate_expand(self):
        # Check if animation is already running or if it's already at the expanded width, beacuse we don't want to animate it again
        if self._is_expanded and (self.animation_group.state() == QParallelAnimationGroup.Running and self.min_width_anim.endValue() == self.expanded_width):
            return
        if self._is_expanded and self.animation_group.state() == QParallelAnimationGroup.Stopped:
            return
        self._is_expanded = True
        # Animate the width to the expanded width
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
        self._update_content_visibility_and_text(False) # Hide content before animation
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
        else: # Collapsed state
            self._update_content_visibility_and_text(False)


    def _update_content_visibility_and_text(self, expanded):
        #self.radio_layout_widget.setVisible(expanded)
        # Action buttons widget is always visible, its content (text) changes
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


    def _update_visual_state_immediately(self): # For initial setup
        self.setFixedWidth(self.expanded_width if self._is_expanded else self.collapsed_width)
        # This call will now correctly set up the action buttons (visible but text-less)
        # and hide the radio_layout_widget for the initial collapsed state.
        self._update_content_visibility_and_text(self._is_expanded)



class Window(QWidget):
    _WINDOW_WIDTH = 800
    _WINDOW_HEIGHT = 600
    _EDIT_MODE = 0
    _VIEW_MODE = 1
    _HOVER_CHECK_INTERVAL = 0.1 # Seconds between hover checks - Adjusted back to 0.1s

    def __init__(self):
        super().__init__()
        self._last_hover_check_time = 0 # Initialize hover check time
        self.setWindowTitle("JCSY Flights 0.5")
        screen = QApplication.primaryScreen()
        # Default start position at bottom right of screen.
        self.setGeometry(screen.availableGeometry().x() + screen.availableGeometry().width() - self._WINDOW_WIDTH, 
                  screen.availableGeometry().y() + screen.availableGeometry().height() - self._WINDOW_HEIGHT,
                  self._WINDOW_WIDTH,
                  self._WINDOW_HEIGHT)
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(5,5,5,5) # Adjust as needed
        main_layout.setSpacing(0)
        # Stacked widget for Editor/Viewer
        self.stacked_widget = QStackedWidget()
        self.editor = QTextEdit()
        self.editor.setPlaceholderText("Enter JCSY data or Markdown text here...")
        self.editor.setFont(_EDIT_FONT)
        self.editor.setFrameStyle(QFrame.NoFrame) # Remove editor border (blue line fix)
        self.viewer = MarkdownViewer() # MarkdownViewer also calls setFrameStyle(QFrame.NoFrame)
        self.stacked_widget.addWidget(self.editor)  # Index 0
        self.stacked_widget.addWidget(self.viewer)  # Index 1
        main_layout.addWidget(self.stacked_widget, 1) # Add with stretch factor of 1 (takes more space)
        # Control Panel (always visible on the right)
        self.control_panel = ControlPanel(self) 
        # ControlPanel now manages its own width via animation and initial state
        self.control_panel.modeChanged.connect(self._handle_mode_change) # Connect to new handler
        main_layout.addWidget(self.control_panel, 0) # Stretch factor 0, panel controls its size
        # Initialize FlightGet for database lookups
        self.flight_getter = FlightGet("flight.db")
        # Instantiate ViewModeHandler
        self.view_mode_handler = ViewModeHandler(self.editor, self.viewer, self.flight_getter)
        self._handle_mode_change(self._EDIT_MODE) # Ensure editor is shown and preview is initially updated based on default mode
        # Enable mouse tracking for hover detection
        self.setMouseTracking(True)
        self.stacked_widget.setMouseTracking(True) # Important for events over this large area
        self.control_panel.setMouseTracking(True) # And the panel itself
        # Install event filter to capture global mouse moves
        QApplication.instance().installEventFilter(self)


    def _handle_mode_change(self, mode_id):
        """Handles switching between Edit and View modes."""
        self.stacked_widget.setCurrentIndex(mode_id)
        if mode_id == self._VIEW_MODE: # Switched to View Mode (index 1 for viewer)
            self.view_mode_handler.update_markdown_view()


    def _check_hover_and_trigger_panel_state(self, pos_in_window: QPoint):
        panel = self.control_panel
        if panel.animation_group.state() == QParallelAnimationGroup.Running:
            return # Don't interfere with ongoing animation
        activation_width = self.control_panel.EXPANDED_WIDTH + 25 # How far from right edge to detect hover for expansion
        #panel_geom = panel.geometry() # Current geometry of the panel
        hover_trigger_rect = QRect(self.width() - activation_width,
                                0,
                                activation_width - self.control_panel.COLLAPSED_WIDTH,
                                self.height())
        #is_mouse_over_panel_area = panel_geom.contains(pos_in_window)
        is_mouse_in_wider_hover_zone = hover_trigger_rect.contains(pos_in_window)
        if is_mouse_in_wider_hover_zone:
            if not panel._is_expanded: panel.animate_expand()
        else: # Mouse is outside panel and its activation zone
            if panel._is_expanded: panel.animate_collapse()


    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        """
        Filters global events to catch mouse movements anywhere because the editor widget has its own mouse tracking that covers the mouseEvent.
        This is used to detect when the mouse is over the control panel and trigger the panel to expand or collapse.
        """
        if isinstance(event, QMouseEvent) and event.type() == QEvent.Type.MouseMove:
            current_time = time.monotonic()
            if current_time - self._last_hover_check_time >= self._HOVER_CHECK_INTERVAL:
                global_pos = event.globalPosition().toPoint()
                pos_in_window = self.mapFromGlobal(global_pos)
                # Check if the mouse is actually within the window's bounds before checking panel state
                if self.rect().contains(pos_in_window):
                    self._check_hover_and_trigger_panel_state(pos_in_window)
                self._last_hover_check_time = current_time  
        # Pass the event along to the default handler
        return super().eventFilter(watched, event)



        