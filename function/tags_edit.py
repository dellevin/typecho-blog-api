# api_tag.py
from flask import Blueprint, request, jsonify, current_app
import logging
import re # 用于 slug 验证
from function.link_db import get_db_connection
from function.verify_user import require_api_auth # 假设这个装饰器检查 editor 权限

# --- 初始化 ---
# 创建一个蓝图
api_bp_tag = Blueprint('api_tag', __name__)
# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 辅助函数 ---

def slugify(name):
    """模仿 Common::slugName 的简单实现"""
    # 转小写，替换非字母数字和连字符的字符为空格，然后替换空格和下划线为连字符，最后清理多余的连字符
    slug = re.sub(r'[^\w\s-]', '', name.strip().lower())
    slug = re.sub(r'[-\s]+', '-', slug)
    return slug

def tag_exists(mid, connection):
    """检查标签是否存在"""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT mid FROM typecho_metas WHERE type = 'tag' AND mid = %s LIMIT 1",
                (mid,)
            )
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking tag existence for mid {mid}: {e}")
        return False

def name_exists(name, connection, ignore_mid=None):
    """检查标签名称是否存在 (排除 ignore_mid)"""
    try:
        with connection.cursor() as cursor:
            sql = "SELECT mid FROM typecho_metas WHERE type = 'tag' AND name = %s LIMIT 1"
            params = [name]
            if ignore_mid:
                sql += " AND mid != %s"
                params.append(ignore_mid)
            cursor.execute(sql, params)
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking name existence for '{name}': {e}")
        return False

def slug_exists(slug, connection, ignore_mid=None):
    """检查标签 slug 是否存在 (排除 ignore_mid)"""
    try:
        with connection.cursor() as cursor:
            sql = "SELECT mid FROM typecho_metas WHERE type = 'tag' AND slug = %s LIMIT 1"
            params = [slug]
            if ignore_mid:
                sql += " AND mid != %s"
                params.append(ignore_mid)
            cursor.execute(sql, params)
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking slug existence for '{slug}': {e}")
        return False

# --- API 路由 ---
@api_bp_tag.route('', methods=['POST']) # /api/tags
@require_api_auth # 需要编辑者权限
def create_tag():
    """增加标签"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        name = data.get('name', '').strip()
        slug = data.get('slug', '').strip()

        # --- 验证 ---
        errors = []
        if not name:
            errors.append("标签名称不能为空")
        else:
            if name_exists(name, connection):
                 errors.append("标签名称已经存在")
            # 这里可以添加更多名称验证，如 XSS 检查（简化处理）

        # 处理 slug
        if not slug:
            # 如果没有提供 slug，根据名称生成
            slug = slugify(name)
        # 验证 slug 格式 (简化)
        if not re.match(r'^[a-zA-Z0-9_-]+$', slug):
             errors.append("缩略名格式不正确，请使用字母、数字、下划线和横杠")
        else:
             if slug_exists(slug, connection):
                 errors.append("缩略名已经存在")

        if errors:
            return jsonify({'error': '; '.join(errors)}), 400

        # --- 插入数据 ---
        with connection.cursor() as cursor:
            sql_insert = """
                INSERT INTO typecho_metas (name, slug, type, description, `count`, `order`, parent)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            # 注意 `order` 字段加了反引号，description, count, order, parent 使用默认值
            values = (name, slug, 'tag', '', 0, 0, 0)
            cursor.execute(sql_insert, values)
            new_mid = cursor.lastrowid

            if not new_mid:
                connection.rollback()
                return jsonify({'error': 'Failed to create tag'}), 500

        connection.commit()
        logger.info(f"Tag created successfully with ID: {new_mid}")
        # 返回创建成功的标签信息
        return jsonify({
            'message': '标签创建成功',
            'tag': {
                'mid': new_mid,
                'name': name,
                'slug': slug
            }
        }), 201

    except Exception as e:
        connection.rollback()
        logger.error(f"Error creating tag: {e}")
        return jsonify({'error': f'Failed to create tag: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp_tag.route('/<int:mid>', methods=['PUT']) # /api/tags/<mid>
@require_api_auth # 需要编辑者权限
def update_tag(mid):
    """更新标签"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    if not tag_exists(mid, connection):
        return jsonify({'error': '标签不存在'}), 404

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        name = data.get('name', '').strip()
        slug = data.get('slug', '').strip()

        # --- 验证 ---
        errors = []
        if not name:
            errors.append("标签名称不能为空")
        else:
            if name_exists(name, connection, ignore_mid=mid):
                 errors.append("标签名称已经存在")

        # 处理 slug
        if slug: # 只有在提供了 slug 时才验证
            # 验证 slug 格式 (简化)
            if not re.match(r'^[a-zA-Z0-9_-]+$', slug):
                 errors.append("缩略名格式不正确，请使用字母、数字、下划线和横杠")
            else:
                 if slug_exists(slug, connection, ignore_mid=mid):
                     errors.append("缩略名已经存在")
        # 如果没有提供 slug，保持原样

        if errors:
            return jsonify({'error': '; '.join(errors)}), 400

        # --- 更新数据 ---
        with connection.cursor() as cursor:
             # 准备更新字段
            update_fields = []
            update_params = []
            if name:
                update_fields.append("name = %s")
                update_params.append(name)
            if slug:
                update_fields.append("slug = %s")
                update_params.append(slug)

            if not update_fields:
                return jsonify({'message': '没有需要更新的字段'}), 200

            sql_update = f"UPDATE typecho_metas SET {', '.join(update_fields)} WHERE mid = %s AND type = 'tag'"
            update_params.append(mid)

            cursor.execute(sql_update, update_params)

        connection.commit()
        logger.info(f"Tag updated successfully with ID: {mid}")
        return jsonify({'message': '标签更新成功'}), 200

    except Exception as e:
        connection.rollback()
        logger.error(f"Error updating tag {mid}: {e}")
        return jsonify({'error': f'Failed to update tag: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp_tag.route('/<int:mid>', methods=['DELETE']) # /api/tags/<mid>
@api_bp_tag.route('', methods=['DELETE']) # /api/tags (批量删除)
@require_api_auth # 需要编辑者权限
def delete_tag(mid=None):
    """删除标签 (单个或批量)"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        mids_to_delete = []
        if mid:
            # 删除单个标签
            if not tag_exists(mid, connection):
                return jsonify({'error': '标签不存在'}), 404
            mids_to_delete = [mid]
        else:
            # 批量删除 (从请求体获取)
            data = request.get_json()
            if not data or 'mids' not in data:
                return jsonify({'error': 'Missing mids in request body for batch delete'}), 400
            mids_input = data.get('mids', [])
            if not isinstance(mids_input, list):
                 return jsonify({'error': 'mids must be a list'}), 400
            # 验证并过滤有效的 MID
            for mid_item in mids_input:
                 try:
                     mid_int = int(mid_item)
                     if tag_exists(mid_int, connection): # 只删除存在的
                         mids_to_delete.append(mid_int)
                 except (ValueError, TypeError):
                     pass # 忽略无效 ID

            if not mids_to_delete:
                return jsonify({'error': 'No valid tags found to delete'}), 404

        delete_count = 0
        with connection.cursor() as cursor:
            for tag_mid in mids_to_delete:
                # 1. 删除标签本身
                sql_delete_tag = "DELETE FROM typecho_metas WHERE mid = %s AND type = 'tag'"
                cursor.execute(sql_delete_tag, (tag_mid,))

                # 2. 删除与该标签关联的关系 (文章关联)
                sql_delete_relationships = "DELETE FROM typecho_relationships WHERE mid = %s"
                cursor.execute(sql_delete_relationships, (tag_mid,))

                delete_count += 1

        connection.commit()
        message = f"成功删除 {delete_count} 个标签" if delete_count > 1 else "标签删除成功"
        logger.info(message)
        return jsonify({'message': message}), 200

    except Exception as e:
        connection.rollback()
        logger.error(f"Error deleting tags: {e}")
        return jsonify({'error': f'Failed to delete tags: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp_tag.route('', methods=['GET']) # /api/tags
# @require_api_auth # 获取列表通常可以公开或对较低权限开放，根据需求决定
def get_tags():
    """获取标签列表 (简化版，可分页)"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 50, type=int), 100) # 限制最大每页数量
        offset = (page - 1) * per_page

        with connection.cursor() as cursor:
            # 获取标签列表
            sql_select = """
                SELECT mid, name, slug, `count`
                FROM typecho_metas
                WHERE type = 'tag'
                ORDER BY mid DESC -- 或者按 count DESC, name ASC 等
                LIMIT %s OFFSET %s
            """
            cursor.execute(sql_select, (per_page, offset))
            tags = cursor.fetchall()

            # 获取总数用于分页信息
            cursor.execute("SELECT COUNT(*) as total FROM typecho_metas WHERE type = 'tag'")
            total_result = cursor.fetchone()
            total = total_result['total'] if total_result else 0

        logger.info(f"Fetched {len(tags)} tags (page {page})")
        return jsonify({
            'tags': tags,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page # 计算总页数
            }
        }), 200

    except Exception as e:
        logger.error(f"Error fetching tags: {e}")
        return jsonify({'error': f'Failed to fetch tags: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp_tag.route('/<int:mid>', methods=['GET']) # /api/tags/<mid>
# @require_api_auth # 获取单个通常可以公开或对较低权限开放
def get_tag(mid):
    """获取单个标签详情"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        with connection.cursor() as cursor:
            sql_select = """
                SELECT mid, name, slug, description, `count`, `order`, parent
                FROM typecho_metas
                WHERE type = 'tag' AND mid = %s
                LIMIT 1
            """
            cursor.execute(sql_select, (mid,))
            tag = cursor.fetchone()

            if not tag:
                return jsonify({'error': '标签不存在'}), 404

        logger.info(f"Fetched tag details for ID: {mid}")
        return jsonify(tag), 200

    except Exception as e:
        logger.error(f"Error fetching tag {mid}: {e}")
        return jsonify({'error': f'Failed to fetch tag: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp_tag.route('/refresh', methods=['POST']) # /api/tags/refresh
@require_api_auth # 需要编辑者权限
def refresh_tags():
    """刷新标签计数并清理孤立标签"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        with connection.cursor() as cursor:
            # 1. 更新所有 tag 的 count
            sql_refresh_count = """
                UPDATE typecho_metas m
                SET `count` = (
                    SELECT COUNT(*)
                    FROM typecho_relationships r
                    JOIN typecho_contents c ON r.cid = c.cid
                    WHERE r.mid = m.mid AND c.type = 'post' AND c.status = 'publish'
                )
                WHERE m.type = 'tag'
            """
            cursor.execute(sql_refresh_count)

            # 2. 删除 count 为 0 的标签 (模仿 clearTags)
            sql_delete_orphaned = "DELETE FROM typecho_metas WHERE type = 'tag' AND `count` = 0"
            cursor.execute(sql_delete_orphaned)
            deleted_orphaned_count = cursor.rowcount

        connection.commit()
        message = f"标签刷新完成，清理了 {deleted_orphaned_count} 个孤立标签"
        logger.info(message)
        return jsonify({'message': message}), 200

    except Exception as e:
        connection.rollback()
        logger.error(f"Error refreshing tags: {e}")
        return jsonify({'error': f'Failed to refresh tags: {str(e)}'}), 500
    finally:
        connection.close()
