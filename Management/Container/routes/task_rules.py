from Container.models.container_model import Container, Task


STATUS_PENDING = 'pending'
STATUS_IN_PROGRESS = 'in-progress'
STATUS_COMPLETED = 'completed'

CONTAINER_ON_SHIP = '在船上'
CONTAINER_UNLOADED = '已卸船'
CONTAINER_TRANSFERRING = '转运中'
CONTAINER_IN_YARD = '堆场存储'
CONTAINER_WAIT_PICKUP = '等待提箱'
CONTAINER_LOADED_TRUCK = '已装车待出闸'
CONTAINER_DEPARTED = '离港'

ADVANCED_CONTAINER_STATUSES = {
    CONTAINER_UNLOADED,
    CONTAINER_TRANSFERRING,
    CONTAINER_IN_YARD,
    CONTAINER_WAIT_PICKUP,
    CONTAINER_LOADED_TRUCK,
    CONTAINER_DEPARTED,
}


def normalize_task_status(status):
    mapping = {
        'processing': STATUS_IN_PROGRESS,
        '进行中': STATUS_IN_PROGRESS,
        '未开始': STATUS_PENDING,
        '已完成': STATUS_COMPLETED,
    }
    return mapping.get(status, status or STATUS_PENDING)


def task_stage(task):
    task_type = task.task_type or ''
    if 'AGV' in task_type or '转运' in task_type:
        return 'agv'
    if '入堆' in task_type or '场桥' in task_type:
        return 'yard'
    if '卸船' in task_type or '岸桥' in task_type:
        return 'unload'
    if '提箱' in task_type:
        return 'pickup'
    return ''


def _container_tasks(container_id, exclude_task_id=None):
    query = Task.query.filter(Task.container_id == container_id)
    if exclude_task_id:
        query = query.filter(Task.id != exclude_task_id)
    return query.all()


def _stage_tasks(container_id, stage, exclude_task_id=None):
    return [
        task for task in _container_tasks(container_id, exclude_task_id)
        if task_stage(task) == stage
    ]


def _has_completed_stage(tasks):
    return any(normalize_task_status(task.status) == STATUS_COMPLETED for task in tasks)


def _unload_done(container, current_task=None):
    if not container:
        return False
    exclude_id = current_task.id if current_task else None
    unload_tasks = _stage_tasks(container.id, 'unload', exclude_id)
    if unload_tasks:
        return _has_completed_stage(unload_tasks)
    if container.status in ADVANCED_CONTAINER_STATUSES:
        return True
    return False


def _agv_done(container, current_task=None):
    if not container:
        return False
    exclude_id = current_task.id if current_task else None
    agv_tasks = _stage_tasks(container.id, 'agv', exclude_id)
    if agv_tasks:
        return _has_completed_stage(agv_tasks)
    if container.status in {CONTAINER_TRANSFERRING, CONTAINER_IN_YARD, CONTAINER_WAIT_PICKUP, CONTAINER_LOADED_TRUCK, CONTAINER_DEPARTED}:
        return True
    return False


def validate_task_transition(task, target_status=None):
    status = normalize_task_status(target_status if target_status is not None else task.status)
    if status not in {STATUS_IN_PROGRESS, STATUS_COMPLETED}:
        return None

    stage = task_stage(task)
    if stage not in {'agv', 'yard'}:
        return None

    container = task.container
    if not container:
        return None

    if not _unload_done(container, task):
        return f'集装箱 {container.container_no} 的卸船作业尚未完成，不能开始或完成后续作业'

    if stage == 'yard' and not _agv_done(container, task):
        return f'集装箱 {container.container_no} 的 AGV 转运尚未完成，不能开始或完成场桥入堆'

    return None


def sync_peer_stage_tasks(task):
    container = task.container
    stage = task_stage(task)
    if not container or not stage or normalize_task_status(task.status) != STATUS_COMPLETED:
        return 0

    changed = 0
    for peer in _stage_tasks(container.id, stage, task.id):
        if normalize_task_status(peer.status) == STATUS_COMPLETED:
            continue
        peer.status = STATUS_COMPLETED
        peer.start_time = peer.start_time or task.start_time
        peer.end_time = peer.end_time or task.end_time
        peer.actual_time = peer.actual_time or task.actual_time
        peer.updated_at = task.updated_at
        changed += 1
    return changed


def reconcile_completed_stage_tasks(tasks):
    changed = 0
    for task in tasks:
        if normalize_task_status(task.status) == STATUS_COMPLETED:
            changed += sync_peer_stage_tasks(task)
    return changed


def sync_container_after_task(task):
    container = task.container
    if not container or normalize_task_status(task.status) != STATUS_COMPLETED:
        return

    sync_peer_stage_tasks(task)
    stage = task_stage(task)
    if stage == 'unload':
        container.status = CONTAINER_UNLOADED
    elif stage == 'agv':
        container.status = CONTAINER_TRANSFERRING
    elif stage == 'yard':
        container.status = CONTAINER_IN_YARD
        slot = task.to_pos or task.remark or ''
        parts = [part.strip() for part in slot.replace('；', '/').split('/') if part.strip()]
        if parts:
            container.yard = parts[0]
        if len(parts) > 1:
            container.area = parts[1]
    elif stage == 'pickup':
        container.status = CONTAINER_LOADED_TRUCK
        container.appointment_status = '已提箱'
