from datetime import datetime
from pathlib import Path
import sys

from flask import Flask, jsonify, redirect, request, send_from_directory, session, url_for
from sqlalchemy import text

CONTAINER_DIR = Path(__file__).resolve().parent
MANAGEMENT_DIR = Path(__file__).resolve().parents[1]
for import_dir in (CONTAINER_DIR, MANAGEMENT_DIR):
    if str(import_dir) not in sys.path:
        sys.path.insert(0, str(import_dir))

from config import Config
from Container.models.container_model import BillingRecord, Container, Equipment, Ship, Task, User, Yard, db
from routes.container_route import container_bp
from routes.dangerous_route import dangerous_bp
from routes.equipment_route import equipment_bp
from routes.finance_route import finance_bp
from routes.import_lifecycle_route import import_bp
from routes.ship_route import ship_bp
from routes.task_route import task_bp
from routes.yard_route import yard_bp


STATUS_SCHEDULED = '\u8ba1\u5212\u4e2d'
STATUS_BERTHED = '\u5df2\u9760\u6cca'
STATUS_DEPARTED = '\u5df2\u79bb\u6e2f'
ROLE_ADMIN = 'admin'
ROLE_DISPATCHER = 'dispatcher'
ROLE_CUSTOMER = 'operator'
ROLE_FINANCE = 'finance'
ROLE_LABELS = {
    ROLE_ADMIN: '\u7ba1\u7406\u5458',
    ROLE_DISPATCHER: '\u8c03\u5ea6\u5458',
    ROLE_CUSTOMER: '\u5ba2\u6237',
    ROLE_FINANCE: '\u8d22\u52a1\u4eba\u5458',
}
ROLE_ALIASES = {
    '\u8d85\u7ea7\u7ba1\u7406\u5458': ROLE_ADMIN,
    '\u7ba1\u7406\u5458': ROLE_ADMIN,
    'admin': ROLE_ADMIN,
    'administrator': ROLE_ADMIN,
    'dispatcher': ROLE_DISPATCHER,
    '\u8c03\u5ea6\u5458': ROLE_DISPATCHER,
    'operator': ROLE_CUSTOMER,
    '\u64cd\u4f5c\u5458': ROLE_DISPATCHER,
    '\u5ba2\u6237': ROLE_CUSTOMER,
    'customer': ROLE_CUSTOMER,
    'client': ROLE_CUSTOMER,
    '\u8d22\u52a1': ROLE_FINANCE,
    '\u8d22\u52a1\u4eba\u5458': ROLE_FINANCE,
    'finance': ROLE_FINANCE,
}
ROLE_PAGE_ACCESS = {
    ROLE_ADMIN: {'home', 'container', 'yard', 'ship', 'terminal-operations', 'import', 'equipment', 'finance', 'dangerous', 'users'},
    ROLE_DISPATCHER: {'home', 'container', 'ship', 'terminal-operations', 'import', 'equipment', 'dangerous'},
    ROLE_CUSTOMER: {'home', 'container', 'import'},
    ROLE_FINANCE: {'home', 'container', 'finance'},
}
ROLE_PERMISSIONS = {
    ROLE_ADMIN: ['*'],
    ROLE_DISPATCHER: [
        'dashboard:read',
        'container:read',
        'yard:read',
        'ship:read',
        'ship:write',
        'task:read',
        'task:write',
        'equipment:read',
        'equipment:write',
        'import:read',
        'import:operate',
        'dangerous:read',
        'dangerous:write',
    ],
    ROLE_CUSTOMER: [
        'dashboard:read',
        'container:read',
        'yard:read',
        'ship:read',
        'task:read',
        'equipment:read',
        'import:read',
        'appointment:write',
        'exception:write',
    ],
    ROLE_FINANCE: [
        'dashboard:read',
        'container:read',
        'finance:read',
        'finance:write',
    ],
}
PERMISSION_CATALOG = [
    ('dashboard:read', '首页大屏', '查看首页统计与全局展示'),
    ('container:read', '集装箱查看', '查看集装箱基础信息'),
    ('container:write', '集装箱维护', '新增和修改集装箱'),
    ('container:delete', '集装箱删除', '删除集装箱'),
    ('yard:read', '堆场查看', '查看堆场与箱位'),
    ('yard:write', '堆场维护', '新增和修改堆场、箱位分配'),
    ('yard:delete', '堆场删除', '删除空堆场'),
    ('ship:read', '船舶查看', '查看船舶计划'),
    ('ship:write', '船舶维护', '新增、修改和启动船舶作业'),
    ('ship:delete', '船舶删除', '删除船舶计划'),
    ('task:read', '任务查看', '查看码头作业单'),
    ('task:write', '任务维护', '新增、修改和推进作业单'),
    ('equipment:read', '设备查看', '查看设备状态'),
    ('equipment:write', '设备维护', '新增、修改、分配和维修设备'),
    ('equipment:delete', '设备删除', '删除设备'),
    ('import:read', '进口查看', '查看进口闭环数据'),
    ('import:operate', '进口操作', '执行放行、闸口、提箱流程'),
    ('appointment:write', '预约维护', '新增或取消提箱预约'),
    ('exception:write', '异常登记', '登记进口异常'),
    ('dangerous:read', '危险品查看', '查看危险品申报'),
    ('dangerous:write', '危险品维护', '维护危险品申报和状态'),
    ('finance:read', '财务查看', '查看账单和汇总'),
    ('finance:write', '财务维护', '生成和结算账单'),
    ('user:read', '用户查看', '查看用户与权限'),
    ('user:write', '用户维护', '新增和修改账号权限'),
    ('user:delete', '用户删除', '删除非当前账号'),
]
VALID_PERMISSIONS = {item[0] for item in PERMISSION_CATALOG}
PERMISSION_PAGE_ACCESS = {
    'dashboard:read': {'home'},
    'container:read': {'container'},
    'yard:read': {'yard'},
    'ship:read': {'ship'},
    'task:read': {'terminal-operations'},
    'equipment:read': {'equipment'},
    'import:read': {'import'},
    'dangerous:read': {'dangerous'},
    'finance:read': {'finance'},
}
DEFAULT_USERS = [
    ('admin01', 'admin123', ROLE_ADMIN),
    ('dispatcher01', 'disp123', ROLE_DISPATCHER),
    ('customer01', 'cust123', ROLE_CUSTOMER),
    ('finance01', 'fin123', ROLE_FINANCE),
]


def normalize_role(role):
    text = (role or '').strip()
    return ROLE_ALIASES.get(text, ROLE_CUSTOMER)


def role_permissions(role):
    return ROLE_PERMISSIONS.get(normalize_role(role), ROLE_PERMISSIONS[ROLE_CUSTOMER])


def user_extra_permissions(user):
    raw = (getattr(user, 'permissions', '') or '').strip()
    if not raw:
        return []
    values = [item.strip() for item in raw.replace(';', ',').split(',')]
    return [item for item in values if item in VALID_PERMISSIONS]


def user_permissions(user):
    merged = list(role_permissions(user.role if user else ROLE_CUSTOMER))
    for permission in user_extra_permissions(user):
        if permission not in merged:
            merged.append(permission)
    return merged


def pages_for_permissions(role, permissions):
    pages = set(ROLE_PAGE_ACCESS.get(normalize_role(role), ROLE_PAGE_ACCESS[ROLE_CUSTOMER]))
    for permission in permissions:
        pages.update(PERMISSION_PAGE_ACCESS.get(permission, set()))
    return sorted(pages)


def user_payload(user):
    data = user.to_safe_dict()
    role = normalize_role(data.get('role'))
    data['roleKey'] = role
    data['role'] = ROLE_LABELS.get(role, '\u5ba2\u6237')
    data['extraPermissions'] = user_extra_permissions(user)
    data['permissions'] = user_permissions(user)
    data['pages'] = pages_for_permissions(role, data['permissions'])
    return data


def _page_key_from_path(path):
    if path in ('/', '/index.html'):
        return 'home'
    mapping = {
        '/pages/container-management.html': 'container',
        '/pages/yard-management.html': 'yard',
        '/pages/ship-plan-management.html': 'ship',
        '/pages/terminal-operations.html': 'terminal-operations',
        '/pages/import-lifecycle.html': 'import',
        '/pages/equipment-management.html': 'equipment',
        '/pages/finance-billing.html': 'finance',
        '/pages/dangerous-management.html': 'dangerous',
        '/pages/user-management.html': 'users',
    }
    return mapping.get(path)


def _permission_allowed(role, permission):
    permissions = role_permissions(role)
    return '*' in permissions or permission in permissions


def _path_permission(path, method):
    if path.startswith('/api/dashboard'):
        return 'dashboard:read'
    if path.startswith('/containers'):
        if method == 'GET':
            return 'container:read'
        if method == 'DELETE':
            return 'container:delete'
        return 'container:write'
    if path.startswith('/yards'):
        if method == 'GET':
            return 'yard:read'
        if method == 'DELETE':
            return 'yard:delete'
        return 'yard:write'
    if path.startswith('/ships'):
        if method == 'GET':
            return 'ship:read'
        if method == 'DELETE':
            return 'ship:delete'
        return 'ship:write'
    if path.startswith('/tasks'):
        return 'task:read' if method == 'GET' else 'task:write'
    if path.startswith('/equipment'):
        if method == 'GET':
            return 'equipment:read'
        if method == 'DELETE':
            return 'equipment:delete'
        return 'equipment:write'
    if path.startswith('/api/import'):
        if method == 'GET':
            return 'import:read'
        if path == '/api/import/appointments' and method == 'POST':
            return 'appointment:write'
        if path.startswith('/api/import/appointments/') and path.endswith('/cancel') and method == 'PUT':
            return 'appointment:write'
        if path == '/api/import/exceptions' and method == 'POST':
            return 'exception:write'
        return 'import:operate'
    if path.startswith('/api/finance'):
        return 'finance:read' if method == 'GET' else 'finance:write'
    if path.startswith('/api/dangerous'):
        return 'dangerous:read' if method == 'GET' else 'dangerous:write'
    if path.startswith('/api/users'):
        if method == 'GET':
            return 'user:read'
        if method == 'DELETE':
            return 'user:delete'
        return 'user:write'
    return None


def _clean_permissions(values):
    if isinstance(values, str):
        candidates = values.replace(';', ',').split(',')
    else:
        candidates = values or []
    cleaned = []
    for item in candidates:
        permission = str(item or '').strip()
        if permission in VALID_PERMISSIONS and permission not in cleaned:
            cleaned.append(permission)
    return cleaned


def _admin_count(exclude_user_id=None):
    users = User.query.all()
    return sum(
        1 for user in users
        if user.id != exclude_user_id and normalize_role(user.role) == ROLE_ADMIN
    )


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    app.register_blueprint(container_bp)
    app.register_blueprint(dangerous_bp)
    app.register_blueprint(equipment_bp)
    app.register_blueprint(finance_bp)
    app.register_blueprint(ship_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(yard_bp)
    app.register_blueprint(import_bp)

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
            user = User.query.get(session.get('user_id'))
            if user is None:
                session.clear()
                if request.path.startswith('/api/'):
                    return jsonify({"message": "\u7528\u6237\u4e0d\u5b58\u5728"}), 401
                return redirect(url_for('login_page'))
            role = normalize_role(session.get('role'))
            role = normalize_role(user.role)
            session['role'] = role
            permissions = user_permissions(user)
            allowed_pages = set(pages_for_permissions(role, permissions))
            page_key = _page_key_from_path(request.path)
            if page_key and page_key not in allowed_pages:
                if request.path.startswith('/pages'):
                    return redirect('/index.html')
                return jsonify({"message": "\u5f53\u524d\u89d2\u8272\u65e0\u6743\u8bbf\u95ee\u8be5\u9875\u9762"}), 403
            permission = _path_permission(request.path, request.method)
            if permission and '*' not in permissions and permission not in permissions:
                return jsonify({"message": "\u5f53\u524d\u89d2\u8272\u65e0\u6743\u6267\u884c\u8be5\u64cd\u4f5c"}), 403
            return None
        if (
            request.path.startswith('/containers') or
            request.path.startswith('/yards') or
            request.path.startswith('/ships') or
            request.path.startswith('/tasks') or
            request.path.startswith('/equipment') or
            request.path.startswith('/api/import') or
            request.path.startswith('/api/finance') or
            request.path.startswith('/api/dangerous') or
            request.path.startswith('/api/dashboard') or
            request.path.startswith('/api/users')
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
        session['role'] = normalize_role(user.role)
        return jsonify({"message": "\u767b\u5f55\u6210\u529f", "data": user_payload(user)})

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
        return jsonify({"data": user_payload(user)})

    @app.route('/api/auth/logout', methods=['POST'])
    def logout():
        session.clear()
        return jsonify({"message": "\u5df2\u9000\u51fa\u767b\u5f55"})

    @app.route('/api/users/options', methods=['GET'])
    def user_options():
        return jsonify({
            "roles": [
                {"value": key, "label": label, "permissions": role_permissions(key)}
                for key, label in ROLE_LABELS.items()
            ],
            "permissions": [
                {"value": value, "label": label, "description": description}
                for value, label, description in PERMISSION_CATALOG
            ],
        })

    @app.route('/api/users', methods=['GET'])
    def list_users():
        users = User.query.order_by(User.id).all()
        return jsonify([user_payload(user) for user in users])

    @app.route('/api/users', methods=['POST'])
    def create_user():
        data = request.get_json(silent=True) or {}
        username = (data.get('username') or '').strip()
        password = data.get('password') or ''
        role = normalize_role(data.get('role'))
        permissions = _clean_permissions(data.get('permissions') or data.get('extraPermissions') or [])
        if not username or not password:
            return jsonify({"message": "\u7528\u6237\u540d\u548c\u5bc6\u7801\u4e0d\u80fd\u4e3a\u7a7a"}), 400
        if User.query.filter_by(username=username).first():
            return jsonify({"message": "\u7528\u6237\u540d\u5df2\u5b58\u5728"}), 409
        user = User(
            username=username,
            password=password,
            role=role,
            permissions=','.join(permissions),
        )
        db.session.add(user)
        db.session.commit()
        return jsonify({"message": "\u7528\u6237\u5df2\u521b\u5efa", "data": user_payload(user)}), 201

    @app.route('/api/users/<int:user_id>', methods=['PUT'])
    def update_user(user_id):
        user = User.query.get_or_404(user_id)
        data = request.get_json(silent=True) or {}
        username = (data.get('username') or user.username).strip()
        if not username:
            return jsonify({"message": "\u7528\u6237\u540d\u4e0d\u80fd\u4e3a\u7a7a"}), 400
        duplicate = User.query.filter(User.username == username, User.id != user.id).first()
        if duplicate:
            return jsonify({"message": "\u7528\u6237\u540d\u5df2\u5b58\u5728"}), 409

        new_role = normalize_role(data.get('role', user.role))
        if user.id == session.get('user_id') and normalize_role(user.role) == ROLE_ADMIN and new_role != ROLE_ADMIN:
            return jsonify({"message": "\u4e0d\u80fd\u5c06\u5f53\u524d\u767b\u5f55\u7ba1\u7406\u5458\u964d\u6743"}), 400
        if normalize_role(user.role) == ROLE_ADMIN and new_role != ROLE_ADMIN and _admin_count(exclude_user_id=user.id) == 0:
            return jsonify({"message": "\u7cfb\u7edf\u81f3\u5c11\u9700\u4fdd\u7559\u4e00\u4e2a\u7ba1\u7406\u5458\u8d26\u53f7"}), 400

        user.username = username
        if data.get('password'):
            user.password = data.get('password')
        user.role = new_role
        user.permissions = ','.join(_clean_permissions(data.get('permissions') or data.get('extraPermissions') or []))
        db.session.commit()
        if user.id == session.get('user_id'):
            session['username'] = user.username
            session['role'] = normalize_role(user.role)
        return jsonify({"message": "\u7528\u6237\u5df2\u66f4\u65b0", "data": user_payload(user)})

    @app.route('/api/users/<int:user_id>', methods=['DELETE'])
    def delete_user(user_id):
        user = User.query.get_or_404(user_id)
        if user.id == session.get('user_id'):
            return jsonify({"message": "\u4e0d\u80fd\u5220\u9664\u5f53\u524d\u767b\u5f55\u8d26\u53f7"}), 400
        if normalize_role(user.role) == ROLE_ADMIN and _admin_count(exclude_user_id=user.id) == 0:
            return jsonify({"message": "\u7cfb\u7edf\u81f3\u5c11\u9700\u4fdd\u7559\u4e00\u4e2a\u7ba1\u7406\u5458\u8d26\u53f7"}), 400
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": "\u7528\u6237\u5df2\u5220\u9664"})

    @app.route('/api/dashboard/stats', methods=['GET'])
    def dashboard_stats():
        containers = Container.query.all()
        yards = Yard.query.all()
        ships = Ship.query.all()
        tasks = Task.query.all()
        equipment = Equipment.query.all()

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
                "equipmentTotal": len(equipment),
                "workingEquipment": sum(1 for item in equipment if item.status == '\u5de5\u4f5c\u4e2d'),
                "faultEquipment": sum(1 for item in equipment if item.status == '\u6545\u969c'),
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
            "equipmentStatus": {
                "idle": sum(1 for item in equipment if item.status == '\u7a7a\u95f2'),
                "working": sum(1 for item in equipment if item.status == '\u5de5\u4f5c\u4e2d'),
                "fault": sum(1 for item in equipment if item.status == '\u6545\u969c'),
            },
        })

    with app.app_context():
        db.create_all()
        ensure_container_import_schema()
        ensure_ship_schema()
        ensure_task_schema()
        ensure_equipment_schema()
        ensure_user_schema()
        seed_data()

    return app


def seed_data():
    existing_users = {user.username: user for user in User.query.all()}
    for username, password, role in DEFAULT_USERS:
        user = existing_users.get(username)
        if user is None:
            db.session.add(User(username=username, password=password, role=role))
        else:
            user.role = normalize_role(user.role)
    for user in existing_users.values():
        user.role = normalize_role(user.role)
    db.session.commit()

    if Yard.query.first() is None:
        db.session.add_all([
            Yard(yard_name='\u5806\u573aA', usage_type='\u8fdb\u53e3\u7bb1', code='Y-A'),
            Yard(yard_name='\u5806\u573aB', usage_type='\u51fa\u53e3\u7bb1', code='Y-B'),
            Yard(yard_name='\u5806\u573aC', usage_type='\u51b7\u85cf\u7bb1', code='Y-C'),
            Yard(yard_name='\u5371\u9669\u54c1\u5806\u573aD', usage_type='\u5371\u9669\u54c1\u5806\u573a', code='Y-DG'),
        ])
        db.session.commit()
    elif not Yard.query.filter((Yard.yard_name.like('%\u5371\u9669%')) | (Yard.usage_type.like('%\u5371\u9669%'))).first():
        db.session.add(Yard(yard_name='\u5371\u9669\u54c1\u5806\u573aD', usage_type='\u5371\u9669\u54c1\u5806\u573a', code='Y-DG'))
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

    if Equipment.query.first() is None:
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.session.add_all([
            Equipment(code='QC01', name='\u5cb8\u68651', equipment_type='\u5cb8\u6865', status='\u7a7a\u95f2', location='\u6cca\u4f4d1', efficiency=30, created_at=now, updated_at=now),
            Equipment(code='QC02', name='\u5cb8\u68652', equipment_type='\u5cb8\u6865', status='\u7a7a\u95f2', location='\u6cca\u4f4d2', efficiency=30, created_at=now, updated_at=now),
            Equipment(code='AGV01', name='AGV1', equipment_type='AGV', status='\u7a7a\u95f2', location='\u6cca\u4f4d\u524d\u6cbf', efficiency=20, created_at=now, updated_at=now),
            Equipment(code='AGV02', name='AGV2', equipment_type='AGV', status='\u7a7a\u95f2', location='\u6cca\u4f4d\u524d\u6cbf', efficiency=20, created_at=now, updated_at=now),
            Equipment(code='AGV03', name='AGV3', equipment_type='AGV', status='\u7a7a\u95f2', location='\u5806\u573aA', efficiency=20, created_at=now, updated_at=now),
            Equipment(code='YC01', name='\u573a\u68651', equipment_type='\u573a\u6865', status='\u7a7a\u95f2', location='\u5806\u573aA', efficiency=25, created_at=now, updated_at=now),
            Equipment(code='YC02', name='\u573a\u68652', equipment_type='\u573a\u6865', status='\u6545\u969c', location='\u5806\u573aB', efficiency=25, remark='\u6db2\u538b\u7cfb\u7edf\u5f85\u68c0\u4fee', created_at=now, updated_at=now),
        ])
        db.session.commit()

    ensure_dangerous_container_locations()


def ensure_dangerous_container_locations():
    dangerous_yards = [
        yard for yard in Yard.query.order_by(Yard.id).all()
        if '\u5371\u9669' in ((yard.yard_name or '') + (yard.usage_type or ''))
    ]
    if not dangerous_yards:
        return

    occupied = {
        (c.yard, c.area, c.column, c.layer)
        for c in Container.query.filter(Container.status != '\u79bb\u6e2f').all()
        if c.yard and c.area and c.column and c.layer
    }
    changed = False
    for container in Container.query.filter_by(is_dangerous=True).all():
        yard_text = (container.yard or '')
        yard = Yard.query.filter_by(yard_name=container.yard).first() if container.yard else None
        if yard:
            yard_text = (yard.yard_name or '') + (yard.usage_type or '')
        if '\u5371\u9669' in yard_text and container.area and container.column and container.layer:
            continue

        target = None
        for danger_yard in dangerous_yards:
            for area in danger_yard.zone_list:
                for column in range(1, danger_yard.total_rows + 1):
                    for layer in range(1, danger_yard.total_tiers + 1):
                        key = (danger_yard.yard_name, area, column, layer)
                        if key not in occupied:
                            target = key
                            break
                    if target:
                        break
                if target:
                    break
            if target:
                break
        if not target:
            continue
        container.yard, container.area, container.column, container.layer = target
        container.status = '\u5806\u573a\u5b58\u50a8'
        occupied.add(target)
        changed = True

    if changed:
        db.session.commit()


def ensure_ship_schema():
    try:
        columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(ship)")).fetchall()}
        if 'status' not in columns:
            db.session.execute(text("ALTER TABLE ship ADD COLUMN status TEXT DEFAULT '\u8ba1\u5212\u4e2d'"))
            db.session.commit()
    except Exception:
            db.session.rollback()


def ensure_container_import_schema():
    try:
        columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(container)")).fetchall()}
        if not columns:
            return
        required_columns = {
            'customs_status': "ALTER TABLE container ADD COLUMN customs_status TEXT DEFAULT '未放行'",
            'appointment_status': "ALTER TABLE container ADD COLUMN appointment_status TEXT DEFAULT '未预约'",
            'damage_status': "ALTER TABLE container ADD COLUMN damage_status TEXT DEFAULT '正常'",
            'locked_by_appointment_id': "ALTER TABLE container ADD COLUMN locked_by_appointment_id INTEGER",
        }

        for column, ddl in required_columns.items():
            if column not in columns:
                db.session.execute(text(ddl))
        db.session.execute(text("UPDATE container SET customs_status = '未放行' WHERE customs_status IS NULL OR customs_status = ''"))
        db.session.execute(text("UPDATE container SET appointment_status = '未预约' WHERE appointment_status IS NULL OR appointment_status = ''"))
        db.session.execute(text("UPDATE container SET damage_status = '正常' WHERE damage_status IS NULL OR damage_status = ''"))
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


def ensure_equipment_schema():
    try:
        columns = {row[1] for row in db.session.execute(text("PRAGMA table_info(equipment)")).fetchall()}
        if not columns:
            return
        required_columns = {
            'code': "ALTER TABLE equipment ADD COLUMN code TEXT",
            'name': "ALTER TABLE equipment ADD COLUMN name TEXT",
            'equipment_type': "ALTER TABLE equipment ADD COLUMN equipment_type TEXT",
            'status': "ALTER TABLE equipment ADD COLUMN status TEXT DEFAULT '\u7a7a\u95f2'",
            'location': "ALTER TABLE equipment ADD COLUMN location TEXT",
            'efficiency': "ALTER TABLE equipment ADD COLUMN efficiency INTEGER DEFAULT 0",
            'current_task_id': "ALTER TABLE equipment ADD COLUMN current_task_id INTEGER",
            'last_maintenance_at': "ALTER TABLE equipment ADD COLUMN last_maintenance_at TEXT",
            'remark': "ALTER TABLE equipment ADD COLUMN remark TEXT",
            'created_at': "ALTER TABLE equipment ADD COLUMN created_at TEXT",
            'updated_at': "ALTER TABLE equipment ADD COLUMN updated_at TEXT",
        }
        for column, ddl in required_columns.items():
            if column not in columns:
                db.session.execute(text(ddl))
        db.session.execute(text("UPDATE equipment SET code = 'EQ-' || id WHERE code IS NULL OR code = ''"))
        db.session.execute(text("UPDATE equipment SET name = code WHERE name IS NULL OR name = ''"))
        db.session.execute(text("UPDATE equipment SET equipment_type = CASE "
                                "WHEN code LIKE 'QC%' OR name LIKE '%\u5cb8\u6865%' THEN '\u5cb8\u6865' "
                                "WHEN code LIKE 'YC%' OR name LIKE '%\u573a\u6865%' THEN '\u573a\u6865' "
                                "WHEN code LIKE 'AGV%' OR name LIKE '%AGV%' THEN 'AGV' "
                                "ELSE 'AGV' END "
                                "WHERE equipment_type IS NULL OR equipment_type = '' OR equipment_type = '\u901a\u7528\u8bbe\u5907'"))
        db.session.execute(text("UPDATE equipment SET status = '\u7a7a\u95f2' WHERE status IS NULL OR status = ''"))
        db.session.commit()
    except Exception:
        db.session.rollback()


def ensure_user_schema():
    try:
        row = db.session.execute(text("SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'user'")).fetchone()
        create_sql = row[0] if row else ''
        if create_sql and 'CHECK' in create_sql.upper() and "'finance'" not in create_sql:
            db.session.execute(text("ALTER TABLE user RENAME TO user_old_role_migration"))
            db.session.execute(text(
                "CREATE TABLE user ("
                "id INTEGER PRIMARY KEY, "
                "username VARCHAR(50) UNIQUE NOT NULL, "
                "password VARCHAR(100) NOT NULL, "
                "role VARCHAR(20) NOT NULL CHECK (role IN ('admin', 'dispatcher', 'operator', 'finance')), "
                "permissions VARCHAR(500), "
                "last_login_at VARCHAR(30)"
                ")"
            ))
            db.session.execute(text(
                "INSERT INTO user (id, username, password, role, permissions, last_login_at) "
                "SELECT id, username, password, "
                "CASE "
                "WHEN role IN ('admin', 'dispatcher', 'operator', 'finance') THEN role "
                "WHEN role IN ('\u7ba1\u7406\u5458', '\u8d85\u7ea7\u7ba1\u7406\u5458') THEN 'admin' "
                "WHEN role IN ('\u8c03\u5ea6\u5458', '\u64cd\u4f5c\u5458') THEN 'dispatcher' "
                "WHEN role IN ('\u8d22\u52a1', '\u8d22\u52a1\u4eba\u5458') THEN 'finance' "
                "ELSE 'operator' END, "
                "NULL, "
                "last_login_at FROM user_old_role_migration"
            ))
            db.session.execute(text("DROP TABLE user_old_role_migration"))
        columns = {column[1] for column in db.session.execute(text("PRAGMA table_info(user)")).fetchall()}
        if columns and 'permissions' not in columns:
            db.session.execute(text("ALTER TABLE user ADD COLUMN permissions TEXT"))
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
