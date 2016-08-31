# coding=utf-8
import logging
import sqlite3

try:
    import xml.etree.cElementTree as ElementTree
except ImportError:
    import xml.etree.ElementTree as ElementTree

from conf import DB


logger = logging.getLogger(__file__)


class Blog(object):

    @staticmethod
    def parse_content(alias, content):
        content = content.replace('&gt;', '>').replace('&lt;', '<')\
            .replace('&amp;', '&').replace('<br/>', '').encode('utf-8')
        print content
        dom = ElementTree.fromstring(content)
        added = False
        for item in dom.iter('category/item'):
            title = item.findtext('title')[9:-3]
            url = item.findtext('url')
            url = url.replace('&amp;', '&')[9:-3]
            try:
                DB.conn.execute("INSERT INTO blog (NAME,TITLE,URL) VALUES (?, ?, ?)", (alias, title, url))
            except sqlite3.IntegrityError:
                logger.warn(u'%s 的 %s: %s 记录失败' % (alias, title, url))
            else:
                added = True
        if added:
            DB.conn.commit()
        return added

    @staticmethod
    def add_blog(alias, title, url):
        try:
            DB.conn.execute("INSERT INTO blog (NAME,TITLE,URL) VALUES (?, ?, ?)", (alias, title, url))
        except sqlite3.IntegrityError:
            logger.warn(u'%s 的 %s: %s 记录失败' % (alias, title, url))
        else:
            DB.conn.commit()
