# -*- coding: utf-8 -*-
"""批量ABC导出器 UI 回归测试(无需安装 Maya)

通过 mock maya 模块 + Qt offscreen 平台,真实构建插件界面,验证:
  1. 自定义格式输入框后方存在清空按钮,使用矢量绘制图标且实际渲染出
     可见像素(不允许出现图标空白),绘制失败时以文字兜底,点击可清空内容;
  2. 输入框为按钮让出宽度,且插件窗口宽度保持不变(含与历史版本的对比);
  3. 进度条百分比文字只显示整数,不显示小数;
  4. 窗口标题栏保留最小化/关闭按钮、不显示最大化按钮;
  5. 版本号已升级为 v2.5;
  6. 范围模式后方 -/+ 按钮成对紧贴,- 向中间收缩、+ 向两边扩张帧范围
     且范围模式自动切换为自定义,当前帧模式下置灰不可点;
  7. 模板切换、变量插入等既有命名规则行为未被破坏。

运行方式(在仓库根目录或任意目录均可):
    python tests/test_batch_abc_export_ui.py -v

依赖: PySide2 或 PySide6(与 Maya 一致即可)。
"""
from __future__ import print_function

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import types
import unittest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)
PLUGIN_PATH = os.path.join(ROOT, "Batch_ABC_Export.py")
PROBE_FLAG = "--probe-plugin"
# 冒充 Maya 用户脚本目录(不存在的子路径):插件只读取设置文件,不会写入
SETTINGS_STUB_DIR = os.path.join(TESTS_DIR, "_no_settings")

# 无显示环境下运行 Qt;必须在导入 PySide 之前设置
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6 import QtCore, QtWidgets, QtGui, QtTest
    PYSIDE_VERSION = 6
except ImportError:
    from PySide2 import QtCore, QtWidgets, QtGui, QtTest
    PYSIDE_VERSION = 2


def _install_maya_stub(script_dir):
    """注入最小的 maya 模块,让插件可以在普通 Python 中导入"""
    cmds = types.SimpleNamespace(
        playbackOptions=lambda **kw: 1001.0 if kw.get("min") else 1500.0,
        currentTime=lambda **kw: 1.0,
        internalVar=lambda **kw: script_dir,
        warning=lambda msg: None,
        ls=lambda **kw: [],
        file=lambda **kw: "",
        workspaceControl=lambda *a, **kw: "",
        deleteUI=lambda *a, **kw: None,
    )
    mel = types.SimpleNamespace(eval=lambda cmd: None)
    omui = types.SimpleNamespace(MQtUtil=types.SimpleNamespace(mainWindow=lambda: 0))
    maya = types.ModuleType("maya")
    maya.cmds = cmds
    maya.mel = mel
    maya.OpenMayaUI = omui
    sys.modules["maya"] = maya
    sys.modules["maya.cmds"] = cmds
    sys.modules["maya.mel"] = mel
    sys.modules["maya.OpenMayaUI"] = omui


def _create_app():
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    # offscreen 平台不会自动加载系统字体,手动挂载中文字体,保证文本宽度真实
    for font_path in (r"C:/Windows/Fonts/msyh.ttc", r"C:/Windows/Fonts/msyh.ttf",
                      r"C:/Windows/Fonts/simsun.ttc"):
        if os.path.isfile(font_path):
            QtGui.QFontDatabase.addApplicationFont(font_path)
            break
    app.setFont(QtGui.QFont("Microsoft YaHei", 9))
    return app


def _load_plugin(path, module_name):
    import importlib.util
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _probe_main(path):
    """子进程入口:加载插件并输出界面几何指标(避免影响主测试进程状态)"""
    _install_maya_stub(SETTINGS_STUB_DIR)
    app = _create_app()
    module = _load_plugin(path, "batch_abc_probe")
    ui = module.ui
    ui.adjustSize()
    ui.show()
    app.processEvents()
    result = {
        "window_width": ui.width(),
        "size_hint_width": ui.sizeHint().width(),
        "name_pattern_width": ui.name_pattern.width(),
        "has_clear_button": hasattr(ui, "clear_pattern_btn"),
    }
    print(json.dumps(result, ensure_ascii=False))
    sys.stdout.flush()


def _measure(path, attempts=2, timeout=60):
    """在独立子进程中测量指定版本插件界面,返回指标 dict

    探针打印完指标 JSON 后,Qt 在 Windows 退出/卸载阶段可能崩溃或
    卡死(与插件代码无关,offscreen 环境已知问题),因此父进程不依赖
    子进程退出:读到指标 JSON 行即主动终止子进程。拿不到输出时自动
    重试一次,仍失败才抛错
    """
    last_error = None
    for _ in range(attempts):
        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), PROBE_FLAG, path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace")
        stdout_lines = queue.Queue()
        stderr_tail = []
        pump_out = threading.Thread(
            target=lambda: [stdout_lines.put(line) for line in proc.stdout
                            if line] or stdout_lines.put(None),
            daemon=True)
        pump_err = threading.Thread(
            target=lambda: stderr_tail.append(proc.stderr.read()),
            daemon=True)
        pump_out.start()
        pump_err.start()
        json_line = None
        hit_eof = False
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                line = stdout_lines.get(timeout=0.5)
            except queue.Empty:
                continue
            if line is None:
                hit_eof = True
                break
            if line.strip().startswith("{"):
                json_line = line
                break
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
        if json_line:
            return json.loads(json_line)
        if hit_eof and proc.poll() is not None and proc.returncode == 0:
            last_error = RuntimeError("探针进程没有输出指标 JSON")
        else:
            last_error = RuntimeError(
                "探针进程未正常产出指标(退出码 {0},是否超时 {1}):\n{2}".format(
                    proc.returncode, not hit_eof,
                    (stderr_tail[0] if stderr_tail else "")[-2000:]))
    raise last_error


class BatchABCExportUITest(unittest.TestCase):
    """插件主界面回归测试"""

    @classmethod
    def setUpClass(cls):
        _install_maya_stub(SETTINGS_STUB_DIR)
        cls.app = _create_app()
        cls.module = _load_plugin(PLUGIN_PATH, "batch_abc_export_under_test")
        cls.ui = cls.module.ui

    def setUp(self):
        # 每个用例都恢复到一个确定的初始状态
        self.ui.name_pattern.setText("{name}")
        self.ui.template_combo.blockSignals(True)
        self.ui.template_combo.setCurrentIndex(0)
        self.ui.template_combo.blockSignals(False)
        self.ui.clear_pattern_btn.setVisible(True)
        self.ui.progress_bar.setValue(0)
        self.ui.progress_label.setText("就绪")
        self.ui.adjustSize()
        self.app.processEvents()

    def test_01_clear_button_exists_after_line_edit(self):
        """清空按钮存在,且紧跟在自定义格式输入框右侧"""
        btn = getattr(self.ui, "clear_pattern_btn", None)
        self.assertIsNotNone(btn, "界面中缺少 clear_pattern_btn")
        self.assertIsInstance(btn, QtWidgets.QPushButton,
                              "清空控件应为按钮")
        parent = btn.parentWidget()
        self.assertIs(parent, self.ui.name_pattern.parentWidget(),
                      "清空按钮应与输入框在同一容器中")

        row_layout = None
        for layout in parent.findChildren(QtWidgets.QHBoxLayout):
            if layout.indexOf(btn) >= 0 and layout.indexOf(self.ui.name_pattern) >= 0:
                row_layout = layout
                break
        self.assertIsNotNone(row_layout, "清空按钮与输入框不在同一行布局中")
        self.assertEqual(row_layout.indexOf(btn),
                         row_layout.indexOf(self.ui.name_pattern) + 1,
                         "清空按钮应排在输入框之后")

        line_geo = self.ui.name_pattern.geometry()
        btn_geo = btn.geometry()
        self.assertGreater(btn_geo.left(), line_geo.right(),
                           "清空按钮应位于输入框右侧")
        self.assertLessEqual(row_layout.spacing(), 3,
                             "输入框与清空图标的行内间距应尽量小")
        gap = btn_geo.left() - line_geo.right() - 1
        self.assertLessEqual(gap, 3,
                             "输入框与清空图标之间的实际间距应尽量小")

    def test_02_clear_button_uses_vector_icon(self):
        """清空按钮使用矢量绘制图标,且实际渲染出可见像素(不允许空白)"""
        btn = self.ui.clear_pattern_btn
        self.assertFalse(btn.icon().isNull(), "矢量绘制的清空图标不应为空")
        pix = btn.icon().pixmap(16, 16)
        self.assertFalse(pix.isNull(), "清空图标应能渲染出位图")
        image = pix.toImage()
        visible = 0
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() > 0:
                    visible += 1
        self.assertGreater(visible, 0,
                           "清空图标渲染结果不应是全透明空白")

    def test_02b_clear_button_fallback_when_icon_missing(self):
        """矢量绘制失败时按钮用文字兜底,不会显示空白"""
        original = self.module.ABCExporterUI.make_vector_close_icon
        self.module.ABCExporterUI.make_vector_close_icon = \
            lambda self: QtGui.QIcon()
        try:
            ui = self.module.ABCExporterUI()
        finally:
            self.module.ABCExporterUI.make_vector_close_icon = original
        try:
            self.assertTrue(ui.clear_pattern_btn.icon().isNull(),
                            "该用例模拟的图标应不可用")
            self.assertEqual(ui.clear_pattern_btn.text(), "×",
                             "图标缺失时应显示文字兜底")
        finally:
            ui.deleteLater()
            self.app.processEvents()

    def test_02c_builtin_icon_is_tinted_by_theme(self):
        """内置图标按主题文字色着色,浅色主题下不会与背景融合"""
        original = self.module.get_maya_icon

        def white_x_icon(name):
            pix = QtGui.QPixmap(16, 16)
            pix.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pix)
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255))   # 模拟浅色内置图标
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(3, 3, 12, 12)
            painter.drawLine(12, 3, 3, 12)
            painter.end()
            return QtGui.QIcon(pix)

        self.module.get_maya_icon = white_x_icon
        try:
            icon = self.ui.make_themed_icon("closeTabButton.png")
        finally:
            self.module.get_maya_icon = original

        self.assertFalse(icon.isNull(), "主题着色后的图标不应为空")
        pix = icon.pixmap(QtCore.QSize(18, 18))
        image = pix.toImage()
        text_color = self.ui.palette().color(QtGui.QPalette.WindowText)
        tinted = 0
        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                if color.alpha() > 128:
                    tinted += 1
                    self.assertLessEqual(abs(color.red() - text_color.red()), 12)
                    self.assertLessEqual(abs(color.green() - text_color.green()), 12)
                    self.assertLessEqual(abs(color.blue() - text_color.blue()), 12)
        self.assertGreater(tinted, 0, "着色后的图标没有可见像素")

    def test_02d_clear_icon_centered_and_enlarged(self):
        """内置图标会裁掉透明边、放大并居中,避免图标偏小或偏移"""
        original = self.module.get_maya_icon

        def small_centered_x_icon(name):
            # 模拟 Maya 图标:32x32 画布中只有中间一小块 X,四周大量透明边
            pix = QtGui.QPixmap(32, 32)
            pix.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pix)
            painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
            pen = QtGui.QPen(QtGui.QColor(255, 255, 255))
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(12, 12, 19, 19)
            painter.drawLine(19, 12, 12, 19)
            painter.end()
            return QtGui.QIcon(pix)

        self.module.get_maya_icon = small_centered_x_icon
        try:
            icon = self.ui.make_themed_icon("closeTabButton.png")
        finally:
            self.module.get_maya_icon = original

        self.assertFalse(icon.isNull(), "裁剪放大后的图标不应为空")
        pix = icon.pixmap(QtCore.QSize(18, 18))
        image = pix.toImage()
        left, top = image.width(), image.height()
        right = bottom = -1
        for y in range(image.height()):
            for x in range(image.width()):
                if image.pixelColor(x, y).alpha() > 0:
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)
        self.assertGreaterEqual(right, left, "图标没有可见像素")

        content_w = right - left + 1
        content_h = bottom - top + 1
        self.assertGreaterEqual(min(content_w, content_h), 12,
                                "图标内容应被放大到接近画布大小")

        canvas_center_x = (image.width() - 1) / 2.0
        canvas_center_y = (image.height() - 1) / 2.0
        content_center_x = (left + right) / 2.0
        content_center_y = (top + bottom) / 2.0
        self.assertLessEqual(abs(content_center_x - canvas_center_x), 1.5,
                             "图标内容应在按钮画布中水平居中")
        self.assertLessEqual(abs(content_center_y - canvas_center_y), 1.5,
                             "图标内容应在按钮画布中垂直居中")

    def test_03_clear_button_clears_text(self):
        """点击清空按钮后输入框内容被清空"""
        self.assertTrue(self.ui.clear_pattern_btn.isEnabled(), "清空按钮应可用")
        self.ui.name_pattern.setText("{scene}_{name}_##")
        self.ui.clear_pattern_btn.click()
        self.assertEqual(self.ui.name_pattern.text(), "",
                         "点击清空按钮后输入框应清空")

    def test_04_clear_button_syncs_template_to_custom(self):
        """清空后预设模板下拉框同步切到“自定义”"""
        self.ui.template_combo.setCurrentIndex(1)
        self.ui.clear_pattern_btn.click()
        self.assertEqual(self.ui.template_combo.currentIndex(), 6,
                         "清空后预设模板应切到“自定义”")

    def test_04b_shift_buttons_adjacent_to_mode_combo(self):
        """-/+ 按钮位于范围模式下拉框右侧,两键之间只有极小间距"""
        minus = getattr(self.ui, "frame_minus_btn", None)
        plus = getattr(self.ui, "frame_plus_btn", None)
        self.assertIsNotNone(minus, "界面中缺少 - 按钮")
        self.assertIsNotNone(plus, "界面中缺少 + 按钮")
        combo = self.ui.range_mode
        self.assertGreater(minus.x(), combo.x() + combo.width(),
                           "- 按钮应在范围模式下拉框右侧")
        gap = plus.x() - (minus.x() + minus.width())
        self.assertTrue(0 <= gap <= 3,
                        "两个按钮之间应只留极小间距,实际间距 {0}px".format(gap))
        self.assertEqual(minus.text(), "-")
        self.assertEqual(plus.text(), "+")

    def test_04c_shift_buttons_expand_shrink_range(self):
        """点击 - 向中间收缩帧范围,点击 + 向两边扩张,且模式自动切自定义"""
        ui = self.ui
        # stub 时间滑块范围为 1001-1500
        ui.range_mode.setCurrentText("时间滑块")
        self.assertEqual((ui.start_frame.value(), ui.end_frame.value()),
                         (1001, 1500), "时间滑块模式应显示 1001-1500")
        ui.frame_plus_btn.click()
        self.assertEqual(ui.range_mode.currentText(), "自定义",
                         "点击 + 后范围模式应自动切换为自定义")
        self.assertEqual((ui.start_frame.value(), ui.end_frame.value()),
                         (1000, 1501), "点击 + 应向两边各扩张 1 帧")
        ui.frame_minus_btn.click()
        self.assertEqual(ui.range_mode.currentText(), "自定义")
        self.assertEqual((ui.start_frame.value(), ui.end_frame.value()),
                         (1001, 1500), "点击 - 应向中间各收缩 1 帧")
        # 与需求示例一致:1001-1010 点击 - 变 1002-1009,点击 + 变 1000-1011
        ui.start_frame.setValue(1001)
        ui.end_frame.setValue(1010)
        ui.frame_minus_btn.click()
        self.assertEqual((ui.start_frame.value(), ui.end_frame.value()),
                         (1002, 1009), "1001-1010 点击 - 应变为 1002-1009")
        ui.frame_plus_btn.click()
        self.assertEqual((ui.start_frame.value(), ui.end_frame.value()),
                         (1001, 1010), "1002-1009 点击 + 应变回 1001-1010")
        ui.frame_plus_btn.click()
        self.assertEqual((ui.start_frame.value(), ui.end_frame.value()),
                         (1000, 1011), "1001-1010 点击 + 应变为 1000-1011")

    def test_04d_shift_buttons_disabled_on_current_frame(self):
        """当前帧模式下 -/+ 按钮置灰不可点,其余模式可用"""
        ui = self.ui
        ui.range_mode.setCurrentText("当前帧")
        self.assertFalse(ui.frame_minus_btn.isEnabled(),
                         "当前帧模式下 - 按钮应置灰")
        self.assertFalse(ui.frame_plus_btn.isEnabled(),
                         "当前帧模式下 + 按钮应置灰")
        # stub currentTime 为 1.0,起止帧应恒为 1-1
        self.assertEqual((ui.start_frame.value(), ui.end_frame.value()), (1, 1))
        QtTest.QTest.mouseClick(ui.frame_minus_btn, QtCore.Qt.LeftButton)
        QtTest.QTest.mouseClick(ui.frame_plus_btn, QtCore.Qt.LeftButton)
        self.assertEqual((ui.start_frame.value(), ui.end_frame.value()), (1, 1),
                         "当前帧模式下点击置灰按钮不应改变帧数值")
        self.assertEqual(ui.range_mode.currentText(), "当前帧",
                         "置灰按钮不应触发模式切换")
        ui.range_mode.setCurrentText("自定义")
        self.assertTrue(ui.frame_minus_btn.isEnabled(), "自定义模式下 - 按钮应可用")
        self.assertTrue(ui.frame_plus_btn.isEnabled(), "自定义模式下 + 按钮应可用")

    def test_05_input_shortened_without_widening_window(self):
        """清空按钮不增加窗口宽度,输入框相应缩短"""
        ui = self.ui
        ui.clear_pattern_btn.setVisible(True)
        self.app.processEvents()
        ui.adjustSize()
        width_with_btn = ui.sizeHint().width()
        line_with_btn = ui.name_pattern.width()

        ui.clear_pattern_btn.setVisible(False)
        self.app.processEvents()
        ui.adjustSize()
        width_without_btn = ui.sizeHint().width()
        line_without_btn = ui.name_pattern.width()

        ui.clear_pattern_btn.setVisible(True)
        self.app.processEvents()
        ui.adjustSize()

        self.assertEqual(width_with_btn, width_without_btn,
                         "添加清空按钮后窗口宽度不应增加")
        self.assertLess(line_with_btn, line_without_btn,
                        "输入框应为清空按钮让出宽度")

    def test_06_window_width_matches_previous_version(self):
        """与 git 历史中未加清空按钮的版本对比:窗口宽度一致、输入框变短"""
        old_source = self._read_previous_release_source()
        if old_source is None:
            self.skipTest("无法从 git 历史读取未加清空按钮的版本")

        # 临时文件直接放在 tests 目录(DSH 沙箱只保证已有工作区路径可写)
        old_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "_old_version_{0}.py".format(os.getpid()))
        try:
            with open(old_path, "w", encoding="utf-8") as f:
                f.write(old_source)
            old = _measure(old_path)
            new = _measure(PLUGIN_PATH)
        finally:
            try:
                os.remove(old_path)
            except OSError:
                pass

        self.assertFalse(old["has_clear_button"], "修改前版本不应有清空按钮")
        self.assertTrue(new["has_clear_button"], "当前版本应包含清空按钮")
        self.assertEqual(new["window_width"], old["window_width"],
                         "修改后插件窗口宽度应与修改前一致")
        self.assertEqual(new["size_hint_width"], old["size_hint_width"],
                         "修改后窗口建议宽度应与修改前一致")
        self.assertLess(new["name_pattern_width"], old["name_pattern_width"],
                        "自定义格式输入框应比修改前缩短")

    def test_07_progress_text_has_no_decimal(self):
        """进度百分比文字为整数,不出现小数点"""
        integer_text = re.compile(r"^(\d+)%  ")
        cases = [(0, 1), (1, 4), (1, 3), (2, 3), (1, 10), (9, 10),
                 (999, 1000), (1, 1), (0, 0)]
        for current, total in cases:
            self.ui.set_progress(current, total, "测试状态")
            text = self.ui.progress_label.text()
            match = integer_text.match(text)
            self.assertIsNotNone(
                match, "进度文本应为“整数% + 两个空格 + 状态”,实际为: {0!r}".format(text))
            self.assertNotIn(".", text.split("%")[0],
                             "百分比文字不应包含小数点: {0!r}".format(text))
            # 百分比应与进度条数值(0~1000 表示 0~100%)一致
            self.assertEqual(int(match.group(1)),
                             int(self.ui.progress_bar.value() / 10),
                             "百分比文字与进度条数值不一致: {0!r}".format(text))

    def test_08_progress_text_specific_values(self):
        """关键进度节点显示整数百分比"""
        self.ui.set_progress(1, 2, "半程")
        self.assertEqual(self.ui.progress_label.text(), "50%  半程")
        self.ui.set_progress(1, 1, "完成")
        self.assertEqual(self.ui.progress_label.text(), "100%  完成")
        self.ui.set_progress(0, 1, "开始")
        self.assertEqual(self.ui.progress_label.text(), "0%  开始")
        self.ui.set_progress(999, 1000, "九成九")
        self.assertEqual(self.ui.progress_label.text(), "99%  九成九")

    def test_09_naming_rules_regression(self):
        """既有命名规则行为未受影响(模板切换、变量插入)"""
        self.ui.template_combo.setCurrentIndex(1)
        self.assertEqual(self.ui.name_pattern.text(), "{scene}_{name}_##",
                         "预设模板切换结果不正确")
        self.ui.name_pattern.setText("abc")
        self.ui.name_pattern.setCursorPosition(3)
        self.ui.insert_variable("{name}")
        self.assertEqual(self.ui.name_pattern.text(), "abc_{name}",
                         "变量插入结果不正确")

    def test_10_window_buttons(self):
        """窗口标题栏保留最小化/关闭按钮,去除最大化按钮"""
        flags = int(self.ui.windowFlags())
        self.assertTrue(flags & int(QtCore.Qt.Window), "应保持独立窗口类型")
        self.assertTrue(flags & int(QtCore.Qt.WindowMinimizeButtonHint),
                        "应保留最小化按钮")
        self.assertTrue(flags & int(QtCore.Qt.WindowCloseButtonHint),
                        "应保留关闭按钮")
        self.assertFalse(flags & int(QtCore.Qt.WindowMaximizeButtonHint),
                         "不应显示最大化按钮")

    def test_11_plugin_version_is_v25(self):
        """插件文件头版本号已升级到 v2.5"""
        self.assertEqual(self.module.PLUGIN_VERSION, "v2.5",
                         "文件头版本号应为 v2.5")
        self.assertIn("v2.5", self.ui.windowTitle(),
                      "窗口标题应显示 v2.5")

    @staticmethod
    def _read_previous_release_source():
        """从 git 历史读取最近一个未加清空按钮的插件版本作为宽度基线

        从最新提交起逐个回溯改动过插件文件的版本,取第一个不含
        clear_pattern_btn 的源码(即 v2.4 加入清空按钮之前的最后版本);
        不可用时返回 None
        """
        try:
            proc = subprocess.run(
                ["git", "-C", ROOT, "log", "--format=%H", "--",
                 "Batch_ABC_Export.py"],
                capture_output=True, timeout=30)
            if proc.returncode != 0:
                return None
            commits = proc.stdout.decode("utf-8", errors="replace").split()
            for commit in commits:
                blob = subprocess.run(
                    ["git", "-C", ROOT,
                     "show", "{0}:Batch_ABC_Export.py".format(commit)],
                    capture_output=True, timeout=30)
                if blob.returncode != 0:
                    continue
                source = blob.stdout.decode("utf-8", errors="replace")
                if "clear_pattern_btn" not in source:
                    return source
        except (OSError, subprocess.SubprocessError):
            pass
        return None


def _report_child_exit_noise(text):
    """过滤 PySide6 在 offscreen 平台退出阶段打印的环境噪音"""
    noise = ("QFontDatabase:", "Note that Qt no longer ships fonts",
             "This plugin does not support propagateSizeHints()",
             "QThreadStorage:")
    return "\n".join(line for line in text.splitlines()
                     if not any(marker in line for marker in noise))


def _run_child_tests():
    """子进程:真正创建 Qt 界面并运行测试"""
    # 管道输出统一 UTF-8,避免 Windows 本地编码造成中文乱码
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    verbosity = 2 if "-v" in sys.argv else 1
    suite = unittest.TestLoader().loadTestsFromTestCase(BatchABCExportUITest)
    result = unittest.TextTestRunner(verbosity=verbosity).run(suite)
    sys.stdout.flush()
    sys.stderr.flush()
    sys.exit(0 if result.wasSuccessful() else 1)


def _run_parent_harness():
    """父进程:不创建 Qt 控件,根据子进程的 unittest 输出判定结果

    本地 PySide6 + offscreen 环境在解释器退出析构 Qt 对象时会偶发
    访问冲突(与插件代码无关,子进程退出码不可靠)。这里让子进程输出
    完整测试结果,父进程按输出中的 OK / FAILED 与测试数量判定成败,
    保证测试命令退出码可信。
    """
    child_cmd = [sys.executable, os.path.abspath(__file__), "--child"] + sys.argv[1:]
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    try:
        proc = subprocess.run(child_cmd, capture_output=True, text=True,
                              encoding="utf-8", errors="replace",
                              timeout=300, env=env)
    except subprocess.TimeoutExpired:
        sys.stderr.write("测试超时(300 秒)\n")
        return 1
    output = _report_child_exit_noise(proc.stdout + proc.stderr)
    if output:
        sys.stderr.write(output + "\n")
        sys.stderr.flush()

    ran = re.search(r"(?m)^Ran (\d+) tests? in ", output)
    passed = (ran is not None and int(ran.group(1)) > 0
              and re.search(r"(?m)^OK( \(.*\))?$", output) is not None
              and "FAILED" not in output)
    if proc.returncode != 0 and passed:
        # 子进程退出阶段的 Qt 析构崩溃:测试结果已完整输出,不影响判定
        sys.stderr.write("[test harness] 子进程退出阶段发生 Qt 析构异常"
                         "(退出码 {0}),测试结果以上方输出为准。\n".format(proc.returncode))
    return 0 if passed else 1


if __name__ == "__main__":
    if PROBE_FLAG in sys.argv:
        _probe_main(sys.argv[sys.argv.index(PROBE_FLAG) + 1])
        sys.stdout.flush()
        sys.stderr.flush()
        # 注意:子进程退出阶段 Qt 卸载偶发崩溃/卡死(Windows ExitProcess
        # 死锁),父进程 _measure 读到指标 JSON 即终止子进程,不依赖此处
        sys.exit(0)
    if "--child" in sys.argv:
        _run_child_tests()
    else:
        sys.exit(_run_parent_harness())
