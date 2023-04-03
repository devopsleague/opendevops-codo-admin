#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Contact : 191715030@qq.com
Author  : shenshuo
Date    : 2018/11/2
Desc    : 发送通知 API
"""

import json
import base64
from tornado.concurrent import run_on_executor
from concurrent.futures import ThreadPoolExecutor
from libs.base_handler import BaseHandler
from libs.notice_utils import notice_factory
from tornado import gen
from libs.utils import SendMail, SendSms
from .configs_init import configs_init
# from websdk2.jwt_token import gen_md5
from websdk2.consts import const
from websdk2.tools import convert
from websdk2.utils import TokenBucket
from websdk2.cache_context import cache_conn
from websdk2.web_logs import ins_log
###
from websdk2.db_context import DBContextV2 as DBContext
from models.admin_model import Users
from models.notice_model import NoticeTemplate, NoticeGroup, NoticeConfig
from models.notice_schemas import add_notice_config, update_notice_config, get_notice_template
from websdk2.model_utils import queryset_to_list, model_to_dict


class SendMailHandler(BaseHandler):
    @gen.coroutine
    def get(self, *args, **kwargs):
        return self.write(dict(code=-1, msg='Hello, SendMail, Please use POST SendMail!'))

    _thread_pool = ThreadPoolExecutor(5)

    @run_on_executor(executor='_thread_pool')
    def send_mail_pool(self, *args_list):
        send_list = args_list[0]
        config_info = args_list[1]
        try:
            obj = SendMail(mail_host=config_info.get(const.EMAIL_HOST),
                           mail_port=config_info.get(const.EMAIL_PORT),
                           mail_user=config_info.get(const.EMAIL_HOST_USER),
                           mail_password=config_info.get(const.EMAIL_HOST_PASSWORD),
                           mail_ssl=True if config_info.get(const.EMAIL_USE_SSL) == '1' else False,
                           mail_tls=True if config_info.get(const.EMAIL_USE_TLS) == '1' else False)

            obj.send_mail(send_list[0], send_list[1], send_list[2], subtype=send_list[3], att=send_list[4])
            return dict(code=0, msg='邮件发送成功')

        except Exception as e:
            return dict(code=-1, msg='邮件发送失败 {}'.format(str(e)))

    @gen.coroutine
    def post(self, *args, **kwargs):
        ### 发送邮件
        data = json.loads(self.request.body.decode('utf-8'))
        to_list = data.get('to_list', None)
        subject = data.get('subject', None)
        content = data.get('content', None)
        subtype = data.get('subtype', None)
        att = data.get('att', None)
        redis_conn = cache_conn()
        if not to_list and not subject and not content:
            return self.write(dict(code=-1, msg='收件人、邮件标题、邮件内容不能为空'))

        configs_init('all')
        config_info = redis_conn.hgetall(const.APP_SETTINGS)
        config_info = convert(config_info)
        send_list = [to_list, subject, content, subtype, att]
        res = yield self.send_mail_pool(send_list, config_info)
        return self.write(res)


class SendSmsHandler(BaseHandler):
    _thread_pool = ThreadPoolExecutor(5)

    @run_on_executor(executor='_thread_pool')
    def send_sms_pool(self, *args_list):
        send_list = args_list[0]
        config_info = args_list[1]
        try:
            obj = SendSms(config_info.get(const.SMS_REGION), config_info.get(const.SMS_DOMAIN),
                          config_info.get(const.SMS_PRODUCT_NAME), config_info.get(const.SMS_ACCESS_KEY_ID),
                          config_info.get(const.SMS_ACCESS_KEY_SECRET))

            params = json.dumps(send_list[1])
            sms_response = obj.send_sms(send_list[0], template_param=params, sign_name=send_list[2],
                                        template_code=send_list[3])
            sms_response = json.loads(sms_response.decode('utf-8'))
            if sms_response.get("Message") == "OK":
                return dict(code=0, msg='短信发送成功')
            else:
                return dict(code=-2, msg='短信发送失败{}'.format(str(sms_response)))

        except Exception as e:
            return dict(code=-1, msg='短信发送失败 {}'.format(str(e)))

    @gen.coroutine
    def get(self, *args, **kwargs):
        return self.write(dict(code=-1, msg='Hello, Send sms, Please use POST !'))

    @gen.coroutine
    def post(self, *args, **kwargs):
        ### 发送短信
        data = json.loads(self.request.body.decode('utf-8'))
        phone = data.get('phone', None)
        msg = data.get('msg', None)  # json格式 对应短信模板里设置的参数
        template_code = data.get('template_code', None)
        sign_name = data.get('sign_name', 'OPS')
        redis_conn = cache_conn()
        if not phone and not msg and not template_code:
            return self.write(dict(code=-1, msg='收件人、邮件标题、邮件内容不能为空'))

        configs_init('all')
        config_info = redis_conn.hgetall(const.APP_SETTINGS)
        config_info = convert(config_info)
        #
        send_list = [phone, msg, sign_name, template_code]
        res = yield self.send_sms_pool(send_list, config_info)
        return self.write(res)


def silence_lock(conn, lock_name, expire=10):
    if conn.setnx(lock_name, 'y'):
        ### 如果没有锁 就加锁
        conn.expire(lock_name, expire)

    elif not conn.ttl(lock_name):
        conn.expire(lock_name, expire)

    return False


class NoticeHandler(BaseHandler):
    _thread_pool = ThreadPoolExecutor(10)

    @run_on_executor(executor='_thread_pool')
    def send_notice(self, way, notice_conf_map=None, **send_kwargs):

        try:
            obj = notice_factory(way, notice_conf_map=notice_conf_map)
            response = obj.send(**send_kwargs)

            if response and isinstance(response, bytes): response = response.decode()
            if response and isinstance(response, str):  response = json.loads(response)
            if response.get("Message") == "OK":
                res_msg = dict(code=0, msg=f'{way}发送成功')
                if "task_id" in response: res_msg["task_id"] = response.get('task_id')
                if "agent_id" in response: res_msg["agent_id"] = response.get('agent_id')
                return res_msg
            else:
                return dict(code=-4, msg=f'{way}发送失败{str(response)}')

        except Exception as e:
            return dict(code=-5, msg=f'{way}发送失败! {str(e)}')

    def send_default(self, **kwargs):
        ins_log.read_log('info', '启用失败策略，发送默认错误通知')
        err_msg = kwargs.get('msg', None)
        err_template = kwargs.get('name', None)

        send_default = "default"
        redis_conn = cache_conn()

        with DBContext('r') as session:
            __info = session.query(NoticeTemplate).filter_by(**dict(name=send_default)).first()
            if not __info: return

        notice_conf = __info.notice_conf
        if notice_conf and not isinstance(notice_conf, dict): notice_conf = json.loads(notice_conf)

        msg = __info.test_msg
        if msg and not isinstance(msg, dict):   msg = json.loads(msg)
        msg['err_msg'] = err_msg
        msg['err_template'] = err_template

        user_info = __info.user_info
        if user_info and not isinstance(user_info, dict): user_info = json.loads(user_info)

        send_kwargs = dict(__conf=notice_conf, send_addr=user_info, msg=msg, msg_template=__info.msg_template)

        ##通知所需要的配置文件
        notice_conf_map = redis_conn.hgetall("notice_conf_map")
        notice_conf_map = convert(notice_conf_map) if notice_conf_map else self.settings.get('notice_conf_map')
        ####
        way = __info.way
        try:
            obj = notice_factory(way, notice_conf_map=notice_conf_map)
            response = obj.send(**send_kwargs)
            if response and isinstance(response, bytes): response = response.decode()
            if response and isinstance(response, str):  response = json.loads(response)
            return
        except Exception as e:
            return

    @gen.coroutine
    def post(self, *args, **kwargs):
        data = json.loads(self.request.body.decode('utf-8'))
        msg = data.get('msg', None)
        id = data.get('id', None)
        name = data.get('name', None)
        up = data.get('up')
        notice_conf = data.get('notice_conf')
        send_addr = data.get('send_addr')

        if not id and not name: self.write(dict(code=-1, msg="通知模板为必填项"))

        with DBContext('r') as session:
            if id:
                __info = session.query(NoticeTemplate).filter_by(**dict(id=id)).first()
            else:
                __info = session.query(NoticeTemplate).filter_by(**dict(name=name)).first()

        if not __info: return self.write(dict(code=-9, msg="通知模板不存在，或者被拉黑"))
        ### 使用限流
        redis_conn = cache_conn()
        silence = __info.silence if __info.silence else 1
        obj = TokenBucket(redis_conn, 'notice', 5, silence)
        lock_name = f"{id}-the-lock" if id else f"{base64.b64encode(name.encode('utf-8')).decode()}-the-lock"
        if not obj.can_access(lock_name):  return self.write(dict(code=-2, msg="静默状态"))

        way = __info.way

        ### 通知配置
        notice_conf = notice_conf if notice_conf else __info.notice_conf
        if notice_conf:
            try:
                notice_conf = json.loads(notice_conf)
            except:
                return self.write(dict(code=-7, msg="通知配置格式化错误"))

        ### 通知消息
        if msg is None:
            try:
                msg = json.loads(__info.test_msg)
            except Exception as err:
                msg = __info.test_msg

        if not msg: return self.write(dict(code=-8, msg="啥消息都没有，你要干啥子"))

        user_info = __info.user_info if not up else __info.manager_info  ###如果升级通知就用manager_info
        user_info = send_addr if send_addr else user_info
        if not user_info: user_info = {}

        if user_info and not isinstance(user_info, dict):
            try:
                user_info = json.loads(user_info)
            except Exception as err:
                user_info = {}

        send_kwargs = dict(__conf=notice_conf, send_addr=user_info, msg=msg, msg_template=__info.msg_template)

        ##通知所需要的配置文件
        notice_conf_map = redis_conn.hgetall("notice_conf_map")
        notice_conf_map = convert(notice_conf_map) if notice_conf_map else self.settings.get('notice_conf_map')
        if not notice_conf_map: notice_conf_map = get_notice_config()
        res = yield self.send_notice(way, notice_conf_map=notice_conf_map, **send_kwargs)
        if res.get('code') != 0:
            self._thread_pool.submit(self.send_default, **dict(msg=msg, name=__info.name))
            ins_log.read_log('info', str(res.get('msg', '')))
        return self.write(res)

    @run_on_executor(executor='_thread_pool')
    def send_notice_custom(self, way, notice_conf_map=None, **send_kwargs):

        try:
            obj = notice_factory(way, notice_conf_map=notice_conf_map)
            response = obj.send_update(**send_kwargs)

            if response and isinstance(response, bytes): response = response.decode()
            if response and isinstance(response, str):  response = json.loads(response)

            if response.get("Message") == "OK":
                return dict(code=0, msg=response.get('msg'))
            else:
                return dict(code=-4, msg=f'{way}发送失败{str(response)}')

        except Exception as e:
            return dict(code=-5, msg=f'{way}发送失败! {str(e)}')

    @gen.coroutine
    def put(self, *args, **kwargs):
        ### 钉钉OA类型的状态变更
        data = json.loads(self.request.body.decode('utf-8'))
        agent_id = data.get('agent_id')
        task_id = data.get('task_id')
        status_value = data.get('status_value')

        if not agent_id: return self.write(dict(code=-1, msg="agent id 必填且为int类型"))
        if not task_id or not isinstance(task_id, int): return self.write(dict(code=-2, msg="task_id 必填且为int类型"))
        if not status_value:  return self.write(dict(code=-3, msg="状态栏值为必填项"))

        ##需要的配置文件
        redis_conn = cache_conn()
        notice_conf_map = redis_conn.hgetall("notice_conf_map")
        notice_conf_map = convert(notice_conf_map) if notice_conf_map else self.settings.get('notice_conf_map')
        if not notice_conf_map: notice_conf_map = get_notice_config()
        way = "dd_work"
        send_kwargs = {"msg": data}
        res = yield self.send_notice_custom(way, notice_conf_map=notice_conf_map, **send_kwargs)
        return self.write(res)


class NoticeTemplateHandler(BaseHandler):

    def get(self):
        count, queryset = get_notice_template(**self.params)
        self.write(dict(code=0, msg='获取通知模板成功', count=count, data=queryset))

    def post(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        name = data.get('name', None)

        with DBContext('w', None, True) as session:
            is_exist = session.query(NoticeTemplate).filter(NoticeTemplate.name == name).first()
            if is_exist:  return self.write(dict(code=-1, msg=f'{name}已存在'))
            data['user_info'] = get_notice_info(**data)[0]
            data['manager_info'] = get_notice_info(**data)[1]
            session.add(NoticeTemplate(**data))
        return self.write(dict(code=0, msg='模板创建成功'))

    def put(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        notice_id = data.get('id')
        name = data.get('name')

        if not notice_id: return self.write(dict(code=-1, msg='ID不能为空'))
        if not name: return self.write(dict(code=-2, msg='名称不能为空'))

        if '_index' in data: data.pop('_index')
        if '_rowKey' in data: data.pop('_rowKey')

        with DBContext('w', None, True) as session:
            is_exist = session.query(NoticeTemplate).filter(NoticeTemplate.id != notice_id,
                                                            NoticeTemplate.name == name).first()
            if is_exist:  return self.write(dict(code=-3, msg=f'"{name}"已存在'))
            data['user_info'] = get_notice_info(**data)[0]
            data['manager_info'] = get_notice_info(**data)[1]
            session.query(NoticeTemplate).filter(NoticeTemplate.id == notice_id).update(data)

        return self.write(dict(code=0, msg='编辑成功'))

    def patch(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        notice_id = data.get('id')

        if not notice_id: return self.write(dict(code=-1, msg='ID不能为空'))
        with DBContext('w', None, True) as session:
            temp_status = session.query(NoticeTemplate.status).filter(NoticeTemplate.id == notice_id).first()
            if temp_status[0] == '0':
                msg = '通知模板禁用成功'
                new_status = '1'
            else:
                msg = '通知模板启用成功'
                new_status = '0'
            session.query(NoticeTemplate).filter(NoticeTemplate.id == notice_id).update(dict(status=new_status))

        return self.write(dict(code=0, msg=msg))

    def delete(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        notice_id = data.get('id')
        if not notice_id:   return self.write(dict(code=-1, msg='ID不能为空'))

        with DBContext('w', None, True) as session:
            session.query(NoticeTemplate).filter(NoticeTemplate.id == notice_id).delete(synchronize_session=False)

        return self.write(dict(code=0, msg='删除成功'))


def get_notice_info(**kwargs):
    notice_group_list = kwargs.get('notice_group')
    user_list = kwargs.get('user_list')
    # redis_conn = cache_conn()

    tel_list = []
    email_list = []
    ddid_list = []
    manager_list = []
    notice_user = []

    ### 处理通知组
    if notice_group_list and isinstance(notice_group_list, list):
        with DBContext('w', None, True) as session:
            group_info = session.query(NoticeGroup.user_list).filter(NoticeGroup.name.in_(notice_group_list)).all()
        for group in group_info:
            if group[0]: notice_user = notice_user + group[0]

    ### 处理通知用户
    if user_list and isinstance(user_list, list):
        notice_user = notice_user + user_list

    nickname_list = list(set(notice_user))
    with DBContext('r') as session:
        notice_user_info = session.query(Users.tel, Users.email, Users.dd_id, Users.manager).filter(
            Users.nickname.in_(nickname_list)).all()

    for u in notice_user_info:
        if u[0]: tel_list.append(u[0])
        if u[1]: email_list.append(u[1])
        if u[2]: ddid_list.append(u[2])
        if u[3]: manager_list.append(u[3])

    ###########
    user_info = {'tel': tel_list, 'email': email_list, 'dd_id': ddid_list}

    ##处理用户上级的逻辑
    try:
        manager_tel_list = []
        manager_email_list = []
        manager_ddid_list = []  ### 钉钉ID

        manager_list2 = []
        for m in manager_list:
            manager_list2.extend(m.split(','))
        manager_list3 = [m2.split('(')[0] for m2 in manager_list2]
        with DBContext('r') as session:
            notice_manager_info = session.query(Users.tel, Users.email, Users.dd_id).filter(
                Users.username.in_(manager_list3)).all()
        for u in notice_manager_info:
            if u[0]: manager_tel_list.append(u[0])
            if u[1]: manager_email_list.append(u[1])
            if u[2]: manager_ddid_list.append(u[2])
        manager_info = {'tel': manager_tel_list, 'email': manager_email_list, 'dd_id': manager_ddid_list}
    except:
        manager_info = {}

    # all_info.append({"id": notice_id, "user_info": user_info, "manager_info": manager_info})
    return user_info, manager_info


class NoticeGroupHandler(BaseHandler):

    def get(self):
        filter_value = self.get_argument('searchValue', default=None, strip=True)
        filter_map = self.get_argument('filter_map', default=None, strip=True)
        page_size = self.get_argument('page', default='1', strip=True)
        limit = self.get_argument('limit', default='15', strip=True)
        limit_start = (int(page_size) - 1) * int(limit)

        filter_map = json.loads(filter_map) if filter_map else {}

        if filter_value: filter_map['name'] = filter_value
        with DBContext('r') as db:
            __info = db.query(NoticeGroup).filter_by(**filter_map).offset(limit_start).limit(int(limit))
            count = db.query(NoticeGroup).filter_by(**filter_map).count()

        queryset = queryset_to_list(__info)
        self.write(dict(code=0, msg='获取成功', count=count, data=queryset))

    def post(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        name = data.get('name', None)

        with DBContext('w', None, True) as session:
            is_exist = session.query(NoticeGroup).filter(NoticeGroup.name == name).first()
            if is_exist:  return self.write(dict(code=-1, msg=f'{name}已存在'))
            count = session.query(NoticeGroup).count()
            if count >= 200:  return self.write(dict(code=-2, msg='不允许创建超过200个通知组，不方便维护'))
            session.add(NoticeGroup(**data))
        return self.write(dict(code=0, msg='通知组创建成功'))

    def put(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        group_id = data.get('id')
        name = data.get('name')

        if not group_id: return self.write(dict(code=-1, msg='ID不能为空'))
        if not name: return self.write(dict(code=-2, msg='名称不能为空'))

        if '_index' in data: data.pop('_index')
        if '_rowKey' in data: data.pop('_rowKey')

        with DBContext('w', None, True) as session:
            is_exist = session.query(NoticeGroup).filter(NoticeGroup.id != group_id,
                                                         NoticeGroup.name == name).first()
            if is_exist:  return self.write(dict(code=-3, msg=f'"{name}"已存在'))

            session.query(NoticeGroup).filter(NoticeGroup.id == group_id).update(data)

        return self.write(dict(code=0, msg='编辑成功'))

    def delete(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        group_id = data.get('id')
        if not group_id:   return self.write(dict(code=-1, msg='ID不能为空'))

        with DBContext('w', None, True) as session:
            session.query(NoticeGroup).filter(NoticeGroup.id == group_id).delete(synchronize_session=False)

        return self.write(dict(code=0, msg='删除成功'))


class NoticeConfigHandler(BaseHandler):

    def get(self):
        filter_value = self.get_argument('searchValue', default=None, strip=True)
        filter_map = self.get_argument('filter_map', default=None, strip=True)
        page_size = self.get_argument('page', default='1', strip=True)
        limit = self.get_argument('limit', default='15', strip=True)
        limit_start = (int(page_size) - 1) * int(limit)

        filter_map = json.loads(filter_map) if filter_map else {}

        if filter_value: filter_map['name'] = filter_value
        with DBContext('r') as db:
            __info = db.query(NoticeConfig).filter_by(**filter_map).offset(limit_start).limit(int(limit))
            count = db.query(NoticeConfig).filter_by(**filter_map).count()

        queryset = queryset_to_list(__info)
        self.write(dict(code=0, msg='获取成功', count=count, data=queryset))

    async def post(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        name = data.get('name')

        with DBContext('r') as session:
            is_exist = session.query(NoticeConfig).filter(NoticeConfig.name == name).first()
            if is_exist:  return self.write(dict(code=-1, msg=f'{name}已存在'))

        res = add_notice_config(data)

        self.cache_config()
        self.write(res)

    async def put(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        config_id = data.get('id')
        name = data.get('name')

        if not config_id: return self.write(dict(code=-1, msg='ID不能为空'))
        if not name: return self.write(dict(code=-2, msg='名称不能为空'))

        if '_index' in data: data.pop('_index')
        if '_rowKey' in data: data.pop('_rowKey')

        with DBContext('r') as session:
            is_exist = session.query(NoticeConfig).filter(NoticeConfig.id != config_id,
                                                          NoticeConfig.name == name).first()

        if is_exist:  return self.write(dict(code=-3, msg=f'"{name}"已存在'))
        res = update_notice_config(data)
        self.cache_config()

        self.write(res)

    def delete(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        config_id = data.get('id')
        if not config_id:  return self.write(dict(code=-1, msg='ID不能为空'))

        with DBContext('w', None, True) as session:
            session.query(NoticeConfig).filter(NoticeConfig.id == config_id).delete(synchronize_session=False)

        self.cache_config()
        return self.write(dict(code=0, msg='删除成功'))

    @staticmethod
    def cache_config():
        all_config_dict = get_notice_config()
        redis_conn = cache_conn()
        redis_conn.hmset("notice_conf_map", all_config_dict)


def get_notice_config():
    with DBContext('r') as session:
        all_config = session.query(NoticeConfig).filter(NoticeConfig.status == '0').all()

    all_config_dict = {}
    for msg in all_config:
        data_dict = model_to_dict(msg)
        key = data_dict['key']
        conf_map = data_dict.get('conf_map')
        try:
            json.loads(conf_map)
        except Exception as err:
            conf_map = "{}"
        if not conf_map: conf_map = "{}"

        all_config_dict[key] = conf_map
    return all_config_dict


notifications_urls = [
    (r'/v2/notifications/mail/', SendMailHandler),
    (r'/v2/notifications/sms/', SendSmsHandler),
    (r'/v3/notifications/factory/', NoticeHandler, {"handle_name": "通知中心-通知接口"}),
    (r'/v3/notifications/template/', NoticeTemplateHandler, {"handle_name": "通知中心-通知模板"}),
    (r'/v3/notifications/group/', NoticeGroupHandler, {"handle_name": "通知中心-通知组"}),
    (r'/v3/notifications/config/', NoticeConfigHandler, {"handle_name": "通知中心-通知配置"}),
]

if __name__ == "__main__":
    pass
