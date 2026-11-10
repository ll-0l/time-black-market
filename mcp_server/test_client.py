"""MCP 서버 검증용 클라이언트: stdio로 서버를 띄우고 도구 목록 조회 + 실제 호출.

    python mcp_server/test_client.py            # 조회 도구만
    python mcp_server/test_client.py --ask      # 몰래 사장 질문까지 (AI 호출 1회)
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


SERVER = Path(__file__).with_name("server.py")


def _text(result) -> str:
    return "\n".join(getattr(c, "text", "") for c in result.content)


async def main() -> None:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            info = await session.initialize()
            print(f"✅ 연결: {info.server_info.name} v{info.server_info.version}")

            tools = await session.list_tools()
            print(f"🔧 도구 {len(tools.tools)}개: " + ", ".join(t.name for t in tools.tools))

            summary = json.loads(_text(await session.call_tool("get_ledger_summary", {})))
            print(f"📒 get_ledger_summary → 지금 외상 {summary['metrics']['current']:.0f}분, "
                  f"등급 {summary['credit']['grade']}, 갚기 좋은 날 {summary['recommendation']['next_date']}")

            records = json.loads(_text(await session.call_tool("get_records", {"start": "2026-09-15", "end": "2026-09-21"})))
            peak = max(records["records"], key=lambda r: r["value"])
            print(f"📅 get_records(9/15~9/21) → {records['count']}건, 최고 {peak['date']} {peak['value']:.0f}분 ({peak['memo']})")

            tasks = json.loads(_text(await session.call_tool("list_tasks", {"status": "open"})))
            print(f"📝 list_tasks → 남은 일 {tasks['count']}개, 합계 {tasks['total_estimated_minutes']}분")

            if "--ask" in sys.argv:
                answer = json.loads(_text(await session.call_tool("ask_mollae", {"message": "MCP로 왔어요. 지금 외상이랑 뭐부터 갚을지 짧게!"})))
                print(f"🕶️ ask_mollae → {answer['reply']}")
                print(f"   (몰래 사장이 쓴 내부 도구: {answer['tools_used_by_mollae']}, 상담 id: {answer['conversation_id']})")


if __name__ == "__main__":
    asyncio.run(main())
