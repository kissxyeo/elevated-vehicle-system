# -*- coding: utf-8 -*-
"""短信通知服务

当前为模拟发送模式：短信内容生成后写入数据库通知记录，控制台同步打印。
接入真实短信时：
  1. 在服务商（阿里云/腾讯云等）开通短信服务并申请签名、模板；
  2. 将 SMS_MODE 环境变量设为 provider，并在 send_violation_sms 中
     调用其 SDK/API 完成真实发送。
"""
import os

_TEMPLATE = ("【高架车辆智能识别系统】尊敬的%s用户：您的车辆%s于%s在高架路段"
             "被系统检测到违规行为（%s），请及时核实并处理。")


class SMSService:

    def __init__(self):
        self.mode = os.environ.get("SMS_MODE", "simulated")

    def send_violation_sms(self, phone, owner_name, plate, violation, time_str):
        """
        发送违规通知短信。

        :return: (是否发送成功, 状态描述, 短信内容)
        """
        content = _TEMPLATE % (owner_name, plate, time_str, violation)
        if self.mode == "simulated":
            # 模拟发送：不产生真实资费，仅记录与打印
            try:
                print("[SMS][simulated] -> %s | %s" % (phone, content))
            except Exception:
                pass
            return True, "已发送（模拟）", content
        # TODO: 在此接入真实短信服务商 API（阿里云/腾讯云 SMS），传入 phone 与 content 发送
        return False, "未配置短信服务商（请设置 SMS_MODE 并接入SDK）", content
