from flask import Blueprint, request, jsonify, current_app
import logging
import re # 用于 slug 验证
from function.link_db import get_db_connection
from function.verify_user import require_api_auth
import pymysql


# --- 初始化 ---
# 创建一个蓝图
api_bp_category = Blueprint('api_bp_category', __name__)
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

def category_exists(mid, connection):
    """检查分类是否存在"""
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT mid FROM typecho_metas WHERE type = 'category' AND mid = %s LIMIT 1",
                (mid,)
            )
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking category existence for mid {mid}: {e}")
        return False

def name_exists(name, connection, ignore_mid=None):
    """检查分类名称是否存在 (排除 ignore_mid)"""
    try:
        with connection.cursor() as cursor:
            sql = "SELECT mid FROM typecho_metas WHERE type = 'category' AND name = %s LIMIT 1"
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
    """检查分类 slug 是否存在 (排除 ignore_mid)"""
    try:
        with connection.cursor() as cursor:
            sql = "SELECT mid FROM typecho_metas WHERE type = 'category' AND slug = %s LIMIT 1"
            params = [slug]
            if ignore_mid:
                sql += " AND mid != %s"
                params.append(ignore_mid)
            cursor.execute(sql, params)
            return cursor.fetchone() is not None
    except Exception as e:
        logger.error(f"Error checking slug existence for '{slug}': {e}")
        return False

def get_max_order(parent_mid, connection):
    """获取指定父分类下的最大 order 值"""
    try:
        with connection.cursor() as cursor:
            sql = "SELECT MAX(`order`) AS max_order FROM typecho_metas WHERE type = 'category' AND parent = %s"
            cursor.execute(sql, (parent_mid,))
            result = cursor.fetchone()
            return result['max_order'] if result and result['max_order'] else 0
    except Exception as e:
        logger.error(f"Error getting max order for parent {parent_mid}: {e}")
        return 0 # 出错则返回 0


# --- API 路由 ---
@api_bp_category.route('', methods=['POST']) # /api/categories
@require_api_auth # 需要编辑者权限，这里用你的认证装饰器
def create_category():
    """增加分类"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        name = data.get('name', '').strip()
        slug = data.get('slug', '').strip()
        description = data.get('description', '')
        parent = data.get('parent', 0) # 默认为顶级分类

        # --- 验证 ---
        errors = []
        if not name:
            errors.append("分类名称不能为空")
        else:
            if name_exists(name, connection):
                 errors.append("分类名称已经存在")
            # 这里可以添加更多名称验证，如 XSS 检查（简化处理）

        if not slug:
            # 如果没有提供 slug，根据名称生成
            slug = slugify(name)
        # 验证 slug 格式 (简化)
        if not re.match(r'^[a-zA-Z0-9_-]+$', slug):
             errors.append("缩略名格式不正确，请使用字母、数字、下划线和横杠")
        else:
             if slug_exists(slug, connection):
                 errors.append("缩略名已经存在")

        # 验证父级分类 (如果提供了 parent)
        if parent:
            try:
                parent = int(parent)
                if parent < 0:
                     errors.append("父级分类 ID 无效")
                elif parent > 0 and not category_exists(parent, connection):
                     errors.append("指定的父级分类不存在")
            except (ValueError, TypeError):
                 errors.append("父级分类 ID 必须是整数")

        if errors:
            return jsonify({'error': '; '.join(errors)}), 400

        # --- 插入数据 ---
        with connection.cursor() as cursor:
            # 计算新分类的 order (在其父级下排序)
            new_order = get_max_order(parent, connection) + 1

            sql_insert = """
                INSERT INTO typecho_metas (name, slug, type, description, `order`, parent, count)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """
            # 注意 `order` 字段加了反引号
            values = (name, slug, 'category', description, new_order, parent, 0)
            cursor.execute(sql_insert, values)
            new_mid = cursor.lastrowid

            if not new_mid:
                connection.rollback()
                return jsonify({'error': 'Failed to create category'}), 500

        connection.commit()
        logger.info(f"Category created successfully with ID: {new_mid}")
        # 返回创建成功的分类信息
        return jsonify({
            'message': '分类创建成功',
            'category': {
                'mid': new_mid,
                'name': name,
                'slug': slug,
                'description': description,
                'parent': parent,
                'order': new_order
            }
        }), 201

    except Exception as e:
        connection.rollback()
        logger.error(f"Error creating category: {e}")
        return jsonify({'error': f'Failed to create category: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp_category.route('/<int:mid>', methods=['PUT']) # /api/categories/<mid>
@require_api_auth
def update_category(mid):
    """更新分类"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    if not category_exists(mid, connection):
        return jsonify({'error': '分类不存在'}), 404

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        name = data.get('name', '').strip()
        slug = data.get('slug', '').strip()
        description = data.get('description', '')
        parent = data.get('parent', None) # None 表示不更新 parent

        # --- 验证 ---
        errors = []
        if not name:
            errors.append("分类名称不能为空")
        else:
            if name_exists(name, connection, ignore_mid=mid):
                 errors.append("分类名称已经存在")

        if slug: # 只有在提供了 slug 时才验证
            # 验证 slug 格式 (简化)
            if not re.match(r'^[a-zA-Z0-9_-]+$', slug):
                 errors.append("缩略名格式不正确，请使用字母、数字、下划线和横杠")
            else:
                 if slug_exists(slug, connection, ignore_mid=mid):
                     errors.append("缩略名已经存在")
        else:
            # 如果没有提供 slug，根据名称生成 (可选，或保持原样)
            # 这里选择保持原样，除非明确提供
            pass

        # 验证父级分类 (如果提供了 parent)
        if parent is not None: # 区分 0 (顶级) 和 None (不更新)
            try:
                parent = int(parent)
                if parent < 0:
                     errors.append("父级分类 ID 无效")
                elif parent > 0 and not category_exists(parent, connection):
                     errors.append("指定的父级分类不存在")
                # TODO: 防止将分类设为自己的子分类或后代分类 (循环检查) - 较复杂，此处省略
            except (ValueError, TypeError):
                 errors.append("父级分类 ID 必须是整数")

        if errors:
            return jsonify({'error': '; '.join(errors)}), 400

        # --- 更新数据 ---
        with connection.cursor() as cursor:
            # 获取当前分类信息
            cursor.execute("SELECT `order`, parent FROM typecho_metas WHERE mid = %s AND type = 'category'", (mid,))
            current_category = cursor.fetchone()
            if not current_category:
                return jsonify({'error': '分类不存在'}), 404 # 再次确认

            current_order = current_category['order']
            current_parent = current_category['parent']

            # 准备更新字段
            update_fields = []
            update_params = []
            if name:
                update_fields.append("name = %s")
                update_params.append(name)
            if slug:
                update_fields.append("slug = %s")
                update_params.append(slug)
            if description is not None: # 允许更新为空字符串
                update_fields.append("description = %s")
                update_params.append(description)
            if parent is not None:
                update_fields.append("parent = %s")
                update_params.append(parent)
                # 如果 parent 改变了，需要更新 order
                if parent != current_parent:
                     new_order = get_max_order(parent, connection) + 1
                     update_fields.append("`order` = %s")
                     update_params.append(new_order)
                     # 注意：原 PHP 代码在 parent 改变时有更复杂的 order 交换逻辑，
                     # 这里简化为直接设置为新父级下的最大 order + 1


            if not update_fields:
                return jsonify({'message': '没有需要更新的字段'}), 200

            sql_update = f"UPDATE typecho_metas SET {', '.join(update_fields)} WHERE mid = %s AND type = 'category'"
            update_params.append(mid)

            cursor.execute(sql_update, update_params)

        connection.commit()
        logger.info(f"Category updated successfully with ID: {mid}")
        return jsonify({'message': '分类更新成功'}), 200

    except Exception as e:
        connection.rollback()
        logger.error(f"Error updating category {mid}: {e}")
        return jsonify({'error': f'Failed to update category: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp_category.route('/<int:mid>', methods=['DELETE']) # /api/categories/<mid>
@require_api_auth
def delete_category(mid):
    """删除分类"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    if not category_exists(mid, connection):
        return jsonify({'error': '分类不存在'}), 404

    try:
        with connection.cursor() as cursor:
            # 获取被删除分类的 parent (用于后续更新子分类)
            cursor.execute("SELECT parent FROM typecho_metas WHERE mid = %s AND type = 'category'", (mid,))
            deleted_category = cursor.fetchone()
            if not deleted_category:
                 return jsonify({'error': '分类不存在'}), 404
            deleted_parent = deleted_category['parent']

            # 1. 删除分类本身
            sql_delete_category = "DELETE FROM typecho_metas WHERE mid = %s AND type = 'category'"
            cursor.execute(sql_delete_category, (mid,))

            # 2. 删除与该分类关联的关系 (文章关联)
            sql_delete_relationships = "DELETE FROM typecho_relationships WHERE mid = %s"
            cursor.execute(sql_delete_relationships, (mid,))

            # 3. 将原本父级是该分类的子分类，提升到该分类的父级 (模仿 PHP 逻辑)
            sql_update_children = "UPDATE typecho_metas SET parent = %s WHERE parent = %s AND type = 'category'"
            cursor.execute(sql_update_children, (deleted_parent, mid))

            # 注意：原 PHP 代码在删除后没有更新受影响分类的 `order` 字段。
            # 如果需要严格的顺序维护，这里需要添加复杂的 order 重排逻辑。

        connection.commit()
        logger.info(f"Category deleted successfully with ID: {mid}")
        return jsonify({'message': '分类删除成功'}), 200

    except Exception as e:
        connection.rollback()
        logger.error(f"Error deleting category {mid}: {e}")
        return jsonify({'error': f'Failed to delete category: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp_category.route('', methods=['GET']) # /api/categories
# @require_api_auth
def get_categories():
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        # 可以添加查询参数，例如是否获取树形结构、分页等
        # flat = request.args.get('flat', 'true').lower() in ('true', '1', 'yes') # 默认扁平
        # page = request.args.get('page', 1, type=int)
        # per_page = request.args.get('per_page', 50, type=int)

        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            # 获取所有分类，按 order 排序
            sql_select = """
                SELECT mid, name, slug, type, description, `order`, parent, count
                FROM typecho_metas
                WHERE type = 'category'
                ORDER BY parent ASC, `order` ASC
            """ # 先按 parent 排序，再按 order 排序，有助于构建树
            cursor.execute(sql_select)
            categories = cursor.fetchall()

        logger.info(f"Fetched {len(categories)} categories")
        # 返回扁平列表
        return jsonify({'categories': categories}), 200

    except Exception as e:
        logger.error(f"Error fetching categories: {e}")
        return jsonify({'error': f'Failed to fetch categories: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp_category.route('/<int:mid>', methods=['GET']) # /api/categories/<mid>
# @require_api_auth
def get_category(mid):
    """获取单个分类详情"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            sql_select = """
                SELECT mid, name, slug, type, description, `order`, parent, count
                FROM typecho_metas
                WHERE type = 'category' AND mid = %s
                LIMIT 1
            """
            cursor.execute(sql_select, (mid,))
            category = cursor.fetchone()

            if not category:
                return jsonify({'error': '分类不存在'}), 404

        logger.info(f"Fetched category details for ID: {mid}")
        return jsonify(category), 200

    except Exception as e:
        logger.error(f"Error fetching category {mid}: {e}")
        return jsonify({'error': f'Failed to fetch category: {str(e)}'}), 500
    finally:
        connection.close()

