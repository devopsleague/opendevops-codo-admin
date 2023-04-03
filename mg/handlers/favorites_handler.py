#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Contact : 191715030@qq.com
Author  : shenshuo
Date    : 2018/11/2
Desc    : 用户收藏
"""

import json
from libs.base_handler import BaseHandler
from models.admin_schemas import get_favorites_list, up_favorites, add_favorites, del_favorites


class FavoritesHandler(BaseHandler):
    def get(self, *args, **kwargs):
        key = self.get_argument('key', default=None, strip=True)  ### 索引
        if not key: return self.write(dict(code=-1, msg="缺少关键字"))

        self.params['nickname'] = self.request_nickname
        count, queryset = get_favorites_list(**self.params)

        return self.write(dict(code=0, result=True, msg="获取成功", data=queryset))

    def post(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        data['nickname'] = self.request_nickname
        res = add_favorites(data)
        self.write(res)

    def patch(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))
        data['nickname'] = self.request_nickname
        res = up_favorites(data)
        self.write(res)

    def delete(self, *args, **kwargs):
        data = json.loads(self.request.body.decode("utf-8"))

        res = del_favorites(data)
        self.write(res)


favorites_urls = [
    (r"/v1/accounts/favorites/", FavoritesHandler, {"handle_name": "PAAS-公用收藏接口"}),

]

if __name__ == "__main__":
    pass
