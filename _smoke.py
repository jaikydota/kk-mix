import sys
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)
from qt.main_window import MainWindow
w = MainWindow()
print("P2 OK, stack count =", w.stack.count())
for i in range(w.stack.count()):
    t = w.stack.widget(i)
    title = getattr(t, "TITLE", "?")
    print(f"  [{i}] {t.objectName()} - {title}")
