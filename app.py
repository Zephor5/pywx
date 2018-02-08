# coding=utf-8
import json
import logging

from twisted.internet import reactor, task
from twisted.web.resource import Resource

from conf import INNER_IP, DB, LOG_FORMAT, LOG_DATEFORMAT
from module.client import WxClient


formatter = logging.Formatter(
        fmt=LOG_FORMAT,
        datefmt=LOG_DATEFORMAT
    )
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logging.root.setLevel(logging.NOTSET)
logging.root.addHandler(handler)
logger = logging.getLogger(__file__)


CLIENTS = {}


def init_clients():
    cur = DB.execute('select * from client')
    for name, proxy, t in cur:
        CLIENTS[name] = WxClient(name)


def check_clients():
    for client in CLIENTS.itervalues():
        if not client.is_running():
            logger.warn(u'%s重新启动' % client.client_name)
            client.run()


class TaskManage(Resource):
    isLeaf = True

    @staticmethod
    def render_GET(request):
        def get_arg(k):
            return request.args.get(k, [None])[0]
        res = {
            "status": False,
            "msg": ""
        }

        path = request.path

        if path.startswith('/v1/wxspider/qrcode/'):
            name = path.rsplit('qrcode/', 1)[-1]
            _client = CLIENTS.get(name)
            if _client:
                if _client.is_online():
                    res['status'] = False
                    res['msg'] = u'已经登录'
                else:
                    res = u'''<!DOCTYPE html><html><head><title>%s二维码</title></head>
                    <body><img style="width:276px;height:276px;" src="/v1/wxspider/img/%s"></body></html>'''\
                          % (_client.client_name, _client.client_name)
                    res = res.encode('utf-8')
            else:
                res['status'] = False
                res['msg'] = u'没找到客户端'
        elif path.startswith('/v1/wxspider/img/'):
            name = path.rsplit('img/', 1)[-1]
            _client = CLIENTS.get(name)
            if _client:
                if _client.is_online():
                    res['status'] = False
                    res['msg'] = u'已经登录'
                else:
                    with open(_client.qrcode_file, 'rb') as f:
                        res = f.read()
            else:
                res['status'] = False
                res['msg'] = u'没找到客户端'
        elif path.startswith('/v1/wxspider/manage'):
            action = get_arg('action')
            _name = get_arg('clientName')
            if action == 'list':
                res['status'] = True
                res['msg'] = {}
                for _client in CLIENTS.itervalues():
                    res['msg'][_client.client_name] = _client.readable_status()
            elif action == 'add':
                if _name and _name not in CLIENTS:
                    CLIENTS[_name] = WxClient(_name)
                    DB.execute("INSERT INTO client (NAME) VALUES (?)", (_name,))
                    DB.commit()
                    CLIENTS[_name].run()
                    res['status'] = True
                    res['msg'] = u'添加成功，请<a href="/v1/wxspider/qrcode/%s">点击</a>扫描二维码登录' % _name
                else:
                    res['msg'] = u'名称未填写或冲突'
            elif action == 'del':
                if _name and _name in CLIENTS:
                    CLIENTS[_name].stop()
                    CLIENTS.pop(_name)
                    DB.execute('delete from client where name=?', (_name,))
                    DB.commit()
                    logger.info(u'移除客户端：%s...' % _name)
                    res['status'] = True
                    res['msg'] = u'删除成功'
                else:
                    res['msg'] = u'名称不存在'
            elif action == 'reset':
                if _name and _name in CLIENTS:
                    CLIENTS[_name].stop()
                    res['status'] = True
                else:
                    res['msg'] = u'名称不存在'
        elif path.startswith('/v1/wxspider/members/'):
            name = path.rsplit('members/', 1)[-1]
            mems = []
            members = CLIENTS[name].members.copy()
            for k, v in members.iteritems():
                mems.append({
                    "id": k,
                    "Alias": v.get("Alias", ""),
                    "NickName": v.get("NickName", ""),
                    "RemarkName": v.get("RemarkName", "")
                })
            res['msg'] = mems
            res['status'] = True
        elif path.startswith('/v1/wxspider/task/'):
            task_name = path.rsplit('task/', 1)[-1]
            client_name = []
            for k, cl in CLIENTS.items():
                for v in cl.members.itervalues():
                    if v.get("NickName") == task_name:
                        client_name.append({
                            "clientname": k
                        })
                        break
            res['msg'] = client_name
            res['status'] = True
        if isinstance(res, dict):
            request.setHeader("Content-Type", "application/json;charset=UTF-8")
            res = json.dumps(res)
        elif path.startswith('/v1/wxspider/img/'):
            request.setHeader('Content-Type', 'image/jpeg')
        else:
            request.setHeader('Content-Type', 'text/html')
        return res


def cleanup():
    for client in CLIENTS.itervalues():
        client.cleanup()


if __name__ == '__main__':
    from twisted.web.server import Site
    from twisted.internet import endpoints

    endpoints.serverFromString(reactor, "tcp:%s:interface=%s" % (8087, INNER_IP)).listen(Site(TaskManage()))
    init_clients()
    for c in CLIENTS.itervalues():
        c.run()
    task.LoopingCall(check_clients).start(40, now=False)
    reactor.addSystemEventTrigger('before', 'shutdown', cleanup)
    reactor.run()
