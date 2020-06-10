import base64
import concurrent.futures
import copy
import json
import logging
import os
import re
import shutil
from threading import active_count
from time import sleep

from bs4 import BeautifulSoup, SoupStrainer

from ebooklib import epub

import requests as r

time_format = f"%d-%m-%Y %H:%M:%S"
# Enable if you want to try to automatize this and wish to save logs
logging.basicConfig(
    # filename=f"/logs/main-{datetime.now().strftime(time_format)}",
    # format=f"%(asctime) %(message)",
    # datefmt=f"%d/%m/%Y %I:%M%S",
    level=logging.DEBUG,
)

PROGRESS = {}
NOVEL = None
EBOOK = None


class WuxiaWorld_Novel():
    def __init__(self, page, url):
        link: list = re.findall(r"href=\"(.*)\" ", BeautifulSoup(page.content, features="lxml", parse_only=SoupStrainer("dl")).prettify())
        img_url: str = re.search(r"src=\"(.*)\" width", BeautifulSoup(page.content, features="lxml", parse_only=SoupStrainer("img")).prettify())[1]
        chapter: list = re.findall(r"   (.*)", BeautifulSoup(page.content, features="lxml", parse_only=SoupStrainer("dl")).prettify())
        self.url = url
        self.author: str = re.search(r"Author：(.*)", BeautifulSoup(
            page.content, features="lxml", parse_only=SoupStrainer("p")).prettify())[1]
        self.chap_dict = dict(zip(chapter, link))
        self.book_name = re.sub(r"-", " ", re.search(r".co/(.*)/", url)[1])
        self.book_filename = re.sub(r" ", r"_", self.book_name.lower())
        self.img_response = r.get(f"https://www.wuxiaworld.co/{img_url}", stream=True)
        self.chap_file = 0
        self.chap_name = -1


class Formatter:
    def __init__(self, raw):
        self.raw = raw

    def warlock_of_the_magus_world(self):
        page = re.sub(r"(\\])", r"]\n<br/>", self.raw)
        return re.sub(r"(\] \[)", r"]\n<br/>\n[", page)


def wuxiaworld_scraper(url: str):
    global PROGRESS
    global NOVEL
    page = r.get(url)
    NOVEL = WuxiaWorld_Novel(page, url)
    with open("temp.jpg", 'wb') as f:
        NOVEL.img_response.raw.decode_content = True
        shutil.copyfileobj(NOVEL.img_response.raw, f)


def full_book_maker():
    global PROGRESS
    global NOVEL
    global EBOOK
    EBOOK = epub.EpubBook()
    EBOOK.set_identifier(base64.b64encode(NOVEL.book_name.encode()).decode())
    EBOOK.set_title(NOVEL.book_name)
    EBOOK.set_language("en")
    EBOOK.add_author(NOVEL.author)
    with open("temp.jpg", "rb") as f:
        EBOOK.set_cover("image.jpg", f.read())
    os.rmdir("temp.jpg")
    EBOOK.spine = ["cover", "nav"]
    NOVEL.chap_dict = {k: NOVEL.chap_dict[k] for k in list(NOVEL.chap_dict.keys())[:100]}
    # throwaway_dict = copy.deepcopy(NOVEL.chap_dict)
    # if PROGRESS == []:
    #     pass
    # else:
    #     for novel, chapter in PROGRESS.items():
    #         if novel == NOVEL.book_name:
    #             for entry, _html in throwaway_dict.items():
    #                 if entry != chapter:
    #                     NOVEL.chap_dict.pop(entry)
    #                 else:
    #                     NOVEL.chap_dict.pop(entry)
    #                     break
    #             break
    html_list = []
    for entry in NOVEL.chap_dict.values():
        html_list.append(entry)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        executor.map(wuxiaworld_adapter, html_list)
    # try:
    #     PROGRESS[NOVEL.book_name] = list(NOVEL.chap_dict)[len(list(NOVEL.chap_dict)) - 1]
    # except IndexError:
    #     try:
    #         logging.info(f"No new chapters for {NOVEL.book_name}")
    #     except NameError:
    #         pass
    EBOOK.add_item(epub.EpubNcx())
    EBOOK.add_item(epub.EpubNav())
    logging.debug(f"| QiQi | Writing {NOVEL.book_name} epub")
    epub.write_epub(f"{NOVEL.book_filename}.epub", EBOOK)

# wuxiaworld_adapter(chap_dict, url, html, book, book_name, i, name)


def wuxiaworld_adapter(html):
    global EBOOK
    sleep(active_count() * 0.025)
    page = r.get(f"{NOVEL.url}/{html}")
    soup = BeautifulSoup(page.content, features="lxml")
    for tag in soup.select(".header,.clear,.nav,.dahengfu,.con_top,.bottem1,.bottem2,#footer"):
        tag.decompose()
    NOVEL.chap_file += 1
    NOVEL.chap_name += 1
    logging.debug(f"| QiQi | Working on: {list(NOVEL.chap_dict.keys())[NOVEL.chap_name]}")
    chapter = epub.EpubHtml(title=NOVEL.chapter[NOVEL.chap_name], file_name=f"{NOVEL.chap_file}.xhtml", lang="en")
    chapter.content = soup.prettify()
    EBOOK.add_item(chapter)
    EBOOK.spine.append(chapter)


def tasker(json_list):
    global PROGRESS
    try:
        with open(f"{json_list}", "r") as f:
            novel_list = json.load(f)
    except FileNotFoundError:
        logging.info("| QiQi | Is this your first time running this? Creating the list input file |")
        with open(json_list, "w+") as f:
            json.dump([], f)
    try:
        with open("progress.json", "r+") as f:
            PROGRESS = json.load(f)
    except FileNotFoundError:
        logging.debug("| QiQi | Creating progress tracker |")
        with open("progress.json", "w+") as f:
            json.dump({}, f)
    for entry in novel_list:
        logging.info(f"| QiQi | Working on :{entry}")
        wuxiaworld_scraper(entry)
        full_book_maker()
    with open(f"progress.json", "w+") as f:
        logging.debug(f"| QiQi | Dumping the progress tracker into the file:\n{PROGRESS}")
        json.dump(PROGRESS, f)


# trio.run(wuxiaworld, "https://www.wuxiaworld.co/Warlock-of-the-Magus-World/")
# cProfile.run('tasker("list.json")')
tasker("list.json")
