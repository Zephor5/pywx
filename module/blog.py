# coding=utf-8
# import time
import logging
import sqlite3
import unicodedata
try:
    import xml.etree.cElementTree as ElementTree
except ImportError:
    import xml.etree.ElementTree as ElementTree

from conf import DB


logger = logging.getLogger(__file__)


def remove_control_characters(s):
    return "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")


class Blog(object):

    @staticmethod
    def parse_content(alias, content):
        content = remove_control_characters(content)
        content = content.replace('&gt;', '>').replace('&lt;', '<')\
            .replace('&amp;', '&').replace('<br/>', '').encode('utf-8')
        try:
            dom = ElementTree.fromstring(content)
        except ElementTree.ParseError:
            logger.error('parse error')
            logger.error(content)
            return
        data = []
        for item in dom.iter('item'):
            title = item.findtext('title')
            url = item.findtext('url')
            # cover = item.findtext('cover')
            # pub_time = item.findtext('pub_time')
            data.append((alias, title, url))
        if data:
            try:
                DB.executemany("INSERT INTO blog (NAME,TITLE,URL) VALUES (?, ?, ?)", data)
            except sqlite3.IntegrityError:
                logger.warn(u'%s 的 %s: %s 重复记录' % (alias, data[0][1], data[0][2]))
            except sqlite3.OperationalError:
                logger.error(u'%s 的 %s: %s 记录失败' % (alias, data[0][1], data[0][2]))
        else:
            title = dom.findtext('appmsg/title')
            url = dom.findtext('appmsg/url')
            # cover = dom.findtext('appmsg/thumburl')
            # pub_time = str(time.time()).split('.')[0]
            try:
                DB.execute("INSERT INTO blog (NAME,TITLE,URL) VALUES (?, ?, ?)", (alias, title, url))
            except sqlite3.IntegrityError:
                logger.warn(u'%s 的 %s: %s 重复记录' % (alias, title, url))
            except sqlite3.OperationalError:
                logger.error(u'%s 的 %s: %s 记录失败' % (alias, title, url))

        try:
            DB.commit()
            logger.info(u'commit success')
        except sqlite3.OperationalError as e:
            logger.warn(u'commit error: %s' % str(e))
