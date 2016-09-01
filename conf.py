# coding=utf-8
import os
import sqlite3
import threading

from module.ip import get_ip

STATUS_ONLINE = 2
STATUS_WAITING = 1
STATUS_STOPPED = 0

ROOT_PATH = os.path.dirname(__file__)
DATA_PATH = os.path.join(ROOT_PATH, 'data')

INNER_IP = get_ip()

LOG_FORMAT = '[%(name)s:%(lineno)d] %(asctime)s %(levelname)s: %(message)s'
LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'


class Db(threading.local):

    @property
    def conn(self):
        if not hasattr(self, '_conn'):
            self._conn = sqlite3.connect(os.path.join(DATA_PATH, 'blog.db'), timeout=1)
        return self._conn

    def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    def commit(self):
        self.conn.commit()


DB = Db()

DB.execute("""CREATE TABLE IF NOT EXISTS blog
       (ID INTEGER PRIMARY KEY AUTOINCREMENT,
       NAME CHAR(64) NOT NULL,
       TITLE TEXT NOT NULL,
       URL CHAR(256) UNIQUE NOT NULL,
       SAVE_TIME TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""")

DB.execute("""CREATE TABLE IF NOT EXISTS client
       (NAME CHAR(64) UNIQUE NOT NULL,
       PROXY CHAR(128),
       SAVE_TIME TIMESTAMP DEFAULT CURRENT_TIMESTAMP);""")
