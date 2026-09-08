"""
自定义网络搜索工具。

基于智谱 AI 的搜狗 Web Search API，供主 Agent 和所有子 Agent 使用。
"""

from langchain_core.tools import tool
from zai import ZhipuAiClient

from agent.core.env_utils import ZHIPU_API_KEY


@tool('web_search', parse_docstring=True)
def web_search(query: str) -> str:
    """
    使用搜狗的API进行Web搜索。

    适用于：市场行情调研、供应商背景调查、物料价格趋势查询、行业资讯获取等。

    Args:
        query: 需要搜索的内容或者关键字。

    Returns:
        返回搜索之后的结果。
    """
    if not ZHIPU_API_KEY or ZHIPU_API_KEY.startswith("replace-"):
        return "网络搜索未配置；请使用已导入的文档证据，或配置 ZHIPU_API_KEY 后重试。"
    try:
        client = ZhipuAiClient(api_key=ZHIPU_API_KEY)
        response = client.web_search.web_search(
            search_engine="search-prime",
            search_query=query,
            count=3,  # 返回结果的条数，范围1-50，默认10
            search_recency_filter="noLimit",  # 搜索指定日期范围内的内容
        )
        if response.search_result:
            return "\n\n".join([d.content for d in response.search_result])
        return '没有搜索到任何内容！'
    except Exception as e:
        print(e)
        return f"搜索失败: {e}"
