import maya.cmds as cmds
import maya.mel as mel
from maya import OpenMayaUI as omui
from PySide2 import QtWidgets, QtCore, QtGui
from shiboken2 import wrapInstance
import re
import os

def get_maya_main_window():
    """获取Maya主窗口指针"""
    maya_ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(maya_ptr), QtWidgets.QWidget)

def get_maya_icon(icon_name):
    """获取Maya内置图标"""
    return QtGui.QIcon(":/{0}".format(icon_name))

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

class ABCExporterUI(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(ABCExporterUI, self).__init__(parent)
        self.setWindowTitle("批量ABC导出器 v1.8")
        self.setMinimumWidth(280)
        self.setWindowFlags(QtCore.Qt.Window)  # 设置为独立窗口
        self.export_path = ""  # 存储导出路径
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)  # 减少外围边距
        layout.setSpacing(8)  # 缩小组件间距
        
        # 帧范围设置 (紧凑布局)
        frame_group = QtWidgets.QGroupBox("帧范围")
        frame_layout = QtWidgets.QGridLayout()
        frame_layout.setVerticalSpacing(6)  # 减少行间距
        frame_layout.setHorizontalSpacing(10)
        frame_layout.setContentsMargins(8, 12, 8, 12)  # 减少内边距
        
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
        self.start_frame.setFixedWidth(70)  # 固定宽度
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
        main_layout = QtWidgets.QVBoxLayout()  # 改用垂直布局

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
        
        # 变量提示
        name_help = QtWidgets.QLabel(
            "可用变量:\n"
            "• {name} - 物体名称\n"
            "• {scene} - 场景名称\n" 
            "• {user} - 当前用户\n"
            "• {date} - 当前日期 (YYYYMMDD)\n"
            "• {time} - 当前时间 (HHMMSS)\n"
            "• {shot} - 镜头编号\n"
            "• {start} - 起始帧\n"
            "• {end} - 结束帧\n"
            "• {assetType} - 资产类型\n"
            "• ## - 自动版本号"
        )
        name_help.setWordWrap(True)
        main_layout.addWidget(name_help)

        # +++ 水平分割线 +++
        h_line = QtWidgets.QFrame()
        h_line.setFrameShape(QtWidgets.QFrame.HLine)
        h_line.setFrameShadow(QtWidgets.QFrame.Sunken)
        main_layout.addWidget(h_line)

        # 命名空间选项
        self.namespace_cb = QtWidgets.QCheckBox("删除命名空间")
        main_layout.addWidget(self.namespace_cb)
        self.namespace_cb.setChecked(True) # 设置默认勾选状态

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
        trim_layout.addStretch()  # 添加弹性空间
        main_layout.addLayout(trim_layout)
        # 向选择复选框
        self.trim_direction_cb = QtWidgets.QCheckBox("从左到右")
        self.trim_direction_cb.setToolTip("勾选后从名称开头删除字符")
        trim_layout.addWidget(self.trim_direction_cb)

        name_group.setLayout(main_layout)
        
        # 导出路径设置组 - 移动到命名规则下方
        path_group = QtWidgets.QGroupBox("导出路径")
        path_layout = QtWidgets.QVBoxLayout()
        path_layout.setContentsMargins(8, 12, 8, 12)
        
        # 路径输入和选择
        path_input_layout = QtWidgets.QHBoxLayout()
        self.path_input = QtWidgets.QLineEdit()
        self.path_input.setPlaceholderText("输入或选择导出路径...")
        # 移除只读限制，允许手动输入
        self.path_input.textChanged.connect(self.on_path_changed)
        path_input_layout.addWidget(self.path_input)
        
        self.browse_btn = QtWidgets.QPushButton()
        self.browse_btn.setIcon(get_maya_icon("fileOpen.png"))
        self.browse_btn.setIconSize(QtCore.QSize(23, 23))  # 设置图标大小为24x24
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

        # 导出按钮
        export_btn = QtWidgets.QPushButton("导出选中物体")
        export_btn.clicked.connect(self.do_export)
        export_btn.setStyleSheet("background-color: #2c7fb8; color: white;")
        
        layout.addWidget(frame_group)
        layout.addWidget(options_group)  # 添加选项组
        layout.addWidget(name_group)
        layout.addWidget(path_group)  # 移动到命名规则下方
        layout.addWidget(export_btn)
        self.setLayout(layout)

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
        file_path = cmds.fileDialog2(
            fileMode=3,
            dialogStyle=2,
            caption="选择导出目录")
        if file_path:
            # 确保路径格式正确，统一使用正斜杠
            path = file_path[0].replace("\\", "/")
            # 确保路径末尾有斜杠
            if not path.endswith("/"):
                path += "/"
            self.export_path = path
            self.path_input.setText(self.export_path)

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
            if self.trim_direction_cb.isChecked():  # 新增方向判断
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
        return re.sub(r'[\\\\/:*?"<>|]', '_', name)

    def do_export(self):
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
    
        # 构建导出选项参数
        export_options = []
        if self.uv_write.isChecked():
            export_options.append("-uvWrite 1")
        if self.color_sets.isChecked():
            export_options.append("-writeColorSets 1")
        if self.world_space.isChecked():
            export_options.append("-worldSpace 1")
        if self.visibility.isChecked():
            export_options.append("-writeVisibility 1")
        if self.uv_sets.isChecked():
            export_options.append("-writeUvSets 1")
        if self.face_sets.isChecked():
            export_options.append("-writeFaceSets 1")
        if self.whole_frame.isChecked():
            export_options.append("-wholeFrameGeo 1") 
        if self.creases.isChecked():
            export_options.append("-writeCreases 1")
    
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
    
                # 构建完整文件路径 - 直接拼接避免路径问题
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

# 创建停靠面板版本（可选）
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

# 使用停靠版本（可选）
# create_dockable()

# 使用浮动版本
show()