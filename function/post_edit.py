from flask import Flask, Blueprint, request, jsonify
import time
import logging
from function.link_db import get_db_connection
from function.verify_user import require_api_auth
import pymysql


# --- 初始化 ---
app = Flask(__name__)

# 创建一个蓝图
api_bp = Blueprint('api', __name__)
# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- API 路由 ---
@api_bp.route('/', methods=['POST'])
@require_api_auth
def create_post():
    """新增文章"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Invalid JSON data'}), 400

        title = data.get('title', '未命名文档')
        text = data.get('text', '')
        slug = data.get('slug', '')  # 可选
        # 简化处理，假设 category 是一个 ID 列表
        category_ids = data.get('category', [1])  # 默认分类ID为1，请根据实际情况修改
        tags_input = data.get('tags', '')  # 例如 "tag1,tag2"
        status = data.get('status', 'publish')  # 默认发布
        # 简化的用户ID，实际应根据API Key或其他方式确定
        author_id = data.get('author_id', 1)  # 请根据实际情况修改或通过API Key关联用户
        created = data.get('created', int(time.time()))  # Unix timestamp
        modified = int(time.time())
        password = data.get('password', '')  # 可选

        # 基本验证
        if not title or not text:
            return jsonify({'error': 'Title and text are required'}), 400

        with connection.cursor() as cursor:
            # 1. 插入文章到 contents 表
            sql_insert_post = """
                INSERT INTO typecho_contents (title, slug, created, modified, text, authorId, type, status, password, commentsNum, `order`, parent, allowComment, allowPing, allowFeed)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            # 注意字段顺序和默认值，根据你的数据库表结构调整
            post_values = (
                title, slug, created, modified, text, author_id, 'post', status, password,
                0, 0, 0, 1, 1, 1  # commentsNum, order, parent, allowComment, allowPing, allowFeed 默认值
            )
            cursor.execute(sql_insert_post, post_values)
            post_id = cursor.lastrowid

            if not post_id:
                connection.rollback()
                return jsonify({'error': 'Failed to create post'}), 500

            # 2. 处理分类 (relationships)
            if category_ids:
                for cat_id in category_ids:
                    # 检查分类是否存在 (简化处理，实际可能需要更严格的检查)
                    cursor.execute("SELECT mid FROM typecho_metas WHERE mid = %s AND type = 'category'", (cat_id,))
                    if cursor.fetchone():
                        sql_insert_relationship = """
                            INSERT INTO typecho_relationships (cid, mid) VALUES (%s, %s)
                        """
                        cursor.execute(sql_insert_relationship, (post_id, cat_id))
                        # 更新分类计数 (简化处理)
                        cursor.execute(
                            "UPDATE typecho_metas SET count = count + 1 WHERE mid = %s AND type = 'category'",
                            (cat_id,))

            # 3. 处理标签 (relationships & 更新计数)
            # 假设 tags_input 现在是一个包含标签 ID 的列表，例如 [39, 40]
            if tags_input and isinstance(tags_input, list):
                # 确保列表中的元素是整数
                tag_ids = [int(tag_id) for tag_id in tags_input if str(tag_id).strip().isdigit()]

                for tag_id in tag_ids:
                    # 可选：检查标签 ID 是否真实存在于 typecho_metas 表中且类型为 'tag'
                    # 这可以增加数据健壮性，防止关联到不存在的标签
                    cursor.execute("SELECT mid FROM typecho_metas WHERE mid = %s AND type = 'tag'", (tag_id,))
                    if cursor.fetchone():
                        # a. 插入标签关系到 typecho_relationships 表
                        sql_insert_tag_relationship = """
                            INSERT INTO typecho_relationships (cid, mid) VALUES (%s, %s)
                        """
                        cursor.execute(sql_insert_tag_relationship, (post_id, tag_id))

                        # b. 更新 typecho_metas 表中该标签的计数 (count + 1)
                        # 注意：这里使用反引号包围 `count`，因为它在某些 MySQL 模式下可能是关键字
                        cursor.execute(
                            "UPDATE typecho_metas SET `count` = `count` + 1 WHERE mid = %s AND type = 'tag'",
                            (tag_id,)
                        )
                    else:
                        # 可选：处理标签 ID 不存在的情况，例如记录警告或返回错误
                        logger.warning(f"Tag ID {tag_id} does not exist in typecho_metas table.")
                        # 如果严格要求所有标签ID必须存在，可以在这里返回错误
                        # return jsonify({'error': f'Tag ID {tag_id} not found'}), 400

            # 如果 tags_input 存在但不是列表，可以记录错误或忽略
            elif tags_input:
                 logger.warning(f"Invalid format for 'tags'. Expected a list of IDs, got: {type(tags_input)}. Skipping tag processing.")


        connection.commit()
        logger.info(f"Post created successfully with ID: {post_id}")
        return jsonify({'message': 'Post created successfully', 'post_id': post_id}), 201

    except Exception as e:
        connection.rollback()
        logger.error(f"Error creating post: {e}")
        return jsonify({'error': f'Failed to create post: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp.route('/<int:post_id>', methods=['DELETE'])
@require_api_auth
def delete_post(post_id):
    """删除文章"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        with connection.cursor() as cursor:
            # 1. 检查文章是否存在
            cursor.execute(
                "SELECT cid, status, type FROM typecho_contents WHERE cid = %s AND (type = 'post' OR type = 'post_draft')",
                (post_id,))
            post_result = cursor.fetchone()
            if not post_result:
                return jsonify({'error': 'Post not found'}), 404

            post_status = post_result['status']
            post_type = post_result['type']

            # 2. 删除文章主体 (contents)
            sql_delete_post = "DELETE FROM typecho_contents WHERE cid = %s"
            cursor.execute(sql_delete_post, (post_id,))

            # 3. 删除分类关系 (relationships) 并更新分类计数
            # 先获取关联的分类ID
            cursor.execute("SELECT mid FROM typecho_relationships WHERE cid = %s", (post_id,))
            related_categories = cursor.fetchall()
            for cat in related_categories:
                cat_id = cat['mid']
                cursor.execute("DELETE FROM typecho_relationships WHERE cid = %s AND mid = %s", (post_id, cat_id))
                if post_status == 'publish' and post_type == 'post':
                    cursor.execute("UPDATE typecho_metas SET count = count - 1 WHERE mid = %s AND type = 'category'",
                                   (cat_id,))

            # 4. 删除标签关系 (relationships) 并更新标签计数
            # 先获取关联的标签ID
            cursor.execute("SELECT mid FROM typecho_relationships WHERE cid = %s", (post_id,))
            related_tags = cursor.fetchall()  # 重新查询，因为分类关系可能已删除
            for tag in related_tags:
                tag_id = tag['mid']
                cursor.execute("DELETE FROM typecho_relationships WHERE cid = %s AND mid = %s", (post_id, tag_id))
                if post_status == 'publish' and post_type == 'post':
                    cursor.execute("UPDATE typecho_metas SET count = count - 1 WHERE mid = %s AND type = 'tag'",
                                   (tag_id,))

            # 5. 删除评论 (comments)
            sql_delete_comments = "DELETE FROM typecho_comments WHERE cid = %s"
            cursor.execute(sql_delete_comments, (post_id,))

            # 6. 解除附件关联 (contents - 假设附件类型为 'attachment')
            sql_unattach = "UPDATE typecho_contents SET parent = 0, status = 'publish' WHERE parent = %s AND type = 'attachment'"
            cursor.execute(sql_unattach, (post_id,))

            # 7. 删除自定义字段 (fields) - 如果存在
            try:
                sql_delete_fields = "DELETE FROM typecho_fields WHERE cid = %s"
                cursor.execute(sql_delete_fields, (post_id,))
            except pymysql.Error as e:
                # typecho_fields 表可能不存在，忽略错误或记录警告
                logger.warning(f"typecho_fields table might not exist or error deleting fields for post {post_id}: {e}")

            # 8. 删除草稿 (如果存在) - 根据 Edit.php 逻辑
            cursor.execute("SELECT cid AS draft_cid FROM typecho_contents WHERE parent = %s AND type = 'post_draft'",
                           (post_id,))
            draft_result = cursor.fetchone()
            if draft_result:
                draft_cid = draft_result['draft_cid']
                # 递归调用自身删除草稿？或者在这里直接处理草稿的删除逻辑
                # 这里简化处理，直接删除草稿相关数据
                cursor.execute("DELETE FROM typecho_contents WHERE cid = %s", (draft_cid,))
                cursor.execute("DELETE FROM typecho_relationships WHERE cid = %s", (draft_cid,))
                # 删除草稿字段等...
                try:
                    cursor.execute("DELETE FROM typecho_fields WHERE cid = %s", (draft_cid,))
                except pymysql.Error as e:
                    logger.warning(f"Error deleting draft fields for draft {draft_cid}: {e}")

        connection.commit()
        logger.info(f"Post deleted successfully with ID: {post_id}")
        # 清理孤立标签的逻辑可以在这里添加 (参考 Metas::alloc()->clearTags();)
        # 为简化，此处省略
        return jsonify({'message': 'Post deleted successfully'}), 200

    except Exception as e:
        connection.rollback()
        logger.error(f"Error deleting post {post_id}: {e}")
        return jsonify({'error': f'Failed to delete post: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp.route('/', methods=['GET'])
@require_api_auth
def get_posts():
    """查看文章列表 (简化版，可分页)"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        # 获取查询参数
        page = request.args.get('page', 1, type=int)
        per_page = min(request.args.get('per_page', 10, type=int), 100)  # 限制最大每页数量
        offset = (page - 1) * per_page

        with connection.cursor() as cursor:
            # 查询文章列表 (只获取基本字段)
            sql_select_posts = """
                SELECT cid, title, slug, created, modified, authorId, status
                FROM typecho_contents
                WHERE type = 'post'
                ORDER BY created DESC
                LIMIT %s OFFSET %s
            """
            cursor.execute(sql_select_posts, (per_page, offset))
            posts = cursor.fetchall()

            # 获取总数用于分页信息
            cursor.execute("SELECT COUNT(*) as total FROM typecho_contents WHERE type = 'post'")
            total_result = cursor.fetchone()
            total = total_result['total'] if total_result else 0

        logger.info(f"Fetched {len(posts)} posts (page {page})")
        return jsonify({
            'posts': posts,
            'pagination': {
                'page': page,
                'per_page': per_page,
                'total': total,
                'pages': (total + per_page - 1) // per_page  # 计算总页数
            }
        }), 200

    except Exception as e:
        logger.error(f"Error fetching posts: {e}")
        return jsonify({'error': f'Failed to fetch posts: {str(e)}'}), 500
    finally:
        connection.close()


@api_bp.route('/<int:post_id>', methods=['GET'])
@require_api_auth
def get_post(post_id):
    """查看单篇文章详情"""
    connection = get_db_connection()
    if not connection:
        return jsonify({'error': 'Database connection failed'}), 500

    try:
        with connection.cursor() as cursor:
            # 查询文章主体
            sql_select_post = """
                SELECT *
                FROM typecho_contents
                WHERE cid = %s AND type = 'post'
            """
            cursor.execute(sql_select_post, (post_id,))
            post = cursor.fetchone()

            if not post:
                return jsonify({'error': 'Post not found'}), 404

            # 查询分类 (可选)
            cursor.execute("""
                SELECT m.*
                FROM typecho_metas m
                JOIN typecho_relationships r ON m.mid = r.mid
                WHERE r.cid = %s AND m.type = 'category'
            """, (post_id,))
            categories = cursor.fetchall()

            # 查询标签 (可选)
            cursor.execute("""
                SELECT m.*
                FROM typecho_metas m
                JOIN typecho_relationships r ON m.mid = r.mid
                WHERE r.cid = %s AND m.type = 'tag'
            """, (post_id,))
            tags = cursor.fetchall()

        post['categories'] = categories
        post['tags'] = tags
        logger.info(f"Fetched post details for ID: {post_id}")
        return jsonify(post), 200

    except Exception as e:
        logger.error(f"Error fetching post {post_id}: {e}")
        return jsonify({'error': f'Failed to fetch post: {str(e)}'}), 500
    finally:
        connection.close()
