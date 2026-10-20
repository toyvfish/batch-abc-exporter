import maya.cmds as cmds
import maya.mel as mel
from maya import OpenMayaUI as omui
import re
import os

# Maya版本兼容性处理
try:
    from PySide6 import QtWidgets, QtCore, QtGui
    from shiboken6 import wrapInstance
    PYSIDE_VERSION = 6
except ImportError:
    try:
        from PySide2 import QtWidgets, QtCore, QtGui
        from shiboken2 import wrapInstance
        PYSIDE_VERSION = 2
    except ImportError:
        raise ImportError("需要PySide2或PySide6支持")

def get_maya_main_window():
    """获取Maya主窗口指针"""
    maya_ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(maya_ptr), QtWidgets.QWidget)

def get_maya_icon(icon_name):
    """获取Maya内置图标"""
    return QtGui.QIcon(":/{0}".format(icon_name))

# 命名规则可用变量: (变量文本, 说明)
AVAILABLE_VARIABLES = [
    ("{name}", "物体名称"),
    ("{scene}", "场景名称"),
    ("{user}", "当前用户"),
    ("{date}", "当前日期 (YYYYMMDD)"),
    ("{time}", "当前时间 (HHMMSS)"),
    ("{shot}", "镜头编号"),
    ("{start}", "起始帧"),
    ("{end}", "结束帧"),
    ("{assetType}", "资产类型"),
    ("##", "自动版本号"),
]

class ProgressDialog(QtWidgets.QDialog):
    """带有ESC中断功能的进度对话框"""
    def __init__(self, parent=None):
        super(ProgressDialog, self).__init__(parent)
        self.setWindowTitle("导出进度")
        self.setModal(True)
        self.setMinimumWidth(400)
        self.cancelled = False
        
        layout = QtWidgets.QVBoxLayout()
        
        self.label = QtWidgets.QLabel("准备导出...")
        layout.addWidget(self.label)
        
        self.progress = QtWidgets.QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setMaximum(100)
        layout.addWidget(self.progress)
        
        self.cancel_btn = QtWidgets.QPushButton("取消 (ESC)")
        self.cancel_btn.clicked.connect(self.cancel)
        layout.addWidget(self.cancel_btn)
        
        self.setLayout(layout)
        
    def keyPressEvent(self, event):
        """处理ESC键按下事件"""
        if event.key() == QtCore.Qt.Key_Escape:
            self.cancel()
        else:
            super(ProgressDialog, self).keyPressEvent(event)
    
    def cancel(self):
        """取消导出"""
        self.cancelled = True
        self.accept()
    
    def update_progress(self, current, total, current_obj=""):
        """更新进度"""
        if self.cancelled:
            return False
            
        progress = int((current / total) * 100) if total > 0 else 0
        self.progress.setValue(progress)
        self.label.setText(f"正在导出: {current_obj} ({current}/{total})")
        
        # 处理Qt事件，确保界面响应
        QtWidgets.QApplication.processEvents()
        
        return not self.cancelled

class HelpDialog(QtWidgets.QDialog):
    """帮助对话框"""
    def __init__(self, parent=None):
        super(HelpDialog, self).__init__(parent)
        self.setWindowTitle("ABC导出器 帮助")
        self.setModal(True)
        self.setFixedWidth(330)   # 宽度固定为原设定值，不随内容变化
        self.setMinimumHeight(700)
        
        layout = QtWidgets.QVBoxLayout()
        
        # 创建滚动区域
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        
        # 创建标签
        label = QtWidgets.QLabel()
        label.setWordWrap(True)  # 启用自动换行
        label.setAlignment(QtCore.Qt.AlignTop)
        label.setMargin(10)

        # 帮助内容
        help_content = """
<h2>ABC导出器使用方法</h2>

<h3>1. 帧范围设置</h3>
<p><b>范围模式：</b></p>
<p>• <b>当前帧</b>：只导出当前时间轴位置的帧</p>
<p>• <b>时间滑块</b>：导出时间滑块范围内的所有帧</p>
<p>• <b>自定义</b>：手动设置起始和结束帧</p>
<p>------------------------------------------------------------------

<h3>2. 导出选项</h3>
<p>• <b>UV Write</b>：导出UV坐标信息</p>
<p>• <b>Write UV Sets</b>：导出多套UV信息</p>
<p>• <b>Write Color Sets</b>：导出顶点颜色信息</p>
<p>• <b>World Space</b>：以世界坐标导出（推荐）</p>
<p>• <b>Write Visibility</b>：导出可见性动画</p>
<p>• <b>Write Face Sets</b>：导出面组信息</p>
<p>• <b>Whole Frame Geo</b>：每帧导出完整几何体</p>
<p>• <b>Write Creases</b>：导出折痕信息</p>
<p>------------------------------------------------------------------

<h3>3. 命名规则</h3>
<p><b>预设模板：</b></p>
<p>• 物体名称：直接使用物体名</p>
<p>• 角色动画：场景_物体_版本号</p>
<p>• 场景缓存：资产类型_物体_cache</p>
<p>• 镜头版本：镜头_物体_版本_用户</p>
<p>• 日期版本：物体_日期_版本</p>
<p>• 时间范围：物体_起始帧-结束帧</p>
<p>------------------------------------------------------------------

<p><b>可用变量：</b>（在主界面命名规则区域点击变量按钮，可直接插入到自定义格式输入框）</p>
<p>• {name} - 物体名称</p>
<p>• {scene} - 场景名称</p>
<p>• {user} - 当前用户</p>
<p>• {date} - 当前日期 (YYYYMMDD)</p>
<p>• {time} - 当前时间 (HHMMSS)</p>
<p>• {shot} - 镜头编号</p>
<p>• {start} - 起始帧</p>
<p>• {end} - 结束帧</p>
<p>• {assetType} - 资产类型</p>
<p>• ## - 自动版本号（v001, v002...）</p>
<p>------------------------------------------------------------------

<h3>4. 高级选项</h3>
<p>• <b>删除命名空间</b>：移除物体名称中的命名空间前缀</p>
<p>• <b>同名自动加后缀防覆盖</b>：导出时若目标文件已存在（如多个同名物体按 {name} 规则单独导出），自动追加 _001、_002 后缀生成新文件，避免相互覆盖（默认开启）</p>
<p>• <b>过滤字符</b>：删除指定字符（用逗号分隔）</p>
<p>• <b>删除末尾</b>：删除名称末尾指定数量的字符</p>
<p>• <b>从左到右</b>：改为从名称开头删除字符</p>
<p>------------------------------------------------------------------

<h3>5. 导出方式</h3>
<p>• <b>单独导出选中</b>：每个选中的物体单独导出为一个ABC文件</p>
<p>• <b>合并导出选中</b>：将所有选中物体合并导出为一个ABC文件</p>
<p>------------------------------------------------------------------
<p>

<h3>6. 使用步骤</h3>
<p>1. 在场景中选择要导出的物体或组</p>
<p>2. 设置帧范围和导出选项</p>
<p>3. 配置命名规则（可选）</p>
<p>4. 选择或输入导出路径</p>
<p>5. 点击导出按钮</p>
<p>------------------------------------------------------------------

<h3>7. 注意事项</h3>
<p>• 确保导出路径存在且有写入权限</p>
<p>• 版本号会自动递增，避免覆盖现有文件</p>
<p>• 勾选"同名自动加后缀防覆盖"时，同名物体单独导出不会相互覆盖（自动追加 _001、_002 后缀）</p>
<p>• 可以按ESC键中断导出过程</p>
<p>• 导出过程中会显示进度条和当前处理的物体</p>
"""

        # 更新日志内容
        changelog_content = """
<h2>更新日志</h2>

<h3>v2.1</h3>

<p style="margin-top: 12px">• <b>[新增] 可用变量一键插入</b></p>
<p style="margin-left: 14px">命名规则中的可用变量（{name}、{scene}、## 等）由纯文本说明改为可点击按钮，点击即把变量插入自定义格式输入框的光标位置。</p>

<h3>v2.0</h3>

<p style="margin-top: 12px">• <b>[修复] 导出选项不生效</b></p>
<p style="margin-left: 14px">UV Write、Write UV Sets、Write Color Sets、World Space、Write Visibility、Write Face Sets、Whole Frame Geo、Write Creases 现已按勾选状态正确生效。</p>

<p style="margin-top: 12px">• <b>[新增] 同名自动加后缀防覆盖</b>（默认开启）</p>
<p style="margin-left: 14px">导出遇到同名文件时自动追加 _001、_002 等后缀生成新文件；多个同名物体按 {name} 规则导出时不再相互覆盖，单独导出与合并导出均支持。</p>

<p style="margin-top: 12px">• <b>[优化] 帮助窗口选项卡化</b></p>
<p style="margin-left: 14px">帮助窗口改为「更新日志 / 使用帮助」两个可切换选项卡。</p>
"""

        # 更新日志选项卡页
        c_scroll = QtWidgets.QScrollArea()
        c_scroll.setWidgetResizable(True)
        c_label = QtWidgets.QLabel()
        c_label.setWordWrap(True)  # 启用自动换行
        c_label.setAlignment(QtCore.Qt.AlignTop)
        c_label.setMargin(10)
        c_label.setText(changelog_content)
        c_scroll.setWidget(c_label)

        # 选项卡：更新日志 / 使用帮助
        tab_widget = QtWidgets.QTabWidget()
        tab_widget.addTab(c_scroll, "更新日志")
        tab_widget.addTab(scroll, "使用帮助")
        layout.addWidget(tab_widget)

        label.setText(help_content)
        scroll.setWidget(label)
        
        # 关闭按钮
        close_btn = QtWidgets.QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        
        self.setLayout(layout)

class ABCExporterUI(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(ABCExporterUI, self).__init__(parent)
        self.setWindowTitle("批量ABC导出器 v2.1")
        self.setMinimumWidth(280)
        self.setWindowFlags(QtCore.Qt.Window)  # 设置为独立窗口
        self.export_path = ""  # 存储导出路径
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)  # 外围边距
        layout.setSpacing(8)  # 组件间距
        
        # 帧范围设置 (紧凑布局)
        frame_group = QtWidgets.QGroupBox("帧范围")
        frame_layout = QtWidgets.QGridLayout()
        frame_layout.setVerticalSpacing(6)  # 行间距
        frame_layout.setHorizontalSpacing(10)
        frame_layout.setContentsMargins(8, 12, 8, 12)  # 内边距
        
        # 第一行：范围模式
        frame_layout.addWidget(QtWidgets.QLabel("范围模式:",), 0, 0)
        self.range_mode = QtWidgets.QComboBox()
        self.range_mode.addItems(["当前帧", "时间滑块", "自定义"])
        # 设置默认为时间滑块
        self.range_mode.setCurrentText("时间滑块")
        frame_layout.addWidget(self.range_mode, 0, 1)  # 跨两列
    
        # 第二行：帧数输入
        frame_layout.addWidget(QtWidgets.QLabel("起始/结束"), 1, 0)
        self.start_frame = QtWidgets.QSpinBox()
        self.start_frame.setRange(-100000, 100000)
        self.start_frame.setFixedWidth(70)  # 宽度
        self.start_frame.setValue(int(cmds.playbackOptions(q=True, min=True)))
        frame_layout.addWidget(self.start_frame, 1, 1)
        self.end_frame = QtWidgets.QSpinBox()
        self.end_frame.setRange(-100000, 100000)
        self.end_frame.setFixedWidth(70)
        self.end_frame.setValue(int(cmds.playbackOptions(q=True, max=True)))
        frame_layout.addWidget(self.end_frame, 1, 2)
        
        # 根据默认模式设置帧输入框状态
        self.start_frame.setEnabled(False)
        self.end_frame.setEnabled(False)
        
        # 连接信号
        self.range_mode.currentIndexChanged.connect(self.update_frame_range)
                
        frame_group.setLayout(frame_layout)

        # 导出选项
        options_group = QtWidgets.QGroupBox("导出选项")
        options_layout = QtWidgets.QGridLayout()
        self.uv_write = QtWidgets.QCheckBox("UV Write")
        self.uv_sets = QtWidgets.QCheckBox("Write UV Sets")
        self.color_sets = QtWidgets.QCheckBox("Write Color Sets")
        self.world_space = QtWidgets.QCheckBox("World Space") 
        self.visibility = QtWidgets.QCheckBox("Write Visibility")
        self.face_sets = QtWidgets.QCheckBox("Write Face Sets")
        self.whole_frame = QtWidgets.QCheckBox("Whole Frame Geo")
        self.creases = QtWidgets.QCheckBox("Write Creases")

        # 设置默认勾选状态
        self.uv_write.setChecked(True)
        self.world_space.setChecked(True)
        self.visibility.setChecked(True)
        self.face_sets.setChecked(True)
                
        options_layout.addWidget(self.uv_write, 0, 0)
        options_layout.addWidget(self.uv_sets, 0, 1)
        options_layout.addWidget(self.color_sets, 1, 0)
        options_layout.addWidget(self.world_space, 1, 1)
        options_layout.addWidget(self.visibility, 2, 0) 
        options_layout.addWidget(self.face_sets, 2, 1)
        options_layout.addWidget(self.whole_frame, 3, 0)
        options_layout.addWidget(self.creases, 3, 1)
        options_group.setLayout(options_layout)

        # 命名规则组 - 将高级选项整合到现有布局中
        name_group = QtWidgets.QGroupBox("命名规则")
        main_layout = QtWidgets.QVBoxLayout()  # 垂直布局

        # 预设模板
        templates_layout = QtWidgets.QHBoxLayout()
        templates_layout.addWidget(QtWidgets.QLabel("预设模板:"))
        main_layout.addLayout(templates_layout)

        # 预设模板选项
        template_layout = QtWidgets.QHBoxLayout()
        self.template_combo = QtWidgets.QComboBox()
        self.template_combo.addItems([
            "物体名称: {name}", 
            "角色动画: {scene}_{name}_##",
            "场景缓存: {assetType}_{name}_cache",
            "镜头版本: {shot}_{name}_##_{user}",
            "日期版本: {name}_{date}_##",
            "时间范围: {name}_{start}-{end}",
            "自定义"
        ])
        template_layout.addWidget(self.template_combo)
        self.template_combo.setCurrentIndex(0)  # 默认选中物体名称模板
        self.template_combo.currentIndexChanged.connect(self.apply_template)
        main_layout.addLayout(template_layout)

        # 自定义格式
        pattern_layout = QtWidgets.QHBoxLayout()
        pattern_layout.addWidget(QtWidgets.QLabel("自定义格式:"))
        main_layout.addLayout(pattern_layout)

        # 输入名称
        name_layout = QtWidgets.QHBoxLayout()
        self.name_pattern = QtWidgets.QLineEdit("{name}")
        name_layout.addWidget(self.name_pattern)
        main_layout.addLayout(name_layout)
        
        # 变量提示:每个变量改为可点击按钮,点击即插入到自定义格式输入框
        main_layout.addWidget(QtWidgets.QLabel("可用变量 (点击插入):"))
        var_list = QtWidgets.QVBoxLayout()
        var_list.setContentsMargins(0, 0, 0, 0)
        var_list.setSpacing(3)   # 按钮行间距,避免按钮连在一起
        for var, desc in AVAILABLE_VARIABLES:
            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(3)    # 说明文字与按钮之间保留少量间距
            var_btn = QtWidgets.QPushButton(var)
            var_btn.setFixedHeight(13)   # 紧凑按钮高度
            var_btn.setToolTip("点击将 {0} 插入到自定义格式输入框({1})".format(var, desc))
            # 边框与文字颜色跟随界面文字颜色,避免纯白过亮刺眼
            text_color = self.palette().color(QtGui.QPalette.WindowText)
            text_css = text_color.name()
            hover_css = "rgba({0}, {1}, {2}, 40)".format(
                text_color.red(), text_color.green(), text_color.blue())
            var_btn.setStyleSheet(
                "QPushButton {"
                "    background: transparent;"   # 透明背景
                "    border: 1px solid " + text_css + ";"   # 边框接近界面文字颜色
                "    color: " + text_css + ";"   # 文字接近界面文字颜色
                "    border-radius: 3px;"
                "    padding: 0 3px;"
                "}"
                "QPushButton:hover {"
                "    background: " + hover_css + ";"   # 悬停轻微反馈
                "}"
            )
            var_btn.clicked.connect(lambda checked=False, v=var: self.insert_variable(v))
            desc_label = QtWidgets.QLabel("- " + desc)
            row.addWidget(var_btn)
            row.addWidget(desc_label)
            row.addStretch()   # 内容靠左,右侧留白
            var_list.addLayout(row)
        main_layout.addLayout(var_list)

        # +++ 水平分割线 +++
        h_line = QtWidgets.QFrame()
        h_line.setFrameShape(QtWidgets.QFrame.HLine)
        h_line.setFrameShadow(QtWidgets.QFrame.Sunken)
        main_layout.addWidget(h_line)

        # 选项行：删除命名空间 + 同名自动加后缀防覆盖（同一行并排）
        checkbox_row = QtWidgets.QHBoxLayout()
        self.namespace_cb = QtWidgets.QCheckBox("删除命名空间")
        self.namespace_cb.setChecked(True) # 默认勾选状态
        checkbox_row.addWidget(self.namespace_cb)

        # 同名文件防覆盖选项
        self.avoid_overwrite_cb = QtWidgets.QCheckBox("同名自动加后缀防覆盖")
        self.avoid_overwrite_cb.setToolTip(
            "导出时若目标文件已存在（例如多个同名物体按 {name} 规则导出），\n"
            "自动追加 _001、_002 等后缀生成新文件，避免相互覆盖")
        self.avoid_overwrite_cb.setChecked(True) # 默认勾选状态
        checkbox_row.addWidget(self.avoid_overwrite_cb)
        checkbox_row.addStretch()  # 弹性空间，选项靠左排列

        main_layout.addLayout(checkbox_row)

        # 过滤设置
        filter_layout = QtWidgets.QHBoxLayout()
        filter_layout.addWidget(QtWidgets.QLabel("过滤字符:"))
        self.filter_input = QtWidgets.QLineEdit()
        self.filter_input.setPlaceholderText("_,geo,mesh")
        self.filter_input.setMaximumWidth(180)
        filter_layout.addWidget(self.filter_input)
        main_layout.addLayout(filter_layout)
        
        # 截断设置
        trim_layout = QtWidgets.QHBoxLayout()
        trim_layout.addWidget(QtWidgets.QLabel("删除末尾:"))
        self.trim_spin = QtWidgets.QSpinBox()
        self.trim_spin.setMaximumWidth(80)
        trim_layout.addWidget(self.trim_spin)
        trim_layout.addWidget(QtWidgets.QLabel("个字符"))
        trim_layout.addStretch()  # 弹性空间
        main_layout.addLayout(trim_layout)
        # 向选择复选框
        self.trim_direction_cb = QtWidgets.QCheckBox("从左到右")
        self.trim_direction_cb.setToolTip("勾选后从名称开头删除字符")
        trim_layout.addWidget(self.trim_direction_cb)

        name_group.setLayout(main_layout)
        
        # 导出路径设置组
        path_group = QtWidgets.QGroupBox("导出路径")
        path_layout = QtWidgets.QVBoxLayout()
        path_layout.setContentsMargins(8, 12, 8, 12)
        
        # 路径输入和选择
        path_input_layout = QtWidgets.QHBoxLayout()
        self.path_input = QtWidgets.QLineEdit()
        self.path_input.setPlaceholderText("输入或选择导出路径...")
        # 允许手动输入
        self.path_input.textChanged.connect(self.on_path_changed)
        path_input_layout.addWidget(self.path_input)
        
        self.browse_btn = QtWidgets.QPushButton()
        self.browse_btn.setIcon(get_maya_icon("fileOpen.png"))
        self.browse_btn.setIconSize(QtCore.QSize(23, 23))  # 图标大小为24x24
        self.browse_btn.clicked.connect(self.browse_export_path)
        self.browse_btn.setFixedSize(25, 25)
        self.browse_btn.setFlat(True)  # 设置为扁平样式，无边框
        self.browse_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 30);
                border-radius: 6px;
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 50);
            }
        """)
        path_input_layout.addWidget(self.browse_btn)

        path_layout.addLayout(path_input_layout)
        path_group.setLayout(path_layout)

        # 导出按钮区域
        button_layout = QtWidgets.QHBoxLayout()
        
        # 帮助按钮
        help_btn = QtWidgets.QPushButton()
        help_btn.setIcon(get_maya_icon("help.png"))
        help_btn.setIconSize(QtCore.QSize(20, 20))
        help_btn.clicked.connect(self.show_help)
        help_btn.setFixedSize(30, 30)
        help_btn.setFlat(True)
        help_btn.setToolTip("显示帮助与更新日志")
        help_btn.setStyleSheet("""
            QPushButton {
                border: none;
                background: transparent;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 30);
                border-radius: 6px;
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 50);
            }
        """)
        button_layout.addWidget(help_btn)
        
        # 导出按钮
        export_btn = QtWidgets.QPushButton("单独导出选中")
        export_btn.clicked.connect(self.do_export)
        export_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
        """)
        button_layout.addWidget(export_btn)
        
        # 合并导出按钮
        merge_export_btn = QtWidgets.QPushButton("合并导出选中")
        merge_export_btn.clicked.connect(self.do_merge_export)
        merge_export_btn.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 6px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1976D2;
            }
            QPushButton:pressed {
                background-color: #1565C0;
            }
        """)
        button_layout.addWidget(merge_export_btn)
        
        layout.addWidget(frame_group)
        layout.addWidget(options_group)
        layout.addWidget(name_group)
        layout.addWidget(path_group)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    def show_help(self):
        """显示帮助对话框"""
        help_dialog = HelpDialog(self)
        help_dialog.exec_()

    def on_path_changed(self):
        """当路径输入框内容改变时更新export_path并统一格式"""
        raw_path = self.path_input.text().strip()
        if raw_path:
            # 统一路径格式：反斜杠转正斜杠
            formatted_path = raw_path.replace("\\", "/")
            # 确保路径末尾有斜杠
            if not formatted_path.endswith("/"):
                formatted_path += "/"
            self.export_path = formatted_path
            
            # 如果格式化后的路径与输入不同，更新显示（避免无限循环）
            if formatted_path != raw_path:
                # 暂时断开信号连接，避免递归调用
                self.path_input.textChanged.disconnect()
                self.path_input.setText(formatted_path)
                # 重新连接信号
                self.path_input.textChanged.connect(self.on_path_changed)
        else:
            self.export_path = ""

    def browse_export_path(self):
        """浏览并选择导出路径"""
        options = QtWidgets.QFileDialog.Options()
        folder_path = QtWidgets.QFileDialog.getExistingDirectory(self, "选择 ABC 导出文件夹", "", options=options)
        if folder_path:
            self.current_folder_path = folder_path
            self.path_input.setText(folder_path)
            self.load_abc_files()

    def process_object_name(self, raw_name):
        """执行高级命名规则处理"""
        processed = raw_name
        
        # 1. 删除命名空间
        if self.namespace_cb.isChecked():
            processed = processed.split(":")[-1]
        
        # 2. 去除指定字符
        filter_chars = self.filter_input.text().strip()
        if filter_chars:
            for char in filter_chars.split(','):
                if char:  # 避免空字符串
                    processed = processed.replace(char.strip(), '')
        
        # 3. 末尾截断
        trim_count = self.trim_spin.value()
        if trim_count > 0:
            if self.trim_direction_cb.isChecked():  # 方向判断
                # 从左到右截断（保留右侧字符）
                processed = processed[trim_count:] if len(processed) > trim_count else ""
            else:
                # 原有从右到左截断
                processed = processed[:-trim_count] if len(processed) > trim_count else processed
        
        return self.sanitize_name(processed)

    def apply_template(self):
        templates = {
            0: "{name}",
            1: "{scene}_{name}_##",
            2: "{assetType}_{name}_cache",
            3: "{shot}_{name}_##_{user}",
            4: "{name}_{date}_##", 
            5: "{name}_{start}-{end}",
            6: "",  # 自定义
        }
        self.name_pattern.setText(templates.get(self.template_combo.currentIndex(), ""))
    
    def insert_variable(self, var):
        """把变量插入到自定义格式输入框的当前光标位置

        光标前已有内容时,先自动补一个下划线分隔,避免变量直接粘连;
        若光标前一个字符已是下划线,则不再重复添加
        """
        line_edit = self.name_pattern
        pos = line_edit.cursorPosition()
        text = line_edit.text()
        prefix = ""
        if pos > 0 and text[:pos]:
            prefix = "" if text[pos - 1] == "_" else "_"
        line_edit.setText(text[:pos] + prefix + var + text[pos:])
        line_edit.setCursorPosition(pos + len(prefix) + len(var))
        line_edit.setFocus()
    
    def update_frame_range(self):
        """根据范围模式更新帧范围控件状态"""
        mode = self.range_mode.currentText()
        if mode == "自定义":
            self.start_frame.setEnabled(True)
            self.end_frame.setEnabled(True)
        else:
            self.start_frame.setEnabled(False)
            self.end_frame.setEnabled(False)
            
            if mode == "当前帧":
                current = int(cmds.currentTime(q=True))
                self.start_frame.setValue(current)
                self.end_frame.setValue(current)
            elif mode == "时间滑块":
                self.start_frame.setValue(int(cmds.playbackOptions(q=True, min=True)))
                self.end_frame.setValue(int(cmds.playbackOptions(q=True, max=True)))
                
    def sanitize_name(self, name):
        """清理非法文件名字符"""
        return re.sub(r'[\\/:*?"<>|]', '_', name)

    def build_export_options(self):
        """根据界面勾选状态构建 AbcExport 作业字符串选项

        注意：AbcExport 的这些导出开关都是布尔旗标（无参数），
        必须单独书写，不能附带参数值。
        诸如 "-uvWrite 1" 的写法属于非法语法——多出来的 "1" 会被
        AbcExport 当成未知参数警告忽略（或直接报错），导致勾选无效。
        """
        export_options = []
        if self.uv_write.isChecked():
            export_options.append("-uvWrite")
        if self.uv_sets.isChecked():
            export_options.append("-writeUVSets")
        if self.color_sets.isChecked():
            export_options.append("-writeColorSets")
        if self.world_space.isChecked():
            export_options.append("-worldSpace")
        if self.visibility.isChecked():
            export_options.append("-writeVisibility")
        if self.face_sets.isChecked():
            export_options.append("-writeFaceSets")
        if self.whole_frame.isChecked():
            export_options.append("-wholeFrameGeo")
        if self.creases.isChecked():
            export_options.append("-writeCreases")
        return export_options

    def resolve_duplicate_name(self, file_path, final_name):
        """同名文件防覆盖：目标文件已存在时追加 _001 式后缀，返回不重复的文件名

        返回 None 表示 001~999 后缀均被占用，无法生成不重复的文件名
        """
        if not os.path.exists(f"{file_path}{final_name}.abc"):
            return final_name
        for suffix in range(1, 1000):
            test_name = f"{final_name}_{suffix:03d}"
            if not os.path.exists(f"{file_path}{test_name}.abc"):
                return test_name
        return None

    def do_merge_export(self):
        """合并导出选中物体为一个ABC文件"""
        from datetime import datetime
        
        # 检查是否已选择导出路径
        if not self.export_path:
            QtWidgets.QMessageBox.warning(self, "警告", "请先选择或输入导出路径！")
            return
        
        # 验证路径是否存在
        test_path = self.export_path.rstrip("/")
        if not os.path.exists(test_path):
            QtWidgets.QMessageBox.warning(self, "警告", f"路径不存在：{test_path}")
            return
        
        selected = cmds.ls(sl=True, long=True) or []
        if not selected:
            cmds.warning("请先选择要导出的物体或组")
            return

        # 创建进度对话框
        progress_dialog = ProgressDialog(self)
        progress_dialog.show()
        
        # 显示准备阶段
        progress_dialog.update_progress(0, 100, "准备合并导出...")
        
        # 获取基础变量
        scene_path = cmds.file(q=True, sceneName=True) or "untitled"
        scene_name = os.path.splitext(os.path.basename(scene_path))[0]
        current_user = os.getenv('USERNAME') or os.getenv('USER') or "unknown"
        current_date = datetime.now().strftime("%Y%m%d")
        current_time = datetime.now().strftime("%H%M%S")
        
        # 获取帧范围
        mode = self.range_mode.currentText()
        if mode == "当前帧":
            start = end = int(cmds.currentTime(q=True))
        elif mode == "时间滑块":
            start = int(cmds.playbackOptions(q=True, min=True))
            end = int(cmds.playbackOptions(q=True, max=True))
        else:  # 自定义模式
            start = self.start_frame.value()
            end = self.end_frame.value()

        # 构建导出选项参数（布尔旗标，不带参数值）
        export_options = self.build_export_options()

        # 确保导出路径格式正确
        file_path = self.export_path.replace("\\", "/")
        if not file_path.endswith("/"):
            file_path += "/"

        try:
            # 显示处理阶段
            progress_dialog.update_progress(25, 100, "处理文件名...")
            
            # 使用最后一个选中物体的名称作为文件名
            last_obj = selected[-1]
            raw_name = last_obj.split('|')[-1]
            obj_name = self.process_object_name(raw_name)
            
            # 准备所有可能的变量
            variables = {
                'name': obj_name,
                'scene': scene_name,
                'user': current_user,
                'date': current_date,
                'time': current_time,
                'shot': 'SHOT001',  # 默认镜头编号，可根据需要修改
                'start': start,
                'end': end,
                'assetType': 'character'  # 默认资产类型，可根据需要修改
            }
            
            # 格式化文件名
            try:
                base_name = self.name_pattern.text().format(**variables)
            except KeyError as e:
                cmds.warning(f"模板变量错误: {e}")
                base_name = obj_name  # 回退到物体名称
            
            # 显示版本检查阶段
            progress_dialog.update_progress(50, 100, "检查版本号...")
            
            # 处理版本号
            if "##" in base_name:
                version = 1
                while True:
                    version_str = f"v{version:03d}"  # 三位数版本号
                    test_name = base_name.replace("##", version_str)
                    full_path = f"{file_path}{test_name}.abc"
                    if not os.path.exists(full_path):
                        break
                    version += 1
                    if version > 999:
                        cmds.warning(f"版本号超过最大值 (v999): {obj_name}")
                        version_str = f"v{version:03d}"
                        break
                final_name = base_name.replace("##", version_str)
            else:
                final_name = base_name

            # 同名文件防覆盖
            if self.avoid_overwrite_cb.isChecked():
                dedup_name = self.resolve_duplicate_name(file_path, final_name)
                if dedup_name is None:
                    progress_dialog.close()
                    QtWidgets.QMessageBox.warning(self, "导出中止",
                        f"无法为 {final_name} 生成不重复的文件名（后缀已达上限），已取消导出")
                    return
                if dedup_name != final_name:
                    print(f"目标文件已存在，自动添加后缀 -> {dedup_name}")
                    final_name = dedup_name

            # 构建完整文件路径
            file_name = f"{file_path}{final_name}.abc"

            # 显示导出阶段
            obj_names = [obj.split('|')[-1] for obj in selected]
            progress_dialog.update_progress(75, 100, f"正在导出 {len(selected)} 个物体: {', '.join(obj_names[:3])}{'...' if len(obj_names) > 3 else ''}")

            # 构建完整导出命令 - 合并导出所有选中物体
            cmd = f'AbcExport -j "-frameRange {start} {end}'
            # 添加所有选中的物体
            for obj in selected:
                cmd += f' -root {obj}'
            if export_options:
                cmd += " " + " ".join(export_options)
            cmd += f' -file \\"{file_name}\\" "'

            # 执行导出
            mel.eval(cmd)
            print(f"成功合并导出: {file_name}")
            
            # 显示完成阶段
            progress_dialog.update_progress(100, 100, "导出完成")
            
            # 关闭进度对话框
            progress_dialog.close()
            
            # 显示成功消息
            QtWidgets.QMessageBox.information(self, "导出结果", f"合并导出完成！\n文件: {final_name}.abc\n包含 {len(selected)} 个物体")
            
        except Exception as e:
            progress_dialog.close()
            cmds.warning(f"合并导出失败: {str(e)}")
            import traceback
            traceback.print_exc()
            QtWidgets.QMessageBox.critical(self, "导出错误", f"合并导出失败:\n{str(e)}")

    def do_export(self):
        """单独导出选中物体为一个ABC文件"""
        from datetime import datetime
        
        # 检查是否已选择导出路径
        if not self.export_path:
            QtWidgets.QMessageBox.warning(self, "警告", "请先选择或输入导出路径！")
            return
        
        # 验证路径是否存在
        test_path = self.export_path.rstrip("/")  # 移除末尾斜杠进行检查
        if not os.path.exists(test_path):
            QtWidgets.QMessageBox.warning(self, "警告", f"路径不存在：{test_path}")
            return
        
        selected = cmds.ls(sl=True, long=True) or []
        if not selected:
            cmds.warning("请先选择要导出的物体或组")
            return
    
        # 创建进度对话框
        progress_dialog = ProgressDialog(self)
        progress_dialog.show()
        
        # 获取基础变量
        scene_path = cmds.file(q=True, sceneName=True) or "untitled"
        scene_name = os.path.splitext(os.path.basename(scene_path))[0]
        current_user = os.getenv('USERNAME') or os.getenv('USER') or "unknown"
        current_date = datetime.now().strftime("%Y%m%d")
        current_time = datetime.now().strftime("%H%M%S")
        
        # 获取帧范围
        mode = self.range_mode.currentText()
        if mode == "当前帧":
            start = end = int(cmds.currentTime(q=True))
        elif mode == "时间滑块":
            start = int(cmds.playbackOptions(q=True, min=True))
            end = int(cmds.playbackOptions(q=True, max=True))
        else:  # 自定义模式
            start = self.start_frame.value()
            end = self.end_frame.value()
    
        # 构建导出选项参数（布尔旗标，不带参数值）
        export_options = self.build_export_options()
    
        # 确保导出路径格式正确
        file_path = self.export_path.replace("\\", "/")
        if not file_path.endswith("/"):
            file_path += "/"
    
        # 批量导出
        success_count = 0
        total_count = len(selected)
        
        for i, obj in enumerate(selected):
            # 检查是否被取消
            if not progress_dialog.update_progress(i, total_count, obj.split('|')[-1]):
                break
                
            try:
                # 生成合法文件名
                raw_name = obj.split('|')[-1]
                obj_name = self.process_object_name(raw_name)
                
                # 准备所有可能的变量
                variables = {
                    'name': obj_name,
                    'scene': scene_name,
                    'user': current_user,
                    'date': current_date,
                    'time': current_time,
                    'shot': 'SHOT001',  # 默认镜头编号，可根据需要修改
                    'start': start,
                    'end': end,
                    'assetType': 'character'  # 默认资产类型，可根据需要修改
                }
                
                # 格式化文件名
                try:
                    base_name = self.name_pattern.text().format(**variables)
                except KeyError as e:
                    cmds.warning(f"模板变量错误: {e}")
                    base_name = obj_name  # 回退到物体名称
                
                # 处理版本号
                if "##" in base_name:
                    version = 1
                    while True:
                        version_str = f"v{version:03d}"  # 修改02d为03d实现三位数
                        test_name = base_name.replace("##", version_str)
                        full_path = f"{file_path}{test_name}.abc"  # 直接拼接，不使用os.path.join
                        if not os.path.exists(full_path):
                            break
                        version += 1
                        if version > 999:  # 修改上限为999
                            cmds.warning(f"版本号超过最大值 (v999): {obj_name}")  # 更新提示信息
                            version_str = f"v{version:03d}"
                            break
                    final_name = base_name.replace("##", version_str)
                else:
                    final_name = base_name
    
                # 同名文件防覆盖
                if self.avoid_overwrite_cb.isChecked():
                    dedup_name = self.resolve_duplicate_name(file_path, final_name)
                    if dedup_name is None:
                        cmds.warning(f"跳过 {obj}: 无法为 {final_name} 生成不重复的文件名（后缀已达上限）")
                        continue
                    if dedup_name != final_name:
                        print(f"{obj}: 目标文件已存在，自动添加后缀 -> {dedup_name}")
                        final_name = dedup_name

                # 构建完整文件路径
                file_name = f"{file_path}{final_name}.abc"
    
                # 构建完整导出命令
                cmd = f'AbcExport -j "-frameRange {start} {end}'
                cmd += f' -root {obj}'
                if export_options:
                    cmd += " " + " ".join(export_options)
                cmd += f' -file \\"{file_name}\\" "'
    
                # 执行导出
                mel.eval(cmd)
                print(f"成功导出: {file_name}")
                success_count += 1
                
            except Exception as e:
                cmds.warning(f"导出失败 {obj}: {str(e)}")
                import traceback
                traceback.print_exc()
        
        # 关闭进度对话框
        progress_dialog.close()
        
        # 显示汇总结果
        if progress_dialog.cancelled:
            msg = f"导出已取消！已完成 {success_count}/{total_count} 个物体"
        else:
            msg = f"导出完成！成功 {success_count}/{total_count} 个物体"
            
        if success_count < total_count:
            msg += " (详见脚本编辑器错误日志)"
        QtWidgets.QMessageBox.information(self, "导出结果", msg)


def show():
    global ui
    try:
        ui.close()
    except:
        pass
    
    # 获取Maya主窗口作为父级
    maya_main = get_maya_main_window()
    ui = ABCExporterUI(parent=maya_main)
    
    # 设置窗口属性
    ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
    ui.show()
    return ui

# 创建停靠面板版本
def create_dockable():
    control_name = "abcExporterDock"
    if cmds.workspaceControl(control_name, exists=True):
        cmds.deleteUI(control_name)
    
    control = cmds.workspaceControl(
        control_name,
        label="ABC导出器",
        tabToControl=["AttributeEditor", -1],
        initialWidth=400
    )
    
    # 将Qt控件嵌入Maya面板
    ptr = omui.MQtUtil.findControl(control)
    widget = wrapInstance(int(ptr), QtWidgets.QWidget)
    widget.setLayout(QtWidgets.QVBoxLayout())
    exporter_ui = show()
    widget.layout().addWidget(exporter_ui)

# 使用浮动版本
show()