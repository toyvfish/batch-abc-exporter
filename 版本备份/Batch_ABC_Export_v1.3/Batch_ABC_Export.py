import maya.cmds as cmds
import maya.mel as mel
from PySide2 import QtWidgets, QtCore
from shiboken2 import wrapInstance
from maya import OpenMayaUI as omui
import re

def get_maya_main_window():
    """获取Maya主窗口指针"""
    maya_ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(maya_ptr), QtWidgets.QWidget)

class ABCExporterUI(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super(ABCExporterUI, self).__init__(parent)
        self.setWindowTitle("批量ABC导出器 v1.3")
        self.setMinimumWidth(280)
        self.setWindowFlags(QtCore.Qt.Window)  # 设置为独立窗口
        self.setup_ui()

    def setup_ui(self):
        layout = QtWidgets.QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)  # 减少外围边距
        layout.setSpacing(8)  # 缩小组件间距
        
        # 帧范围设置
        frame_group = QtWidgets.QGroupBox("帧范围")
        frame_layout = QtWidgets.QGridLayout()
        frame_layout.setVerticalSpacing(6)  # 减少行间距
        frame_layout.setHorizontalSpacing(10)
        frame_layout.setContentsMargins(8, 12, 8, 12)  # 减少内边距
        self.range_mode = QtWidgets.QComboBox()
        self.range_mode.addItems(["当前帧", "时间滑块", "自定义"])
        self.start_frame = QtWidgets.QSpinBox()
        self.end_frame = QtWidgets.QSpinBox()
        self.start_frame.setValue(int(cmds.playbackOptions(q=True, min=True)))
        self.end_frame.setValue(int(cmds.playbackOptions(q=True, max=True)))
        self.start_frame.setEnabled(False)
        self.end_frame.setEnabled(False)
        self.range_mode.currentIndexChanged.connect(self.update_frame_range)
        
        # 第一行：范围模式
        frame_layout.addWidget(QtWidgets.QLabel("范围模式:"), 0, 0)
        self.range_mode = QtWidgets.QComboBox()
        self.range_mode.addItems(["当前帧", "时间滑块", "自定义"])
        # 设置默认为时间滑块
        self.range_mode.setCurrentText("时间滑块")
        frame_layout.addWidget(self.range_mode, 0, 1)  # 跨两列
    
        # 第二行：帧数输入
        frame_layout.addWidget(QtWidgets.QLabel("起始/结束"), 1, 0)
        self.start_frame = QtWidgets.QSpinBox()
        self.start_frame.setFixedWidth(70)  # 固定宽度
        frame_layout.addWidget(self.start_frame, 1, 1)
        self.end_frame = QtWidgets.QSpinBox()
        self.end_frame.setFixedWidth(70)
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
        self.color_sets = QtWidgets.QCheckBox("Write Color Sets")
        self.world_space = QtWidgets.QCheckBox("World Space") 
        self.visibility = QtWidgets.QCheckBox("Write Visibility")
        self.uv_sets = QtWidgets.QCheckBox("Write UV Sets")

        # 设置默认勾选状态
        self.uv_write.setChecked(True)
        self.world_space.setChecked(True)
        self.visibility.setChecked(True)
                
        options_layout.addWidget(self.uv_write, 0, 0)
        options_layout.addWidget(self.color_sets, 0, 1)
        options_layout.addWidget(self.world_space, 1, 0)
        options_layout.addWidget(self.visibility, 1, 1) 
        options_layout.addWidget(self.uv_sets, 2, 0)
        options_group.setLayout(options_layout)

        # 命名规则
        name_group = QtWidgets.QGroupBox("命名规则")
        name_layout = QtWidgets.QVBoxLayout()
        
        # 预设模板选择器
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
        self.template_combo.setCurrentIndex(0)  # 默认选中物体名称模板
        self.template_combo.currentIndexChanged.connect(self.apply_template)
        
        # 格式输入框
        self.name_pattern = QtWidgets.QLineEdit("{name}")
        
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
        
        name_layout.addWidget(QtWidgets.QLabel("预设模板:"))
        name_layout.addWidget(self.template_combo)
        name_layout.addWidget(QtWidgets.QLabel("自定义格式:"))
        name_layout.addWidget(self.name_pattern)
        name_layout.addWidget(name_help)
        name_group.setLayout(name_layout)

        # 导出按钮
        export_btn = QtWidgets.QPushButton("导出选中物体")
        export_btn.clicked.connect(self.do_export)
        export_btn.setStyleSheet("background-color: #2c7fb8; color: white;")
        
        layout.addWidget(frame_group)
        layout.addWidget(options_group)  # 添加选项组
        layout.addWidget(name_group)
        layout.addWidget(export_btn)
        self.setLayout(layout)

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
        return re.sub(r'[\\/:*?"<>|]', '_', name)

    def do_export(self):
        import os
        from datetime import datetime
        
        selected = cmds.ls(sl=True, long=True) or []
        if not selected:
            cmds.warning("请先选择要导出的物体或组")
            return
    
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
    
        # 文件路径选择
        file_path = cmds.fileDialog2(
            fileMode=3,
            dialogStyle=2,
            caption="选择导出目录")
        if not file_path:
            return
        file_path = file_path[0]
    
        # 批量导出
        success_count = 0
        for obj in selected:
            try:
                # 生成合法文件名
                obj_name = self.sanitize_name(obj.split('|')[-1])
                
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
                        version_str = f"v{version:02d}"
                        test_name = base_name.replace("##", version_str)
                        full_path = os.path.join(file_path, f"{test_name}.abc")
                        if not os.path.exists(full_path):
                            break
                        version += 1
                        if version > 99:  # 防止无限循环
                            cmds.warning(f"版本号超过最大值 (v99): {obj_name}")
                            version_str = f"v{version:02d}"
                            break
                    final_name = base_name.replace("##", version_str)
                else:
                    final_name = base_name
    
                # 构建完整文件路径
                file_name = os.path.join(file_path, f"{final_name}.abc")
                # 确保路径格式兼容Maya
                file_name = file_name.replace("\\", "/")
    
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
    
        # 显示汇总结果
        msg = f"导出完成！成功 {success_count}/{len(selected)} 个物体"
        if success_count < len(selected):
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

show()