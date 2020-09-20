import base64
import concurrent.futures
import json
import logging
import os
import re
import shutil
from itertools import repeat
from queue import Queue
from threading import RLock
from time import perf_counter


from bs4 import BeautifulSoup, SoupStrainer

from ebooklib import epub

from matplotlib import pyplot as plt

import requests as r


time_format = f"%d-%m-%Y %H:%M:%S"
# Enable if you want to try to automatize this and wish to save logs
logging.basicConfig(
    # filename=f"/logs/main-{datetime.now().strftime(time_format)}",
    # format=f"%(asctime) %(message)",
    # datefmt=f"%d/%m/%Y %I:%M%S",
    level=logging.DEBUG,
)

# Global variables are evil, but so am I (Actually I'm lazy and just want this working)
progress = {}
lock = RLock()


class Wuxiaworld_Novel:
    """
    This is a class for novels hosted on wuxiaworld.co

    | Attributes |

    page (Response): Response to GET request of the novel\n
    link (list): List of all the available partial links to chapters\n
    chapter (list): List with the name of all the available chapters\n
    url (str): URL of the novel\n
    author (str): Author's name\n
    chap_dict (dict): zip of the chapter and link attributes\n
    book_name (str): Name of the novel\n
    book_filename (str): Filename in which to record the novel\n
    img_response (Response): Cover of the novel\n
    """

    def __init__(self, url):
        """
        The constructor for WuxiaWorld_Novel class

        | Parameters |

        url (str): URL of the novel
        """
        self.page = r.get(url)
        self.link: list = [
            re.search(r"/.*/(.*.html)", i)[1]
            for i in [
                entry["href"]
                for entry in [
                    entry
                    for entry in BeautifulSoup(self.page.content, features="lxml").select(".chapter-list")[0]
                    if entry.find("a") is None
                ]
            ]
        ]
        img_url: str = [
            entry
            for entry in BeautifulSoup(self.page.content, features="lxml", parse_only=SoupStrainer("img")).contents[
                1:-1
            ]
            if entry["class"] == ["bg-img"]
        ][0]["src"]
        self.chapter: list = [
            entry.contents[0]
            for entry in BeautifulSoup(self.page.content, features="lxml", parse_only=SoupStrainer("p")).contents[1:]
            if entry["class"] == ["chapter-name"]
        ]
        self.chapter.insert(0, "padding")
        self.url = url
        self.author: str = BeautifulSoup(self.page.content, features="lxml", parse_only=SoupStrainer("span")).select(
            ".name"
        )[0].contents[0]
        self.chap_dict = dict(zip(self.chapter, self.link))
        self.book_name = (
            BeautifulSoup(self.page.content, features="lxml", parse_only=SoupStrainer("div"))
            .select(".book-name")[0]
            .contents[0]
        )
        self.book_filename = re.sub(r" ", r"_", self.book_name.lower())
        self.img_response = r.get(f"{img_url}", stream=True)


def book_maker(novel, lock):
    counter = 0
    ebook = epub.EpubBook()
    ebook.set_identifier(base64.b64encode(novel.book_name.encode()).decode())
    ebook.set_title(novel.book_name)
    ebook.set_language("en")
    ebook.add_author(novel.author)
    with lock:
        novel.img_response.raw.decode_content = True
        with open(f"temp.jpg", "wb") as f:
            shutil.copyfileobj(novel.img_response.raw, f)
        with open("temp.jpg", "rb") as f:
            ebook.set_cover("image.jpg", f.read())
        os.remove("temp.jpg")
    ebook.spine = ["cover", "nav"]
    ebook.add_item(epub.EpubNcx())
    ebook.add_item(epub.EpubNav())
    return [novel, ebook, counter]


def book_update(novel, ebook, counter, chapter_cut=50, max_workers=10, benchmark=False, thread_benchmark=False):
    global progress
    if benchmark:
        start = perf_counter()
        novel.chap_dict = {k: novel.chap_dict[k] for k in list(novel.chap_dict.keys())[:chapter_cut]}
    if thread_benchmark:
        novel.chap_dict = {k: novel.chap_dict[k] for k in list(novel.chap_dict.keys())[:chapter_cut]}
    if progress == []:
        pass
    else:
        for book_name, chapter in progress.items():
            if book_name == novel.book_name:
                for entry, _html in {k: v for (k, v) in novel.chap_dict.items()}.items():
                    if entry != chapter:
                        novel.chap_dict.pop(entry)
                    else:
                        novel.chap_dict.pop(entry)
                        break
                break
    # html_list = [entry for entry in novel.chap_dict.values()]
    q = Queue()
    for _i in novel.chap_dict:
        counter += 1
        q.put(counter)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = executor.map(wuxiaworld_adapter, list(novel.chap_dict.values()), repeat(novel), repeat(q))
        for chapter in results:
            ebook.add_item(chapter)
            ebook.spine.append(chapter)
    try:
        progress[novel.book_name] = list(novel.chap_dict.keys())[-1]
        ebook.toc = ()
        logging.debug(f"| QiQi | Writing {novel.book_name} epub")
        epub.write_epub(f"{novel.book_filename}.epub", ebook)
        if benchmark:
            stop = perf_counter()
            with open("timing", "a+") as f:
                f.write(f"{max_workers} threads: {round(stop-start, 3)} for {len(novel.chap_dict)}\n")
        logging.debug(f"| QiQi | Saving the progress:\n{progress}")
        with open(f"progress.json", "w+") as f:
            json.dump(progress, f)
    except IndexError:
        try:
            logging.info(f"No new chapters for {novel.book_name}")
        except NameError:
            pass
    if benchmark:
        return [len(novel.chap_dict), round((stop - start), 3)]


def wuxiaworld_adapter(html, novel, q):
    page = r.get(f"{novel.url}/{html}")
    soup = BeautifulSoup(page.content, features="lxml")
    # Getting rid of page elements
    for tag in soup.find_all(["script", "link", "ins", "amp-auto-ads, iframe"]):
        tag.decompose()
    for tag in soup.select(
        ".t-header,.book-wrapper,.chapter-entity > a:nth-child(91),.section-end,.reader-page,.empty-container,.guide-wrapper,.bar-header,.readtool-footer,.font-tool,.disqus_box,.t-footer,body > div:nth-child(16),.login_dim,.app-download"
    ):
        tag.decompose()
    bookname = soup.find("h1").contents[0]
    i = q.get()
    chapter = epub.EpubHtml(uid=f"chapter_{i}", title=bookname, file_name=f"{i}.xhtml", lang="en")
    # chapter.content = Formatter(soup.prettify()).novel_guesser(novel)
    chapter.content = re.sub(r"Please ((.|\n)*) free", "", soup.prettify())
    logging.debug(f"| QiQi | Working on: {novel.chapter[i]}")
    return chapter


def book_logic(entry, lock1, chaps=50, max_workers=10, bench=False):
    global progress
    logging.info(f"| QiQi | Working on: {entry}")
    novel = Wuxiaworld_Novel(entry)
    novel.img_response.raw.decode_content = True
    if novel.book_name in progress:
        counter = -4
        ebook = epub.read_epub(f"{novel.book_filename}.epub")
        for _entry in ebook.get_items():
            counter += 1
        book_update(novel, ebook, counter, chaps, max_workers, False, bench)
    else:
        variab = book_maker(novel, lock1)
        book_update(variab[0], variab[1], variab[2], chaps, max_workers, False, bench)


def tasker(json_list):
    global progress
    try:
        with open(f"{json_list}", "r") as f:
            novel_list = json.load(f)
    except FileNotFoundError:
        logging.info("| QiQi | Is this your first time running this? Creating the list input file |")
        with open(json_list, "w+") as f:
            json.dump([], f)
        logging.info("| QiQi | Ignore this exception |")
        raise UnboundLocalError
    try:
        with open("progress.json", "r+") as f:
            progress = json.load(f)
    except FileNotFoundError:
        logging.debug("| QiQi | Creating progress tracker |")
        with open("progress.json", "w+") as f:
            json.dump({}, f)
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = executor.map(book_logic, novel_list, repeat(RLock()))
        for future in futures:
            print(future)


def single_benchmark():
    global progress
    chap_sample = [50, 200, 500, 1000]
    x = []
    y = []
    for entry in chap_sample:
        max_workers = 10
        while max_workers < 76:
            max_workers += 2
            progress = {}
            novel = Wuxiaworld_Novel("https://www.wuxiaworld.co/Warlock-of-the-Magus-World/")
            novel.img_response.raw.decode_content = True
            variab = book_maker(novel, RLock())
            results = book_update(variab[0], variab[1], variab[2], entry, max_workers, True)
            y.append(results[1] / results[0])
            x.append(max_workers)
        print(x)
        print(y)
        plt.plot(x, y)
        plt.ylabel("Time per chapter")
        plt.xlabel("Threads")
        # plt.show()
        plt.savefig(f"graph{results[0]}_0.png")


def multiple_benchmark():
    global progress
    chap_sample = [50, 200, 500, 1000]
    x = []
    y = []
    for entry in chap_sample:
        max_workers = 10
        while max_workers < 76:
            max_workers += 2
            progress = {}
            start = perf_counter()
            with open("list.json", "r") as f:
                novel_list = json.load(f)
            with concurrent.futures.ThreadPoolExecutor() as executor:
                executor.map(book_logic, novel_list, repeat(RLock()), repeat(entry), repeat(max_workers), repeat(True))
            stop = perf_counter()
            y.append(round((stop - start), 3) / (entry * len(novel_list)))
            x.append(max_workers)
        print(x)
        print(y)
        plt.plot(x, y)
        plt.ylabel("Time per chapter")
        plt.xlabel("Threads")
        # plt.show()
        plt.savefig(f"graph{entry}_multiple.png")


class Formatter:
    """
    Class for reformatting whatever errors there are in a novel

    | Methods |

    novel_guesser: Tries to apply a known formatter to the novel based on it's (supposed) filename
    """

    def __init__(self, raw):
        """
        Constructor method for Formatter class

        | Parameters |

        raw (str): String you want formatted
        """
        self.raw = raw

    def novel_guesser(self, novel):
        if isinstance(novel, Wuxiaworld_Novel):
            for method_name in dir(self):
                if novel.book_filename == method_name:
                    method = getattr(Formatter, method_name)
                    return method(self)

    def warlock_of_the_magus_world(self):
        page = re.sub(r"(\\])", r"]\n<br/>", self.raw)
        return re.sub(r"(\] \[)", r"]\n<br/>\n[", page)


tasker("list.json")
# single_benchmark()
# multiple_benchmark()
# print(link)

# TODO
# implement tasker switching adapter on reading the url to boxnovel.com since that seems to work
# implement check for incomplete chapters and make it go for novelupdates.cc to get those since that's how it seems to work
# make possible to have this running as a discord bot
