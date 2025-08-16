import pymysql
import pymysql.cursors
import logging

# --- 配置 ---
DB_CONFIG = {
    'host': '152.136.153.72',
    'user': 'root',
    'password': 'zhaoyang0902',
    'database': 'typecho',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# --- 数据库连接辅助函数 ---
def get_db_connection():
    """获取数据库连接"""
    try:
        connection = pymysql.connect(**DB_CONFIG)
        return connection
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return None
