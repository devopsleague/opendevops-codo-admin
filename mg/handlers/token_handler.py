#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Version : 0.0.1
Contact : 191715030@qq.com
Author  : shenshuo
Date    : 2021/1/11 15:38 
Desc    : 解释一下吧
"""

import json
from libs.base_handler import BaseHandler
from websdk2.utils import SendMail
from .configs_init import configs_init
from websdk2.consts import const
from websdk2.tools import convert
from websdk2.cache_context import cache_conn
from websdk2.jwt_token import gen_md5
from websdk2.jwt_token import AuthToken
from websdk2.db_context import DBContextV2 as DBContext
from models.admin_model import UserToken, Users
from models.admin_schemas import get_token_list
from datetime import datetime, timedelta


class TokenHandler(BaseHandler):

    def get(self, *args, **kwargs):
        if not self.is_superuser: return self.write(dict(code=-1, msg='不是超级管理员，没有权限'))

        filter_value = self.get_argument('searchValue', default=None, strip=True)
        filter_map = self.get_argument('filter_map', default=None, strip=True)
        page_size = self.get_argument('page', default='1', strip=True)
        limit = self.get_argument('limit', default="50", strip=True)

        filter_map = json.loads(filter_map) if filter_map else {}
        count, queryset = get_token_list(int(page_size), int(limit), filter_value, **filter_map)

        return self.write(dict(code=0, result=True, msg="获取成功", count=count, data=queryset))

    ### 获取长期令牌
    def post(self, *args, **kwargs):
        if not self.is_superuser: return self.write(dict(code=-1, msg='不是超级管理员，没有权限'))

        data = json.loads(self.request.body.decode("utf-8"))
        user_list = data.get('user_list', None)

        if len(user_list) != 1:  return self.write(dict(code=-2, msg='一次只能选择一个用户，且不能为空'))

        user_id = user_list[0]
        with DBContext('r') as session:
            user_info = session.query(Users).filter(Users.user_id == user_id).first()
            if user_info.have_token == 'no':
                if not user_info.username.startswith('c-') and not user_info.username.startswith('v-'):
                    return self.write(dict(code=-3, msg='只有虚拟用户或者开启令牌才能拥有长期令牌'))
            # if user_info.superuser == '0': return self.write(dict(code=-4, msg='超级用户不能生成长期令牌'))

        ### 生成token
        is_superuser = True if user_info.superuser == '0' else False

        token_info = dict(user_id=user_id, username=user_info.username, nickname=user_info.nickname,
                          is_superuser=is_superuser, exp_days=1825)
        auth_token = AuthToken()
        auth_key = auth_token.encode_auth_token_v2(**token_info)
        if isinstance(auth_key, bytes): auth_key = auth_key.decode()

        ## 入库
        with DBContext('w', None, True) as session:
            token_count = session.query(UserToken).filter(UserToken.user_id == user_id,
                                                          UserToken.status != '10').count()
            if token_count >= 3:  return self.write(dict(code=-5, msg='不能拥有太多的token'))

            expire_time = datetime.now() + timedelta(days=+360 * 5)
            session.add(UserToken(user_id=int(user_id), nickname=user_info.nickname, token=auth_key,
                                  expire_time=expire_time, token_md5=gen_md5(auth_key)))

        redis_conn = cache_conn()
        configs_init('all')
        config_info = redis_conn.hgetall(const.APP_SETTINGS)
        config_info = convert(config_info)
        obj = SendMail(mail_host=config_info.get(const.EMAIL_HOST), mail_port=config_info.get(const.EMAIL_PORT),
                       mail_user=config_info.get(const.EMAIL_HOST_USER),
                       mail_password=config_info.get(const.EMAIL_HOST_PASSWORD),
                       mail_ssl=True if config_info.get(const.EMAIL_USE_SSL) == '1' else False,
                       mail_tls=True if config_info.get(const.EMAIL_USE_TLS) == '1' else False)

        with DBContext('w', None, True) as session:
            mail_to = session.query(Users.email).filter(Users.user_id == self.get_current_id()).first()

        if mail_to[0] == user_info.email:
            obj.send_mail(mail_to[0], '令牌，有效期五年', auth_key, subtype='plain')
        else:
            obj.send_mail(mail_to[0], '令牌，有效期五年', auth_key, subtype='plain')
            obj.send_mail(user_info.email, '令牌，有效期五年', auth_key, subtype='plain')
        return self.write(dict(code=0, msg='Token已经发送到邮箱', data=auth_key))

    def patch(self, *args, **kwargs):
        if not self.is_superuser: return self.write(dict(code=-1, msg='不是超级管理员，没有权限'))

        """禁用、启用"""
        data = json.loads(self.request.body.decode("utf-8"))
        token_id = data.get('token_id', None)
        msg = 'token不存在'

        if not token_id:   return self.write(dict(code=-1, msg='不能为空'))

        with DBContext('r') as session:
            t_status = session.query(UserToken.status).filter(UserToken.token_id == token_id,
                                                              UserToken.status != 10).first()

        if not t_status:   return self.write(dict(code=-2, msg=msg))

        if t_status[0] == '0':
            msg = '禁用成功'
            new_status = '20'

        elif t_status[0] == '20':
            msg = '启用成功'
            new_status = '0'
        else:
            msg = '状态不符合预期，删除'
            new_status = '10'

        with DBContext('w', None, True) as session:
            session.query(UserToken).filter(UserToken.token_id == token_id, UserToken.status != '10').update(
                {UserToken.status: new_status})

        return self.write(dict(code=0, msg=msg))

    def put(self, *args, **kwargs):
        if not self.is_superuser: return self.write(dict(code=-1, msg='不是超级管理员，没有权限'))

        data = json.loads(self.request.body.decode("utf-8"))
        token_id = data.get('token_id')
        details = data.get('details')
        if not token_id:   return self.write(dict(code=-2, msg='不能为空'))

        with DBContext('w', None, True) as session:
            session.query(UserToken).filter(UserToken.token_id == token_id).update({UserToken.details: details})

        return self.write(dict(code=0, msg="修改备注信息完成"))

    def delete(self, *args, **kwargs):
        if not self.is_superuser: return self.write(dict(code=-1, msg='不是超级管理员，没有权限'))
        data = json.loads(self.request.body.decode("utf-8"))
        token_id = data.get('token_id')
        if not token_id:   return self.write(dict(code=-1, msg='不能为空'))

        with DBContext('w', None, True) as session:
            session.query(UserToken).filter(UserToken.token_id == token_id).update({UserToken.status: '10'})

        return self.write(dict(code=0, msg='删除成功'))


token_urls = [
    (r"/v3/accounts/token/", TokenHandler, {"handle_name": "权限中心-令牌管理"}),

]

if __name__ == "__main__":
    pass
