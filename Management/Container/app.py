from datetime import datetime
from pathlib import Path
import sys

from flask import Flask, jsonify, redirect, request, send_from_directory, session, url_for
from sqlalchemy import text

MANAGEMENT_DIR = Path(__file__).resolve().parents[1]
if str(MANAGEMENT_DIR) not in sys.path:
    sys.path.insert(0, str(MANAGEMENT_DIR))

from config import Config
from Container.models.container_model import Container, Ship, Task, User, Yard, db
from routes.container_route import container_bp
from routes.ship_route import ship_bp
from routes.task_route import task_bp
from routes.yard_route import yard_bp


STATUS_SCHEDULED = '\u8ba1\u5212\u4e2d'
STATUS_BERTHED = '\u5df2\u9760\u6cca'
STATUS_DEPARTED = '\u5df2\u79bb\u6e2f'


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(container_bp)
    app.register_blueprint(ship_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(yard_bp)

    def is_public_endpoint():
        endpoint = request.endpoint or ''
        public_endpoints = {
            'login_page',
            'login',
            'legacy_login',
            'current_user',
            'css',
            'js',
        }
        return endpoint in public_endpoints

    @app.before_request
    def require_login():
        if request.method == 'OPTIONS' or is_public_endpoint():
            return None
        if request.path.startswith('/api/auth/login') or request.path.startswith('/api/user/login'):
            return None
        if session.get('user_id'):
            return None
        if (
            request.path.startswith('/containers') or
            request.path.startswith('/yards') or
            request.path.startswith('/ships') or
            request.path.startswith('/tasks') or
            request.path.startswith('/api/dashboard')
        ):
            return jsonify({"message": "\u8bf7\u5148\u767b\u5f55"}), 401
        return redirect(url_for('login_page'))

    @app.after_request
    def add_cors_headers(response):
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
        return response

    @app.route('/', methods=['GET'])
    def root():
        if session.get('user_id'):
            return redirect('/index.html')
        return redirect('/login.html')

    @app.route('/login.html', methods=['GET'])
    def login_page():
        html_dir = Path(__file__).resolve().parents[2]
        response = send_from_directory(html_dir, 'login.html')
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response

    @app.route('/index.html', methods=['GET'])
    def index():
        html_dir = Path(__file__).resolve().parents[2]
        response = send_from_directory(html_dir, 'index.html')
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response

    @app.route('/pages/<path:filename>', methods=['GET'])
    def pages(filename):
        pages_dir = Path(__file__).resolve().parents[2] / 'pages'
        response = send_from_directory(pages_dir, filename)
        response.headers['Content-Type'] = 'text/html; charset=utf-8'
        return response

    @app.route('/css/<path:filename>', methods=['GET'])
    def css(filename):
        css_dir = Path(__file__).resolve().parents[2] / 'css'
        return send_from_directory(css_dir, filename)

    @app.route('/js/<path:filename>', methods=['GET'])
    def js(filename):
        js_dir = Path(__file__).resolve().parents[2] / 'js'
        return send_from_directory(js_dir, filename)

    @app.route('/api/auth/login', methods=['POST'])
    def login():
        data = request.get_json(silent=True) or {}
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        if not username or not password:
            return jsonify({"message": "\u7528\u6237\u540d\u548c\u5bc6\u7801\u4e0d\u80fd\u4e3a\u7a7a"}), 400

        user = User.query.filter_by(username=username).first()
        if user is None or user.password != password:
            return jsonify({"message": "\u7528\u6237\u540d\u6216\u5bc6\u7801\u9519\u8bef"}), 401

        user.last_login_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.session.commit()
        session['user_id'] = user.id
        session['username'] = user.username
        session['role'] = user.role
        return jsonify({"message": "\u767b\u5f55\u6210\u529f", "data": user.to_safe_dict()})

    @app.route('/api/user/login', methods=['POST'])
    def legacy_login():
        return login()

    @app.route('/api/auth/me', methods=['GET'])
    def current_user():
        user_id = session.get('user_id')
        if not user_id:
            return jsonify({"message": "\u672a\u767b\u5f55"}), 401
        user = User.query.get(user_id)
        if user is None:
            session.clear()
            return jsonify({"message": "\u7528\u6237\u4e0d\u5b58\u5728"}), 401
        return jsonify({"data": user.to_safe_dict()})

    @app.route('/api/auth/logout', methods=['POST'])
    def logout():
        session.clear()
        return jsonify({"message": "\u5df2\u9000\u51fa\u767b\u5f55"})

    @app.route('/api/dashboard/stats', methods=['GET'])
    def dashboard_stats():
        containers = Container.query.all()
        yards = Yard.query.all()
        ships = Ship.query.all()
        tasks = Task.query.all()

        yard_total = sum(yard.total_capacity for yard in yards)
        yard_used = sum(yard.used_capacity() for yard in yards)
        task_counts = {
            "pending": sum(1 for task in tasks if task.status in ('pending', '\u672a\u5f00\u59cb')),
            "inProgress": sum(1 for task in tasks if task.status in ('in-progress', 'processing', '\u8fdb\u884c\u4e2d')),
            "completed": sum(1 for task in tasks if task.status in ('completed', '\u5df2\u5b8c\u6210')),
        }
        ship_counts = {
            "berthed": sum(1 for ship in ships if ship.status == STATUS_BERTHED),
            "scheduled": sum(1 for ship in ships if ship.status == STATUS_SCHEDULED),
            "departed": sum(1 for ship in ships if ship.status == STATUS_DEPARTED),
        }

        return jsonify({
            "kpis": {
                "containerTotal": len(containers),
                "yardTotalCapacity": yard_total,
                "yardUsedCapacity": yard_used,
                "yardUsageRate": round((yard_used / yard_total) * 100, 2) if yard_total else 0,
                "shipTotal": len(ships),
                "berthedShips": ship_counts["berthed"],
                "taskTotal": len(tasks),
                "runningTasks": task_counts["inProgress"],
                "alerts": sum(1 for yard in yards if yard.total_capacity and yard.used_capacity() / yard.total_capacity >= 0.8),
            },
            "taskStatus": task_counts,
            "shipStatus": ship_counts,
            "containerTypes": _count_by(containers, lambda item: item.container_type or '\u672a\u77e5'),
            "yardUsage": [
                {
                    "name": yard.yard_name,
                    "used": yard.used_capacity(),
                    "total": yard.total_capacity,
                    "usageRate": round((yard.used_capacity() / yard.total_capacity) * 100, 2) if yard.total_capacity else 0,
                }
                for yard in yards
            ],
        })

    with app.app_context():
        db.create_all()
        ensure_ship_schema()
        ensure_task_schema()
        seed_data()

    return app


def seed_data():
    if Yard.query.first() is None:
        db.session.add_all([
            Yard(yard_name='\u5806\u573aA', usage_type='\u8fdb\u53e3\u7bb1', code='Y-A'),
            Yard(yard_name='\u5806\u573aB', usage_type='\u51fa\u53e3\u7bb1', code='Y-B'),
            Yard(yard_name='\u5806\u573aC', usage_type='\u51b7\u85cf\u7bb1', code='Y-C'),
        ])
        db.session.commit()

    if Ship.query.first():
        for ship in Ship.query.filter((Ship.status == None) | (Ship.status == '')).all():
            ship.status = STATUS_BERTHED if ship.berth else STATUS_SCHEDULED
        db.session.commit()

    if Container.query.first() is None:
        test_data = [
            Container(
                container_no='MSCU1234567',
                container_type='20GP',
                is_full=True,
                yard='\u5806\u573aA',
                area='Zone-1',
                column=3,
                layer=2,
                status='\u5806\u573a\u5b58\u50a8',
            ),
            Container(
                container_no='CMAU9876543',
                container_type='40HQ',
                is_full=True,
                is_dangerous=True,
                yard='\u5806\u573aA',
                area='Zone-1',
                column=3,
                layer=1,
                status='\u5806\u573a\u5b58\u50a8',
            ),
            Container(
                container_no='OOLU4567890',
                container_type='20GP',
                yard='\u5806\u573aB',
                area='Zone-3',
                column=7,
                layer=1,
                status='\u7b49\u5f85\u63d0\u7bb1',
            ),
        ]
        db.session.add_all(test_data)
        db.session.commit()

    if Task.query.first() is None:
        first_container = Container.query.first()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.session.add(Task(
            task_no='TSK-SEED-001',
            task_type='\u96c6\u88c5\u7bb1\u5378\u8239\u5165\u5806',
            container_id=first_container.id if first_container else None,
            from_pos='\u6cca\u4f4d1',
            to_pos='\u5806\u573aA',
            status='pending',
            remark='Zone-1/3/2',
            created_at=now,
            updated_at=now,
        ))
        db.session.commit()


def ensure_ship_schema():
    try:
        columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(ship)")).fetchall()}
        if 'status' not in columns:
            db.session.execute(text("ALTER TABLE ship ADD COLUMN status TEXT DEFAULT '\u8ba1\u5212\u4e2d'"))
            db.session.commit()
    except Exception:
        db.session.rollback()


def ensure_task_schema():
    try:
        columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(task)")).fetchall()}
        if not columns:
            return
        if 'task_no' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN task_no TEXT"))
        if 'remark' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN remark TEXT"))
        if 'created_at' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN created_at TEXT"))
        if 'updated_at' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN updated_at TEXT"))
        if 'estimated_time' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN estimated_time INTEGER"))
        if 'actual_time' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN actual_time INTEGER"))
        if 'start_time' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN start_time TEXT"))
        if 'end_time' not in columns:
            db.session.execute(text("ALTER TABLE task ADD COLUMN end_time TEXT"))
        db.session.commit()
    except Exception:
        db.session.rollback()


def _count_by(items, key_fn):
    counts = {}
    for item in items:
        key = key_fn(item)
        counts[key] = counts.get(key, 0) + 1
    return [{"name": key, "value": value} for key, value in counts.items()]


app = create_app()


if __name__ == '__main__':
    app.run(debug=True)
