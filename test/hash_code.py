import hashlib
import base64
# base64编码
original_string = "DelLevin:zhaoyang0902"
print("base64编码:", base64.b64encode(original_string.encode('utf-8')))
password = 'zhaoyang0902'
# 加密密码
print('MD5加密：', hashlib.md5(password.encode('utf-8')).hexdigest())