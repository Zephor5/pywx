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
        dom = ElementTree.fromstring(content)
        added = False
        for item in dom.iter('item'):
            title = item.findtext('title')
            url = item.findtext('url')
            try:
                DB.execute("INSERT INTO blog (NAME,TITLE,URL) VALUES (?, ?, ?)", (alias, title, url))
            except sqlite3.IntegrityError:
                logger.warn(u'%s 的 %s: %s 重复记录' % (alias, title, url))
            except sqlite3.OperationalError:
                logger.error(u'%s 的 %s: %s 记录失败' % (alias, title, url))
            else:
                added = True
        if added:
            try:
                DB.execute("delete from blog where id in "
                           "(select id from blog where name=? order by save_time desc limit "
                           "(select count(id) from blog where name=?) offset 100)", (alias, alias))
            except sqlite3.OperationalError:
                logger.warn(u'删除操作失败')
            DB.commit()
        return added

    @staticmethod
    def add_blog(alias, title, url):
        try:
            DB.execute("INSERT INTO blog (NAME,TITLE,URL) VALUES (?, ?, ?)", (alias, title, url))
        except sqlite3.IntegrityError:
            logger.warn(u'%s 的 %s: %s 重复记录' % (alias, title, url))
        except sqlite3.OperationalError:
            logger.error(u'%s 的 %s: %s 记录失败' % (alias, title, url))
        else:
            try:
                DB.execute("delete from blog where id in "
                           "(select id from blog where name=? order by save_time desc limit "
                           "(select count(id) from blog where name=?) offset 100)", (alias, alias))
            except sqlite3.OperationalError:
                logger.warn(u'删除操作失败')
            DB.commit()
