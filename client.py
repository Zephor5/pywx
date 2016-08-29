# coding=utf-8
import json
import logging
import random
import time

import re
import urllib

import treq
import os
import certifi
try:
    import xml.etree.cElementTree as ElementTree
except ImportError:
    import xml.etree.ElementTree as ElementTree
from twisted.internet import reactor, defer

from conf import STATUS_STOPPED, STATUS_ONLINE, STATUS_WAITING

__author__ = 'zephor'
os.environ["SSL_CERT_FILE"] = certifi.where()
logging.root.setLevel(logging.NOTSET)
logging.root.addHandler(logging.StreamHandler())
logger = logging.getLogger(__file__)


class WxClient(object):
    def __init__(self, client_name):
        self.device_id = ('e%f' % (random.random() * 1000000000000000)).split('.')[0]
        self.client_name = client_name if client_name else self.device_id
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
        self.cookies = {}
        self.login_check_d = None
        self.sync_check_d = None

    def _notice_log(self, msg):
        logger.info('%s: %s' % (self.client_name, msg))

    def _error_log(self, msg):
        logger.error('%s: %s' % (self.client_name, msg))

    @property
    def dn(self):
        self._dn += 1
        return self._dn

    @property
    def r(self):
        return 1473173782527 - int(time.time() * 1000)

    @defer.inlineCallbacks
    def run(self):
        url = 'https://wx.qq.com'
        try:
            res = yield treq.get(url)
            self.cookies = res.cookies()
            content = yield res.content()
        except:
            self._error_log('main page fail')
            return
        r = re.search(r'window\.MMCgi\s*=\s*\{\s*isLogin\s*:\s*(!!"1")', content, re.M)
        if r and r.group(1) == '!!"1"':
            self.online = STATUS_ONLINE
            self._notice_log("微信已登录")
            d = self.sync_check_d = self._wx_sync_check()
        else:
            d = self._get_uuid()
        yield d

    @defer.inlineCallbacks
    def _get_uuid(self):
        self.online = STATUS_WAITING
        url = 'https://login.wx.qq.com/jslogin?appid=wx782c26e4c19acffb&redirect_uri=' + urllib.quote(
            "https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxnewloginpage") + "&fun=new&lang=zh_CN&_=" + str(self.dn)
        # print url
        try:
            res = yield treq.get(url, cookies=self.cookies)
            self.cookies = res.cookies()
            content = yield res.content()
        except:
            self._error_log('获取uuid失败，准备重试...')
            reactor.callLater(0.5, self.run)
            return
        r = re.match(r'window\.QRLogin\.code = (\d+); window\.QRLogin\.uuid = "([^"]+)"', content)
        self.uuid = r.group(2)
        self._get_qrcode()
        yield self._login_check(1)

    @defer.inlineCallbacks
    def _get_qrcode(self):
        url = 'https://login.weixin.qq.com/qrcode/' + self.uuid
        res = yield treq.get(url)
        content = yield res.content()
        with open('test.png', 'wb') as f:
            f.write(content)
        self._notice_log('二维码准备就绪...')

    @defer.inlineCallbacks
    def _login_check(self, tip=0):
        login_check_dict = {
            'loginicon': 'true',
            'uuid': self.uuid,
            'tip': tip,
            '_': self.dn,
            'r': self.r
        }
        url = 'https://login.wx.qq.com/cgi-bin/mmwebwx-bin/login?%s' % urllib.urlencode(login_check_dict)
        self.login_check_d = treq.get(url)
        res = yield self.login_check_d
        self.cookies = res.cookies()
        self.login_check_d = res.content()
        content = yield self.login_check_d
        r = re.search(r'window\.code=(\d+)', content)
        code = int(r.group(1))
        if code == 200:
            self._notice_log("正在登陆...")
            r = re.search(r'window\.redirect_uri="([^"]+)"', content)
            url = r.group(1) + '&fun=new&version=v2'
            res = yield treq.get(url)
            self.cookies = res.cookies()
            content = yield res.content()
            dom = ElementTree.fromstring(content)
            self.sid = dom.findtext('wxsid')
            self.uin = dom.findtext('wxuin')
            self.skey = dom.findtext('skey')
            self.pass_ticket = dom.findtext('pass_ticket')
        elif code == 201:
            self._notice_log("已扫码，请点击登录...")
            yield self._login_check()
        elif code == 408:
            self._notice_log("等待手机扫描二维码...")
            yield self._login_check()
        elif code in {0, 400, 500}:
            self._notice_log('等待超时，重新载入...')
            yield self.run()

    def _init(self):
        query_dict = {
            'r': self.r,
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
        res = yield treq.post(url, data)
        content = yield res.content()
        content = json.loads(content)
        self.syncKey = content['SyncKey']
        self._form_sync_str()
        self._parse_contact(content['ContactList'])
        self.myUserName = content['User']['UserName']
        self._notice_log("初始化成功，开始监听消息")
        self.online = STATUS_ONLINE
        self._status_notify()
        self._get_contact()
        self.sync_check_d = self._sync_check()
        yield self.sync_check_d

    @defer.inlineCallbacks
    def _sync_check(self):
        yield

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
        res = yield treq.post(url, data)
        content = yield res.content()
        body_dic = json.loads(content)
        if body_dic['BaseResponse']['Ret'] == 0:
            self._notice_log('状态同步成功')
        else:
            self._notice_log('状态同步失败: ' + body_dic['BaseResponse']['ErrMsg'])

    @defer.inlineCallbacks
    def _get_contact(self):
        query_dict = {
            'pass_ticket': self.pass_ticket,
            'skey': self.skey,
            'r': self.r
        }
        url = 'https://wx.qq.com/cgi-bin/mmwebwx-bin/webwxgetcontact?' + urllib.urlencode(query_dict)
        res = yield treq.get(url)
        content = yield res.content()
        body_dic = json.loads(content)
        yield self._parse_contact(body_dic['MemberList'])

    @defer.inlineCallbacks
    def _batch_get_contact(self, group_list):
        pass


if __name__ == '__main__':
    c = WxClient('test')
    c.run()
    reactor.run()
