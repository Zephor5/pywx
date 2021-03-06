# coding=utf-8
import time
import flask

from conf import DB

app = flask.Flask('pywx')


@app.route('/v1/wxspider/blogs')
@app.route('/v1/wxspider/blogs/<wx_id>')
def blogs(wx_id=None):
    res = {}
    if wx_id:
        cur = DB.execute('select * from blog where name=? order by save_time desc limit 20', (wx_id,))
    else:
        cur = DB.execute('select * from blog order by save_time desc limit 100')
    for _, name, title, url, t in cur:
        if name not in res:
            res[name] = {'list': [], 'uptime': int(time.time() * 1000)}
        res[name]['list'].append({'title': title, 'url': url})
    if wx_id:
        res = res.get(wx_id, {'list': [], 'uptime': 0})
    return flask.jsonify(res)


if __name__ == '__main__':
    app.run()
