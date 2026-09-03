'''
用途: 
Date: 2026-09-02 14:56:46
LastEditTime: 2026-09-02 14:56:54
说明: 
'''
import requests
import json


class QyWechatWebhook:
    def __init__(self, webhook_key: str):
        """
        初始化企业微信webhook
        :param webhook_key: webhook的key值
        """
        self.webhook_url = f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={webhook_key}"
        self.headers = {"Content-Type": "application/json"}

    def send_text(self, content: str, mentioned_list=None, mentioned_mobile_list=None):
        """
        发送文本消息
        :param content: 消息内容
        :param mentioned_list: @成员列表，["user1","user2"]，@所有人填 ["@all"]
        :param mentioned_mobile_list: @手机号列表
        :return: 响应字典
        """
        payload = {
            "msgtype": "text",
            "text": {
                "content": content,
                "mentioned_list": mentioned_list if mentioned_list else [],
                "mentioned_mobile_list": mentioned_mobile_list if mentioned_mobile_list else []
            }
        }
        resp = requests.post(self.webhook_url, data=json.dumps(payload), headers=self.headers, timeout=10)
        return resp.json()

    def send_markdown(self, content: str):
        """
        发送markdown消息，企业微信markdown支持语法有限
        """
        payload = {
            "msgtype": "markdown",
            "markdown": {
                "content": content
            }
        }
        resp = requests.post(self.webhook_url, data=json.dumps(payload), headers=self.headers, timeout=10)
        return resp.json()


if __name__ == "__main__":
    # 这里替换为你的真实key
    KEY = ""
    qy_msg = QyWechatWebhook(KEY)

    # 1.发送普通文本
    res1 = qy_msg.send_text("这是一条来自Python程序的企业微信测试通知")
    print("文本消息返回：", res1)

    # 2.发送@所有人文本通知
    # res2 = qy_msg.send_text("告警通知！请注意查看", mentioned_list=["@all"])
    # print(res2)

    # 3.发送markdown格式消息
    markdown_text = """### 程序告警通知
> 状态：<font color="info">正常</font>
- 服务名称：测试服务
- 触发时间：2026‑09‑02
"""
    res3 = qy_msg.send_markdown(markdown_text)
    print("markdown消息返回：", res3)
