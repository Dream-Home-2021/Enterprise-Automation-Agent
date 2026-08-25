import os

# langchain_core.tools.tool: LangChain 提供的装饰器，把普通函数注册为 Tool。

from langchain_core.tools import tool
# WebBaseLoader: LangChain 内置的网页抓取器（轻量，抓取静态网页）。
from langchain_community.document_loaders import WebBaseLoader, FireCrawlLoader
try:
    from langchain_crw import CrwLoader
except ImportError:
    CrwLoader = None
# Selenium 相关导入：用于驱动 Chrome 浏览器进行 Google 搜索。
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from typing import Annotated, List
# BeautifulSoup: HTML 解析器，从网页源码里提取出我们需要的纯文本。
from bs4 import BeautifulSoup

from ..logger import setup_logger
from ..config import FIRECRAWL_API_KEY,CRW_API_KEY,CRW_API_URL,CHROMEDRIVER_PATH
logger = setup_logger()

@tool
def google_search(query: Annotated[str, "The search query to use"]) -> Annotated[str, "The top 5 Google search results."]:
    """
    Perform a Google search based on the given query and return the top 5 results.
    """
    try:
        logger.info(f"Performing Google search for query: {query}")
        chrome_options = Options()
        chrome_binary = os.environ.get(
            "CHROME_BINARY",
            r"C:\Users\Administrator\AppData\Local\Google\Chrome\Bin\chrome.exe",
        )
        if os.path.isfile(chrome_binary):
            chrome_options.binary_location = chrome_binary
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        service = Service(CHROMEDRIVER_PATH)

        with webdriver.Chrome(options=chrome_options, service=service) as driver:
            # Set a timeout to prevent hanging on slow network
            # 页面加载超时 30 秒，避免网络慢时一直卡住。
            driver.set_page_load_timeout(30)
            url = f"https://www.google.com/search?q={query}"
            logger.debug(f"Accessing URL: {url}")
            # 让浏览器访问 Google 搜索页。
            driver.get(url)
            html = driver.page_source

        soup = BeautifulSoup(html, 'html.parser')
        search_results = soup.select('.g')
        search = ""
        for result in search_results[:5]:
            title_element = result.select_one('h3')
            title = title_element.text if title_element else 'No Title'
            snippet_element = result.select_one('.VwiC3b')
            snippet = snippet_element.text if snippet_element else 'No Snippet'
            link_element = result.select_one('a')
            link = link_element['href'] if link_element else 'No Link'
            search += f"{title}\n{snippet}\n{link}\n\n"

        logger.info("Google search completed successfully")
        return search
    except Exception as e:
        logger.error(f"Error during Google search: {str(e)}")
        return f'Error: {e}'


def _scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from WebBaseLoader."]:
    """
    Scrape the provided web pages for detailed information using WebBaseLoader.
    """
    try:
        logger.info(f"Scraping webpages: {urls}")
        loader = WebBaseLoader(urls)
        docs = loader.load()
        # 用双换行符把多个网页的正文拼起来。
        content = "\n\n".join([f'\n{doc.page_content}\n' for doc in docs])
        logger.info("Webpage scraping completed successfully")
        return content
    except Exception as e:
        logger.error(f"Error during webpage scraping: {str(e)}")
        raise


def _firecrawl_scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from FireCrawl."]:
    """
    Scrape the provided web pages for detailed information using FireCrawlLoader.
    """
    # 如果没有 API Key，直接抛出异常让上层处理。
    if not FIRECRAWL_API_KEY:
        raise ValueError("FireCrawl API key is not set")

    try:
        logger.info(f"Scraping webpages using FireCrawl: {urls}")
        results = []
        for url in urls:
            loader = FireCrawlLoader(
                api_key=FIRECRAWL_API_KEY,
                url=url,
                mode="scrape"
            )
            res = loader.load()
            if isinstance(res, list):
                for doc in res:
                    if hasattr(doc, "page_content"):
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
        raise

# 内部函数：使用 fastCRW（CrwLoader）抓取网页，是 FireCrawl 的兼容替代方案。

def _crw_scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from fastCRW."]:
    """
    Scrape the provided web pages for detailed information using fastCRW.

    fastCRW is a Firecrawl-compatible web scraper (single binary; self-host or cloud).

    This function uses the CrwLoader to load and scrape the content of the provided URLs.
    """
    try:
        logger.info(f"Scraping webpages using fastCRW: {urls}")
        results = []
        # 逐条遍历 URL，构造 CrwLoader 并抓取。
        for url in urls:
            loader = CrwLoader(
                api_key=CRW_API_KEY,
                api_url=CRW_API_URL,
                url=url,
                mode="scrape"
            )
            res = loader.load()
            if isinstance(res, list):
                for doc in res:
                    if hasattr(doc, "page_content"):
                        results.append(str(doc.page_content))
                    else:
                        results.append(str(doc))
            else:
                results.append(str(res))
        aggregated = "\n\n".join(results)
        logger.info("fastCRW scraping completed successfully")
        return aggregated
    except Exception as e:
        logger.error(f"Error during fastCRW scraping: {str(e)}")
        raise

# 第二个 Tool: scrape_webpages
# 利用"分级降级"策略：先尝试 fastCRW，再 FireCrawl，最后 WebBaseLoader。

@tool
def scrape_webpages(urls: Annotated[List[str], "List of URLs to scrape"]) -> Annotated[str, "The scraped content from fastCRW, FireCrawl or WebBaseLoader."]:
    """
    Attempt to scrape webpages using fastCRW, falling back to FireCrawl then WebBaseLoader if unsuccessful.
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
        return _scrape_webpages(urls)
    except Exception as e:
        # 三种都失败时，返回错误文本给 LLM，让它知道"没抓到"。
        logger.error(f"Both scraping methods failed. Error: {str(e)}")
        return f"Error: Unable to scrape webpages using both methods. {str(e)}"

# 模块加载完成时的提示日志，方便启动时确认 internet.py 已注册。
logger.info("Web scraping tools initialized")