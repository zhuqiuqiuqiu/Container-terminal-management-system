from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()


class Container(db.Model):
    __tablename__ = 'container'

    id = db.Column(db.Integer, primary_key=True)
    container_no = db.Column(db.String(30), unique=True, nullable=False)
    container_type = db.Column(db.String(10), nullable=False)
    status = db.Column(db.String(20), default='\u5728\u8239\u4e2d')
    yard = db.Column('yard_name', db.String(30))
    ship_id = db.Column(db.Integer)
    load_flag = db.Column(db.String(20), default='\u7a7a\u7bb1')
    area = db.Column(db.String(20))
    column = db.Column('col', db.Integer)
    layer = db.Column(db.Integer)
    is_dangerous = db.Column('dangerous_goods', db.Boolean, default=False)
    is_refrigerated = db.Column('refrigerated', db.Boolean, default=False)

    @property
    def is_full(self):
        return self.load_flag in ('\u5df2\u88c5\u8f7d', '\u91cd\u7bb1', 'full', 'loaded')

    @is_full.setter
    def is_full(self, value):
        self.load_flag = '\u5df2\u88c5\u8f7d' if value else '\u7a7a\u7bb1'

    def to_dict(self):
        return {
            "id": self.id,
            "container_no": self.container_no,
            "containerNo": self.container_no,
            "container_type": self.container_type,
            "containerType": self.container_type,
            "is_full": self.is_full,
            "loadStatus": "\u91cd\u7bb1" if self.is_full else "\u7a7a\u7bb1",
            "is_dangerous": self.is_dangerous,
            "isDangerous": self.is_dangerous,
            "is_refrigerated": self.is_refrigerated,
            "isReefer": self.is_refrigerated,
            "yard": self.yard,
            "area": self.area,
            "zone": self.area,
            "column": self.column,
            "row": self.column,
            "layer": self.layer,
            "tier": self.layer,
            "status": self.status
        }


class Yard(db.Model):
    __tablename__ = 'yard'

    id = db.Column(db.Integer, primary_key=True)
    yard_name = db.Column('name', db.String(30), unique=True, nullable=False)
    usage_type = db.Column('type', db.String(30), default='\u7efc\u5408\u5806\u573a')
    capacity = db.Column(db.Integer, default=0)
    code = db.Column(db.String(20), unique=True)
    db_total_capacity = db.Column('total_capacity', db.Integer, default=240)
    db_used_capacity = db.Column('used_capacity', db.Integer, default=0)
    db_available_capacity = db.Column('available_capacity', db.Integer, default=240)
    address = db.Column(db.String(100))
    manager = db.Column(db.String(30))
    contact_phone = db.Column(db.String(30))
    status = db.Column(db.String(20), default='active')
    created_at = db.Column(db.String(30))
    updated_at = db.Column(db.String(30))

    @property
    def zone_list(self):
        return ['A\u533a', 'B\u533a', 'C\u533a', 'D\u533a', 'Zone-1', 'Zone-2', 'Zone-3', 'Zone-4']

    @property
    def total_capacity(self):
        return self.db_total_capacity or self.capacity or 240

    @property
    def total_rows(self):
        return 12

    @property
    def total_tiers(self):
        return 5

    def used_capacity(self):
        actual_used = Container.query.filter(
            Container.yard == self.yard_name,
            Container.status != '\u79bb\u6e2f'
        ).count()
        return actual_used

    def to_dict(self):
        used = self.used_capacity()
        total = self.total_capacity
        return {
            "id": self.id,
            "yard_name": self.yard_name,
            "yardName": self.yard_name,
            "usage_type": self.usage_type,
            "usageType": self.usage_type,
            "zones": self.zone_list,
            "total_rows": self.total_rows,
            "totalRows": self.total_rows,
            "total_tiers": self.total_tiers,
            "totalTiers": self.total_tiers,
            "total_capacity": total,
            "totalCapacity": total,
            "used_capacity": used,
            "usedCapacity": used,
            "remaining_capacity": max(total - used, 0),
            "remainingCapacity": max(total - used, 0),
            "usageRate": round((used / total) * 100, 2) if total else 0,
            "status": self.status,
            "code": self.code,
            "address": self.address,
            "manager": self.manager,
            "contactPhone": self.contact_phone,
        }


class Ship(db.Model):
    __tablename__ = 'ship'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    voyage = db.Column(db.String(40), nullable=False)
    eta = db.Column('ETA', db.String(30))
    etd = db.Column('ETD', db.String(30))
    berth = db.Column(db.String(30))
    status = db.Column(db.String(20), default='计划中')

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "voyage": self.voyage,
            "eta": self.eta,
            "ETA": self.eta,
            "etd": self.etd,
            "ETD": self.etd,
            "berth": self.berth,
            "status": self.status or '计划中',
        }


class Task(db.Model):
    __tablename__ = 'task'

    id = db.Column(db.Integer, primary_key=True)
    task_type = db.Column(db.String(80))
    container_id = db.Column(db.Integer)
    from_pos = db.Column(db.String(80))
    to_pos = db.Column(db.String(80))
    status = db.Column(db.String(30), default='pending')
    task_no = db.Column(db.String(40), unique=True)
    priority = db.Column(db.Integer, default=3)
    operator_id = db.Column(db.Integer)
    equipment_id = db.Column(db.Integer)
    start_time = db.Column(db.String(30))
    end_time = db.Column(db.String(30))
    estimated_time = db.Column(db.Integer)
    actual_time = db.Column(db.Integer)
    created_at = db.Column(db.String(30))
    updated_at = db.Column(db.String(30))
    remark = db.Column(db.String(200))

    @property
    def container(self):
        if not self.container_id:
            return None
        return Container.query.get(self.container_id)

    def normalized_status(self):
        mapping = {
            'processing': 'in-progress',
            '进行中': 'in-progress',
            '未开始': 'pending',
            '已完成': 'completed',
        }
        return mapping.get(self.status, self.status or 'pending')

    def to_dict(self):
        container = self.container
        return {
            "id": self.id,
            "task_no": self.task_no,
            "taskNo": self.task_no,
            "taskName": self.task_type or '',
            "task_type": self.task_type,
            "containerId": container.container_no if container else '',
            "container_id": self.container_id,
            "containerDbId": self.container_id,
            "origin": self.from_pos or '',
            "from_pos": self.from_pos,
            "destination": self.to_pos or '',
            "to_pos": self.to_pos,
            "yardSlot": self.remark or '',
            "status": self.normalized_status(),
            "priority": self.priority or 3,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }


class User(db.Model):
    __tablename__ = 'user'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    last_login_at = db.Column(db.String(30))

    def to_safe_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "lastLoginAt": self.last_login_at,
        }
