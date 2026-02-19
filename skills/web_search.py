"""
Web skills: web_fetch
Fetches and extracts readable text from a URL.

The LLM's built-in search (enable_search) handles free-text queries.
This skill handles explicit URL fetching so the model can "open" a page.
"""

from core.skills import SkillManager


def register(manager: SkillManager) -> None:

    @manager.skill(
        name="web_fetch",
        description=(
            "抓取指定 URL 网页的正文文本内容，返回纯文字。"
            "当你已经知道具体网址、需要阅读某个页面详细内容时使用。"
        ),
        parameters={
            "properties": {
                "url": {
                    "type": "string",
                    "description": "要抓取的网页 URL，必须以 http:// 或 https:// 开头",
                },
                "max_chars": {
                    "type": "integer",
                    "description": "返回的最大字符数，默认 3000，最大 8000",
                },
            },
            "required": ["url"],
        },
        category="web",
    )
    def web_fetch(url: str, max_chars: int = 3000) -> str:
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError:
            return "❌ 缺少依赖：请执行 `pip install requests beautifulsoup4`"

        max_chars = min(int(max_chars), 8000)

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }

        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding  # handle charset correctly
        except requests.exceptions.Timeout:
            return f"❌ 请求超时（15s）: {url}"
        except requests.exceptions.HTTPError as e:
            return f"❌ HTTP 错误 {e.response.status_code}: {url}"
        except Exception as e:
            return f"❌ 请求失败: {e}"

        soup = BeautifulSoup(resp.text, "html.parser")

        # Remove noise elements
        for tag in soup(["script", "style", "nav", "footer", "header",
                         "aside", "form", "noscript", "svg", "img"]):
            tag.decompose()

        # Extract text
        text = soup.get_text(separator="\n", strip=True)

        # Collapse blank lines
        lines = [ln for ln in text.splitlines() if ln.strip()]
        cleaned = "\n".join(lines)

        if len(cleaned) > max_chars:
            cleaned = cleaned[:max_chars] + f"\n\n...[内容过长, 已截断至 {max_chars} 字符]"

        if not cleaned:
            return "⚠️ 页面内容为空或无法解析。"

        return f"[页面内容: {url}]\n\n{cleaned}"
