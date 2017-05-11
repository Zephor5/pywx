# coding=utf-8
import datetime
from conf import DB


if __name__ == '__main__':
    stamp = datetime.datetime.now() - datetime.timedelta(days=3)

    DB.execute("delete from blog where save_time < ? ", (stamp.strftime('%Y-%m-%d %H:%M:%S'),))
    DB.commit()
