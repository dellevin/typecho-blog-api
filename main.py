from flask import Flask,render_template
from function.post_edit import api_bp
from function.category_edit import api_bp_category
from function.tags_edit import api_bp_tag
from function.link_db import get_db_connection

app = Flask(__name__)
app.register_blueprint(api_bp, url_prefix='/api/posts')
app.register_blueprint(api_bp_category, url_prefix='/api/categories')
app.register_blueprint(api_bp_tag, url_prefix='/api/tags')


# 根路径显示API文档
@app.route('/')
def api_documentation():
    """返回API文档页面"""
    return render_template('api_document.html')



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
