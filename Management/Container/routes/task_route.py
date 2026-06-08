from datetime import datetime

from flask import Blueprint, jsonify, request

from Container.models.container_model import Container, Equipment, Task, db
from Container.routes.task_rules import reconcile_completed_stage_tasks, sync_container_after_task, validate_task_transition


task_bp = Blueprint('task_bp', __name__, url_prefix='/tasks')


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _next_task_no():
    return 'TSK-' + datetime.now().strftime('%Y%m%d%H%M%S%f')[:-3]


def _resolve_container(data):
    container_db_id = data.get('container_db_id') or data.get('containerDbId') or data.get('container_id')
    if container_db_id:
        return Container.query.get(container_db_id)

    container_no = (data.get('containerNo') or data.get('containerId') or data.get('container_no') or '').strip()
    if not container_no:
        return None
    return Container.query.filter_by(container_no=container_no).first()


def _task_payload(data):
    payload = {
        'task_type': (data.get('taskName') or data.get('task_type') or data.get('taskType') or '').strip(),
        'from_pos': (data.get('origin') or data.get('from_pos') or data.get('fromPos') or '').strip(),
        'to_pos': (data.get('destination') or data.get('to_pos') or data.get('toPos') or '').strip(),
        'remark': (data.get('yardSlot') or data.get('remark') or '').strip(),
        'status': (data.get('status') or 'pending').strip(),
        'priority': int(data.get('priority') or 3),
    }
    _normalize_transfer_flow(payload)
    return payload


def _slot_to_transfer_point(slot_text):
    if not slot_text or '/' not in slot_text:
        return ''
    yard_name = slot_text.split('/', 1)[0].strip()
    return f'{yard_name}\u8f6c\u8fd0\u70b9' if yard_name else ''


def _append_final_slot_remark(remark, slot_text):
    final_text = f'\u6700\u7ec8\u7bb1\u4f4d {slot_text}'
    if final_text in (remark or ''):
        return remark
    return f'{final_text}\uff1b{remark}' if remark else final_text


def _normalize_transfer_flow(payload):
    task_type = payload['task_type']
    destination = payload['to_pos']
    transfer_point = _slot_to_transfer_point(destination)

    if 'AGV' in task_type and transfer_point:
        payload['to_pos'] = transfer_point
        payload['remark'] = _append_final_slot_remark(payload['remark'], destination)
        return

    if ('\u573a\u6865' in task_type or '\u5165\u5806' in task_type) and transfer_point:
        if not payload['from_pos'] or payload['from_pos'] == destination or '/' in payload['from_pos']:
            payload['from_pos'] = transfer_point


@task_bp.route('', methods=['GET'])
def list_tasks():
    tasks = Task.query.order_by(Task.id.desc()).all()
    if reconcile_completed_stage_tasks(tasks):
        db.session.commit()
        tasks = Task.query.order_by(Task.id.desc()).all()
    return jsonify([task.to_dict() for task in tasks])


@task_bp.route('', methods=['POST'])
def create_task():
    data = request.get_json(silent=True) or {}
    payload = _task_payload(data)
    if not payload['task_type']:
        return jsonify({"message": "\u7f3a\u5c11\u4efb\u52a1\u540d\u79f0"}), 400

    container = _resolve_container(data)
    now = _now()
    task = Task(
        task_no=data.get('taskNo') or data.get('task_no') or _next_task_no(),
        container_id=container.id if container else None,
        created_at=now,
        updated_at=now,
        **payload,
    )
    error = validate_task_transition(task)
    if error:
        return jsonify({"message": error}), 400
    db.session.add(task)
    if task.normalized_status() == 'completed':
        task.end_time = task.end_time or task.updated_at
        sync_container_after_task(task)
    db.session.commit()
    return jsonify({"message": "\u65b0\u589e\u4f5c\u4e1a\u5355\u6210\u529f", "data": task.to_dict()}), 201


@task_bp.route('/<int:task_id>', methods=['PUT'])
def update_task(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.get_json(silent=True) or {}
    payload = _task_payload(data)
    container = _resolve_container(data)

    task.task_type = payload['task_type'] or task.task_type
    task.from_pos = payload['from_pos']
    task.to_pos = payload['to_pos']
    task.remark = payload['remark']
    task.status = payload['status'] or task.status
    task.priority = payload['priority']
    task.container_id = container.id if container else task.container_id
    task.updated_at = _now()
    error = validate_task_transition(task)
    if error:
        db.session.rollback()
        return jsonify({"message": error}), 400
    if task.normalized_status() == 'completed':
        task.end_time = task.end_time or task.updated_at
        sync_container_after_task(task)
    db.session.commit()
    return jsonify({"message": "\u4fee\u6539\u4f5c\u4e1a\u5355\u6210\u529f", "data": task.to_dict()})


@task_bp.route('/<int:task_id>/next_status', methods=['PUT'])
def next_status(task_id):
    task = Task.query.get_or_404(task_id)
    flow = {
        'pending': 'in-progress',
        'in-progress': 'completed',
        '\u672a\u5f00\u59cb': 'in-progress',
        '\u8fdb\u884c\u4e2d': 'completed',
    }
    next_task_status = flow.get(task.status, task.status)
    error = validate_task_transition(task, next_task_status)
    if error:
        return jsonify({"message": error}), 400
    task.status = next_task_status
    task.updated_at = _now()
    if task.status == 'in-progress' and not task.start_time:
        task.start_time = task.updated_at
    if task.status == 'completed':
        task.end_time = task.updated_at
        equipment = Equipment.query.get(task.equipment_id) if task.equipment_id else None
        if equipment:
            equipment.status = '\u7a7a\u95f2'
            equipment.current_task_id = None
            equipment.updated_at = task.updated_at
        sync_container_after_task(task)
    db.session.commit()
    return jsonify({"message": "\u4efb\u52a1\u72b6\u6001\u5df2\u66f4\u65b0", "data": task.to_dict()})


@task_bp.route('/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return jsonify({"message": "\u5220\u9664\u4f5c\u4e1a\u5355\u6210\u529f"})
