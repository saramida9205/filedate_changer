import sys
import os
import subprocess
import shutil
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QTreeView, QListView, QSplitter, 
    QPushButton, QListWidget, QDateTimeEdit, QLabel, QTextEdit,
    QMessageBox, QMenu, QAbstractItemView, QLineEdit, QRadioButton, QGroupBox
)
from PyQt6.QtCore import Qt, QDateTime, QDir, QModelIndex, QPoint, QSortFilterProxyModel
from PyQt6.QtGui import QAction, QCursor, QFileSystemModel, QIcon

class CustomFileSystemModel(QFileSystemModel):
    """'만든 날짜' 컬럼을 추가하고 순서를 조정한 커스텀 파일 시스템 모델"""
    def columnCount(self, parent=QModelIndex()):
        return super().columnCount(parent) + 1

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if section == 3: return "만든 날짜"
            if section == 4: return "수정된 날짜"
        return super().headerData(section, orientation, role)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole:
            if index.column() == 3: # 기존 '수정된 날짜' 자리에 '만든 날짜' 표시
                path = self.fileInfo(index).absoluteFilePath()
                try:
                    creation_time = os.path.getctime(path)
                    return QDateTime.fromMSecsSinceEpoch(int(creation_time * 1000)).toString("yyyy-MM-dd HH:mm:ss")
                except: return ""
            elif index.column() == 4: # 새로운 컬럼에 '수정된 날짜' 표시
                return super().data(self.index(index.row(), 3, index.parent()), role)
                
        return super().data(index, role)

class FolderFirstProxyModel(QSortFilterProxyModel):
    """폴더를 항상 파일보다 위에 표시하는 커스텀 프록시 모델"""
    def lessThan(self, left, right):
        # 날짜 컬럼(3, 4번) 정렬 지원
        if left.column() in [3, 4] or right.column() in [3, 4]:
            left_data = self.sourceModel().data(left)
            right_data = self.sourceModel().data(right)
            return left_data < right_data

        model = self.sourceModel()
        left_is_dir = model.isDir(left)
        right_is_dir = model.isDir(right)

        if left_is_dir and not right_is_dir:
            return self.sortOrder() == Qt.SortOrder.AscendingOrder
        if not left_is_dir and right_is_dir:
            return self.sortOrder() == Qt.SortOrder.DescendingOrder

        return super().lessThan(left, right)

class FileDateModifier(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("파일 및 폴더 날짜 수정기 (Explorer 스타일) - SaRaM_ida(망고아빠)")
        self.resize(1300, 800) # 컬럼 추가로 너비 확장

        # 아이콘 설정 (사용자 요청)
        icon_path = os.path.join(os.path.dirname(__file__), "app_icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # 복사/붙여넣기를 위한 클립보드 변수
        self.clipboard_paths = []
        self.clipboard_action = None  # 'copy' or 'cut'
        self.remembered_paths = []

        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(5, 5, 5, 5) # 전체 여백 축소
        main_layout.setSpacing(5)

        # 상단 경로 표시 및 제어 바 (컴팩트하게 조정)
        top_bar = QHBoxLayout()
        top_bar.setContentsMargins(0, 0, 0, 0)
        top_bar.setSpacing(5)
        
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setFixedHeight(25) # 높이 고정
        
        path_label = QLabel("현재 경로:")
        top_bar.addWidget(path_label)
        top_bar.addWidget(self.path_edit)
        
        btn_up = QPushButton("위로")
        btn_up.setFixedHeight(25)
        btn_up.clicked.connect(self.go_up_level)
        top_bar.addWidget(btn_up)
        
        main_layout.addLayout(top_bar)

        # 메인 스플리터 (탐색기 / 기능창)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # 1. 탐색기 영역 (왼쪽: 트리뷰, 오른쪽: 리스트뷰)
        explorer_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 가독성을 위해 만든 날짜 컬럼을 포함한 커스텀 모델 사용
        self.model = CustomFileSystemModel()
        self.model.setRootPath("")

        # 리스트 뷰를 위한 프록시 모델 설정 (폴더 우선 정렬용)
        self.proxy_model = FolderFirstProxyModel()
        self.proxy_model.setSourceModel(self.model)
        self.proxy_model.setDynamicSortFilter(True)

        # 트리 뷰
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.clicked.connect(self.on_tree_clicked)
        # 트리에서는 이름만 표시
        for i in range(1, self.model.columnCount()):
            self.tree_view.setColumnHidden(i, True)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.show_tree_context_menu)

        # 리스트 뷰
        self.list_view = QTreeView()
        self.list_view.setModel(self.proxy_model)
        # 모든 컬럼 표시 (0:Name, 1:Size, 2:Type, 3:Modified)
        # QFileSystemModel은 기본 4개 컬럼을 가짐. '만든 날짜'를 위해 추가 컬럼이 필요할 수 있으나
        # 기본 모델 안에서 처리하기 위해 헤더 명칭을 조정하거나 표시 방식을 개선함.
        self.list_view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_view.doubleClicked.connect(self.on_list_double_clicked)
        self.list_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_view.customContextMenuRequested.connect(self.show_context_menu)
        self.list_view.setSortingEnabled(True)
        self.list_view.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        
        # 헤더 설정
        self.list_view.header().setStretchLastSection(True)
        self.list_view.header().setDefaultSectionSize(120)

        explorer_layout = QVBoxLayout()
        
        # 리스트 뷰 상단에 '위로..' 버튼 추가 (사용자 요청)
        self.btn_up_list = QPushButton(".. (상위 폴더로 이동)")
        self.btn_up_list.setStyleSheet("text-align: left; padding-left: 10px; height: 30px; font-weight: bold; background-color: #f0f0f0;")
        self.btn_up_list.clicked.connect(self.go_up_level)
        self.btn_up_list.setVisible(False) # 처음엔 숨김 (루트일 수 있으므로)
        
        explorer_splitter.addWidget(self.tree_view)
        
        list_container = QWidget()
        list_layout = QVBoxLayout(list_container)
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.setSpacing(0)
        list_layout.addWidget(self.btn_up_list)
        list_layout.addWidget(self.list_view)
        
        explorer_splitter.addWidget(list_container)
        explorer_splitter.setStretchFactor(0, 1) # 트리 영역 비율
        explorer_splitter.setStretchFactor(1, 4) # 리스트 영역 비율

        main_splitter.addWidget(explorer_splitter)

        # 2. 기능 영역 (오른쪽 패널)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        # 경로 기억 리스트
        right_layout.addWidget(QLabel("기억된 경로 리스트:"))
        self.list_remembered = QListWidget()
        right_layout.addWidget(self.list_remembered)

        btn_remember = QPushButton("경로기억")
        btn_remember.setToolTip("선택한 파일/폴더 경로를 리스트에 추가합니다.")
        btn_remember.clicked.connect(self.remember_selected_paths)
        right_layout.addWidget(btn_remember)

        btn_clear_list = QPushButton("리스트 초기화")
        btn_clear_list.clicked.connect(self.clear_remembered_list)
        right_layout.addWidget(btn_clear_list)

        # 날짜 조절 섹션
        date_group = QGroupBox("변경할 일자 및 시간")
        date_group_layout = QVBoxLayout()

        # 만든 날짜
        date_group_layout.addWidget(QLabel("만든 날짜:"))
        self.creation_date_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.creation_date_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.creation_date_edit.setCalendarPopup(True)
        date_group_layout.addWidget(self.creation_date_edit)

        # 수정된 날짜
        date_group_layout.addWidget(QLabel("수정된 날짜:"))
        self.modified_date_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.modified_date_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        self.modified_date_edit.setCalendarPopup(True)
        date_group_layout.addWidget(self.modified_date_edit)

        # 동기화 체크박스 (두 날짜를 동일하게 맞출지 여부)
        from PyQt6.QtWidgets import QCheckBox
        self.sync_dates_checkbox = QCheckBox("만든 날짜와 수정된 날짜를 동일하게")
        self.sync_dates_checkbox.setChecked(True)
        self.sync_dates_checkbox.stateChanged.connect(self.on_sync_dates_changed)
        date_group_layout.addWidget(self.sync_dates_checkbox)

        # 동기화 활성화 시 만든 날짜 변경하면 수정된 날짜도 따라가도록
        self.creation_date_edit.dateTimeChanged.connect(self.on_creation_date_changed)

        date_group.setLayout(date_group_layout)

        # 초기 상태: 동기화 체크 시 수정날짜 비활성화
        self.modified_date_edit.setEnabled(False)

        btn_change = QPushButton("변경")
        btn_change.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; height: 40px;")
        btn_change.clicked.connect(self.run_date_change)

        right_layout.addWidget(date_group)
        right_layout.addWidget(btn_change)
        
        # 엔터 키 동작 설정 옵션 (사용자 요청)
        enter_opt_group = QGroupBox("엔터 키 동작 설정")
        enter_opt_layout = QVBoxLayout()
        self.radio_enter_default = QRadioButton("기존 동작 (폴더이동/기억 리스트 추가)")
        self.radio_enter_explorer = QRadioButton("탐색기 스타일 (파일 실행/폴더 이동)")
        self.radio_enter_default.setChecked(True) # 기본값
        enter_opt_layout.addWidget(self.radio_enter_default)
        enter_opt_layout.addWidget(self.radio_enter_explorer)
        enter_opt_group.setLayout(enter_opt_layout)
        right_layout.addWidget(enter_opt_group)

        right_layout.addStretch()

        # 결과 로그 영역
        right_layout.addWidget(QLabel("실행 결과 상세 정보:"))
        self.log_display = QTextEdit()
        self.log_display.setReadOnly(True)
        right_layout.addWidget(self.log_display)

        main_splitter.addWidget(right_panel)
        main_splitter.setStretchFactor(0, 3)
        main_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(main_splitter)

    # --- 탐색기 기능 구현 ---

    def on_tree_clicked(self, index):
        path = self.model.fileInfo(index).absoluteFilePath()
        source_root_index = self.model.setRootPath(path)
        self.list_view.setRootIndex(self.proxy_model.mapFromSource(source_root_index))
        self.path_edit.setText(path)
        
        # 루트 경로가 아니면 리스트 내 '위로' 버튼 표시
        is_root = (os.path.dirname(path) == path)
        self.btn_up_list.setVisible(not is_root)

    def on_list_double_clicked(self, index):
        # 더블클릭 시 폴더 이동 (롤백)
        source_index = self.proxy_model.mapToSource(index)
        if self.model.isDir(source_index):
            path = self.model.fileInfo(source_index).absoluteFilePath()
            source_root_index = self.model.setRootPath(path)
            self.list_view.setRootIndex(self.proxy_model.mapFromSource(source_root_index))
            self.tree_view.setCurrentIndex(self.model.index(path))
            self.path_edit.setText(path)
            
            # 루트 경로가 아니면 리스트 내 '위로' 버튼 표시
            is_root = (os.path.dirname(path) == path)
            self.btn_up_list.setVisible(not is_root)
        else:
            # 파일일 경우 경로 기억 리스트에 추가하는 편의 기능 유지 가능 (선택적)
            path = self.model.fileInfo(source_index).absoluteFilePath()
            if path not in self.remembered_paths:
                self.remembered_paths.append(path)
                self.list_remembered.addItem(path)
                self.log_display.append(f"더블클릭으로 경로 기억됨: {os.path.basename(path)}")

    def go_up_level(self):
        current_path = self.path_edit.text()
        if not current_path: return
        parent_path = os.path.dirname(current_path)
        if parent_path and parent_path != current_path:
            source_root_index = self.model.setRootPath(parent_path)
            self.list_view.setRootIndex(self.proxy_model.mapFromSource(source_root_index))
            self.path_edit.setText(parent_path)
            self.tree_view.setCurrentIndex(self.model.index(parent_path))
            
            # 드라이브 루트인지 확인하여 위로 버튼 표시 여부 결정
            is_root = (os.path.dirname(parent_path) == parent_path)
            self.btn_up_list.setVisible(not is_root)
        else:
            self.btn_up_list.setVisible(False)

    def show_tree_context_menu(self, pos):
        self.show_context_menu(pos, is_tree=True)

    def show_context_menu(self, pos, is_tree=False):
        menu = QMenu()
        view = self.tree_view if is_tree else self.list_view
        
        # 선택된 인덱스들 가져오기
        if is_tree:
            indices = [view.indexAt(pos)]
        else:
            indices = view.selectionModel().selectedIndexes()
        
        if not indices or not indices[0].isValid():
            return

        copy_action = QAction("복사", self)
        copy_action.triggered.connect(lambda: self.handle_clipboard('copy', is_tree))
        menu.addAction(copy_action)

        cut_action = QAction("잘라내기", self)
        cut_action.triggered.connect(lambda: self.handle_clipboard('cut', is_tree))
        menu.addAction(cut_action)

        paste_action = QAction("붙여넣기", self)
        paste_action.triggered.connect(lambda: self.paste_files(is_tree))
        if not self.clipboard_paths:
            paste_action.setEnabled(False)
        menu.addAction(paste_action)

        menu.addSeparator()

        remember_action = QAction("기억 리스트에 추가", self)
        remember_action.triggered.connect(lambda: self.remember_selected_paths(is_tree))
        menu.addAction(remember_action)

        menu.addSeparator()
        
        change_date_action = QAction("선택 항목 날짜 변경", self)
        change_date_action.triggered.connect(lambda: self.change_date_from_menu(is_tree))
        menu.addAction(change_date_action)

        refresh_action = QAction("새로고침", self)
        refresh_action.triggered.connect(self.refresh_list)
        menu.addAction(refresh_action)

        menu.addSeparator()
        
        delete_action = QAction("삭제", self)
        delete_action.triggered.connect(lambda: self.delete_selected(is_tree))
        menu.addAction(delete_action)

        menu.exec(view.mapToGlobal(pos))

    def change_date_from_menu(self, is_tree=False):
        view = self.tree_view if is_tree else self.list_view
        selection_model = view.selectionModel()
        
        if is_tree:
            proxy_indices = [view.currentIndex()]
        else:
            proxy_indices = selection_model.selectedRows()
            if not proxy_indices:
                proxy_indices = selection_model.selectedIndexes()

        unique_paths = set()
        for i in proxy_indices:
            if is_tree:
                source_index = i
            else:
                source_index = self.proxy_model.mapToSource(i)
                
            if not source_index.isValid(): continue
            path = self.model.fileInfo(source_index).absoluteFilePath()
            unique_paths.add(path)

        if not unique_paths: return
        unique_paths_list = list(unique_paths)

        creation_date = self.creation_date_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        modified_date = self.modified_date_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        msg = f"선택한 {len(unique_paths_list)}개 항목의 날짜를 변경하시겠습니까?\n만든 날짜: [{creation_date}]\n수정된 날짜: [{modified_date}]"
        reply = QMessageBox.question(self, '날짜 변경 확인', msg,
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            old_remembered = self.remembered_paths
            self.remembered_paths = unique_paths_list
            self.run_date_change()
            self.remembered_paths = old_remembered
            self.refresh_list()

    def refresh_list(self):
        """현재 리스트 뷰의 내용을 강제로 새로고침"""
        current_path = self.path_edit.text()
        if current_path:
            # 1. 모델의 루트 경로를 다시 설정하여 갱신 트리거
            self.model.setRootPath("") 
            self.model.setRootPath(current_path)
            # 2. 뷰 갱신 강제
            self.list_view.viewport().update()
            self.log_display.append("리스트를 새로고침했습니다.")

    def handle_clipboard(self, action, is_tree=False):
        view = self.tree_view if is_tree else self.list_view
        if is_tree:
            indices = [view.currentIndex()]
        else:
            selection_model = view.selectionModel()
            indices = selection_model.selectedRows()
            if not indices:
                indices = selection_model.selectedIndexes()
            
        if not indices or not indices[0].isValid():
            self.log_display.append("알림: 선택된 항목이 없습니다.")
            return
        
        self.clipboard_paths = []
        unique_paths = set()
        for i in indices:
            if is_tree:
                source_index = i
            else:
                source_index = self.proxy_model.mapToSource(i)
            
            if not source_index.isValid(): continue
            path = self.model.fileInfo(source_index).absoluteFilePath()
            unique_paths.add(path)
            
        self.clipboard_paths = list(unique_paths)
        if not self.clipboard_paths: return

        self.clipboard_action = action
        action_name = "복사" if action == 'copy' else "잘라내기"
        self.log_display.append(f"알림: {len(self.clipboard_paths)}개 항목이 클립보드에 {action_name}되었습니다.")

    def paste_files(self, is_tree=False):
        if not self.clipboard_paths: return
        
        # 붙여넣을 대상 디렉토리 결정
        if is_tree:
            idx = self.tree_view.currentIndex()
            dest_dir = self.model.fileInfo(idx).absoluteFilePath()
            if not os.path.isdir(dest_dir):
                dest_dir = os.path.dirname(dest_dir)
        else:
            dest_dir = self.path_edit.text()
            
        if not os.path.exists(dest_dir): return

        for src in self.clipboard_paths:
            try:
                dest = os.path.join(dest_dir, os.path.basename(src))
                if src == dest: continue # 동일 경로 패스
                
                if self.clipboard_action == 'copy':
                    if os.path.isdir(src):
                        shutil.copytree(src, dest, dirs_exist_ok=True)
                    else:
                        shutil.copy2(src, dest)
                elif self.clipboard_action == 'cut':
                    shutil.move(src, dest)
                
                self.log_display.append(f"성공: {src} -> {dest}")
            except Exception as e:
                self.log_display.append(f"실패: {src} ({str(e)})")

        if self.clipboard_action == 'cut':
            self.clipboard_paths = []
            self.clipboard_action = None
            
        self.refresh_list() # 작업 완료 후 새로고침

    def delete_selected(self, is_tree=False):
        view = self.tree_view if is_tree else self.list_view
        if is_tree:
            proxy_indices = [view.currentIndex()]
        else:
            proxy_indices = view.selectionModel().selectedRows()
            if not proxy_indices:
                proxy_indices = view.selectionModel().selectedIndexes()
            
        if not proxy_indices or not proxy_indices[0].isValid(): return
        
        # 실제 고유 경로 추출하여 정확한 개수 계산
        unique_paths = set()
        for i in proxy_indices:
            source_index = i if is_tree else self.proxy_model.mapToSource(i)
            if source_index.isValid():
                unique_paths.add(self.model.fileInfo(source_index).absoluteFilePath())

        if not unique_paths: return
        
        reply = QMessageBox.question(self, '삭제 확인', f"선택한 {len(unique_paths)}개 항목을 삭제하시겠습니까?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.Yes:
            for path in unique_paths:
                try:
                    if os.path.isdir(path):
                        shutil.rmtree(path)
                    else:
                        os.remove(path)
                    self.log_display.append(f"삭제됨: {path}")
                except Exception as e:
                    self.log_display.append(f"삭제 실패: {path} ({str(e)})")
            
            self.refresh_list() # 모든 삭제 작업 후 새로고침

    # --- 키보드 단축키 및 편의 기능 ---

    def keyPressEvent(self, event):
        # 현재 포커스가 있는 뷰 확인
        focus_widget = QApplication.focusWidget()
        is_tree = (focus_widget == self.tree_view)
        is_list = (focus_widget == self.list_view)
        
        if not (is_tree or is_list):
            super().keyPressEvent(event)
            return

        # Ctrl + C (복사)
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_C:
            self.handle_clipboard('copy', is_tree)
        # Ctrl + X (잘라내기)
        elif event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_X:
            self.handle_clipboard('cut', is_tree)
        # Ctrl + V (붙여넣기)
        elif event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.key() == Qt.Key.Key_V:
            self.paste_files(is_tree)
        # Delete (삭제)
        elif event.key() == Qt.Key.Key_Delete:
            self.delete_selected(is_tree)
        # Enter / Return (폴더 이동 또는 파일 추가/실행)
        elif event.key() in [Qt.Key.Key_Return, Qt.Key.Key_Enter]:
            try:
                view = focus_widget
                index = view.currentIndex()
                if index.isValid():
                    source_index = index if is_tree else self.proxy_model.mapToSource(index)
                    is_dir = self.model.isDir(source_index)
                    path = self.model.fileInfo(source_index).absoluteFilePath()

                    if is_dir:
                        # 폴더인 경우 항상 해당 폴더 이동
                        if is_tree:
                            self.on_tree_clicked(index)
                        else:
                            self.on_list_double_clicked(index)
                    else:
                        # 파일인 경우 옵션에 따라 동작
                        if self.radio_enter_default.isChecked():
                            # 기존 동작: 기억 리스트 추가
                            if path not in self.remembered_paths:
                                self.remembered_paths.append(path)
                                self.list_remembered.addItem(path)
                                self.log_display.append(f"엔터 키로 경로 기억됨: {os.path.basename(path)}")
                        else:
                            # 탐색기 스타일: 파일 실행
                            try:
                                os.startfile(path)
                                self.log_display.append(f"파일 실행: {os.path.basename(path)}")
                            except Exception as ex:
                                self.log_display.append(f"파일 실행 실패: {str(ex)}")
            except Exception as e:
                self.log_display.append(f"오류: 엔터 키 처리 중 문제 발생 ({str(e)})")
        else:
            super().keyPressEvent(event)

    # --- 날짜 변경 핵심 기능 ---

    def remember_selected_paths(self, is_tree=False):
        view = self.tree_view if is_tree else self.list_view
        if is_tree:
            proxy_indices = [view.currentIndex()]
        else:
            proxy_indices = view.selectionModel().selectedIndexes()
            
        if not proxy_indices or not proxy_indices[0].isValid():
            QMessageBox.warning(self, "알림", "항목을 선택해주세요.")
            return
        
        for i in proxy_indices:
            if is_tree:
                source_index = i
            else:
                source_index = self.proxy_model.mapToSource(i)
                # 중복 제거를 위해 Column 0의 정보만 사용
                if source_index.column() != 0: continue
            
            path = self.model.fileInfo(source_index).absoluteFilePath()
            if path not in self.remembered_paths:
                self.remembered_paths.append(path)
                self.list_remembered.addItem(path)
        
        self.log_display.append(f"선택된 항목 경로 기억됨.")

    def clear_remembered_list(self):
        self.remembered_paths = []
        self.list_remembered.clear()
        self.log_display.append("리스트 초기화됨.")

    def on_sync_dates_changed(self, state):
        """동기화 체크박스 상태 변경 시 호출"""
        if state == 2:  # Checked
            # 체크 시 수정된 날짜를 만든 날짜와 동기화
            self.modified_date_edit.setDateTime(self.creation_date_edit.dateTime())
            self.modified_date_edit.setEnabled(False)
        else:
            self.modified_date_edit.setEnabled(True)

    def on_creation_date_changed(self, datetime):
        """만든 날짜 변경 시 동기화 체크박스가 켜져 있으면 수정 날짜도 함께 변경"""
        if self.sync_dates_checkbox.isChecked():
            self.modified_date_edit.setDateTime(datetime)

    def is_file_locked(self, path):
        """파일이 다른 프로세스에서 사용 중인지 확인 (폴더는 항상 False 반환)"""
        if os.path.isdir(path):
            return False
        try:
            # 배타적 쓰기 모드로 파일 열기를 시도하여 잠금 확인
            import msvcrt
            handle = open(path, 'r+b')
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                handle.close()
                return False
            except (IOError, OSError):
                handle.close()
                return True
        except (IOError, OSError, PermissionError):
            return True

    def get_locking_processes(self, path):
        """PowerShell을 사용하여 파일을 사용 중인 프로세스 이름 조회"""
        try:
            safe_path = path.replace("'", "''")
            # handle.exe가 없어도 동작하는 PowerShell 기반 조회
            ps_cmd = (
                f"try {{ "
                f"$proc = Get-Process | Where-Object {{ $_.Modules.FileName -eq '{safe_path}' -or "
                f"($_.MainModule.FileName -eq '{safe_path}') }} | Select-Object -ExpandProperty Name -Unique; "
                f"if ($proc) {{ $proc -join ', ' }} else {{ "
                f"$h = & handle.exe '{safe_path}' 2>$null; "
                f"if ($h) {{ ($h | Select-String 'pid:' | ForEach-Object {{ ($_ -split '\\s+')[0] }}) -join ', ' }} "
                f"else {{ '' }} }} "
                f"}} catch {{ '' }}"
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_cmd],
                capture_output=True, text=True, shell=False,
                creationflags=0x08000000, timeout=5
            )
            proc_names = result.stdout.strip()
            return proc_names if proc_names else None
        except Exception:
            return None

    def run_date_change(self):
        if not self.remembered_paths:
            QMessageBox.warning(self, "알림", "수정할 경로가 기억되어 있지 않습니다. '경로기억'을 눌러주세요.")
            return

        creation_date = self.creation_date_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")
        modified_date = self.modified_date_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")

        # 사전 검사: 사용 중인 파일 확인
        locked_files = []
        self.log_display.append(f"\n--- 파일 사용 상태 검사 중... ---")
        QApplication.processEvents()  # UI 업데이트

        for path in self.remembered_paths:
            if not os.path.exists(path):
                continue
            if self.is_file_locked(path):
                proc_info = self.get_locking_processes(path)
                locked_files.append((path, proc_info))

        if locked_files:
            # 사용 중인 파일 목록을 보여주고 사용자에게 선택권 부여
            msg = f"다음 {len(locked_files)}개 파일이 다른 프로세스에서 사용 중입니다:\n\n"
            for lf_path, lf_proc in locked_files:
                basename = os.path.basename(lf_path)
                if lf_proc:
                    msg += f"  • {basename} (사용 중: {lf_proc})\n"
                else:
                    msg += f"  • {basename} (사용 중인 프로세스 확인 불가)\n"
            msg += f"\n사용 중인 파일을 건너뛰고 나머지만 변경하시겠습니까?\n(아니오 = 전체 작업 취소)"
            
            reply = QMessageBox.question(
                self, '사용 중인 파일 발견', msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                self.log_display.append("사용자가 작업을 취소했습니다.")
                return
            
            locked_set = {lf[0] for lf in locked_files}
            self.log_display.append(f"사용 중인 {len(locked_files)}개 파일을 건너뜁니다.")
        else:
            locked_set = set()
            self.log_display.append("모든 파일이 사용 가능합니다.")

        self.log_display.append(f"\n--- 날짜 변경 시작 ---")
        self.log_display.append(f"  만든 날짜: {creation_date}")
        self.log_display.append(f"  수정된 날짜: {modified_date}")

        for i, path in enumerate(self.remembered_paths):
            if not os.path.exists(path):
                self.log_display.append(f"[{i+1}/{len(self.remembered_paths)}] 오류: 존재하지 않는 경로 {path}")
                continue

            # 사용 중인 파일 건너뛰기
            if path in locked_set:
                self.log_display.append(f"[{i+1}/{len(self.remembered_paths)}] 건너뜀(사용 중): {os.path.basename(path)}")
                continue

            # 읽기 전용 속성 체크 및 해제
            try:
                import stat
                current_mode = os.stat(path).st_mode
                if not (current_mode & stat.S_IWRITE):
                    self.log_display.append(f"안내: '{os.path.basename(path)}'의 읽기 전용 속성을 해제합니다.")
                    os.chmod(path, current_mode | stat.S_IWRITE)
            except Exception as e:
                self.log_display.append(f"경고: 속성 변경 실패 ({str(e)})")

            # PowerShell 명령어 구성 (CreationTime과 LastWriteTime 각각 다른 날짜로 수정)
            safe_path = path.replace("'", "''")
            ps_command = (
                f'$item = Get-Item -LiteralPath \'{safe_path}\'; '
                f'$item.CreationTime = [DateTime]"{creation_date}"; '
                f'$item.LastWriteTime = [DateTime]"{modified_date}"'
            )
            
            try:
                # 윈도우 환경이므로 powershell.exe 사용
                result = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", ps_command],
                    capture_output=True,
                    text=True,
                    shell=False,
                    creationflags=0x08000000 # CREATE_NO_WINDOW
                )

                if result.returncode == 0:
                    self.log_display.append(f"[{i+1}/{len(self.remembered_paths)}] 성공: {os.path.basename(path)}")
                    
                    # 모델 데이터 갱신 알림
                    source_idx = self.model.index(path)
                    if source_idx.isValid():
                        self.model.dataChanged.emit(source_idx, source_idx)
                else:
                    self.log_display.append(f"[{i+1}/{len(self.remembered_paths)}] 실패: {os.path.basename(path)}")
                    error_msg = result.stderr.strip() or result.stdout.strip()
                    self.log_display.append(f"  └ 에러: {error_msg}")

            except Exception as e:
                self.log_display.append(f"치명적 에러: {str(e)}")

        self.log_display.append("--- 모든 작업 완료 ---")
        self.refresh_list() # 모든 작업 완료 후 자동 새로고침

def is_admin():
    try:
        import ctypes
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

if __name__ == "__main__":
    if is_admin():
        app = QApplication(sys.argv)
        window = FileDateModifier()
        window.show()
        sys.exit(app.exec())
    else:
        import ctypes
        # 실행 안정성을 위해 다시 SW_SHOWNORMAL(1)로 복구 (콘솔 표시 허용)
        script = os.path.abspath(sys.argv[0])
        params = f'"{script}"'
        if len(sys.argv) > 1:
            params += " " + " ".join([f'"{arg}"' for arg in sys.argv[1:]])
        
        # ShellExecuteW를 통해 관리자 권한으로 재실행
        ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, params, None, 1)
