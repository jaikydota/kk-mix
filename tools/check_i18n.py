"""i18n 覆盖率检查。

规则：
  1. 函数体内的中文字符串字面量必须写成 tr("...")（f-string 请改为 tr("...{0}").format(...)）
  2. 模块级 / 类级的中文常量（TITLE、选项列表等）允许保持中文，但显示时必须 tr()，
     因此它们也必须在 translations_en.EN 中有译文
  3. 每个 key 的 {n} 占位符集合必须与译文一致
  4. 行尾带 "# i18n: skip" 的行不检查（用于按中文匹配数据的逻辑，如字体名）

用法: uv run python tools/check_i18n.py    # 退出码非 0 表示有问题
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

CJK = re.compile(r"[一-鿿]")
PLACEHOLDER = re.compile(r"\{(\d+)(?:![rsa])?(?::[^}]*)?\}")
SKIP_FILES = {"qt/core/fonts.py", "qt/core/i18n.py", "qt/core/translations_en.py"}
SKIP_MARK = "# i18n: skip"


def iter_source_files():
    yield ROOT / "kk_qt.py"
    for p in sorted((ROOT / "qt").rglob("*.py")):
        if p.relative_to(ROOT).as_posix() not in SKIP_FILES:
            yield p


class Scanner(ast.NodeVisitor):
    def __init__(self, src: str):
        self.lines = src.splitlines()
        self.scope: list[str] = []
        self.wrapped: list[tuple[int, str]] = []      # tr("...") 的 key
        self.data: list[tuple[int, str]] = []         # 模块/类级中文常量
        self.unwrapped: list[tuple[int, str]] = []    # 函数内未包装的中文
        self.docstrings: set[ast.Constant] = set()

    def mark_docstrings(self, tree):
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                b = node.body
                if b and isinstance(b[0], ast.Expr) and isinstance(b[0].value, ast.Constant) \
                        and isinstance(b[0].value.value, str):
                    self.docstrings.add(b[0].value)

    def _skip_line(self, lineno: int) -> bool:
        return SKIP_MARK in self.lines[lineno - 1]

    def visit_ClassDef(self, node):
        self.scope.append("class"); self.generic_visit(node); self.scope.pop()

    def visit_FunctionDef(self, node):
        self.scope.append("func"); self.generic_visit(node); self.scope.pop()
    visit_AsyncFunctionDef = visit_Lambda = visit_FunctionDef

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name) and node.func.id == "tr":
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                self.wrapped.append((node.lineno, node.args[0].value))
            elif node.args and isinstance(node.args[0], ast.JoinedStr):
                self.unwrapped.append((node.lineno, "tr(f-string) 不允许，请改为 tr('...{0}').format()"))
            return  # tr() 内部不再下钻
        self.generic_visit(node)

    def visit_JoinedStr(self, node):
        text = "".join(v.value for v in node.values if isinstance(v, ast.Constant))
        if CJK.search(text) and not self._skip_line(node.lineno):
            self.unwrapped.append((node.lineno, "f-string: " + text[:50]))
        # f-string 中的表达式仍需检查（例如 f"{tr('x')}"）
        for v in node.values:
            if isinstance(v, ast.FormattedValue):
                self.visit(v.value)

    def visit_Constant(self, node):
        if not (isinstance(node.value, str) and CJK.search(node.value)):
            return
        if node in self.docstrings or self._skip_line(node.lineno):
            return
        if "func" in self.scope:
            self.unwrapped.append((node.lineno, node.value[:50]))
        else:
            self.data.append((node.lineno, node.value))


def main() -> int:
    from qt.core.translations_en import EN

    problems: list[str] = []
    keys: dict[str, str] = {}
    for path in iter_source_files():
        rel = path.relative_to(ROOT).as_posix()
        src = path.read_text(encoding="utf-8")
        tree = ast.parse(src)
        sc = Scanner(src)
        sc.mark_docstrings(tree)
        sc.visit(tree)
        for ln, msg in sc.unwrapped:
            problems.append(f"{rel}:{ln}: 未包装的中文: {msg!r}")
        for ln, k in sc.wrapped + sc.data:
            keys.setdefault(k, f"{rel}:{ln}")

    for k, where in keys.items():
        if k not in EN:
            problems.append(f"{where}: 缺少英文译文: {k!r}")
            continue
        a = set(PLACEHOLDER.findall(k))
        b = set(PLACEHOLDER.findall(EN[k]))
        if a != b:
            problems.append(f"{where}: 占位符不一致 {sorted(a)} vs {sorted(b)}: {k!r}")

    unused = [k for k in EN if k not in keys]
    for k in unused:
        problems.append(f"translations_en.py: 多余的译文（源码中已无此 key）: {k!r}")

    if problems:
        print("\n".join(problems))
        print(f"\n✗ {len(problems)} 个问题")
        return 1
    print(f"✓ i18n OK：{len(keys)} 个 key 全部有译文，占位符一致，无未包装中文")
    return 0


if __name__ == "__main__":
    sys.exit(main())
