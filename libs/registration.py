#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Version : 0.0.1
Contact : 191715030@qq.com
Author  : shenshuo
Date    : 2021/11/1 17:07
Desc    : 注册各种信息到pass平台
"""

import json
from websdk2.client import AcsClient
from websdk2.configs import configs
from settings import settings

if configs.can_import: configs.import_dict(**settings)
client = AcsClient()

uri = "/api/mg/v3/accounts/authority/register/"

menu_list = [
    {
        "name": "MGauthoritycenter",
        "details": "权限中心"
    }, {
        "name": "MGuserlist",
        "details": "用户列表"
    }, {
        "name": "MGtokenlist",
        "details": "令牌列表"
    }, {
        "name": "MGapplist",
        "details": "应用列表"
    },{
        "name": "MGbusiness",
        "details": "业务列表"
    },{
        "name": "MGmenus",
        "details": "菜单列表"
    }, {
        "name": "MGcomponents",
        "details": "前端组件"
    }, {
        "name": "MGfunctions",
        "details": "权限列表"
    }, {
        "name": "MGrole",
        "details": "角色管理"
    }, {
        "name": "MGappfuncs",
        "details": "应用权限"
    },
    {
        "name": "MGappmenus",
        "details": "应用菜单"
    },
    {
        "name": "MGappcomponents",
        "details": "应用组件"
    },
    {
        "name": "noticeCenter",
        "details": "通知中心"
    },
    {
        "name": "noticeTemplate",
        "details": "通知模板"
    },
    {
        "name": "noticeGroup",
        "details": "通知组"
    },
    {
        "name": "noticeConf",
        "details": "通知配置"
    },
]
component_list = [
    {
        "name": "reset_password_btn",
        "details": "权限中心-用户列表-重置密码"
    }, {
        "name": "reset_mfa_btn",
        "details": "权限中心-用户列表-重置二次认证"
    }, {
        "name": "get_token_btn",
        "details": "权限中心 用户列表 获取令牌"
    }, {
        "name": "edit_user_btn",
        "details": "权限中心 用户列表 编辑用户"
    }, {
        "name": "del_user_btn",
        "details": "权限中心 用户列表 删除用户"
    }, {
        "name": "new_user_btn",
        "details": "权限中心 用户列表 添加用户"
    }, {
        "name": "edit_token_a",
        "details": "权限中心-编辑令牌备注"
    }, {
        "name": "del_token_a",
        "details": "权限中心-删除令牌"
    },{
        "name": "edit_app_btn",
        "details": "权限中心 应用列表 编辑按钮"
    }, {
        "name": "del_app_btn",
        "details": "权限中心 应用列表 删除按钮"
    }, {
        "name": "new_app_btn",
        "details": "权限中心 应用列表 添加按钮"
    }, {
        "name": "new_func_btn",
        "details": "权限中心 权限列表 添加权限按钮"
    }, {
        "name": "edit_fun_a",
        "details": "权限中心 权限列表 编辑A标签"
    }, {
        "name": "del_fun_a",
        "details": "权限中心 权限列表 删除A标签"
    }, {
        "name": "new_menu_btn",
        "details": "权限中心 前端菜单列表 添加菜单按钮"
    }, {
        "name": "edit_menu_a",
        "details": "权限中心 前端菜单列表 编辑A标签"
    }, {
        "name": "del_menu_a",
        "details": "权限中心 前端菜单列表 删除A标签"
    }, {
        "name": "new_component_btn",
        "details": "权限中心 前端组件列表 添加组件按钮"
    }, {
        "name": "edit_component_a",
        "details": "权限中心 前端组件列表 编辑A标签"
    }, {
        "name": "del_component_a",
        "details": "权限中心 前端组件列表 删除A标签"
    }, {
        "name": "new_role_btn",
        "details": "权限中心 角色列表 添加角色按钮"
    }, {
        "name": "edit_role_btn",
        "details": "权限中心 角色列表 编辑角色按钮"
    }, {
        "name": "del_role_btn",
        "details": "权限中心 角色列表 删除角色按钮"
    }, {
        "name": "edit_role_user_btn",
        "details": "权限中心 角色列表 编辑角色-用户 按钮"
    }, {
        "name": "edit_role_app_btn",
        "details": "权限中心 角色列表 编辑角色-应用 按钮"
    }, {
        "name": "edit_role_func_btn",
        "details": "权限中心 角色列表 编辑角色-权限 按钮"
    }, {
        "name": "edit_role_menu_btn",
        "details": "权限中心 角色列表 编辑角色-菜单 按钮"
    }, {
        "name": "edit_role_component_btn",
        "details": "权限中心 角色列表 编辑角色-组件 按钮"
    }, {
        "name": "new_notice_template_btn",
        "details": "通知中心-添加通知模板"
    }, {
        "name": "edit_notice_template_btn",
        "details": "通知中心-编辑通知模板"
    }, {
        "name": "test_notice_template_btn",
        "details": "通知中心-通知模板测试"
    }, {
        "name": "del_notice_template_btn",
        "details": "通知中心-通知模板测试按钮"
    }, {
        "name": "new_notice_group_btn",
        "details": "通知中心-添加通知组按钮"
    }, {
        "name": "edit_notice_group_btn",
        "details": "通知中心-编辑通知组按钮"
    }, {
        "name": "del_notice_group_btn",
        "details": "通知中心-删除通知组按钮"
    }, {
        "name": "new_notice_config_btn",
        "details": "通知中心-添加通知配置按钮"
    }, {
        "name": "edit_notice_config_btn",
        "details": "通知中心-编辑通知配置按钮"
    }, {
        "name": "del_notice_config_btn",
        "details": "通知中心-删除通知配置按钮"
    }
]
func_list = []
role_list = []

method_dict = dict(
    ALL="管理",
    GET="只读",
    # POST="添加",
    # PATCH="修改",
    # DELETE="删除"
)


def registration_to_paas():
    app_code = "mg"
    api_info_url = f"/api/{app_code}/v1/probe/meta/urls/"
    func_info = client.do_action_v2(**dict(
        method='GET',
        url=api_info_url,
    ))
    if func_info.status_code == 200:
        temp_func_list = func_info.json().get('data')
        func_list.append(dict(method_type='ALL', name=f"{app_code}-管理员", uri=f"/api/{app_code}/*"))
        func_list.append(dict(method_type='GET', name=f"{app_code}-查看所有", uri=f"/api/{app_code}/*"))
        for f in temp_func_list:
            if 'name' not in f or f.get('name') == '暂无': continue
            for m, v in method_dict.items():
                func = dict(method_type=m, name=f"{v}-{f['name']}", uri=f"/api/{app_code}{f.get('url')}")
                if f.get('status') == 'y':  func['status'] = '0'
                func_list.append(func)
    body = {
        "app_code": app_code,
        "menu_list": menu_list,
        "component_list": component_list,
        "func_list": func_list,
        "role_list": role_list
    }
    registration_data = dict(method='POST',
                             url=uri,
                             body=json.dumps(body),
                             description='自动注册')
    response = client.do_action(**registration_data)
    print(json.loads(response))
    return response


class Registration:
    def __init__(self, **kwargs):
        pass

    def start_server(self):
        registration_to_paas()
        raise Exception('初始化完成')
