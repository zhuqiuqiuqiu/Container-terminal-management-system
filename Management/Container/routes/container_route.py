from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from Container.models.container_model import Container, Yard, db
from Container.routes.yard_route import is_dangerous_yard


'''把所有操作变成HTTP接口 -API'''
container_bp = Blueprint('container_bp', __name__)  #创建一个集装箱功能模块

STATUS_FLOW = {
    "\u5728\u8239\u4e0a": "\u5df2\u5378\u8239",
    "\u5728\u8239\u4e2d": "\u5df2\u5378\u8239",
    "\u5df2\u5378\u8239": "\u8f6c\u8fd0\u4e2d",
    "\u8f6c\u8fd0\u4e2d": "\u5806\u573a\u5b58\u50a8",
    "\u5806\u573a\u5b58\u50a8": "\u7b49\u5f85\u63d0\u7bb1",
    "\u5728\u573a": "\u7b49\u5f85\u63d0\u7bb1",
    "\u7b49\u5f85\u63d0\u7bb1": "\u5df2\u88c5\u8f66\u5f85\u51fa\u95f8",
    "\u5df2\u88c5\u8f66\u5f85\u51fa\u95f8": "\u79bb\u6e2f",
    "\u5728\u5806": "\u5f85\u88c5\u8239",
    "\u5f85\u88c5\u8239": "\u79bb\u6e2f",
}


def _validate_dangerous_yard(container):
    if not container.yard:
        return None
    yard = Yard.query.filter_by(yard_name=container.yard).first()
    if not yard:
        return None
    if container.is_dangerous and not is_dangerous_yard(yard):
        return '\u5371\u9669\u54c1\u96c6\u88c5\u7bb1\u5fc5\u987b\u5b58\u653e\u5728\u5371\u9669\u54c1\u5806\u573a'
    if not container.is_dangerous and is_dangerous_yard(yard):
        return '\u5371\u9669\u54c1\u5806\u573a\u4ec5\u7528\u4e8e\u5b58\u653e\u5371\u9669\u54c1\u96c6\u88c5\u7bb1'
    return None


@container_bp.route('/containers', methods=['POST'])
def create_container():
    '''创建一个集装箱'''
    data = request.get_json() or {}

    required_fields = {
        'container_no': data.get('container_no') or data.get('containerNo'),
        'container_type': data.get('container_type') or data.get('containerType'),
    }
    missing_fields = [field for field, value in required_fields.items() if not value]
    if missing_fields:
        return jsonify({
            "message": "\u7f3a\u5c11\u5fc5\u586b\u5b57\u6bb5",
            "fields": missing_fields
        }), 400

    container = Container(
        container_no=data.get('container_no') or data.get('containerNo'),
        container_type=data.get('container_type') or data.get('containerType'),
        is_full=data.get('is_full', data.get('loadStatus') == '\u91cd\u7bb1'),
        is_dangerous=data.get('is_dangerous', data.get('isDangerous', False)),
        is_refrigerated=data.get('is_refrigerated', data.get('isReefer', False)),
        yard=data.get('yard'),
        area=data.get('area') or data.get('zone'),
        column=data.get('column') if data.get('column') is not None else data.get('row'),
        layer=data.get('layer') if data.get('layer') is not None else data.get('tier'),
        status=data.get('status', '\u5728\u8239\u4e0a'),
        customs_status=data.get('customs_status') or data.get('customsStatus') or '\u672a\u653e\u884c',
        appointment_status=data.get('appointment_status') or data.get('appointmentStatus') or '\u672a\u9884\u7ea6',
        damage_status=data.get('damage_status') or data.get('damageStatus') or '\u6b63\u5e38',
    )

    error = _validate_dangerous_yard(container)
    if error:
        return jsonify({"message": error}), 400

    db.session.add(container)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "\u7bb1\u53f7\u5df2\u5b58\u5728"}), 409

    return jsonify({
        "message": "\u65b0\u589e\u6210\u529f",
        "data": container.to_dict()
    }), 201


@container_bp.route('/containers', methods=['GET'])
def get_all_containers():
    '''查询所有集装箱'''
    containers = Container.query.order_by(Container.id).all()
    return jsonify([container.to_dict() for container in containers])



@container_bp.route('/containers/<int:id>', methods=['GET'])
def get_container(id):
    '''查询单个集装箱的信息'''
    container = Container.query.get_or_404(id)
    return jsonify(container.to_dict())



@container_bp.route('/containers/<int:id>', methods=['PUT'])
def update_container(id):
    '''修改箱子基本信息'''
    container = Container.query.get_or_404(id)
    data = request.get_json() or {}

    container.container_no = data.get('container_no', container.container_no)
    container.container_no = data.get('containerNo', container.container_no)
    container.container_type = data.get('container_type') or data.get('containerType') or container.container_type
    container.is_full = data.get('is_full', data.get('loadStatus') == '\u91cd\u7bb1' if 'loadStatus' in data else container.is_full)
    container.is_dangerous = data.get('is_dangerous', data.get('isDangerous', container.is_dangerous))
    container.is_refrigerated = data.get('is_refrigerated', data.get('isReefer', container.is_refrigerated))
    container.yard = data.get('yard', container.yard)
    container.area = data.get('area') or data.get('zone') or container.area
    container.column = data.get('column') if data.get('column') is not None else data.get('row', container.column)
    container.layer = data.get('layer') if data.get('layer') is not None else data.get('tier', container.layer)
    container.status = data.get('status', container.status)
    container.customs_status = data.get('customs_status') or data.get('customsStatus') or container.customs_status
    container.appointment_status = data.get('appointment_status') or data.get('appointmentStatus') or container.appointment_status
    container.damage_status = data.get('damage_status') or data.get('damageStatus') or container.damage_status
    error = _validate_dangerous_yard(container)
    if error:
        return jsonify({"message": error}), 400

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "\u7bb1\u53f7\u5df2\u5b58\u5728"}), 409

    return jsonify({
        "message": "\u4fee\u6539\u6210\u529f",
        "data": container.to_dict()
    })


@container_bp.route('/containers/<int:id>/location', methods=['PUT'])
def update_location(id):
    '''修改箱子的位置，更新位置'''
    container = Container.query.get_or_404(id)
    data = request.get_json() or {}

    container.yard = data.get('yard')
    container.area = data.get('area') or data.get('zone')
    container.column = data.get('column') if data.get('column') is not None else data.get('row')
    container.layer = data.get('layer') if data.get('layer') is not None else data.get('tier')

    db.session.commit()

    return jsonify({
        "message": "\u4f4d\u7f6e\u66f4\u65b0\u6210\u529f",
        "data": container.to_dict()
    })


@container_bp.route('/containers/<int:id>/next_status', methods=['PUT'])
def next_status(id):
    '''状态流转'''
    container = Container.query.get_or_404(id)
    current_status = container.status

    if current_status not in STATUS_FLOW:
        return jsonify({"message": "\u8be5\u96c6\u88c5\u7bb1\u5df2\u79bb\u6e2f"}), 400

    next_state = STATUS_FLOW[current_status]
    container.status = next_state
    db.session.commit()

    return jsonify({
        "message": "\u72b6\u6001\u66f4\u65b0\u6210\u529f",
        "old_status": current_status,
        "new_status": next_state
    })


@container_bp.route('/containers/<int:id>', methods=['DELETE'])
def delete_container(id):
    '''删除集装箱，通过ID删除'''
    container = Container.query.get_or_404(id)

    db.session.delete(container)
    db.session.commit()

    return jsonify({"message": "\u5220\u9664\u6210\u529f"})
