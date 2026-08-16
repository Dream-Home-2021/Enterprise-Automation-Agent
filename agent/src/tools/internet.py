# ====================================================================
# 文件角色: src/tools/internet.py
# 本文件负责提供"联网搜索/网页抓取"工具，供 Agent (智能体) 调用。
# 它通过 Selenium + BeautifulSoup 实现 Google 搜索，并通过
# WebBaseLoader / FireCrawlLoader / CrwLoader 三种抓取器抓取网页正文。
#
# 小白导读:
# - LLM (大语言模型): 像 ChatGPT 一样能"理解"语言的 AI；只能看到文字，不能直接上网。
# - Agent (智能体): 一个能调用工具(Tool)来完成复杂任务的 LLM 工作流。
# - Tool (工具): Agent 可以调用的一个功能单元，就像 App 里的一个按钮。
# - MCP (Model Context Protocol): Agent 与外部工具/数据源之间的标准化"对话协议"，
#   类比：MCP 就像 USB 接口，让不同的外设（数据库、API）能即插即用地连上 Agent。
# - WebBaseLoader / FireCrawlLoader / CrwLoader: 三种"网页吸尘器"，
#   各自通过不同方式把网页 HTML 转成纯文本供 LLM 阅读。
# - Selenium: 一个能控制浏览器的自动化工具，这里用来模拟真人打开 Google 搜索页面。
#
# 与其他文件的协作:
# - ../config.py 提供 API Key 和 CHROMEDRIVER_PATH 等配置。
# - ../logger.py 提供统一日志工具，方便排错。
# - 本文件导出的 google_search、scrape_webpages 是 @tool 装饰的函数，
#   可被上层 Agent 通过名字直接调用（例如 query="python 教程"）。
# ====================================================================

import os  # 操作系统接口，用于读取环境变量、检查文件路径等

# langchain_core.tools.tool: LangChain 提供的装饰器，把普通函数注册为 Tool。
# 小白导读: 被 @tool 包过的函数就像贴了"可调用"标签的卡片，Agent 可以扫码使用它。
from langchain_core.tools import tool
# WebBaseLoader: LangChain 内置的网页抓取器（轻量，抓取静态网页）。
from langchain_community.document_loaders import WebBaseLoader, FireCrawlLoader
# fastCRW (Firecrawl-compatible web scraper; single binary, self-host or cloud)
# CrwLoader: 兼容 FireCrawl API 的抓取器（fastCRW 项目）。
try:
    from langchain_crw import CrwLoader
except ImportError:
    CrwLoader = None
# Selenium 相关导入：用于驱动 Chrome 浏览器进行 Google 搜索。
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
# typing.Annotated: 给参数加类型提示和说明文字，方便 LLM 理解入参含义。
from typing import Annotated, List
# BeautifulSoup: HTML 解析器，从网页源码里提取出我们需要的纯文本。
from bs4 import BeautifulSoup

# 相对导入: 从项目根目录下的 src 包里引入 logger 和 config。
from ..logger import setup_logger
from ..config import FIRECRAWL_API_KEY,CRW_API_KEY,CRW_API_URL,CHROMEDRIVER_PATH
# Set up logger
# 创建一个logger实例，用于在控制台/文件中记录运行信息（info/debug/error 级别）。
logger = setup_logger()

# 第一个 Tool: google_search
# 当 Agent 需要"查一下某个关键词"时，会调用这个函数。
@tool  # 小白导读: 这个函数被 @tool 装饰器包装，Agent 可以通过其名字"google_search"调用它
def google_search(query: Annotated[str, "The search query to use"]) -> Annotated[str, "The top 5 Google search results."]:
    """
    Perform a Google search based on the given query and return the top 5 results.
    用 Selenium 打开"无头"Chrome 浏览器、搜索 Google，再用 BeautifulSoup 抓取前 5 条结果。

    小白导读:
    - headless: 浏览器在后台运行，不会弹出可视窗口（服务器/CLI 环境常用）。
    - BeautifulSoup: HTML 解析器，从网页源码中提取标题、摘要、链接。

    假数据示例:
        输入: query="Python 教程"
        输出: "Python 教程 - 百度百科\n百度百科简介...\nhttps://baike.baidu.com/...\n... (5 组 标题+摘要+链接)"
    """
    try:
        # 记录日志，方便调试时看到 Agent 正在搜什么。
        logger.info(f"Performing Google search for query: {query}")
        # 配置 Chrome 浏览器为"无头(headless)"模式，即在后台运行，不弹出窗口。
        chrome_options = Options()
        # 显式指定 Chrome 安装路径（Windows 环境下 Selenium 可能找不到）
        chrome_binary = os.environ.get(
            "CHROME_BINARY",
            r"C:\Users\Administrator\AppData\Local\Google\Chrome\Bin\chrome.exe",
        )
        if os.path.isfile(chrome_binary):
            chrome_options.binary_location = chrome_binary
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")          # Linux 环境下防止权限报错
        chrome_options.add_argument("--disable-dev-shm-usage")  # 防止 /dev/shm 太小导致崩溃
        # 指定 ChromeDriver 可执行文件路径。
        service = Service(CHROMEDRIVER_PATH)

        # 使用 with 语句打开浏览器，确保即使出错也会自动关闭浏览器进程。
        # 假数据示例: query="Python 教程" -> 打开 https://www.google.com/search?q=Python 教程
        with webdriver.Chrome(options=chrome_options, service=service) as driver:
            # Set a timeout to prevent hanging on slow network
            # 页面加载超时 30 秒，避免网络慢时一直卡住。
            driver.set_page_load_timeout(30)
            url = f"https://www.google.com/search?q={query}"
            logger.debug(f"Accessing URL: {url}")
            # 让浏览器访问 Google 搜索页。
            driver.get(url)
            # 获取加载完成后的 HTML 源码。
            html = driver.page_source

        # 使用 BeautifulSoup 把 HTML 解析成可查询的对象树。
        soup = BeautifulSoup(html, 'html.parser')
        # 每一条搜索结果都在 class="g" 的 div 里（选择器: .g）。
        search_results = soup.select('.g')
        # 拼接最终返回给 LLM 的文本。
        search = ""
        # 只取前 5 条结果。
        for result in search_results[:5]:
            title_element = result.select_one('h3')          # 标题: <h3> 标签
            title = title_element.text if title_element else 'No Title'
            snippet_element = result.select_one('.VwiC3b')   # 摘要片段
            snippet = snippet_element.text if snippet_element else 'No Snippet'
            link_element = result.select_one('a')            # 链接: <a href=...>
            link = link_element['href'] if link_element else 'No Link'
            search += f"{title}\n{snippet}\n{link}\n\n"

        logger.info("Google search completed successfully")
        # 返回值是一个纯字符串，包含 5 条结果的"标题+摘要+链接"。
        return search
    except Exception as e:
        # 出错时记录错误，并返回错误文本（不让 Agent 因为异常直接崩溃）。
        logger.error(f"Error during Google search: {str(e)}")
        return f'Error: {e}'

# 内部函数（无 @Tool 装饰，供自身内部调用）：使用 WebBaseLoader 抓取网页。
# 小白导读: 这是兜底方案，无需 API Key，纯 Python 即可抓取静态网页。
def _scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from WebBaseLoader."]:
    """
    Scrape the provided web pages for detailed information using WebBaseLoader.
    使用 WebBaseLoader 抓取网页。

    小白导读: WebBaseLoader 是 LangChain 内置的最轻量抓取器，不需要 API Key。
    但它只能处理静态 HTML，对动态渲染（JS）的网页效果较差。

    假数据示例:
        输入: urls=["https://example.com"]
        输出: (网页纯文本内容，包含标题、段落等)
    """
    try:
        logger.info(f"Scraping webpages: {urls}")
        # WebBaseLoader 会把网页转成 Document 对象，page_content 就是正文。
        # 假数据示例: urls=["https://example.com"] -> 返回网页正文文本
        loader = WebBaseLoader(urls)  # 小白导读: 创建抓取器实例
        docs = loader.load()  # 小白导读: 实际执行抓取，返回 Document 列表
        # 用双换行符把多个网页的正文拼起来。
        content = "\n\n".join([f'\n{doc.page_content}\n' for doc in docs])
        logger.info("Webpage scraping completed successfully")
        return content
    except Exception as e:
        logger.error(f"Error during webpage scraping: {str(e)}")
        raise  # Re-raise the exception to be caught by the calling function

# 内部函数：使用 FireCrawlLoader 抓取网页（比 WebBaseLoader 更强大，支持动态 JS 渲染）。
# 小白导读: FireCrawl 是一个云端付费服务，能处理复杂 JS 渲染网页。
def _firecrawl_scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from FireCrawl."]:
    """
    Scrape the provided web pages for detailed information using FireCrawlLoader.
    使用 FireCrawlLoader 抓取网页（通过 FireCrawl 云端 API）。

    小白导读:
    - 需要先配置 FIRECRAWL_API_KEY 环境变量。
    - mode="scrape": 只抓单页；mode="crawl": 递归爬整站。
    """
    # 如果没有 API Key，直接抛出异常让上层处理。
    if not FIRECRAWL_API_KEY:
        raise ValueError("FireCrawl API key is not set")  # 小白导读: 未配置 API Key 时主动失败

    try:
        logger.info(f"Scraping webpages using FireCrawl: {urls}")
        results = []
        # FireCrawl 一次只能处理一个 URL，所以逐条遍历。
        for url in urls:
            loader = FireCrawlLoader(
                api_key=FIRECRAWL_API_KEY,  # 小白导读: 从 src/config.py 读到的 API Key
                url=url,
                mode="scrape"          # scrape = 单页抓取；crawl = 整站爬取（此处用 scrape）
            )
            res = loader.load()  # 小白导读: 实际调用 FireCrawl API
            # Normalize different possible return types from the loader
            # 返回值可能是 list 或单个对象，统一转成字符串列表。
            if isinstance(res, list):
                for doc in res:
                    if hasattr(doc, "page_content"):  # 小白导读: 有 page_content 属性说明是 Document 对象
                        results.append(str(doc.page_content))
                    else:
                        results.append(str(doc))
            else:
                results.append(str(res))
        # 用双换行符把多个结果拼起来。
        aggregated = "\n\n".join(results)
        logger.info("FireCrawl scraping completed successfully")
        return aggregated
    except Exception as e:
        logger.error(f"Error during FireCrawl scraping: {str(e)}")
        raise  # Re-raise the exception to be caught by the calling function

# 内部函数：使用 fastCRW（CrwLoader）抓取网页，是 FireCrawl 的兼容替代方案。
# 小白导读: fastCRW 是一个开源、本地部署的 FireCrawl 兼容服务，省钱又可控。
def _crw_scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from fastCRW."]:
    """
    Scrape the provided web pages for detailed information using fastCRW.
    使用 fastCRW (CrwLoader) 抓取网页。

    fastCRW is a Firecrawl-compatible web scraper (single binary; self-host or cloud).
    与 FireCrawl 类似但可本地部署（src/config.py 的 CRW_API_URL）。

    假数据示例:
        输入: urls=["https://example.com"]
        输出: (网页纯文本内容)

    This function uses the CrwLoader to load and scrape the content of the provided URLs.
    """
    try:
        logger.info(f"Scraping webpages using fastCRW: {urls}")
        results = []
        # 逐条遍历 URL，构造 CrwLoader 并抓取。
        for url in urls:
            loader = CrwLoader(
                api_key=CRW_API_KEY,
                api_url=CRW_API_URL,    # fastCRW 需要一个自定义 URL，默认为本地
                url=url,
                mode="scrape"  # 小白导读: scrape 只抓单页，crawl 递归整站
            )
            res = loader.load()
            # Normalize different possible return types from the loader
            # 与 FireCrawl 类似，做返回值类型归一化处理。
            if isinstance(res, list):
                for doc in res:
                    if hasattr(doc, "page_content"):  # 小白导读: 是 Document 对象
                        results.append(str(doc.page_content))
                    else:
                        results.append(str(doc))
            else:
                results.append(str(res))  # 小白导读: 单个对象直接转字符串
        aggregated = "\n\n".join(results)
        logger.info("fastCRW scraping completed successfully")
        return aggregated
    except Exception as e:
        logger.error(f"Error during fastCRW scraping: {str(e)}")
        raise  # Re-raise the exception to be caught by the calling function

# 第二个 Tool: scrape_webpages
# 利用"分级降级"策略：先尝试 fastCRW，再 FireCrawl，最后 WebBaseLoader。
# 小白导读: 分级降级就好比"先坐高铁 -> 再坐大巴 -> 最后走路"，总有一种方式能到达。
@tool
def scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from fastCRW, FireCrawl or WebBaseLoader."]:
    """
    Attempt to scrape webpages using fastCRW, falling back to FireCrawl then WebBaseLoader if unsuccessful.
    分级降级抓取：先尝试本地 fastCRW (省钱) -> 再次 FireCrawl (云端稳定) -> 最后 WebBaseLoader (兜底)。

    假数据示例:
        输入: urls=["https://example.com"]
        输出: 网页正文文本（约若干 KB）
    """
    try:
        # 首选: fastCRW，本地自部署更快更便宜。
        return _crw_scrape_webpages(urls)
    except Exception as e:
        logger.warning(f"fastCRW scraping failed: {str(e)}. Falling back to FireCrawl.")

    try:
        # 次选: FireCrawl，云端服务更稳定。
        return _firecrawl_scrape_webpages(urls)
    except Exception as e:
        logger.warning(f"FireCrawl scraping failed: {str(e)}. Falling back to WebBaseLoader.")

    try:
        # 兜底: WebBaseLoader，最轻量但功能最弱。
        return _scrape_webpages(urls)  # 小白导读: 最终兜底，不需要 API Key
    except Exception as e:
        # 三种都失败时，返回错误文本给 LLM，让它知道"没抓到"。
        logger.error(f"Both scraping methods failed. Error: {str(e)}")
        return f"Error: Unable to scrape webpages using both methods. {str(e)}"

# 模块加载完成时的提示日志，方便启动时确认 internet.py 已注册。
logger.info("Web scraping tools initialized")