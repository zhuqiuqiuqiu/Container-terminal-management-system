from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from Container.models.container_model import Equipment, Task, db


equipment_bp = Blueprint('equipment_bp', __name__, url_prefix='/equipment')

STATUS_IDLE = '\u7a7a\u95f2'
STATUS_WORKING = '\u5de5\u4f5c\u4e2d'
STATUS_FAULT = '\u6545\u969c'
VALID_STATUSES = {STATUS_IDLE, STATUS_WORKING, STATUS_FAULT}
TYPE_QUAY_CRANE = '\u5cb8\u6865'
TYPE_YARD_CRANE = '\u573a\u6865'
TYPE_AGV = 'AGV'
VALID_TYPES = {TYPE_QUAY_CRANE, TYPE_YARD_CRANE, TYPE_AGV}


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _normalize_payload(data):
    equipment_type = (data.get('equipmentType') or data.get('equipment_type') or '').strip()
    return {
        'code': (data.get('code') or '').strip(),
        'name': (data.get('name') or '').strip(),
        'equipment_type': equipment_type,
        'status': (data.get('status') or STATUS_IDLE).strip(),
        'location': (data.get('location') or '').strip(),
        'efficiency': int(data.get('efficiency') or 0),
        'remark': (data.get('remark') or '').strip(),
    }


def _task_required_equipment_type(task):
    task_name = task.task_type or ''
    if 'AGV' in task_name:
        return TYPE_AGV
    if '\u573a\u6865' in task_name or '\u5165\u5806' in task_name:
        return TYPE_YARD_CRANE
    if '\u5cb8\u6865' in task_name or '\u5378\u8239' in task_name:
        return TYPE_QUAY_CRANE

    text = f'{task.task_type or ""} {task.from_pos or ""} {task.to_pos or ""} {task.remark or ""}'
    if '\u573a\u6865' in text or '\u5165\u5806' in text or '\u5806\u573a' in text:
        return TYPE_YARD_CRANE
    if '\u5cb8\u6865' in text or '\u5378\u8239' in text or '\u6cca\u4f4d' in text:
        return TYPE_QUAY_CRANE
    if 'AGV' in text or '\u8f6c\u8fd0' in text or '\u8fd0\u9001' in text:
        return TYPE_AGV
    return None


def _assign_task_to_equipment(equipment, task):
    previous_equipment = Equipment.query.filter_by(current_task_id=task.id).first()
    if previous_equipment and previous_equipment.id != equipment.id:
        previous_equipment.current_task_id = None
        previous_equipment.status = STATUS_IDLE
        previous_equipment.updated_at = _now()

    now = _now()
    task.equipment_id = equipment.id
    task.status = 'in-progress'
    task.start_time = task.start_time or now
    task.updated_at = now
    equipment.current_task_id = task.id
    equipment.status = STATUS_WORKING
    equipment.updated_at = now


def _validate_equipment_payload(data):
    if not data['code'] or not data['name'] or not data['equipment_type']:
        return "\u8bf7\u586b\u5199\u8bbe\u5907\u7f16\u53f7\u3001\u540d\u79f0\u548c\u7c7b\u578b"
    if data['status'] not in VALID_STATUSES:
        return "\u8bbe\u5907\u72b6\u6001\u53ea\u80fd\u662f\u7a7a\u95f2\u3001\u5de5\u4f5c\u4e2d\u6216\u6545\u969c"
    if data['equipment_type'] not in VALID_TYPES:
        return "\u8bbe\u5907\u7c7b\u578b\u53ea\u80fd\u662f\u5cb8\u6865\u3001\u573a\u6865\u6216 AGV"
    return None


@equipment_bp.route('', methods=['GET'])
def list_equipment():
    items = Equipment.query.order_by(Equipment.id).all()
    return jsonify([item.to_dict() for item in items])


@equipment_bp.route('/summary', methods=['GET'])
def equipment_summary():
    items = Equipment.query.all()
    by_status = {
        STATUS_IDLE: sum(1 for item in items if item.status == STATUS_IDLE),
        STATUS_WORKING: sum(1 for item in items if item.status == STATUS_WORKING),
        STATUS_FAULT: sum(1 for item in items if item.status == STATUS_FAULT),
    }
    by_type = {}
    for item in items:
        by_type[item.equipment_type] = by_type.get(item.equipment_type, 0) + 1
    return jsonify({
        "total": len(items),
        "byStatus": by_status,
        "validTypes": [TYPE_QUAY_CRANE, TYPE_YARD_CRANE, TYPE_AGV],
        "byType": [{"name": key, "value": value} for key, value in by_type.items()],
    })


@equipment_bp.route('', methods=['POST'])
def create_equipment():
    data = _normalize_payload(request.get_json(silent=True) or {})
    error = _validate_equipment_payload(data)
    if error:
        return jsonify({"message": error}), 400

    now = _now()
    equipment = Equipment(created_at=now, updated_at=now, **data)
    db.session.add(equipment)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "\u8bbe\u5907\u7f16\u53f7\u5df2\u5b58\u5728"}), 409
    return jsonify({"message": "\u65b0\u589e\u8bbe\u5907\u6210\u529f", "data": equipment.to_dict()}), 201


@equipment_bp.route('/<int:equipment_id>', methods=['PUT'])
def update_equipment(equipment_id):
    equipment = Equipment.query.get_or_404(equipment_id)
    data = _normalize_payload(request.get_json(silent=True) or {})
    error = _validate_equipment_payload(data)
    if error:
        return jsonify({"message": error}), 400

    equipment.code = data['code'] or equipment.code
    equipment.name = data['name'] or equipment.name
    equipment.equipment_type = data['equipment_type'] or equipment.equipment_type
    equipment.status = data['status'] or equipment.status
    equipment.location = data['location']
    equipment.efficiency = data['efficiency']
    equipment.remark = data['remark']
    if equipment.status != STATUS_WORKING:
        equipment.current_task_id = None
    equipment.updated_at = _now()
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "\u8bbe\u5907\u7f16\u53f7\u5df2\u5b58\u5728"}), 409
    return jsonify({"message": "\u4fee\u6539\u8bbe\u5907\u6210\u529f", "data": equipment.to_dict()})


@equipment_bp.route('/<int:equipment_id>', methods=['DELETE'])
def delete_equipment(equipment_id):
    equipment = Equipment.query.get_or_404(equipment_id)
    if equipment.status == STATUS_WORKING:
        return jsonify({"message": "\u8bbe\u5907\u6b63\u5728\u5de5\u4f5c\u4e2d\uff0c\u4e0d\u80fd\u5220\u9664"}), 400
    db.session.delete(equipment)
    db.session.commit()
    return jsonify({"message": "\u5220\u9664\u8bbe\u5907\u6210\u529f"})


@equipment_bp.route('/<int:equipment_id>/assign_task', methods=['POST'])
def assign_task(equipment_id):
    equipment = Equipment.query.get_or_404(equipment_id)
    data = request.get_json(silent=True) or {}
    task_id = data.get('taskId') or data.get('task_id')
    if not task_id:
        return jsonify({"message": "\u8bf7\u9009\u62e9\u9700\u8981\u5206\u914d\u7684\u4efb\u52a1"}), 400
    if equipment.status == STATUS_FAULT:
        return jsonify({"message": "\u6545\u969c\u8bbe\u5907\u4e0d\u80fd\u5206\u914d\u4efb\u52a1"}), 400

    task = Task.query.get_or_404(task_id)
    if task.status == 'completed':
        return jsonify({"message": "\u5df2\u5b8c\u6210\u4efb\u52a1\u4e0d\u9700\u518d\u5206\u914d\u8bbe\u5907"}), 400
    required_type = _task_required_equipment_type(task)
    if required_type and equipment.equipment_type != required_type:
        return jsonify({
            "message": f"\u8be5\u4efb\u52a1\u9700\u8981 {required_type}\uff0c\u4e0d\u80fd\u5206\u914d {equipment.equipment_type}"
        }), 400

    _assign_task_to_equipment(equipment, task)
    db.session.commit()
    return jsonify({
        "message": f"{equipment.name} \u5df2\u5206\u914d\u5230\u4efb\u52a1 {task.task_no or task.id}",
        "equipment": equipment.to_dict(),
        "task": task.to_dict(),
    })


@equipment_bp.route('/agv_dispatch', methods=['POST'])
def agv_dispatch():
    idle_agvs = Equipment.query.filter(
        Equipment.equipment_type == TYPE_AGV,
        Equipment.status == STATUS_IDLE,
    ).order_by(Equipment.id).all()

    candidate_tasks = Task.query.filter(
        Task.status != 'completed',
        Task.equipment_id.is_(None),
    ).order_by(Task.priority.desc(), Task.id).all()
    agv_tasks = [task for task in candidate_tasks if _task_required_equipment_type(task) == TYPE_AGV]

    assignments = []
    for equipment, task in zip(idle_agvs, agv_tasks):
        _assign_task_to_equipment(equipment, task)
        assignments.append({
            "equipment": equipment.to_dict(),
            "task": task.to_dict(),
        })

    db.session.commit()
    return jsonify({
        "message": f"\u8d2a\u5a6a\u8c03\u5ea6\u5b8c\u6210\uff0c\u5df2\u5206\u914d {len(assignments)} \u4e2a AGV \u4efb\u52a1",
        "assignedCount": len(assignments),
        "idleAgvCount": len(idle_agvs),
        "waitingTaskCount": len(agv_tasks),
        "assignments": assignments,
    })


@equipment_bp.route('/<int:equipment_id>/release', methods=['POST'])
def release_equipment(equipment_id):
    equipment = Equipment.query.get_or_404(equipment_id)
    task = Task.query.get(equipment.current_task_id) if equipment.current_task_id else None
    now = _now()
    if task:
        task.status = 'completed'
        task.end_time = now
        task.updated_at = now
    equipment.current_task_id = None
    equipment.status = STATUS_IDLE
    equipment.updated_at = now
    db.session.commit()
    return jsonify({"message": "\u8bbe\u5907\u5df2\u91ca\u653e\u4e3a\u7a7a\u95f2", "data": equipment.to_dict()})


@equipment_bp.route('/<int:equipment_id>/fault', methods=['POST'])
def mark_fault(equipment_id):
    equipment = Equipment.query.get_or_404(equipment_id)
    task = Task.query.get(equipment.current_task_id) if equipment.current_task_id else None
    if task and task.status != 'completed':
        task.status = 'pending'
        task.updated_at = _now()
        task.equipment_id = None
    equipment.current_task_id = None
    equipment.status = STATUS_FAULT
    equipment.remark = (request.get_json(silent=True) or {}).get('remark') or equipment.remark
    equipment.updated_at = _now()
    db.session.commit()
    return jsonify({"message": "\u8bbe\u5907\u5df2\u6807\u8bb0\u4e3a\u6545\u969c", "data": equipment.to_dict()})


@equipment_bp.route('/<int:equipment_id>/repair', methods=['POST'])
def repair_equipment(equipment_id):
    equipment = Equipment.query.get_or_404(equipment_id)
    now = _now()
    equipment.status = STATUS_IDLE
    equipment.current_task_id = None
    equipment.last_maintenance_at = now
    equipment.updated_at = now
    db.session.commit()
    return jsonify({"message": "\u8bbe\u5907\u5df2\u7ef4\u4fee\u5b8c\u6210\u5e76\u6062\u590d\u7a7a\u95f2", "data": equipment.to_dict()})
