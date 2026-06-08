from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import or_

from Container.models.container_model import (
    Container,
    CustomsRelease,
    ExceptionRecord,
    GateTransaction,
    PickupAppointment,
    Task,
    db,
)


import_bp = Blueprint('import_bp', __name__, url_prefix='/api/import')

STATUS_IN_YARD = '堆场存储'
STATUS_IN_YARD_ALT = '在场'
STATUS_WAIT_PICKUP = '等待提箱'
STATUS_LOADED_TRUCK = '已装车待出闸'
STATUS_DEPARTED = '离港'
CUSTOMS_RELEASED = '已放行'
APPOINTMENT_ACTIVE = ('待确认', '已确认', '已进闸', '已提箱')


def _now():
    return datetime.now()


def _format_dt(value=None):
    return (value or _now()).strftime('%Y-%m-%d %H:%M:%S')


def _parse_dt(value):
    if not value:
        return None
    text = str(value).strip()
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M:%S', '%Y/%m/%d %H:%M'):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _next_no(prefix):
    return f'{prefix}-{_now().strftime("%Y%m%d%H%M%S%f")[:-3]}'


def _resolve_container(data):
    container_id = data.get('containerId') or data.get('container_id')
    if container_id:
        return Container.query.get(container_id)
    container_no = (data.get('containerNo') or data.get('container_no') or '').strip()
    if container_no:
        return Container.query.filter_by(container_no=container_no).first()
    return None


def _find_appointment(data):
    appointment_no = (data.get('appointmentNo') or data.get('appointment_no') or '').strip()
    if appointment_no:
        return PickupAppointment.query.filter_by(appointment_no=appointment_no).first()

    truck_plate = (data.get('truckPlate') or data.get('truck_plate') or '').strip()
    container_no = (data.get('containerNo') or data.get('container_no') or '').strip()
    if not truck_plate and not container_no:
        return None

    query = PickupAppointment.query.filter(PickupAppointment.status.in_(APPOINTMENT_ACTIVE))
    if truck_plate:
        query = query.filter(PickupAppointment.truck_plate == truck_plate)
    if container_no:
        query = query.join(Container, Container.id == PickupAppointment.container_id).filter(Container.container_no == container_no)
    return query.order_by(PickupAppointment.id.desc()).first()


def _record_exception(object_type, object_id, exception_type, description):
    record = ExceptionRecord(
        object_type=object_type,
        object_id=object_id,
        exception_type=exception_type,
        description=description,
        status='待处理',
        created_at=_format_dt(),
    )
    db.session.add(record)
    return record


def _record_gate(appointment, gate_type, truck_plate, container_no, result, reason='', ticket_no=''):
    record = GateTransaction(
        appointment_id=appointment.id if appointment else None,
        gate_type=gate_type,
        truck_plate=truck_plate,
        container_no=container_no,
        check_result=result,
        block_reason=reason,
        ticket_no=ticket_no,
        created_at=_format_dt(),
    )
    db.session.add(record)
    return record


def _appointment_time_valid(appointment):
    start = _parse_dt(appointment.time_window_start)
    end = _parse_dt(appointment.time_window_end)
    if not start or not end:
        return True, ''
    grace = timedelta(minutes=30)
    now = _now()
    if now < start - grace:
        return False, '未到预约时间窗'
    if now > end + grace:
        return False, '预约时间窗已过期'
    return True, ''


def _container_available_for_pickup(container):
    if not container:
        return False, '集装箱不存在'
    if container.status not in (STATUS_IN_YARD, STATUS_IN_YARD_ALT, STATUS_WAIT_PICKUP):
        return False, f'箱子当前状态为“{container.status}”，不允许预约提箱'
    if (container.customs_status or '未放行') != CUSTOMS_RELEASED:
        return False, '海关未放行，禁止预约提箱'
    if (container.damage_status or '正常') not in ('正常', '轻微残损'):
        return False, f'箱子残损状态为“{container.damage_status}”，需要异常处理'
    existing = PickupAppointment.query.filter(
        PickupAppointment.container_id == container.id,
        PickupAppointment.status.in_(APPOINTMENT_ACTIVE),
    ).first()
    if existing:
        return False, f'该箱已有未完成预约：{existing.appointment_no}'
    return True, ''


@import_bp.route('/overview', methods=['GET'])
def overview():
    containers = Container.query.all()
    appointments = PickupAppointment.query.all()
    gates = GateTransaction.query.order_by(GateTransaction.id.desc()).limit(20).all()
    exceptions = ExceptionRecord.query.order_by(ExceptionRecord.id.desc()).limit(20).all()

    return jsonify({
        "stats": {
            "inYard": sum(1 for item in containers if item.status in (STATUS_IN_YARD, STATUS_IN_YARD_ALT, STATUS_WAIT_PICKUP)),
            "customsReleased": sum(1 for item in containers if (item.customs_status or '') == CUSTOMS_RELEASED),
            "waitingRelease": sum(1 for item in containers if (item.customs_status or '未放行') != CUSTOMS_RELEASED),
            "activeAppointments": sum(1 for item in appointments if item.status in APPOINTMENT_ACTIVE),
            "gateBlocks": sum(1 for item in GateTransaction.query.all() if item.check_result == '拦截'),
            "openExceptions": sum(1 for item in ExceptionRecord.query.all() if item.status != '已关闭'),
        },
        "appointments": [item.to_dict() for item in sorted(appointments, key=lambda x: x.id, reverse=True)[:30]],
        "gateTransactions": [item.to_dict() for item in gates],
        "exceptions": [item.to_dict() for item in exceptions],
    })


@import_bp.route('/customs/releases', methods=['GET'])
def list_customs_releases():
    releases = CustomsRelease.query.order_by(CustomsRelease.id.desc()).all()
    return jsonify([item.to_dict() for item in releases])


@import_bp.route('/customs/release', methods=['POST'])
def update_customs_release():
    data = request.get_json(silent=True) or {}
    container = _resolve_container(data)
    if not container:
        return jsonify({"message": "集装箱不存在"}), 404

    customs_status = (data.get('customsStatus') or data.get('customs_status') or CUSTOMS_RELEASED).strip()
    inspection_status = (data.get('inspectionStatus') or data.get('inspection_status') or '已通过').strip()
    release_no = (data.get('releaseNo') or data.get('release_no') or _next_no('REL')).strip()
    hold_reason = (data.get('holdReason') or data.get('hold_reason') or '').strip()
    now = _format_dt()

    release = CustomsRelease.query.filter_by(container_id=container.id).first()
    if release is None:
        release = CustomsRelease(container_id=container.id)
        db.session.add(release)
    release.customs_status = customs_status
    release.inspection_status = inspection_status
    release.release_no = release_no
    release.released_at = now if customs_status == CUSTOMS_RELEASED else None
    release.hold_reason = hold_reason
    release.updated_at = now

    container.customs_status = customs_status
    if customs_status != CUSTOMS_RELEASED:
        _record_exception('container', container.id, '监管未放行', hold_reason or '箱子未获得海关/商检放行')

    db.session.commit()
    return jsonify({"message": "放行状态已更新", "data": release.to_dict(), "container": container.to_dict()})


@import_bp.route('/appointments', methods=['GET'])
def list_appointments():
    appointments = PickupAppointment.query.order_by(PickupAppointment.id.desc()).all()
    return jsonify([item.to_dict() for item in appointments])


@import_bp.route('/appointments', methods=['POST'])
def create_appointment():
    data = request.get_json(silent=True) or {}
    container = _resolve_container(data)
    ok, reason = _container_available_for_pickup(container)
    if not ok:
        if container:
            _record_exception('container', container.id, '预约校验失败', reason)
            db.session.commit()
        return jsonify({"message": reason}), 400

    truck_plate = (data.get('truckPlate') or data.get('truck_plate') or '').strip().upper()
    if not truck_plate:
        return jsonify({"message": "车牌号不能为空"}), 400

    start = (data.get('timeWindowStart') or data.get('time_window_start') or '').strip()
    end = (data.get('timeWindowEnd') or data.get('time_window_end') or '').strip()
    if not start or not end:
        return jsonify({"message": "预约时间窗不能为空"}), 400
    if _parse_dt(start) and _parse_dt(end) and _parse_dt(start) >= _parse_dt(end):
        return jsonify({"message": "预约开始时间必须早于结束时间"}), 400

    now = _format_dt()
    appointment = PickupAppointment(
        appointment_no=data.get('appointmentNo') or data.get('appointment_no') or _next_no('APT'),
        container_id=container.id,
        truck_plate=truck_plate,
        driver_name=(data.get('driverName') or data.get('driver_name') or '').strip(),
        driver_phone=(data.get('driverPhone') or data.get('driver_phone') or '').strip(),
        customer=(data.get('customer') or '').strip(),
        time_window_start=start,
        time_window_end=end,
        status='已确认',
        created_at=now,
        updated_at=now,
        remark=(data.get('remark') or '').strip(),
    )
    db.session.add(appointment)
    db.session.flush()

    container.appointment_status = '已预约锁定'
    container.locked_by_appointment_id = appointment.id
    if container.status in (STATUS_IN_YARD, STATUS_IN_YARD_ALT):
        container.status = STATUS_WAIT_PICKUP

    db.session.commit()
    return jsonify({"message": "提箱预约已创建", "data": appointment.to_dict()}), 201


@import_bp.route('/appointments/<int:appointment_id>/cancel', methods=['PUT'])
def cancel_appointment(appointment_id):
    appointment = PickupAppointment.query.get_or_404(appointment_id)
    if appointment.status not in ('待确认', '已确认'):
        return jsonify({"message": f"预约状态为“{appointment.status}”，不能取消"}), 400

    appointment.status = '已取消'
    appointment.updated_at = _format_dt()
    container = appointment.container
    if container and container.locked_by_appointment_id == appointment.id:
        container.locked_by_appointment_id = None
        container.appointment_status = '未预约'
        if container.status == STATUS_WAIT_PICKUP:
            container.status = STATUS_IN_YARD
    db.session.commit()
    return jsonify({"message": "预约已取消", "data": appointment.to_dict()})


@import_bp.route('/appointments/<int:appointment_id>/pickup', methods=['POST'])
def complete_yard_pickup(appointment_id):
    appointment = PickupAppointment.query.get_or_404(appointment_id)
    container = appointment.container
    if not container:
        return jsonify({"message": "预约未绑定集装箱"}), 400
    if appointment.status != '已进闸':
        return jsonify({"message": "车辆未进闸，不能执行堆场提箱"}), 400

    now = _format_dt()
    task = Task(
        task_no=_next_no('PICK'),
        task_type='堆场提箱',
        container_id=container.id,
        from_pos=f'{container.yard or ""}/{container.area or ""}/列{container.column or ""}/层{container.layer or ""}',
        to_pos=appointment.truck_plate,
        status='completed',
        priority=2,
        start_time=now,
        end_time=now,
        created_at=now,
        updated_at=now,
        remark=f'预约 {appointment.appointment_no} 提箱完成',
    )
    db.session.add(task)

    appointment.status = '已提箱'
    appointment.updated_at = now
    container.status = STATUS_LOADED_TRUCK
    container.appointment_status = '已提箱'
    db.session.commit()
    return jsonify({"message": "堆场提箱已完成", "data": appointment.to_dict(), "task": task.to_dict()})


@import_bp.route('/gate/in', methods=['POST'])
def gate_in():
    data = request.get_json(silent=True) or {}
    appointment = _find_appointment(data)
    truck_plate = (data.get('truckPlate') or data.get('truck_plate') or (appointment.truck_plate if appointment else '')).strip().upper()
    container_no = (data.get('containerNo') or data.get('container_no') or (appointment.container.container_no if appointment and appointment.container else '')).strip()

    if not appointment:
        reason = '未找到有效预约'
        _record_gate(None, '进闸', truck_plate, container_no, '拦截', reason)
        _record_exception('gate', None, '闸口拦截', reason)
        db.session.commit()
        return jsonify({"message": reason}), 400

    container = appointment.container
    reason = ''
    if appointment.status != '已确认':
        reason = f'预约状态为“{appointment.status}”，不能进闸'
    elif truck_plate != appointment.truck_plate:
        reason = '车牌与预约不一致'
    elif not container or container.container_no != container_no:
        reason = '箱号与预约不一致'
    elif (container.customs_status or '未放行') != CUSTOMS_RELEASED:
        reason = '海关未放行，闸口拦截'
    else:
        valid, time_reason = _appointment_time_valid(appointment)
        if not valid:
            reason = time_reason

    if reason:
        _record_gate(appointment, '进闸', truck_plate, container_no, '拦截', reason)
        _record_exception('appointment', appointment.id, '闸口进场失败', reason)
        db.session.commit()
        return jsonify({"message": reason, "appointment": appointment.to_dict()}), 400

    ticket_no = _next_no('TICKET')
    appointment.status = '已进闸'
    appointment.updated_at = _format_dt()
    container.appointment_status = '已进闸'
    gate_record = _record_gate(appointment, '进闸', truck_plate, container_no, '通过', ticket_no=ticket_no)
    db.session.commit()
    return jsonify({"message": "闸口进场通过", "ticketNo": ticket_no, "data": gate_record.to_dict(), "appointment": appointment.to_dict()})


@import_bp.route('/gate/out', methods=['POST'])
def gate_out():
    data = request.get_json(silent=True) or {}
    appointment = _find_appointment(data)
    truck_plate = (data.get('truckPlate') or data.get('truck_plate') or (appointment.truck_plate if appointment else '')).strip().upper()
    container_no = (data.get('containerNo') or data.get('container_no') or (appointment.container.container_no if appointment and appointment.container else '')).strip()

    if not appointment:
        reason = '未找到有效预约'
        _record_gate(None, '出闸', truck_plate, container_no, '拦截', reason)
        _record_exception('gate', None, '闸口拦截', reason)
        db.session.commit()
        return jsonify({"message": reason}), 400

    container = appointment.container
    reason = ''
    if appointment.status != '已提箱':
        reason = f'预约状态为“{appointment.status}”，必须完成堆场提箱后才能出闸'
    elif truck_plate != appointment.truck_plate:
        reason = '车牌与预约不一致'
    elif not container or container.container_no != container_no:
        reason = '车载箱号与预约不一致'
    elif (container.customs_status or '未放行') != CUSTOMS_RELEASED:
        reason = '海关放行状态异常，禁止出闸'

    if reason:
        _record_gate(appointment, '出闸', truck_plate, container_no, '拦截', reason)
        _record_exception('appointment', appointment.id, '闸口出场失败', reason)
        db.session.commit()
        return jsonify({"message": reason, "appointment": appointment.to_dict()}), 400

    appointment.status = '已出闸'
    appointment.updated_at = _format_dt()
    container.status = STATUS_DEPARTED
    container.appointment_status = '已出闸'
    container.locked_by_appointment_id = None
    gate_record = _record_gate(appointment, '出闸', truck_plate, container_no, '通过', ticket_no=_next_no('OUT'))
    db.session.commit()
    return jsonify({"message": "闸口出场通过，集装箱已离港", "data": gate_record.to_dict(), "appointment": appointment.to_dict()})


@import_bp.route('/exceptions', methods=['GET'])
def list_exceptions():
    records = ExceptionRecord.query.order_by(ExceptionRecord.id.desc()).all()
    return jsonify([item.to_dict() for item in records])


@import_bp.route('/exceptions', methods=['POST'])
def create_exception():
    data = request.get_json(silent=True) or {}
    record = _record_exception(
        data.get('objectType') or data.get('object_type') or 'manual',
        data.get('objectId') or data.get('object_id'),
        (data.get('exceptionType') or data.get('exception_type') or '人工异常').strip(),
        (data.get('description') or '').strip(),
    )
    db.session.commit()
    return jsonify({"message": "异常已登记", "data": record.to_dict()}), 201


@import_bp.route('/exceptions/<int:record_id>/resolve', methods=['PUT'])
def resolve_exception(record_id):
    record = ExceptionRecord.query.get_or_404(record_id)
    data = request.get_json(silent=True) or {}
    record.status = '已关闭'
    record.handler = (data.get('handler') or '调度员').strip()
    record.resolution = (data.get('resolution') or '已处理').strip()
    record.resolved_at = _format_dt()
    db.session.commit()
    return jsonify({"message": "异常已关闭", "data": record.to_dict()})


@import_bp.route('/containers/pickup-ready', methods=['GET'])
def pickup_ready_containers():
    containers = Container.query.filter(
        Container.status.in_((STATUS_IN_YARD, STATUS_IN_YARD_ALT, STATUS_WAIT_PICKUP)),
        or_(Container.locked_by_appointment_id == None, Container.appointment_status == '未预约'),
    ).order_by(Container.id.desc()).all()
    return jsonify([item.to_dict() for item in containers])
