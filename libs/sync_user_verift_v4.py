#!/usr/bin/env python
# -*-coding:utf-8-*-
"""
author : shenshuo
date   : 2025年02月28日
"""

import datetime
import hashlib
import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import requests
from websdk2.cache_context import cache_conn
from websdk2.configs import configs
from websdk2.consts import const
from websdk2.db_context import DBContextV2 as DBContext
from websdk2.jwt_token import gen_md5
from websdk2.tools import RedisLock, now_timestamp, convert

from libs.etcd import Etcd3Client
from libs.feature_model_utils import insert_or_update
from models.authority import Users, Roles, UserRoles, RoleFunctions, Functions, UserToken
from models.paas_model import BizModel
from services.role_service import get_all_user_list_for_role
from settings import settings

if configs.can_import: configs.import_dict(**settings)

requests.packages.urllib3.disable_warnings()


def deco(cls, release=False):
    def _deco(func):
        def __deco(*args, **kwargs):
            if not cls.get_lock(cls, key_timeout=300, func_timeout=120): return False
            try:
                return func(*args, **kwargs)
            finally:
                # 执行完就释放key，默认不释放
                if release: cls.release(cls)

        return __deco

    return _deco


def deco1(cls, release=False):
    def _deco(func):
        def __deco(*args, **kwargs):
            if not cls.get_lock(cls, key_timeout=1800, func_timeout=120): return False
            try:
                return func(*args, **kwargs)
            finally:
                # 执行完就释放key，默认不释放
                if release: cls.release(cls)

        return __deco

    return _deco


def deco2(cls, release=False):
    def _deco(func):
        def __deco(*args, **kwargs):
            if not cls.get_lock(cls, key_timeout=7200, func_timeout=120): return False
            try:
                return func(*args, **kwargs)
            finally:
                # 执行完就释放key，默认不释放
                if release: cls.release(cls)

        return __deco

    return _deco


class MyVerify:
    def __init__(self, is_superuser=False, **kwargs):
        self.redis_conn = cache_conn()
        if "etcds" not in settings: raise SystemExit('找不到ETCD配置')
        self.etcd_dict = settings.get('etcds').get(const.DEFAULT_ETCD_KEY)
        self.etcd_prefix = settings.get('etcd_prefix', '/')
        self.crbac_prefix = f"{self.etcd_prefix}codorbac/"
        self.token_block_prefix = f"{self.etcd_prefix}token/block/"
        self.biz_acl_prefix = f"{self.etcd_prefix}biz/acl/"
        self.is_superuser = is_superuser
        self.method_list = ["GET", "POST", "PATCH", "DELETE", "PUT", "ALL"]
        self.etcd_client = Etcd3Client(host=self.etcd_dict.get(const.DEFAULT_ETCD_HOST),
                                       port=self.etcd_dict.get(const.DEFAULT_ETCD_PORT))

    # 2024年5月14日 优化查询 v2
    @staticmethod
    def get_role_info(session, role_id):
        role = session.query(Roles).filter(Roles.id == role_id).first()
        if not role:
            return None, []
        _role_list = [role_id]
        if role.role_type == 'normal' and role.role_subs:
            _role_list.extend(role.role_subs)
        return role, set(_role_list)

    def api_permissions(self):
        # 超级用户网关直接放行
        api_permissions_dict = dict()
        # logging.error(check_user_func_list_md5())

        with DBContext('r') as session:
            role_list = session.query(UserRoles).all()
            roles = {role.id: role for role in
                     session.query(Roles).filter(Roles.id.in_([i.role_id for i in role_list])).all()}

        for i in role_list:
            role = roles.get(i.role_id)
            if not role:
                continue

            role, _role_list = self.get_role_info(session, i.role_id)
            func_list = session.query(
                Functions.id, Functions.func_name, Functions.app_code, Functions.uri, Functions.method_type
            ).outerjoin(RoleFunctions, Functions.id == RoleFunctions.func_id
                        ).filter(Functions.status == '0', RoleFunctions.role_id.in_(_role_list)).all()

            for func in func_list:
                key = f"{func.id}---{func.func_name}---{func.app_code}---{func.uri}---{func.method_type}"
                val = i.user_id
                if key in api_permissions_dict:
                    api_permissions_dict[key][val] = "y"
                else:
                    api_permissions_dict[key] = {val: "y"}
        return api_permissions_dict

    @staticmethod
    def api_permissions_bak():
        # 超级用户网关直接放行
        api_permissions_dict = dict()

        with DBContext('r') as session:
            role_list = session.query(UserRoles).all()

        for i in role_list:
            with DBContext('r') as session:
                role = session.query(Roles).filter(Roles.id == i.role_id).first()

            _role_list = [i.role_id]
            if role.role_type == 'normal' and role.role_subs:
                _role_list.extend(role.role_subs)

            _role_list = set(_role_list)

            for _role_id in _role_list:
                # with DBContext('r') as session:
                func_list = session.query(Functions.id, Functions.func_name, Functions.app_code, Functions.uri,
                                          Functions.method_type
                                          ).outerjoin(RoleFunctions, Functions.id == RoleFunctions.func_id
                                                      ).filter(Functions.status == '0',
                                                               RoleFunctions.role_id == _role_id).all()

                for func in func_list:
                    key, val = f"{func[0]}---{func[1]}---{func[2]}---{func[3]}---{func[4]}", i.user_id

                    val_dict = api_permissions_dict.get(key)
                    if val_dict and isinstance(val_dict, dict):
                        api_permissions_dict[key] = {**val_dict, **{val: "y"}}
                    else:
                        api_permissions_dict[key] = {val: "y"}

        return api_permissions_dict

    def sync_all_permission(self):
        ttl_id = now_timestamp()
        logging.info(f'全量同步权限到ETCD 准备 {ttl_id}')
        api_data = self.api_permissions()
        try:
            self.etcd_client.ttl(ttl_id=ttl_id, ttl=720000)
        except Exception as err:
            logging.error(f"全量同步权限到ETCD ttl_id 出错 {err}")
        ###
        for k, v in api_data.items():
            func_id, func_name, app_code, uri, method = k.split('---')
            match_key = f"/{app_code}/{method}{uri}"
            value = {
                "name": func_name,
                "time": now_timestamp(),
                "key": match_key,
                "uri": uri,
                "method": method,
                "func_id": func_id,
                "app_code": app_code,
                "status": 1,
                "rules": v
            }
            key = f"{self.crbac_prefix}{func_id}{match_key}"
            try:
                self.etcd_client.put(key, json.dumps(value), lease=ttl_id)
            except Exception as err:
                logging.error(f"全量同步权限到ETCD 出错 {err}")

        logging.info(f'全量同步权限到ETCD 结束 {ttl_id}')

    @deco2(RedisLock("async_all_api_permission_v4_redis_lock_key"))
    def sync_all_api_permission(self):
        self.sync_all_permission()

    @deco(RedisLock("async_diff_api_permission_v4_redis_lock_key"))
    def sync_diff_api_permission(self):
        ttl_id = now_timestamp()
        logging.info(f'差异同步权限到ETCD 检查开始 {ttl_id}')

        api_data = self.api_permissions()
        try:
            self.etcd_client.ttl(ttl_id=ttl_id, ttl=720000)
        except Exception as err:
            logging.error(f"差异同步权限到ETCD ttl_id 出错 {err}")
        ###
        api_permission_new_dict = {}
        api_permission_dict_key = "api_permission_dict_key"
        api_permission_old_dict = self.redis_conn.hgetall(api_permission_dict_key)

        for k, v in api_data.items():
            k_md5 = gen_md5(k)
            v_md5 = gen_md5(json.dumps(v))
            api_permission_new_dict[k_md5] = v_md5

        self.redis_conn.hmset(api_permission_dict_key, api_permission_new_dict)
        self.redis_conn.expire(api_permission_dict_key, 300)
        api_permission_old_dict = convert(api_permission_old_dict)

        if api_permission_new_dict == api_permission_old_dict: return

        for k, v in api_data.items():
            func_id, func_name, app_code, uri, method = k.split('---')
            k_md5 = gen_md5(k)
            v_md5 = gen_md5(json.dumps(v))
            match_key = f"/{app_code}/{method}{uri}"
            value = {
                "name": func_name,
                "time": now_timestamp(),
                "key": match_key,
                "uri": uri,
                "method": method,
                "func_id": func_id,
                "app_code": app_code,
                "status": 1,
                "rules": v
            }
            key = f"{self.crbac_prefix}{func_id}{match_key}"
            ########
            try:
                if k_md5 in api_permission_old_dict:
                    if v_md5 != api_permission_old_dict.get(k_md5):
                        # print(f'{k}   ####API关联关系改变，要更新一下')
                        self.etcd_client.put(key, json.dumps(value), lease=ttl_id)
                else:
                    # print(f'{k}    ####新API  要更新一下')
                    self.etcd_client.put(key, json.dumps(value), lease=ttl_id)
            except Exception as err:
                logging.error(f"差异同步权限到ETCD 出错 {err}")

    ##################################################################
    @deco(RedisLock("async_token_block_lock_key"))
    def sync_token_block_to_gw(self):
        try:
            ttl_id = now_timestamp()
            logging.info(f'同步令牌黑名单数据 {ttl_id}')
            with DBContext('r') as session:
                token_info = session.query(UserToken.token_md5).filter(UserToken.status != '0').all()

            self.etcd_client.ttl(ttl_id=ttl_id, ttl=86400)  # 一天
            block_dict = {token_md5[0]: 'y' for token_md5 in token_info}

            self.etcd_client.put(self.token_block_prefix, json.dumps(block_dict), lease=ttl_id)
        except Exception as err:
            logging.error(f"推送令牌黑名单出错 {err}")

    @deco(RedisLock("async_biz_list_to_gw_lock_key"))
    def sync_biz_to_gw(self):
        try:
            ttl_id = now_timestamp()
            logging.info(f'同步业务数据 {ttl_id}')
            with DBContext('r') as session:
                business_info = session.query(BizModel).all()

            for info in business_info:
                acl_prefix = f"{self.biz_acl_prefix}{info.biz_id}"
                users_info = {user: "y" for user in info.users_info} if isinstance(info.users_info,
                                                                                   (list, dict)) else {}
                self.etcd_client.ttl(ttl_id=ttl_id, ttl=720000)  # TTL set to 200 hours
                self.etcd_client.put(acl_prefix, json.dumps(users_info), lease=ttl_id)
        except Exception as err:
            logging.error(f"推送业务信息出错 {err}")


def check_user_list_md5():
    user_list_key = "check_user_list_md5"
    redis_conn = cache_conn()
    # users_dict = dict()
    with DBContext('r', None, True, **settings) as session:
        users = session.query(Users).all()
        users_dict = {user.id: {'email': user.email, 'user_status': user.status} for user in users}

        user_list_md5 = gen_md5(json.dumps(users_dict))
        old_user_list_md5 = redis_conn.get(user_list_key)
        if old_user_list_md5:
            old_user_list_md5 = convert(old_user_list_md5)
        if old_user_list_md5 == user_list_md5:
            return False
        else:
            redis_conn.set(user_list_key, user_list_md5, ex=8640)  # todo 259200
            return True


def check_user_func_list_md5():
    user_role_key = "check_user_role_key_md5"
    func_role_key = "check_func_role_key_md5"
    redis_conn = cache_conn()
    with DBContext('r', None, True, **settings) as session:
        users_role = session.query(UserRoles).all()
        funcs_role = session.query(RoleFunctions).all()

        users_dict = {u.id: {'role': u.role_id, 'user': u.user_id} for u in users_role}
        funcs_dict = {f.id: {'role': f.role_id, 'func': f.func_id} for f in funcs_role}

        combined_dict = {'users': users_dict, 'funcs': funcs_dict}
        combined_md5 = gen_md5(json.dumps(combined_dict))

        old_combined_md5 = redis_conn.get(user_role_key)
        if old_combined_md5:
            old_combined_md5 = convert(old_combined_md5)

        if old_combined_md5 == combined_md5:
            return False
        else:
            redis_conn.set(func_role_key, combined_md5, ex=8640)  # 259200 秒 = 3 天
            return True


def get_all_user():
    def md5hex(sign):
        md5 = hashlib.md5()  # 创建md5加密对象
        md5.update(sign.encode('utf-8'))  # 指定需要加密的字符串
        str_md5 = md5.hexdigest()  # 加密后的字符串
        return str_md5

    uc_conf = settings.get('uc_conf')

    now = int(time.time())
    params = {
        "app_id": "devops",
        "sign": md5hex(uc_conf['app_id'] + str(now) + uc_conf['app_secret']),
        "token": uc_conf['token'],
        "timestamp": now
    }
    url = uc_conf['endpoint'] + "/api/all-users-4-outer"
    response = requests.get(url=url, params=params)
    res = response.json()
    # logging.info(res.get('message'))
    return res.get('data')


def sync_user_from_uc():
    @deco1(RedisLock("async_all_user_redis_lock_key"))
    def index():
        logging.info(f'开始同步用户中心数据 {datetime.datetime.now()}')
        with DBContext('w', None, True, **settings) as session:
            user_id_list = []
            for user in get_all_user():
                user_id = str(user.get('uid'))
                user_id_list.append(user_id)
                username = user.get('english_name')
                if not user.get('position'):
                    try:
                        session.query(Users).filter(Users.id == user_id).delete(synchronize_session=False)
                        session.commit()
                    except Exception as err:
                        print('del', err)
                    continue
                # if username.startswith('wb-'): continue

                try:
                    session.add(insert_or_update(Users,
                                                 # f"username='{user_name}' and source_account_id='{user_id}' and nickname='{user.get('name')}'",
                                                 f"source_account_id='{user_id}'",
                                                 source_account_id=user_id, fs_id=user.get('feishu_userid'),
                                                 nickname=user.get('name'), manager=user.get('manager', ''),
                                                 department=user.get('position'), email=user.get('email'),
                                                 source="ucenter", tel=user.get('mobile'), status='0',
                                                 avatar=user.get('avatar'), username=user.get('english_name')))
                except Exception as err:
                    logging.error(f'同步用户中心数据 出错 {err}')

            session.query(Users).filter(Users.source == "ucenter", Users.status != "20",
                                        Users.source_account_id.notin_(user_id_list)).update(
                {"status": "20"}, synchronize_session=False)
        logging.info('开始同步用户中心数据 结束')

    index()


def sync_user_to_gw():
    """
    本数据提供给网关，用来和其他系统做SSO
    """

    @deco1(RedisLock("async_all_user_to_gw_redis_lock_key"))
    def index():
        logging.info(f'同步用户信息到网关ETCD 开始检查！')
        etcd_dict = settings.get('etcds').get(const.DEFAULT_ETCD_KEY)
        etcd_client = Etcd3Client(host=etcd_dict.get(const.DEFAULT_ETCD_HOST),
                                  port=etcd_dict.get(const.DEFAULT_ETCD_PORT))
        redis_conn = cache_conn()
        users_dict = {}
        etcd_prefix = settings.get('etcd_prefix', '/')
        user_list_prefix = f"{etcd_prefix}uc/userinfo/"
        user_list_key = "user_list_md5_for_sync_user_to_gw"
        with DBContext('r', None, True, **settings) as session:
            for user in session.query(Users).all():
                # users_dict[user.id] = dict(email=user.email, uid=user.source_account_id)
                uid = user.source_account_id
                users_dict[uid] = dict(email=user.email, uid=uid, codo_user_id=user.id,
                                       codo_is_superuser=user.superuser)
            user_list_md5 = gen_md5(json.dumps(users_dict))
            old_user_list_md5 = redis_conn.get(user_list_key)
            if old_user_list_md5:
                old_user_list_md5 = convert(old_user_list_md5)
            if old_user_list_md5 == user_list_md5:
                return
            redis_conn.set(user_list_key, user_list_md5, ex=720000)

        ttl_id = now_timestamp()
        logging.info(f'同步用户信息到网关ETCD 开始 {ttl_id}')
        etcd_client.ttl(ttl_id=ttl_id, ttl=720000)
        for user in get_all_user():
            email = user.get('email')
            key = f"{user_list_prefix}{email}"
            uid = user.get('uid')
            user_dict = users_dict.get(str(uid))
            if isinstance(user_dict, dict):
                user['codo_user_id'] = user_dict.get('codo_user_id')
                user['codo_is_superuser'] = True if user_dict.get('codo_is_superuser') == '0' else False
            etcd_client.put(key, json.dumps(user), lease=ttl_id)
        logging.info('同步用户信息到网关ETCD 结束！')

    try:
        index()
    except Exception as err:
        logging.error(f"同步用户信息到网关ETCD 出错：{err}")


@deco(RedisLock("async_role_users_redis_lock_key"))
def sync_all_user_list_for_role():
    get_all_user_list_for_role()


@deco2(RedisLock("async_archive_old_logs_lock_key"))
def archive_old_logs():
    try:
        from services.audit_service import archive_data
        archive_data()
    except Exception as err:
        logging.error(f"归档审计日志出错 {err}")


def async_api_permission_v4():
    # 启用线程去同步任务，防止阻塞
    obj = MyVerify()
    executor = ThreadPoolExecutor(max_workers=3)
    executor.submit(obj.sync_diff_api_permission)
    executor.submit(obj.sync_all_api_permission)
    executor.submit(sync_all_user_list_for_role)
    executor.submit(sync_user_to_gw)
    executor.submit(obj.sync_token_block_to_gw)
    executor.submit(obj.sync_biz_to_gw)


def async_archive_old_logs():
    executor = ThreadPoolExecutor(max_workers=1)
    executor.submit(archive_old_logs)


def async_user_center():
    # 启用线程去同步用户
    executor = ThreadPoolExecutor(max_workers=2)
    executor.submit(sync_user_from_uc)
