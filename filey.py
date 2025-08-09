import sys
import os
import shutil
import time
import json
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QListWidget,
    QListWidgetItem, QPushButton, QLabel, QFileIconProvider,
    QToolTip, QDialog, QComboBox, QDialogButtonBox, QInputDialog,
    QMessageBox, QMenu, QLineEdit, QAbstractItemView, QColorDialog
)
from PyQt6.QtGui import QFont, QAction, QDrag, QCursor, QColor
from PyQt6.QtCore import (
    Qt, QEvent, QPropertyAnimation, QEasingCurve, QMimeData, QUrl,
    pyqtSignal, QThread, QObject, pyqtSlot, QPoint
)


SETTINGS_FILE = Path.home() / ".filey_settings.json"


def save_settings(data):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print("Failed to save settings:", e)


def load_settings():
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("Failed to load settings:", e)
    return None


def sizeof_fmt(num, suffix='B'):
    for unit in ['','K','M','G','T','P','E','Z']:
        if abs(num) < 1024.0:
            return f"{num:3.1f} {unit}{suffix}"
        num /= 1024.0
    return f"{num:.1f} Y{suffix}"


DEFAULT_THEMES = {
    "Light": {
        "background": "#f0f0f0",
        "text": "#202020",
        "selected_bg": "#007acc",
        "hover_bg": "#cce4f7",
        "tooltip_bg": "#eeeeee",
    },
    "Dark": {
        "background": "#1e1e1e",
        "text": "#dddddd",
        "selected_bg": "#007acc",
        "hover_bg": "#094771",
        "tooltip_bg": "#333333",
    }
}


def theme_to_stylesheet(theme):
    return f"""
    QWidget {{ background-color: {theme['background']}; color: {theme['text']}; }}
    QListWidget {{ background-color: {theme['background']}; border: 1px solid #888; border-radius: 8px; font-size: 11pt; }}
    QListWidget::item {{ padding: 10px 8px; border-radius: 6px; }}
    QListWidget::item:selected {{ background-color: {theme['selected_bg']}; color: white; }}
    QListWidget::item:hover {{ background-color: {theme['hover_bg']}; color: white; }}
    QLabel {{ font-weight: 600; }}
    QToolTip {{ background-color: {theme['tooltip_bg']}; color: {theme['text']}; border: 1px solid #555; padding: 5px; border-radius: 5px; font-size: 10pt; }}
    QPushButton {{ background-color: transparent; border: none; font-size: 16pt; }}
    QPushButton:hover {{ color: #00aaff; font-weight: bold; }}
    """


class AnimationSettingsDialog(QDialog):
    def __init__(self, current_duration, current_type, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Animation Settings")
        self.resize(300, 150)
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.duration_combo = QComboBox()
        self.duration_combo.addItems(["100 ms", "200 ms", "400 ms", "800 ms"])
        self.duration_combo.setCurrentText(f"{current_duration} ms")
        layout.addWidget(QLabel("Animation Duration:"))
        layout.addWidget(self.duration_combo)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["Fade", "Slide", "None"])
        self.type_combo.setCurrentText(current_type)
        layout.addWidget(QLabel("Animation Type:"))
        layout.addWidget(self.type_combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_settings(self):
        duration = int(self.duration_combo.currentText().split()[0])
        anim_type = self.type_combo.currentText()
        return duration, anim_type


class ThemeEditorDialog(QDialog):
    def __init__(self, current_theme_dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Edit Theme")
        self.resize(400, 300)
        self.theme = current_theme_dict.copy()
        layout = QVBoxLayout()
        self.setLayout(layout)

        self.color_buttons = {}
        for key in ["background", "text", "selected_bg", "hover_bg", "tooltip_bg"]:
            h = QHBoxLayout()
            label = QLabel(key.replace("_", " ").title() + ":")
            btn = QPushButton()
            btn.setFixedSize(40, 25)
            btn.setStyleSheet(f"background-color: {self.theme[key]}")
            btn.clicked.connect(lambda _, k=key: self.pick_color(k))
            self.color_buttons[key] = btn
            h.addWidget(label)
            h.addWidget(btn)
            layout.addLayout(h)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def pick_color(self, key):
        color = QColorDialog.getColor(QColor(self.theme[key]), self)
        if color.isValid():
            self.theme[key] = color.name()
            self.color_buttons[key].setStyleSheet(f"background-color: {self.theme[key]}")

    def get_theme(self):
        return self.theme


class Worker(QObject):
    finished = pyqtSignal(list)

    def __init__(self, path):
        super().__init__()
        self.path = path

    @pyqtSlot()
    def run(self):
        try:
            entries = os.listdir(self.path)
            folders = []
            files = []

            for e in entries:
                full_path = os.path.join(self.path, e)
                if os.path.isdir(full_path):
                    folders.append(e)
                elif os.path.isfile(full_path):
                    files.append(e)

            folders.sort(key=str.lower)
            files.sort(key=str.lower)

            results = []

            for folder in folders:
                full_path = os.path.join(self.path, folder)
                results.append({
                    "name": folder,
                    "full_path": full_path,
                    "is_folder": True,
                    "size_text": ""
                })

            for file in files:
                full_path = os.path.join(self.path, file)
                try:
                    size_bytes = os.path.getsize(full_path)
                    size_text = sizeof_fmt(size_bytes)
                except Exception:
                    size_text = ""
                results.append({
                    "name": file,
                    "full_path": full_path,
                    "is_folder": False,
                    "size_text": size_text
                })

            self.finished.emit(results)

        except Exception:
            self.finished.emit([])


class Filey(QListWidget):
    path_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Filey - Modern File Explorer")
        self.resize(1000, 650)

        font = QFont("Segoe UI", 10)
        self.setFont(font)

        # Load settings if exist
        settings = load_settings()
        if settings:
            self.current_path = settings.get("last_path", os.path.expanduser("~"))
            self.anim_duration = settings.get("anim_duration", 200)
            self.anim_type = settings.get("anim_type", "Fade")
            theme_loaded = settings.get("theme", DEFAULT_THEMES["Dark"])
            # Validate loaded theme keys
            if all(k in theme_loaded for k in DEFAULT_THEMES["Dark"]):
                self.current_theme = theme_loaded
            else:
                self.current_theme = DEFAULT_THEMES["Dark"]
        else:
            self.current_path = os.path.expanduser("~")
            self.anim_duration = 200
            self.anim_type = "Fade"
            self.current_theme = DEFAULT_THEMES["Dark"]

        self.apply_theme(self.current_theme)

        self.history = []
        self.history_index = -1

        self.clipboard_path = None

        self.icon_provider = QFileIconProvider()

        self.full_entry_list = []

        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

        self.load_thread = None
        self.worker = None

        self._load_start_time = 0

        self.load_path(self.current_path, add_history=True, animate=False)

        self.drag_start_pos = None

        self.itemDoubleClicked.connect(self.item_activated)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self.open_context_menu)

        self.search_bar = None

    def save_session(self):
        data = {
            "last_path": self.current_path,
            "anim_duration": self.anim_duration,
            "anim_type": self.anim_type,
            "theme": self.current_theme
        }
        save_settings(data)

    def apply_theme(self, theme_dict):
        self.current_theme = theme_dict
        self.setStyleSheet(theme_to_stylesheet(theme_dict))

    def open_context_menu(self, pos):
        item = self.itemAt(pos)
        menu = QMenu()

        new_folder_action = QAction("New Folder", self)
        new_folder_action.triggered.connect(self.create_folder)
        menu.addAction(new_folder_action)

        new_file_action = QAction("New File", self)
        new_file_action.triggered.connect(self.create_file)
        menu.addAction(new_file_action)

        if item:
            menu.addSeparator()

            open_action = QAction("Open", self)
            open_action.triggered.connect(lambda: self.item_activated(item))
            menu.addAction(open_action)

            rename_action = QAction("Rename", self)
            rename_action.triggered.connect(self.rename_item)
            menu.addAction(rename_action)

            delete_action = QAction("Delete", self)
            delete_action.triggered.connect(self.delete_item)
            menu.addAction(delete_action)

            copy_action = QAction("Copy", self)
            copy_action.triggered.connect(self.copy_item)
            menu.addAction(copy_action)

        if self.clipboard_path:
            paste_action = QAction("Paste", self)
            paste_action.triggered.connect(self.paste_item)
            menu.addAction(paste_action)

        menu.exec(self.viewport().mapToGlobal(pos))

    def create_folder(self):
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if ok and name.strip():
            new_path = os.path.join(self.current_path, name.strip())
            try:
                os.mkdir(new_path)
                self.load_path(self.current_path, add_history=False, animate=False)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not create folder:\n{e}")

    def create_file(self):
        name, ok = QInputDialog.getText(self, "New File", "File name:")
        if ok and name.strip():
            new_path = os.path.join(self.current_path, name.strip())
            if os.path.exists(new_path):
                QMessageBox.warning(self, "Error", "File already exists.")
                return
            try:
                with open(new_path, 'w', encoding='utf-8') as f:
                    f.write("")
                self.load_path(self.current_path, add_history=False, animate=False)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not create file:\n{e}")

    def delete_item(self):
        item = self.currentItem()
        if not item:
            QMessageBox.information(self, "Delete", "No item selected.")
            return
        path = item.data(256)
        is_folder = item.data(257)
        reply = QMessageBox.question(
            self, "Confirm Delete",
            f"Are you sure you want to delete '{os.path.basename(path)}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                if is_folder:
                    shutil.rmtree(path)
                else:
                    os.remove(path)
                self.load_path(self.current_path, add_history=False, animate=False)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not delete:\n{e}")

    def rename_item(self):
        item = self.currentItem()
        if not item:
            QMessageBox.information(self, "Rename", "No item selected.")
            return
        old_path = item.data(256)
        old_name = os.path.basename(old_path)
        new_name, ok = QInputDialog.getText(self, "Rename", "New name:", text=old_name)
        if ok and new_name.strip():
            new_path = os.path.join(self.current_path, new_name.strip())
            if os.path.exists(new_path):
                QMessageBox.warning(self, "Error", "Name already exists.")
                return
            try:
                os.rename(old_path, new_path)
                self.load_path(self.current_path, add_history=False, animate=False)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not rename:\n{e}")

    def copy_item(self):
        item = self.currentItem()
        if not item:
            QMessageBox.information(self, "Copy", "No item selected.")
            return
        self.clipboard_path = item.data(256)

    def paste_item(self):
        if not self.clipboard_path or not os.path.exists(self.clipboard_path):
            QMessageBox.information(self, "Paste", "Nothing to paste or source no longer exists.")
            return
        src = self.clipboard_path
        base_name = os.path.basename(src)
        dest = os.path.join(self.current_path, base_name)

        def unique_path(path):
            if not os.path.exists(path):
                return path
            base, ext = os.path.splitext(path)
            i = 1
            while True:
                new_path = f"{base} - Copy{i}{ext}"
                if not os.path.exists(new_path):
                    return new_path
                i += 1

        dest_unique = unique_path(dest)
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dest_unique)
            else:
                shutil.copy2(src, dest_unique)
            self.load_path(self.current_path, add_history=False, animate=False)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not paste:\n{e}")

    def load_path(self, path, add_history=False, animate=True):
        self._load_start_time = time.perf_counter()
        self.current_path = path
        self.path_changed.emit(self.current_path)

        if add_history:
            self.history = self.history[:self.history_index + 1]
            self.history.append(path)
            self.history_index += 1

        parent = self.parent()
        if parent and hasattr(parent, "update_nav_buttons"):
            parent.update_nav_buttons()

        # Safely stop any previous loading thread if running
        if self.load_thread is not None:
            try:
                if self.load_thread.isRunning():
                    self.load_thread.quit()
                    self.load_thread.wait()
            except RuntimeError:
                # Thread object already deleted; ignore
                pass
            self.load_thread = None

        self.load_thread = QThread()
        self.worker = Worker(path)
        self.worker.moveToThread(self.load_thread)

        self.load_thread.started.connect(self.worker.run)
        self.worker.finished.connect(lambda results: self._on_load_finished(results, animate))
        self.worker.finished.connect(self.load_thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.load_thread.finished.connect(self.load_thread.deleteLater)

        self.load_thread.start()

        self.save_session()

    def _on_load_finished(self, entries, animate):
        duration_ms = (time.perf_counter() - self._load_start_time) * 1000
        print(f"Loaded {len(entries)} items in {duration_ms:.1f} ms")
        self.full_entry_list = entries
        if animate:
            self.animate_file_list_reload(entries)
        else:
            self._rebuild_file_list(entries)

    def animate_file_list_reload(self, entries):
        if self.anim_type == "None":
            self._rebuild_file_list(entries)
            return

        if self.anim_type == "Fade":
            self.animation = QPropertyAnimation(self.viewport(), b"windowOpacity")
            self.animation.setDuration(self.anim_duration)
            self.animation.setStartValue(1.0)
            self.animation.setEndValue(0.0)
            self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
            self.animation.finished.connect(lambda: self._after_fade_out(entries))
            self.animation.start()
        elif self.anim_type == "Slide":
            self.animation = QPropertyAnimation(self.viewport(), b"pos")
            self.animation.setDuration(self.anim_duration)
            start_pos = self.viewport().pos()
            end_pos = QPoint(start_pos.x() + 50, start_pos.y())
            self.animation.setStartValue(start_pos)
            self.animation.setEndValue(end_pos)
            self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
            self.animation.finished.connect(lambda: self._after_slide_out(entries))
            self.animation.start()

    def _after_fade_out(self, entries):
        self._rebuild_file_list(entries)
        self.animation = QPropertyAnimation(self.viewport(), b"windowOpacity")
        self.animation.setDuration(self.anim_duration)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.animation.start()

    def _after_slide_out(self, entries):
        self._rebuild_file_list(entries)
        self.animation = QPropertyAnimation(self.viewport(), b"pos")
        self.animation.setDuration(self.anim_duration)
        end_pos = self.viewport().pos()
        start_pos = QPoint(end_pos.x() - 50, end_pos.y())
        self.viewport().move(start_pos)
        self.animation.setStartValue(start_pos)
        self.animation.setEndValue(end_pos)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        self.animation.start()

    def _rebuild_file_list(self, entries):
        self.clear()
        for entry in entries:
            display_name = f"{entry['name']}"
            if entry['size_text']:
                display_name += f" ({entry['size_text']})"
            item = QListWidgetItem(display_name)
            icon = self.icon_provider.icon(QFileIconProvider.IconType.Folder if entry['is_folder'] else QFileIconProvider.IconType.File)
            item.setIcon(icon)
            item.setData(256, entry['full_path'])
            item.setData(257, entry['is_folder'])
            self.addItem(item)

    def item_activated(self, item):
        if item is None:
            return
        path = item.data(256)
        is_folder = item.data(257)
        if is_folder:
            self.load_path(path, add_history=True)
        else:
            try:
                if sys.platform == "win32":
                    os.startfile(path)
                elif sys.platform == "darwin":
                    os.system(f"open \"{path}\"")
                else:
                    os.system(f"xdg-open \"{path}\"")
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not open file:\n{e}")

    def search_items(self, text):
        text = text.strip().lower()
        if not text:
            self._rebuild_file_list(self.full_entry_list)
            return
        filtered = [e for e in self.full_entry_list if text in e['name'].lower()]
        self._rebuild_file_list(filtered)

    # Drag and drop move support
    def startDrag(self, supportedActions):
        selected = self.selectedItems()
        if not selected:
            return
        drag = QDrag(self)
        mime_data = QMimeData()
        urls = []
        for item in selected:
            path = item.data(256)
            urls.append(QUrl.fromLocalFile(path))
        mime_data.setUrls(urls)
        drag.setMimeData(mime_data)
        drag.exec(Qt.DropAction.MoveAction)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        target_pos = event.position().toPoint()
        target_item = self.itemAt(target_pos)
        if target_item:
            target_path = target_item.data(256)
            if not os.path.isdir(target_path):
                target_path = os.path.dirname(target_path)
        else:
            target_path = self.current_path

        for url in urls:
            src_path = url.toLocalFile()
            base_name = os.path.basename(src_path)
            dest_path = os.path.join(target_path, base_name)
            try:
                # Prevent moving into same folder (no-op)
                if os.path.abspath(src_path) == os.path.abspath(dest_path):
                    continue
                shutil.move(src_path, dest_path)
            except Exception as e:
                QMessageBox.warning(self, "Error", f"Could not move:\n{e}")

        self.load_path(self.current_path, add_history=False, animate=True)
        event.acceptProposedAction()

    # For hover tooltip showing folder content names
    def event(self, e):
        if e.type() == QEvent.Type.ToolTip:
            pos = e.pos()  # <-- FIX here: Use e.pos() instead of e.position()
            item = self.itemAt(pos)
            if item:
                path = item.data(256)
                if os.path.isdir(path):
                    try:
                        content = os.listdir(path)
                        content = [c for c in content if not c.startswith('.')]
                        preview = ", ".join(content[:5])
                        if len(content) > 5:
                            preview += ", ..."
                        QToolTip.showText(e.globalPos(), preview, self)
                    except Exception:
                        QToolTip.hideText()
                else:
                    QToolTip.hideText()
            else:
                QToolTip.hideText()
        return super().event(e)


class FileyWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Filey - Modern File Explorer")
        self.resize(1000, 700)

        main_layout = QVBoxLayout()
        self.setLayout(main_layout)

        nav_layout = QHBoxLayout()
        main_layout.addLayout(nav_layout)

        self.back_button = QPushButton("←")
        self.back_button.setFixedWidth(40)
        self.back_button.clicked.connect(self.go_back)
        nav_layout.addWidget(self.back_button)

        self.forward_button = QPushButton("→")
        self.forward_button.setFixedWidth(40)
        self.forward_button.clicked.connect(self.go_forward)
        nav_layout.addWidget(self.forward_button)

        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        nav_layout.addWidget(self.path_label)

        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search current folder...")
        nav_layout.addWidget(self.search_bar)

        self.anim_settings_btn = QPushButton("Animation Settings")
        self.anim_settings_btn.clicked.connect(self.open_animation_settings)
        nav_layout.addWidget(self.anim_settings_btn)

        self.theme_edit_btn = QPushButton("Edit Theme")
        self.theme_edit_btn.clicked.connect(self.open_theme_editor)
        nav_layout.addWidget(self.theme_edit_btn)

        self.file_list = Filey()
        main_layout.addWidget(self.file_list)

        self.file_list.path_changed.connect(self.path_label.setText)

        self.back_button.setEnabled(False)
        self.forward_button.setEnabled(False)

        self.file_list.search_bar = self.search_bar
        self.search_bar.textChanged.connect(self.file_list.search_items)

        self.file_list.setParent(self)
        self.file_list.viewport().installEventFilter(self.file_list)

    def update_nav_buttons(self):
        idx = self.file_list.history_index
        history_len = len(self.file_list.history)
        self.back_button.setEnabled(idx > 0)
        self.forward_button.setEnabled(idx < history_len - 1)

    def go_back(self):
        if self.file_list.history_index > 0:
            self.file_list.history_index -= 1
            path = self.file_list.history[self.file_list.history_index]
            self.file_list.load_path(path, add_history=False, animate=False)
            self.update_nav_buttons()

    def go_forward(self):
        if self.file_list.history_index < len(self.file_list.history) - 1:
            self.file_list.history_index += 1
            path = self.file_list.history[self.file_list.history_index]
            self.file_list.load_path(path, add_history=False, animate=False)
            self.update_nav_buttons()

    def open_animation_settings(self):
        dlg = AnimationSettingsDialog(self.file_list.anim_duration, self.file_list.anim_type, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            duration, anim_type = dlg.get_settings()
            self.file_list.anim_duration = duration
            self.file_list.anim_type = anim_type
            self.file_list.save_session()

    def open_theme_editor(self):
        dlg = ThemeEditorDialog(self.file_list.current_theme, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_theme = dlg.get_theme()
            self.file_list.current_theme = new_theme
            self.file_list.apply_theme(new_theme)
            self.file_list.save_session()


def main():
    app = QApplication(sys.argv)
    window = FileyWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
