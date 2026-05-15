#!/usr/bin/env python3
"""
Pre-commit hook：检查子宪法修改是否符合规范

集成方式（在各 agent 的 .git/hooks/pre-commit 中调用）：
    python tools/check_constitution_change.py || exit $?

功能：
1. 检测本次 commit 是否修改了 CLAUDE.md
2. 如果修改了，检查 commit message 是否符合强制模板
3. 检查修改内容是否违反总宪法核心条款
4. 违规则返回 exit code 2（阻断提交）

返回值：
- 0: 未修改子宪法 或 修改符合规范
- 2: 修改违规，阻断提交
"""

import json
import os
import sys
import subprocess
import re
from pathlib import Path


def run_command(cmd):
    """执行命令并返回输出"""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            shell=True
        )
        return result.stdout.strip(), result.returncode
    except Exception as e:
        return f"ERROR: {e}", 1


def get_staged_files():
    """获取暂存区的文件列表"""
    output, _ = run_command("git diff --cached --name-only")
    return output.split('\n') if output else []


def get_commit_message():
    """获取 commit message（从 .git/COMMIT_EDITMSG）"""
    commit_msg_file = Path(".git/COMMIT_EDITMSG")
    if commit_msg_file.exists():
        return commit_msg_file.read_text(encoding='utf-8', errors='ignore')
    return ""


def get_staged_diff(file_path):
    """获取某个文件在暂存区的修改内容"""
    output, _ = run_command(f"git diff --cached {file_path}")
    return output


def check_commit_message_format(commit_msg):
    """检查 commit message 是否符合子宪法修改的强制模板"""
    required_patterns = {
        "title": r"^docs\(constitution\):",
        "tag": r"\[CONSTITUTION_CHANGE\]",
        "article": r"Article:\s*.+",
        "scope": r"Scope:\s*(agent-only|cross-agent)",
        "type": r"Type:\s*(add-detail|clarify|restrict-further)",
        "violates": r"Violates-Core:\s*(NO|YES)"
    }

    errors = []

    for field, pattern in required_patterns.items():
        if not re.search(pattern, commit_msg, re.MULTILINE):
            errors.append(f"  - 缺少字段: {field} (pattern: {pattern})")

    # 检查 Scope
    scope_match = re.search(r"Scope:\s*(.+)", commit_msg)
    if scope_match:
        scope = scope_match.group(1).strip()
        if scope == "cross-agent":
            errors.append("  - Scope 为 cross-agent，应通过提案修改总宪法，不应直接修改子宪法")

    # 检查 Violates-Core
    violates_match = re.search(r"Violates-Core:\s*(.+)", commit_msg)
    if violates_match:
        violates = violates_match.group(1).strip()
        if violates == "YES":
            errors.append("  - Violates-Core 声明为 YES，禁止提交")

    return errors


def _load_extra_protected_patterns():
    """Project-specific (regex, description) pairs from
    .governance/core_keywords.json's optional 'extra_protected_patterns'
    field. Returns [] when the file or field is absent."""
    try:
        repo_root = Path(__file__).resolve().parent.parent
        cfg = repo_root / ".governance" / "core_keywords.json"
        if not cfg.exists():
            return []
        data = json.loads(cfg.read_text(encoding="utf-8"))
        out = []
        for item in data.get("extra_protected_patterns", []):
            if isinstance(item, (list, tuple)) and len(item) == 2:
                out.append((item[0], item[1]))
        return out
    except Exception:
        return []


def check_core_article_violation(diff_content):
    """检查修改内容是否违反总宪法核心条款"""
    # 核心条款关键词（简化版，与 audit_sub_constitutions.py 一致）
    protected_keywords = [
        # 第四条：配置管理
        (r"允许.*\.get\(.*default", "第四条：禁止放宽 .get 兜底约束"),
        (r"可以.*硬编码", "第四条：禁止允许硬编码"),

        # 第八条：测试生产统一
        (r"允许.*is_paper.*is_live", "第八条：禁止允许 paper/live 分叉"),
        (r"可以.*分叉", "第八条：禁止允许业务逻辑分叉"),

        # 第九条：Git 纪律
        (r"修改.*Conventional Commits", "第九条：禁止修改 Conventional Commits 规范"),

        # 第十二条：Scope 执行
        (r"移除.*pre-commit.*hook", "第十二条：禁止移除 pre-commit hook"),
        (r"弱化.*scope.*检查", "第十二条：禁止弱化 scope 检查"),
        (r"绕过.*三层防御", "第十二条：禁止绕过三层防御"),

        # 第十三条：宪法保护（完全禁止修改）
        (r"修改.*宪法保护", "第十三条：禁止修改宪法保护条款"),
        (r"修改.*附录", "第十三条：禁止修改核心条款清单附录"),

        # 第十四条：阶段总结
        (r"移除.*阻塞规则", "第十四条：禁止移除阻塞规则"),
        (r"豁免.*STATE\.md", "第十四条：禁止豁免 STATE.md 更新"),
        (r"豁免.*Git.*提交", "第十四条：禁止豁免 Git 提交"),
        (r"豁免.*Notion", "第十四条：禁止豁免 Notion 更新"),

        # Project-specific extra patterns are appended from
        # .governance/core_keywords.json's optional 'extra_protected_patterns'.
    ]
    protected_keywords += _load_extra_protected_patterns()

    violations = []
    for pattern, description in protected_keywords:
        if re.search(pattern, diff_content, re.IGNORECASE):
            violations.append(f"  - {description}")

    return violations


def main():
    """主函数"""
    staged_files = get_staged_files()

    # 检查是否修改了 CLAUDE.md
    if "CLAUDE.md" not in staged_files:
        # 未修改子宪法，放行
        sys.exit(0)

    print("[CONSTITUTION CHANGE DETECTED]")
    print("检测到子宪法修改，执行合规检查...")
    print()

    # 获取 commit message
    commit_msg = get_commit_message()

    if not commit_msg:
        print("❌ 错误：无法读取 commit message")
        sys.exit(2)

    # 检查 commit message 格式
    msg_errors = check_commit_message_format(commit_msg)

    if msg_errors:
        print("❌ Commit message 格式不符合要求:")
        print()
        for error in msg_errors:
            print(error)
        print()
        print("要求的格式:")
        print("""
docs(constitution): <one-line summary>

[CONSTITUTION_CHANGE]
- Article: 第X条
- Scope: agent-only
- Type: add-detail | clarify | restrict-further
- Violates-Core: NO

<详细说明>
- 修改原因: ...
- 影响范围: 仅本 agent

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
""")
        sys.exit(2)

    # 获取 CLAUDE.md 的修改内容
    diff_content = get_staged_diff("CLAUDE.md")

    # 检查是否违反核心条款
    violations = check_core_article_violation(diff_content)

    if violations:
        print("❌ 检测到违反总宪法核心条款的修改:")
        print()
        for violation in violations:
            print(violation)
        print()
        print("请通过提案流程修改总宪法，不应直接修改子宪法的核心约束。")
        print("提案流程：在 proposals/ 目录创建提案文件，等待 core agent 审查。")
        sys.exit(2)

    # 所有检查通过
    print("✅ 子宪法修改符合规范")
    sys.exit(0)


if __name__ == "__main__":
    main()
