#!/usr/bin/env python3
"""
审计各 agent 子宪法修改，检测潜在违宪

Usage:
    python tools/audit_sub_constitutions.py [--verbose]

功能：
1. 检查各 agent clone 的 git log 中的宪法修改
2. 对比修改内容与总宪法核心条款（CLAUDE.md 附录定义）
3. 生成审计报告，标记潜在违规
4. 如有 HIGH 违规，返回 exit code 1
"""

import os
import sys
import subprocess
import re
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime


# 项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent  # pythonProject1/
AGENTS = ["data", "rules", "trade", "research"]

# 总宪法核心条款关键词（从附录提取）
CORE_KEYWORDS = {
    "第零条": ["如君所愿"],
    "第四条": ["禁止", ".get(", "default", "硬编码", "配置"],
    "第五条": ["classify", "PROPOSAL_REQUIRED", "NO_PROPOSAL", "入口", "非平凡"],
    "第八条": ["is_paper", "is_live", "分叉", "测试", "生产"],
    "第九条": ["feat:", "fix:", "docs:", "Conventional Commits", "分支"],
    "第十二条": ["scope", "pre-commit", "hook", "三层防御"],
    "第十三条": ["宪法", "修改权限", "附录", "红线"],
    "第十四条": ["STATE.md", "Git", "Notion", "阶段总结", "阻塞"],
    "第十五条": ["Futu OpenD", "预检", "端口检测"],
}


def run_command(cmd: List[str], cwd: Path) -> str:
    """执行命令并返回输出"""
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore'
        )
        return result.stdout
    except Exception as e:
        return f"ERROR: {e}"


def get_constitution_commits(agent_dir: Path) -> List[Dict[str, str]]:
    """获取某 agent 的所有子宪法修改 commit"""
    output = run_command(
        ["git", "log", "--all", "--grep=docs(constitution)", "--oneline", "--no-merges"],
        cwd=agent_dir
    )

    commits = []
    for line in output.strip().split('\n'):
        if not line or "ERROR" in line:
            continue
        parts = line.split(' ', 1)
        if len(parts) == 2:
            commits.append({
                "hash": parts[0],
                "message": parts[1]
            })

    return commits


def get_constitution_diff(agent_dir: Path, commit_hash: str) -> str:
    """获取某个 commit 对 CLAUDE.md 的修改内容"""
    output = run_command(
        ["git", "show", f"{commit_hash}:CLAUDE.md"],
        cwd=agent_dir
    )
    return output


def check_violates_core(diff_content: str) -> List[Dict[str, Any]]:
    """检测修改是否违反总宪法核心条款"""
    violations = []

    for article, keywords in CORE_KEYWORDS.items():
        for keyword in keywords:
            # 检测是否有放宽约束的迹象
            relaxation_patterns = [
                rf"允许.*{re.escape(keyword)}",
                rf"可.*{re.escape(keyword)}",
                rf"豁免.*{re.escape(keyword)}",
                rf"移除.*{re.escape(keyword)}",
                rf"不.*禁止.*{re.escape(keyword)}",
            ]

            for pattern in relaxation_patterns:
                if re.search(pattern, diff_content, re.IGNORECASE):
                    violations.append({
                        "article": article,
                        "keyword": keyword,
                        "pattern": pattern,
                        "severity": "HIGH"
                    })

    return violations


def extract_commit_metadata(agent_dir: Path, commit_hash: str) -> Dict[str, str]:
    """提取 commit message 中的元数据"""
    output = run_command(
        ["git", "log", "-1", "--format=%B", commit_hash],
        cwd=agent_dir
    )

    metadata = {
        "article": "未知",
        "scope": "未知",
        "violates_core": "未声明"
    }

    # 提取 [CONSTITUTION_CHANGE] 块中的信息
    if "[CONSTITUTION_CHANGE]" in output:
        article_match = re.search(r"Article:\s*(.+)", output)
        scope_match = re.search(r"Scope:\s*(.+)", output)
        violates_match = re.search(r"Violates-Core:\s*(.+)", output)

        if article_match:
            metadata["article"] = article_match.group(1).strip()
        if scope_match:
            metadata["scope"] = scope_match.group(1).strip()
        if violates_match:
            metadata["violates_core"] = violates_match.group(1).strip()

    return metadata


def generate_report(audit_results: List[Dict[str, Any]], verbose: bool = False) -> str:
    """生成审计报告"""
    report_lines = [
        "=" * 80,
        "子宪法审计报告",
        f"审计时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 80,
        ""
    ]

    high_violations = [r for r in audit_results if r.get("severity") == "HIGH"]

    if not audit_results:
        report_lines.append("[OK] 未发现子宪法修改记录")
    elif not high_violations:
        report_lines.append(f"[OK] 检查了 {len(audit_results)} 个修改，未发现 HIGH 级别违规")
    else:
        report_lines.append(f"[WARN] 发现 {len(high_violations)} 个 HIGH 级别潜在违规")
        report_lines.append("")

        for result in high_violations:
            report_lines.append(f"Agent: {result['agent']}")
            report_lines.append(f"Commit: {result['commit_hash']} - {result['commit_message']}")
            report_lines.append(f"条款: {result['violated_article']}")
            report_lines.append(f"关键词: {result['keyword']}")
            report_lines.append(f"模式: {result['pattern']}")
            report_lines.append(f"声明 Violates-Core: {result['metadata']['violates_core']}")
            report_lines.append("-" * 80)

    if verbose:
        report_lines.append("")
        report_lines.append("所有检测记录:")
        report_lines.append("")
        for result in audit_results:
            report_lines.append(f"  [{result.get('severity', 'INFO')}] {result['agent']}: {result['commit_hash']}")
            report_lines.append(f"    {result['commit_message']}")
            report_lines.append(f"    条款: {result['metadata']['article']}, Scope: {result['metadata']['scope']}")

    report_lines.append("")
    report_lines.append("=" * 80)

    return "\n".join(report_lines)


def main():
    """主函数"""
    verbose = "--verbose" in sys.argv or "-v" in sys.argv

    audit_results = []

    print("开始审计各 agent 子宪法...")
    print()

    for agent in AGENTS:
        agent_dir = PROJECT_ROOT / f"agent-{agent}"

        if not agent_dir.exists():
            print(f"[WARN] agent-{agent} 目录不存在，跳过")
            continue

        print(f"[INFO] 检查 agent-{agent}...")

        # 获取所有子宪法修改 commit
        commits = get_constitution_commits(agent_dir)

        if not commits:
            print(f"   未发现子宪法修改记录")
            continue

        print(f"   发现 {len(commits)} 个子宪法修改")

        for commit in commits:
            # 获取 commit 的完整 diff
            diff_content = get_constitution_diff(agent_dir, commit["hash"])

            # 提取 commit 元数据
            metadata = extract_commit_metadata(agent_dir, commit["hash"])

            # 检测是否违反核心条款
            violations = check_violates_core(diff_content)

            if violations:
                for violation in violations:
                    audit_results.append({
                        "agent": agent,
                        "commit_hash": commit["hash"],
                        "commit_message": commit["message"],
                        "violated_article": violation["article"],
                        "keyword": violation["keyword"],
                        "pattern": violation["pattern"],
                        "severity": violation["severity"],
                        "metadata": metadata
                    })
                    print(f"   [WARN] {commit['hash']}: 潜在违规 ({violation['article']})")
            else:
                audit_results.append({
                    "agent": agent,
                    "commit_hash": commit["hash"],
                    "commit_message": commit["message"],
                    "severity": "INFO",
                    "metadata": metadata
                })
                if verbose:
                    print(f"   [OK] {commit['hash']}: 未发现违规")

    print()
    print(generate_report(audit_results, verbose=verbose))

    # 如有 HIGH 违规，返回 exit code 1
    high_violations = [r for r in audit_results if r.get("severity") == "HIGH"]
    if high_violations:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
