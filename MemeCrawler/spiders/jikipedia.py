import os
import re
import pickle
import scrapy
import numpy as np
from MemeCrawler.settings import JIKI_INDEX_FILE
from MemeCrawler.logger import logger
from MemeCrawler.items import JikiItem


class JikiSpider(scrapy.Spider):
    name = 'jiki'

    # Saved data
    saved_dict = {}
    todo_list = []

    # Url format of Jikipedia
    enytry_url = 'https://jikipedia.com/definition/{index}'
    max_index = 40000

    # Patterns
    pat_dict = {
        'name': '<title.*?>(.*?)是什么意思',
        'time': '([0-9]{4}-[0-9]{2}-[0-9]{2})',
        'image_url': '<img src="(https://api.jikipedia.com/upload/.*?)"',
        'view': 'view basic-info-element.*?>(.*?)<',
        'like': 'like-count.*?>(.*?)<',
        'dislike': 'dislike-count.*?>(.*?)<',
        'comment_count': 'comment-count.*?>(.*?)<'
    }

    # Default values
    default_dict = {
        'name': 'noname',
        'time': '0000-00-00',
        'image_url': '',
        'view': '0',
        'like': '0',
        'dislike': '0',
        'comment_count': '0'
    }

    # Handle bad http status
    handle_httpstatus_list = [404, 500]

    def start_requests(self) -> scrapy.Request:
        # Init saved index and next index sequence
        self.init_index()
        # Iterates all indices
        for index in self.todo_list:
            # Transform int64 to int so that it could be jsonfied
            index = int(index)
            yield scrapy.Request(self.enytry_url.format(index=index),
                                 callback=self.parse, meta={'index': index})

    def parse(self, response: scrapy.http.response) -> scrapy.Item:
        index = response.meta['index']
        status = response.status
        # Check if ip has been banned: redirected to moss CAPTCHA
        if response.text.find('hello moss') >= 0:
            self.crawler.engine.close_spider(self, 'IP banned.')
        # Can't be reached
        if status == 200:
            text = response.text
            item = JikiItem()
            # Parse items
            item['index'] = index
            for attr, pat in self.pat_dict.items():
                try:
                    item[attr] = re.search(pat, text).group(1)
                except AttributeError:
                    item[attr] = self.default_dict[attr]
            item['tag_list'] = self.get_tag_list(text)
            item['content'] = self.get_content(text)
            # Record name
            self.saved_dict[index] = item['name']
            # Yield item
            if item['name'] != self.default_dict['name']:
                yield item
        elif status == 404:
            self.saved_dict[index] = 'error'
        else:  # status == 500
            self.crawler.engine.close_spider(self, 'Connection failed.')

    def init_index(self) -> None:
        # Load from index file and shuffle index
        if os.path.exists(JIKI_INDEX_FILE):
            with open(JIKI_INDEX_FILE, 'rb') as f:
                saved: dict = pickle.load(f)
        else:
            saved = {}
        # Get unsaved index
        all_index = np.ones(self.max_index + 1)
        all_index[list(saved.keys())] = 0
        todo = np.where(all_index > 0)[0]
        # Shuffle index
        np.random.shuffle(todo)
        self.todo_list = todo
        self.saved_dict = saved

    @staticmethod
    def get_content(raw: str) -> str:
        # Extract content of entry.
        # Truncate first modal-container
        left = raw.find('<span class="brax-node"')
        right = raw.find('<div class="modal-container')
        raw = raw[left:right]
        content = re.sub('<.*?>', '', raw)
        return content

    @staticmethod
    def get_tag_list(raw: str) -> list:
        # Extract tag index list of entry.
        pat = '<span class="tag-text".*?>#(.*?)</span>'
        tags = re.findall(pat, raw)
        return tags

    def close(self, spider, reason):
        # Dump save record before close spider
        logger.info(reason)
        with open(JIKI_INDEX_FILE, 'wb') as f:
            pickle.dump(self.saved_dict, f)
