# -*- coding: utf-8 -*-
from exceptions import WeChatApiError, WeChatUserError
from urllib import quote
import requests
import json
import hashlib
import re
import random
import string


class WeChatApi(object):
    """
    WeChat Api just do one thing: give params to wechat and get the data what wechat return.
    """

    def __init__(self, settings):

        self.settings = settings
        self.global_access_token = {}

    def get_code_url(self, redirect_url, state='STATE'):
        """
        Get the url which 302 jump back and bring a code.

        :param redirect_url: Jump back url
        :param state: Jump back state
        :return: url
        """

        if redirect_url:
            redirect_url = quote(self.settings.REGISTER_URL + redirect_url[1:])
        else:
            redirect_url = self.settings.REDIRECT_URL

        url = ('https://open.weixin.qq.com/connect/oauth2/authorize?' +
               'appid=%s&redirect_uri=%s' +
               '&response_type=code' +
               '&scope=snsapi_userinfo' +
               '&state=%s#wechat_redirect') % (self.settings.APP_ID, redirect_url, state)

        return url

    def get_access_token(self, code):
        """
        Use code for get access token, refresh token, openid etc.

        :param code: A code see function get_code_url.
        :return: Raw data that wechat returns.
        """

        data = requests.get('https://api.weixin.qq.com/sns/oauth2/access_token', params={
            'appid': self.settings.APP_ID,
            'secret': self.settings.APP_SECRET,
            'code': code,
            'grant_type': 'authorization_code'
        }).json()

        return data

    def refresh_access_token(self, refresh_token):
        """
        Refresh user access token by refresh token.

        :param refresh_token: function get_access_token returns.
        :return: Raw data that wechat returns.
        """

        data = requests.get('https://api.weixin.qq.com/sns/oauth2/refresh_token', params={
            'appid': self.settings.APP_ID,
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token
        }).json()

        if 'errcode' in data.keys():
            return 'error'

        return data

    def get_userinfo(self, openid):
        """
        Get user info with global access token (content subscribe, language, remark and groupid).

        :param openid: User openid.
        :return: Raw data that wechat returns.
        """

        access_token = self.settings.GET_GLOBAL_ACCESS_TOKEN(self)
        data = {
            'access_token': access_token,
            'openid': openid,
            'lang': 'zh_CN'
        }
        data = requests.get('https://api.weixin.qq.com/cgi-bin/user/info', params=data).json()

        if 'errcode' in data.keys():
            raise WeChatApiError('errcode: {}, msg: {}'.format(data['errcode'], data['errmsg']))

        return data

    def set_user_remark(self, openid, remark):
        """
        Set user remark.

        :param openid: User openid.
        :param remark: The remark you want to set.
        :return: Raw data that wechat returns.
        """

        access_token = self.settings.GET_GLOBAL_ACCESS_TOKEN(self)
        data = {
            'openid': openid,
            'remark': remark
        }
        url = 'https://api.weixin.qq.com/cgi-bin/user/info/updateremark?access_token=%s' % access_token
        data = requests.post(url, data=json.dumps(data)).json()

        if 'errcode' in data.keys() and data['errcode'] != 0:
            raise WeChatApiError('errcode: {}, msg: {}'.format(data['errcode'], data['errmsg']))

    def get_userinfo_by_token(self, openid, access_token):
        """
        Get user info with user access token (without subscribe, language, remark and groupid).

        :param openid: User openid.
        :param access_token: function get_access_token returns.
        :return: Raw data that wechat returns.
        """

        data = requests.get('https://api.weixin.qq.com/sns/userinfo', params={
            'access_token': access_token,
            'openid': openid,
            'lang': 'zh_CN'
        })

        data.encoding = 'utf-8'
        return data.json()

    def get_global_access_token(self):
        """
        Get global access token.

        :return: Raw data that wechat returns.
        """

        data = requests.get("https://api.weixin.qq.com/cgi-bin/token", params={
            'grant_type': 'client_credential',
            'appid': self.settings.APP_ID,
            'secret': self.settings.APP_SECRET
        }).json()

        return data

    def get_unifiedorder(self, order_info):

        default_settings = {
            'appid': self.settings.APP_ID,
            'mch_id': self.settings.MCH_ID,
            'nonce_str': self._get_random_code(),
        }
        data = dict(default_settings, **order_info)

        self._check_unifiedorder_params(data)

        data['sign'] = self._make_sign(data)

        xml = self._make_xml(data).encode('utf-8')
        data = requests.post('https://api.mch.weixin.qq.com/pay/unifiedorder', data=xml).content

        return self._analysis_xml(data)

    def _get_random_code(self):
        """
        Get random code
        """

        return reduce(lambda x,y: x+y, [random.choice(string.printable[:62]) for i in range(32)])

    def _make_sign(self, data):
        """
        Generate wechat pay for signature
        """

        temp = ['%s=%s' % (k, data[k]) for k in sorted(data.keys())]
        temp.append('key=' + self.settings.MCH_SECRET)
        temp = '&'.join(temp)
        md5 = hashlib.md5()
        md5.update(temp.encode('utf-8'))

        return md5.hexdigest().upper()

    def _make_xml(self, k, v=None):
        """
        Recursive generate XML
        """

        if not v:
            v = k
            k = 'xml'
        if type(v) is dict:
            v = ''.join([self._make_xml(key, val) for key, val in v.iteritems()])
        return '<%s>%s</%s>' % (k, v, k)

    def _analysis_xml(self, xml):
        """
        Convert the XML to dict
        """

        return {k: v for v,k in re.findall('\<.*?\>\<\!\[CDATA\[(.*?)\]\]\>\<\/(.*?)\>', xml)}
    
    def _check_unifiedorder_params(self, params):
        """
        check if params is available

        :param params: a dict.
        :return: None
        """
        required_list = [
            'appid',
            'mch_id',
            'nonce_str',
            'body',
            'out_trade_no',
            'total_fee',
            'spbill_create_ip',
            'notify_url',
            'trade_type'
        ]

        for i in required_list:
            if i not in params or not params[i]:
                raise WeChatApiError('Missing required parameters "{param}" (缺少必须的参数 "{param}")'.format(param=i))

    def get_all_groups(self):
        """
        Get all user groups.

        :return: Raw data that wechat returns.
        """

        access_token = self.settings.GET_GLOBAL_ACCESS_TOKEN(self)
        url = "https://api.weixin.qq.com/cgi-bin/groups/get?access_token=%s" % access_token
        req = requests.get(url)

        return req.json()

    def change_group_name(self, groupid, name):
        """
        Change group name.

        :param groupid: Group ID.
        :param name: New name.
        :return: Raw data that wechat returns.
        """

        access_token = self.settings.GET_GLOBAL_ACCESS_TOKEN(self)
        data = {
            'group': {
                'id': groupid,
                'name': name
            }
        }
        url = 'https://api.weixin.qq.com/cgi-bin/groups/update?access_token=%s' % access_token
        data = requests.post(url, data=json.dumps(data)).json()

        return data

    def change_user_group(self, openid, groupid):
        """
        Move user to a new group.

        :param openid: User openid.
        :param groupid: Group ID.
        :return: Raw data that wechat returns.
        """

        access_token = self.settings.GET_GLOBAL_ACCESS_TOKEN(self)
        data = {
            'openid': openid,
            'to_groupid': groupid
        }
        url = 'https://api.weixin.qq.com/cgi-bin/groups/members/update?access_token=%s' % access_token
        data = requests.post(url, data=json.dumps(data)).json()

        return data

    def del_group(self, groupid):
        """
        Delete a group.

        :param groupid: Group id.
        :return: Raw data that wechat returns.
        """

        access_token = self.settings.GET_GLOBAL_ACCESS_TOKEN(self)
        data = {
            'group': {
                'id': groupid
            }
        }
        url = 'https://api.weixin.qq.com/cgi-bin/groups/delete?access_token=%s' % access_token
        data = requests.post(url, data=json.dumps(data)).json()

        return data

    def create_menu(self, data):
        """
        Create a menu.

        :param data: Menu data.
        :return: Raw data that wechat returns.
        """
        
        access_token = self.settings.GET_GLOBAL_ACCESS_TOKEN(self)
        url = "https://api.weixin.qq.com/cgi-bin/menu/create?access_token=%s" % access_token
        data = requests.post(url, data=json.dumps(data, ensure_ascii=False).encode('utf8')).json()

        return data


# TODO 更方便定制
def get_global_access_token(self):
    """
    获取全局 access token
    """
    def create_group(self, name):
        """
        Create a user group.

        :param name: Group name.
        :return: Raw data that wechat returns.
        """

        access_token = self.settings.GET_GLOBAL_ACCESS_TOKEN(self)
        data = {
            'group': {
                'name': name
            }
        }
        url = 'https://api.weixin.qq.com/cgi-bin/groups/create?access_token=%s' % access_token
        data = requests.post(url, data=json.dumps(data)).json()

        return data
