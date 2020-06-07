import base64
import json
import re
from time import perf_counter

from bs4 import BeautifulSoup, SoupStrainer

from ebooklib import epub

import httpx

# from joblib import Parallel, delayed

import trio


PROGRESS = {}


class Formatter:
    def __init__(self, raw):
        try:
            logging.debug("Created formatter object")
        except NameError:
            pass
        self.raw = raw

    def warlock_of_the_magus_world(self):
        page = re.sub(r"(\\])", r"]\n<br/>", self.raw)
        return re.sub(r"(\] \[)", r"]\n<br/>\n[", page)


async def wuxiaworld(url: str):
    """Adapter for downloading novels from wuxiaworld.co. By being given the novel link, downloads all chapters and returns a list with them (hopefully) organized."""
    global PROGRESS
    start = perf_counter()
    async with httpx.AsyncClient() as client:
        page = await client.get(url)
    tags = SoupStrainer("dl")
    author_tag = SoupStrainer("p")
    # img_tag = SoupStrainer("img")
    soup = BeautifulSoup(page.content, features="lxml", parse_only=tags).prettify()
    author_soup = BeautifulSoup(page.content, features="lxml", parse_only=author_tag).prettify()
    # img_soup = BeautifulSoup(page.content, features="lxml", parse_only=img_tag).prettify()
    chapter: list = re.findall(r"   (.*)", soup)
    link: list = re.findall(r"href=\"(.*)\" ", soup)
    author: str = re.search(r"Author：(.*)", author_soup)[1]
    # img_url: str = re.search(r"src=\"(.*)\" width", img_soup)[1]
    chap_dict = dict(zip(chapter, link))
    book_name_dirty = re.search(r".co/(.*)/", url)
    book_name = re.sub(r"-", " ", book_name_dirty[1])
    book_filename = re.sub(r" ", r"_", book_name.lower())
    book = epub.EpubBook()
    book.set_identifier(base64.b64encode(book_name.encode()).decode())
    book.set_title(book_name)
    book.set_language("en")
    book.add_author(author)
    book.spine = ["cover", "nav"]
    # with httpx.stream("GET", f"https://www.wuxiaworld.co/{img_url}") as response:
    #     with open("image.jpg", "wb") as f:
    #         f.write(next(response.iter_raw()))
    # book.set_cover("image.jpg", response)
    i = 1
    #chap_dict = {k: chap_dict[k] for k in list(chap_dict.keys())[:4]}
    #print(chap_dict)
    for name, html in chap_dict.items():
        async with httpx.AsyncClient() as client:
            page = await client.get(f"{url}/{html}")
        soup = BeautifulSoup(page.content, features="lxml")
        for tag in soup.select(".header,.clear,.nav,.dahengfu,.con_top,.bottem1,.bottem2,#footer"):
            tag.decompose()
        chapter = epub.EpubHtml(title=name, file_name=f"{i}.xhtml", lang="en")
        chapter.content = Formatter(soup.prettify()).warlock_of_the_magus_world()
        book.add_item(chapter)
        i += 1
        book.toc.append(chapter)
        book.spine.append(chapter)
        print(name)
    print(PROGRESS)
    for novel, _chapter in PROGRESS.items():
        if book_name == novel:
            PROGRESS[book_name] = list(chap_dict)[len(list(chap_dict)) - 1]
    stop = perf_counter()
    with open("timing", "a+") as f:
        f.write(f"#With Asyncio | PyPy 3.6.9 | Time elapsed: {round(stop - start, 3)} \n")
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(f'{book_filename}.epub', book)
    return True


def tasker(json_list):
    global PROGRESS
    with open(f"{json_list}", "r") as f:
        novel_list = json.load(f)
    with open(f"progress.json", "r+") as f:
        PROGRESS = json.load(f)
    for entry in novel_list:
        print(entry)
        trio.run(wuxiaworld, entry)
    with open(f"progress.json", "w+") as f:
        print(PROGRESS)
        json.dump(PROGRESS, f)


# trio.run(wuxiaworld, "https://www.wuxiaworld.co/Warlock-of-the-Magus-World/")
tasker("list.json")