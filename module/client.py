# coding=utf-8
import json
import logging
import random
import time
import os
import re
import urllib

import treq

try:
    import xml.etree.cElementTree as ElementTree
except ImportError:
    import xml.etree.ElementTree as ElementTree
from cookielib import Cookie
from requests.cookies import RequestsCookieJar
from twisted.internet import reactor, defer

from conf import STATUS_STOPPED, STATUS_ONLINE, STATUS_WAITING, DATA_PATH
from .blog import Blog

__author__ = 'zephor'

logger = logging.getLogger(__file__)


class WxClient(object):

    RUNTIME_KEYS = {"device_id", "uuid", "sid", "uin", "skey", "pass_ticket",
                    "syncKey", "syncStr", "myUserName", "members", "groups", "_dn"}

    def __init__(self, client_name):
        self.device_id = ('e%f' % (random.random() * 1000000000000000)).split('.')[0]
        self.client_name = client_name if client_name else self.device_id
        self.qrcode_file = os.path.join(DATA_PATH, '%s.jpg' % self.client_name)
        self.data_file = os.path.join(DATA_PATH, '%s.dat' % self.client_name)
        self.online = STATUS_STOPPED
        self._dn = int(time.time() * 1000) - 1
        self.uuid = None
        self.sid = None
        self.uin = None
        self.skey = None
        self.pass_ticket = None
        self.syncKey = None
        self.syncStr = None
        self.myUserName = None
        self.members = {}
        self.groups = {}
        self.cookies = RequestsCookieJar()
        self._request_d = {}
        self._uptime = time.time()
        self._recover()

    def is_running(self):
        return time.time() - self._uptime < 35.5

    def is_online(self):
        return self.is_running() and self.online == STATUS_ONLINE

    def readable_status(self):
        return ['STOPPED', 'WAITING', 'ONLINE'][self.online]

    def cleanup(self):
        dat = {}
        for k in self.RUNTIME_KEYS:
            dat[k] = getattr(self, k)
        cookies = []
        for cookie in self.cookies:
            cookies.append(repr(cookie))
        dat['cookies'] = cookies
        with open(self.data_file, 'w') as f:
            f.write(json.dumps(dat))

    def stop(self):
        for _d in self._request_d.values():
            _d.cancel()
        self.reset()
        self.online = STATUS_STOPPED

    def reset(self):
        self.device_id = ('e%f' % (random.random() * 1000000000000000)).split('.')[0]
        self._dn = int(time.time() * 1000) - 1
        self.uuid = None
        self.sid = None
        self.uin = None
        self.skey = None
        self.pass_ticket = None
        self.syncKey = None
        self.syncStr = None
        self.myUserName = None
        self.members = {}
        self.groups = {}
        self.cookies = RequestsCookieJar()

    def _recover(self):
        if not os.path.isfile(self.data_file):
            return
        with open(self.data_file) as f:
            data = f.read()
        data = json.loads(data or '{}')
        for k, v in data.iteritems():
            if k in self.RUNTIME_KEYS:
                setattr(self, k, v)
        for cookie_repr in data.get('cookies', []):
            self.cookies.set_cookie(eval(cookie_repr, {'Cookie': Cookie}))

    def _notice_log(self, msg):
        logger.info('[%s] %s' % (self.client_name, msg))

    def _warn_log(self, msg):
        logger.warn('[%s] %s' % (self.client_name, msg))

    def _error_log(self, msg):
        logger.error('[%s] %s' % (self.client_name, msg))

    @property
    def dn(self):
        self._dn += 1
        return self._dn

    @property
    def _r(self):
        return 1473173782527 - int(time.time() * 1000)

    @property
    def r(self):
        return int(time.time() * 1000)

    @defer.inlineCallbacks
    def treq_request(self, url, data=None):
        args = [url]
        headers = {
            'Referer': 'https://wx.qq.com'
        }
        method = 'get'
        if data:
            method = 'post'
            data = json.dumps(data)
            args.append(data)
            headers['Content-Type'] = 'application/json; charset=UTF-8'
        k = url.split('?')[0]
        _d = self._request_d.get(k)
        if isinstance(_d, defer.Deferred):
            _d.cancel()
        _d = self._request_d[k] = getattr(treq, method)(*args, cookies=self.cookies, headers=headers, timeout=35)
        try:
            res = yield _d
        except Exception as e:
            if isinstance(e.message, list) and getattr(e.message[0], 'type', None) is defer.CancelledError:
                # print type(e.message[0]), e.message[0].type
                self._warn_log('request %s cancelled' % k)
            else:
                import traceback
                self._error_log(traceback.format_exc())
                defer.returnValue('')
        else:
            self.cookies = res.cookies()
            content = yield res.content()
            defer.returnValue(content)
        finally:
            self._uptime = time.time()
            self._request_d.pop(k, None)

    @defer.inlineCallbacks
    def run(self):
        url = 'https://wx.qq.com'
        try:
            content = yield self.treq_request(url)
        except Exception as e:
            self._error_log('main page fail: %s' % e)
            return
        if content is None:
            return
        r = re.search(r'window\.MMCgi\s*=\s*\{\s*isLogin\s*:\s*(\S+)', content)
        if r:
            if r.group(1) == '!!"1"':
                self.online = STATUS_ONLINE
                self._notice_log(u"微信已登录")
                d = self._sync_check()
            else:
                self.members = {}
                self.groups = {}
                d = self._get_uuid()
            yield d
        else:
            self._error_log(u'主页返回格式有误')

    @defer.inlineCallbacks
    def _get_uuid(self):
        self.online = STATUS_WAITING
        url = 'https://login.wx.qq.com/jslogin?appid=wx782c26e4c19acffb&redirect_uri=' + urllib.quote(
            "https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxnewloginpage") + "&fun=new&lang=zh_CN&_=" + str(self.dn)
        try:
            content = yield self.treq_request(url)
        except:
            self._error_log(u'获取uuid失败，准备重试...')
            reactor.callLater(0.5, self.run)
            return
        if content is None:
            return
        r = re.match(r'window\.QRLogin\.code = (\d+); window\.QRLogin\.uuid = "([^"]+)"', content)
        if r:
            self.uuid = r.group(2)
            self._get_qrcode()
            yield self._login_check(1)
        else:
            self._error_log(u'uuid返回内容有误，%s' % content)

    @defer.inlineCallbacks
    def _get_qrcode(self):
        url = 'https://login.weixin.qq.com/qrcode/' + self.uuid
        res = yield treq.get(url)
        content = yield res.content()
        with open(self.qrcode_file, 'wb') as f:
            f.write(content)
        self._notice_log(u'二维码准备就绪...')

    @defer.inlineCallbacks
    def _login_check(self, tip=0):
        login_check_dict = {
            'loginicon': 'true',
            'uuid': self.uuid,
            'tip': tip,
            '_': self.dn,
            'r': self._r
        }
        url = 'https://login.wx.qq.com/cgi-bin/mmwebwx-bin/login?%s' % urllib.urlencode(login_check_dict)
        content = yield self.treq_request(url)
        if content is None:
            return
        r = re.search(r'window\.code=(\d+)', content)
        if not r:
            return
        code = int(r.group(1))
        if code == 200:
            self._notice_log(u"正在登陆...")
            r = re.search(r'window\.redirect_uri="([^"]+)"', content)
            url = r.group(1) + '&fun=new&version=v2'
            content = yield self.treq_request(url)
            dom = ElementTree.fromstring(content)
            self.sid = dom.findtext('wxsid')
            self.uin = dom.findtext('wxuin')
            self.skey = dom.findtext('skey')
            self.pass_ticket = dom.findtext('pass_ticket')
            yield self._init()
        elif code == 201:
            self._notice_log(u"已扫码，请点击登录...")
            yield self._login_check()
        elif code == 408:
            self._notice_log(u"等待手机扫描二维码...")
            yield self._login_check()
        elif code in {0, 400, 500}:
            self._notice_log(u'等待超时，重新载入...')
            yield self.run()

    @defer.inlineCallbacks
    def _init(self):
        query_dict = {
            'r': self._r,
            'pass_ticket': self.pass_ticket,
            'lang': 'zh_CN'
        }
        url = 'https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxinit?' + urllib.urlencode(query_dict)
        data = {
            "BaseRequest": {
                "Uin": self.uin,
                "Sid": self.sid,
                "Skey": self.skey,
                "DeviceID": self.device_id
            }
        }
        content = yield self.treq_request(url, data)
        if content is None:
            return
        body_dic = json.loads(content)
        if body_dic and body_dic['BaseResponse']['Ret'] == 0:
            self.syncKey = body_dic['SyncKey']
            self._form_sync_str()
            self._parse_contact(body_dic['ContactList'])
            self.myUserName = body_dic['User']['UserName']
            self._notice_log(u"初始化成功，开始监听消息")
            self.online = STATUS_ONLINE
            self._status_notify()
            self._get_contact()
            yield self._sync_check()
        else:
            self._error_log(u'初始化失败%s' % unicode(body_dic))

    @defer.inlineCallbacks
    def _sync_check(self):
        query_dict = {
            'r': self.r,
            'skey': self.skey,
            'sid': self.sid,
            'uin': self.uin,
            'deviceid': self.device_id,
            'synckey': self.syncStr,
            '_': self.dn
        }
        url = 'https://webpush.wx.qq.com/cgi-bin/mmwebwx-bin/synccheck?' + urllib.urlencode(query_dict)
        try:
            content = yield self.treq_request(url)
        except Exception as e:
            self._error_log(u'同步失败: ' + str(e))
            yield self._sync_check()
            return
        if content is None:
            return
        r = re.match(r'window\.synccheck=\{retcode:"(\d+)",selector:"(\d+)"}', content)
        if not r:
            self._error_log(u'同步失败: body格式有误，%s' % content)
            yield self._sync_check()
            return
        retcode = int(r.group(1))
        selector = int(r.group(2))
        if retcode == 0:
            if selector == 0:
                self._notice_log(u'同步检查')
                yield self._sync_check()
            elif selector == 2:
                self._notice_log(u'收到新消息')
            elif selector == 4:
                self._notice_log(u'朋友圈有新动态')
            elif selector == 7:
                self._notice_log(u'app操作消息')
            else:
                self._notice_log(u'未知消息')
            if selector != 0:
                yield self._sync()
        elif retcode == 1100:
            self._notice_log(u'你在手机上登出了微信，再见！')
        elif retcode == 1101:
            self._notice_log(u'你在其他地方登录了web微信，再见！')
        elif retcode == 1102:
            self._notice_log(u"未知登出，再见！")
        else:
            self._notice_log(u"未知retcode")

    def _form_sync_str(self):
        sync_str = ''
        for i, sync_key in enumerate(self.syncKey['List']):
            sync_str += '%s_%s' % (sync_key['Key'], sync_key['Val'])
            if i != self.syncKey['Count'] - 1:
                sync_str += '|'
        self.syncStr = sync_str

    @defer.inlineCallbacks
    def _parse_contact(self, contact_list):
        group_list = []
        for contact in contact_list:
            un = contact['UserName']
            if un.find('@@') != -1:
                self.groups[un] = contact
                group_list.append(un)
            else:
                self.members[un] = contact
        if group_list:
            yield self._batch_get_contact(group_list)

    @defer.inlineCallbacks
    def _status_notify(self):
        query_dict = {
            'pass_ticket': self.pass_ticket
        }
        url = 'https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxstatusnotify?' + urllib.urlencode(query_dict)
        data = {
            "BaseRequest": {
                "Uin": self.uin,
                "Sid": self.sid,
                "Skey": self.skey,
                "DeviceID": self.device_id
            },
            "Code": 3,
            "FromUserName": self.myUserName,
            "ToUserName": self.myUserName,
            "ClientMsgId": int(time.time() * 1000)
        }
        content = yield self.treq_request(url, data)
        if content:
            body_dic = json.loads(content)
            if body_dic['BaseResponse']['Ret'] == 0:
                self._notice_log(u'状态同步成功')
            else:
                self._notice_log(u'状态同步失败: ' + body_dic['BaseResponse']['ErrMsg'])

    @defer.inlineCallbacks
    def _get_contact(self):
        query_dict = {
            'pass_ticket': self.pass_ticket,
            'skey': self.skey,
            'r': self.r
        }
        url = 'https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxgetcontact?' + urllib.urlencode(query_dict)
        content = yield self.treq_request(url)
        if content:
            body_dic = json.loads(content)
            yield self._parse_contact(body_dic['MemberList'])

    @defer.inlineCallbacks
    def _batch_get_contact(self, group_list):
        query_dict = {
            "type": "ex",
            "pass_ticket": self.pass_ticket,
            "r": self.r
        }
        url = 'https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxbatchgetcontact?' + urllib.urlencode(query_dict)
        _list = []
        for un in group_list:
            _list.append({
                'UserName': un,
                'ChatRoomId': ''
            })
        data = {
            'BaseRequest': {
                "DeviceID": self.device_id,
                "Sid": self.sid,
                "Skey": self.skey,
                "Uin": self.uin,
            },
            'Count': len(_list),
            'List': _list
        }
        content = yield self.treq_request(url, data)
        if content is None:
            return
        body_dic = json.loads(content)
        if not body_dic or body_dic['BaseResponse']['Ret'] != 0:
            return
        for contact in body_dic['ContactList']:
            for member in contact['MemberList']:
                self.members[member['UserName']] = member

    @defer.inlineCallbacks
    def _sync(self):
        query_dict = {
            'sid': self.sid,
            'skey': self.skey,
            'pass_ticket': self.pass_ticket,
            'lang': 'zh_CN'
        }
        url = 'https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxsync?' + urllib.urlencode(query_dict)
        data = {
            "BaseRequest": {
                "Uin": self.uin,
                "Sid": self.sid
            },
            "SyncKey": self.syncKey,
            "rr": self._r
        }
        try:
            content = yield self.treq_request(url, data)
        except Exception as e:
            self._warn_log(u'获取消息失败: %s' % e)
            yield self._sync_check()
            return
        if content is None:
            return
        body_dic = json.loads(content)
        if body_dic['BaseResponse']['Ret'] != 0:
            self._warn_log(u'消息错误: %d' % body_dic['BaseResponse']['Ret'])
            reactor.callLater(1, self._sync_check)
            return
        if body_dic['SyncKey'] and body_dic['SyncKey']['Count']:
            self.syncKey = body_dic['SyncKey']
            self._form_sync_str()
        for contact in body_dic['DelContactList']:
            self.members.pop(contact['UserName'], None)
        self._parse_contact(body_dic['ModContactList'])
        self._handle_msg(body_dic['AddMsgList'])
        yield self._sync_check()

    def _handle_msg(self, msgs):
        for msg in msgs:
            getattr(self, '_msg_%d' % msg['MsgType'], self._msg_default)(msg)

    @defer.inlineCallbacks
    def _get_user_remark_name(self, username):
        remark_name = None
        is_group = username.find('@@') == 0
        if username in self.members:
            remark_name = self.members[username].get('RemarkName')
            remark_name = remark_name if remark_name else self.members[username].get('NickName')
        elif is_group:
            if username in self.groups:
                remark_name = self.groups[username].get('RemarkName')
                remark_name = remark_name if remark_name else self.groups[username].get('NickName')
            else:
                yield self._batch_get_contact([username])
                if username in self.groups:
                    remark_name = self.groups[username].get('RemarkName')
                    remark_name = remark_name if remark_name else self.groups[username].get('NickName')
        defer.returnValue(remark_name if remark_name else u'未知')

    @defer.inlineCallbacks
    def _get_public_alias(self, username):
        if username not in self.members:
            yield self._batch_get_contact([username])
        alias = None
        if 'Alias' in self.members[username]:
            alias = self.members[username]['Alias']
        alias = alias if alias else (yield self._get_user_remark_name(username))
        defer.returnValue(alias if alias else u'未知')

    @defer.inlineCallbacks
    def _msg_1(self, msg):
        src_name = yield self._get_user_remark_name(msg['FromUserName'])
        dst_name = yield self._get_user_remark_name(msg['ToUserName'])
        self._notice_log('%s -> %s: %s' % (src_name, dst_name, msg['Content']))

    @defer.inlineCallbacks
    def _msg_49(self, msg):
        url = msg['Url'].replace('&amp;', '&')
        name = yield self._get_user_remark_name(msg['FromUserName'])
        alias = yield self._get_public_alias(msg['FromUserName'])
        title = msg['FileName']
        self._notice_log(u'标题: %s' % title)
        self._notice_log(u'链接: %s' % url)
        self._notice_log(u'%s，分享了一个链接，请粘贴url到浏览器查看' % name)
        Blog.parse_content(alias, msg['Content'])

        # purge cache for wxdata
        # noinspection PyBroadException
        try:
            res = yield treq.get('http://wxspider.pub.sina.com.cn:8086/_purge/v1/wxspider/blogs/%s' %
                                 urllib.quote(alias.encode('utf-8')), timeout=3)
            content = yield res.content()
            if content.find('Successful purge') > 0:
                self._notice_log('purge cache ok')
            elif content.find('Not Found') > 0:
                self._notice_log('no cache there')
            else:
                self._warn_log('purge cache failed content: %s' % content)
        except Exception as e:
            self._warn_log('purge cache failed: %s' % str(e))

    def _msg_default(self, msg):
        self._notice_log(u'发现未定义的msgType: %d' % msg['MsgType'])
        self._notice_log(msg['Content'])
