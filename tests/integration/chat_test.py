"""多轮对话集成测试脚本。

通过 subprocess 启动 main.py，向 stdin 写入多轮消息，观察输出。
用于手动验证：记忆注入、多轮上下文、memory 命令等功能。

运行方式：
    python tests/integration/chat_test.py
"""
import subprocess
import sys
import time
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CONVERSATIONS = [
    # (用途, 消息列表)
    (
        "多轮上下文记忆测试",
        [
            "你好，我叫小明，我是一个Python开发者",
            "我刚才说我叫什么名字？",
            "我的职业是什么？",
            "/memory",
            "/memory set user_name 小明",
            "/memory set occupation Python开发者",
            "/memory",
            "/memory forget user_name",
            "/memory",
        ],
    ),
    (
        "连续话题切换测试",
        [
            "Python中如何读取一个大文件而不占用太多内存？",
            "你刚才提到的方法，有没有适用于二进制文件的版本？",
            "好的，现在换个话题，Git rebase 和 merge 有什么区别？",
            "所以在多人协作时应该用哪个？",
        ],
    ),
    (
        "compress 命令测试",
        [
            "给我介绍一下Python的装饰器",
            "再给我讲讲生成器",
            "上下文管理器呢",
            "/compress",
            "/memory",
            "刚才我们聊了哪些话题？",
        ],
    ),
]


def run_conversation(title: str, messages: list[str]) -> dict:
    """运行一组对话，返回结果摘要。"""
    print(f"\n{'='*60}")
    print(f"测试：{title}")
    print(f"{'='*60}")

    # 构造 stdin 输入（每条消息加换行，末尾发 Ctrl+D 模拟 EOF）
    stdin_data = "\n".join(messages) + "\n"

    result = subprocess.run(
        [sys.executable, "main.py"],
        input=stdin_data,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        cwd=PROJECT_ROOT,
        timeout=300,  # 5分钟超时
    )

    output = result.stdout + result.stderr
    print(output)

    # 分析结果
    issues = []
    successes = []

    if "规划失败" in output:
        count = output.count("规划失败")
        issues.append(f"规划失败出现 {count} 次")
    else:
        successes.append("无规划失败")

    if "错误:" in output:
        count = output.count("错误:")
        issues.append(f"错误提示出现 {count} 次")

    if "结果:" in output:
        count = output.count("结果:")
        successes.append(f"成功回答 {count} 次")
    else:
        issues.append("没有任何成功回答")

    if "/memory" in stdin_data and "Token:" in output:
        successes.append("/memory 命令正常工作")
    elif "/memory" in stdin_data and "未知命令" in output:
        issues.append("/memory 命令未识别")

    if "/compress" in stdin_data and "已手动压缩" in output:
        successes.append("/compress 命令正常工作")

    if "/memory set" in stdin_data and "已设置事实" in output:
        successes.append("/memory set 命令正常工作")

    if "/memory forget" in stdin_data and "已删除事实" in output:
        successes.append("/memory forget 命令正常工作")

    return {
        "title": title,
        "issues": issues,
        "successes": successes,
        "returncode": result.returncode,
    }


def main():
    print("MicroAgent 多轮对话集成测试")
    print(f"项目根目录: {PROJECT_ROOT}")

    all_results = []
    for title, messages in CONVERSATIONS:
        try:
            result = run_conversation(title, messages)
            all_results.append(result)
        except subprocess.TimeoutExpired:
            print(f"\n[超时] 测试 '{title}' 超过 5 分钟未完成")
            all_results.append({
                "title": title,
                "issues": ["超时"],
                "successes": [],
                "returncode": -1,
            })
        except Exception as e:
            print(f"\n[异常] 测试 '{title}' 发生异常: {e}")
            all_results.append({
                "title": title,
                "issues": [str(e)],
                "successes": [],
                "returncode": -1,
            })

    # 汇总报告
    print(f"\n{'='*60}")
    print("测试汇总报告")
    print(f"{'='*60}")
    total_issues = 0
    for r in all_results:
        status = "✅" if not r["issues"] else "⚠️"
        print(f"\n{status} {r['title']}")
        for s in r["successes"]:
            print(f"   ✓ {s}")
        for i in r["issues"]:
            print(f"   ✗ {i}")
            total_issues += 1

    print(f"\n总计：{len(all_results)} 组测试，{total_issues} 个问题")
    return 0 if total_issues == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
