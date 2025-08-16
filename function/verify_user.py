# auth.py (或者直接放在你的 API 路由文件中)
from flask import request, jsonify
import logging
import base64
import hashlib

from function.link_db import get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# --- 身份验证 ---
def require_api_auth(f):
    """
    装饰器：检查请求头中的用户名和密码
    客户端应发送 Base64 编码的 'username:password' 在 'Authorization' 头中，
    格式类似于 Basic Auth: Authorization: Basic base64(username:password)
    或者使用自定义头: X-API-Auth: base64(username:password)
    """

    def decorated_function(*args, **kwargs):
        auth_header = request.headers.get('Authorization')
        custom_auth_header = request.headers.get('X-API-Auth')

        auth_string = None
        if auth_header and auth_header.startswith('Basic '):
            # 尝试从标准 Basic Auth 头解析
            encoded_credentials = auth_header.split(None, 1)[1]
            try:
                decoded_bytes = base64.b64decode(encoded_credentials)
                auth_string = decoded_bytes.decode('utf-8')
            except Exception as e:
                logger.warning(f"Failed to decode Authorization header: {e}")
        elif custom_auth_header:
            # 尝试从自定义头解析
            try:
                decoded_bytes = base64.b64decode(custom_auth_header)
                auth_string = decoded_bytes.decode('utf-8')
            except Exception as e:
                logger.warning(f"Failed to decode X-API-Auth header: {e}")

        if not auth_string or ':' not in auth_string:
            logger.warning("Missing or invalid authorization credentials")
            return jsonify({'error': 'Unauthorized: Missing or invalid credentials'}), 401

        try:
            username, password = auth_string.split(':', 1)
        except ValueError:
            logger.warning("Invalid authorization format")
            return jsonify({'error': 'Unauthorized: Invalid credentials format'}), 401

        # --- 验证用户名和密码 ---
        if not authenticate_user(username, password):
            logger.warning(f"Authentication failed for user: {username}")
            return jsonify({'error': 'Unauthorized: Invalid username or password'}), 401

        # 验证成功，执行被装饰的函数
        return f(*args, **kwargs)

    decorated_function.__name__ = f.__name__  # 修复 Flask 装饰器问题
    return decorated_function


def authenticate_user(username, password):
    # if f'{username}:{password}' == "username:password":
    #     return True
    # else:
    #     return False

    """
    根据用户名和密码验证用户身份。
    密码在数据库中是以 MD5 哈希存储的。
    """
    connection = get_db_connection()
    if not connection:
        logger.error("Failed to connect to database for authentication")
        return False  # 数据库连接失败，拒绝访问

    try:
        with connection.cursor() as cursor:
            # 1. 查询用户及其 python_api_pwd
            # 注意：实际查询字段名请根据你的数据库表结构调整
            sql = "SELECT uid, name, python_api_pwd FROM typecho_users WHERE name = %s  LIMIT 1"
            cursor.execute(sql, (username,))
            user = cursor.fetchone()

            if not user:
                logger.info(f"User not found or not activated: {username}")
                return False  # 用户不存在或未激活

            stored_hashed_password = user.get('python_api_pwd')
            if not stored_hashed_password:
                logger.warning(f"User {username} has no python_api_pwd set")
                return False  # 用户没有设置 API 密码
            # print(username,password)
            # 2. 处理客户端传入的密码
            client_hashed_password = hashlib.md5(password.encode('utf-8')).hexdigest()
            # 3. 比对哈希值
            if client_hashed_password == stored_hashed_password:
                logger.info(f"Authentication successful for user: {username}")
                return True
            else:
                return False

    except Exception as e:
        logger.error(f"Error during authentication for user {username}: {e}")
        return False
    finally:
        connection.close()
