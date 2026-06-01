from datetime import datetime

from flask import Blueprint, jsonify, request

from Container.models.container_model import Container, Task, db


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
    return {
        'task_type': (data.get('taskName') or data.get('task_type') or data.get('taskType') or '').strip(),
        'from_pos': (data.get('origin') or data.get('from_pos') or data.get('fromPos') or '').strip(),
        'to_pos': (data.get('destination') or data.get('to_pos') or data.get('toPos') or '').strip(),
        'remark': (data.get('yardSlot') or data.get('remark') or '').strip(),
        'status': (data.get('status') or 'pending').strip(),
        'priority': int(data.get('priority') or 3),
    }


@task_bp.route('', methods=['GET'])
def list_tasks():
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
    db.session.add(task)
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
    task.status = flow.get(task.status, task.status)
    task.updated_at = _now()
    if task.status == 'in-progress' and not task.start_time:
        task.start_time = task.updated_at
    if task.status == 'completed':
        task.end_time = task.updated_at
    db.session.commit()
    return jsonify({"message": "\u4efb\u52a1\u72b6\u6001\u5df2\u66f4\u65b0", "data": task.to_dict()})


@task_bp.route('/<int:task_id>', methods=['DELETE'])
def delete_task(task_id):
    task = Task.query.get_or_404(task_id)
    db.session.delete(task)
    db.session.commit()
    return jsonify({"message": "\u5220\u9664\u4f5c\u4e1a\u5355\u6210\u529f"})
