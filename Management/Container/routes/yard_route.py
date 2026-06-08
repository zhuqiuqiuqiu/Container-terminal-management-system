from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from Container.models.container_model import Container, Ship, Yard, db


yard_bp = Blueprint('yard_bp', __name__, url_prefix='/yards')


def _zones_to_text(zones):
    if isinstance(zones, list):
        return ','.join(str(zone).strip() for zone in zones if str(zone).strip())
    if isinstance(zones, str):
        return zones
    return 'Zone-1,Zone-2,Zone-3,Zone-4'


def _validate_slot(yard, area, column, layer):
    if area not in yard.zone_list:
        return f'\u533a\u57df {area} \u4e0d\u5c5e\u4e8e\u5806\u573a {yard.yard_name}'
    if not isinstance(column, int) or column < 1 or column > yard.total_rows:
        return f'\u5217\u53f7\u5fc5\u987b\u5728 1-{yard.total_rows} \u4e4b\u95f4'
    if not isinstance(layer, int) or layer < 1 or layer > yard.total_tiers:
        return f'\u5c42\u53f7\u5fc5\u987b\u5728 1-{yard.total_tiers} \u4e4b\u95f4'
    return None


def _slot_occupied(yard_name, area, column, layer, except_container_id=None):
    query = Container.query.filter(
        Container.yard == yard_name,
        Container.area == area,
        Container.column == column,
        Container.layer == layer,
        Container.status != '\u79bb\u6e2f'
    )
    if except_container_id is not None:
        query = query.filter(Container.id != except_container_id)
    return query.first()


def is_dangerous_yard(yard):
    text = (yard.yard_name or '') + (yard.usage_type or '')
    return '\u5371\u9669' in text


def _yard_matches_container(yard, container):
    name = (yard.yard_name or '') + (yard.usage_type or '')
    if container.is_dangerous:
        return is_dangerous_yard(yard)
    if is_dangerous_yard(yard):
        return False
    if container.is_refrigerated:
        return '\u51b7\u85cf' in name or '\u51b7' in name
    if container.is_full:
        return '\u91cd' in name or '\u8fdb\u53e3' in name or '\u7efc\u5408' in name
    return '\u7a7a' in name or '\u51fa\u53e3' in name or '\u7efc\u5408' in name


def _official_yard_names():
    return {yard.yard_name for yard in Yard.query.all()}


def find_best_slot_for_container(container, yards, occupied, ship_plan_counts):
    candidates = []
    for yard in yards:
        if yard.status not in ('\u542f\u7528', 'active'):
            continue
        if container.is_dangerous and not is_dangerous_yard(yard):
            continue
        if not container.is_dangerous and is_dangerous_yard(yard):
            continue
        used = sum(1 for key in occupied if key[0] == yard.yard_name)
        if used >= yard.total_capacity:
            continue
        for area in yard.zone_list:
            for column in range(1, yard.total_rows + 1):
                for layer in range(1, yard.total_tiers + 1):
                    key = (yard.yard_name, area, column, layer)
                    if key in occupied:
                        continue
                    score = 0
                    if _yard_matches_container(yard, container):
                        score += 120
                    score += ship_plan_counts.get((yard.yard_name, area), 0) * 30
                    score += max(0, 8 - abs(column - 4))
                    score += max(0, 6 - layer) * 2
                    if container.is_dangerous:
                        same_col_danger = any(
                            item[0] == yard.yard_name and item[1] == area and item[2] == column
                            for item in occupied
                        )
                        if not same_col_danger:
                            score += 10
                    candidates.append((score, yard, area, column, layer))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1].id, item[2], item[3], item[4]))
    return candidates[0][1:]


def _find_best_slot(container, yards, occupied, ship_plan_counts):
    return find_best_slot_for_container(container, yards, occupied, ship_plan_counts)


@yard_bp.route('', methods=['GET'])
def list_yards():
    """查询堆场列表，同时动态计算容量、已用位和剩余位。"""
    yards = Yard.query.order_by(Yard.id).all()
    return jsonify([yard.to_dict() for yard in yards])


@yard_bp.route('', methods=['POST'])
def create_yard():
    """新增堆场。容量由区域数量、最大列数、最大层数共同决定。"""
    data = request.get_json() or {}
    yard_name = data.get('yard_name') or data.get('yardName')
    if not yard_name:
        return jsonify({"message": "\u7f3a\u5c11\u5806\u573a\u540d\u79f0"}), 400

    yard = Yard(
        yard_name=yard_name,
        usage_type=data.get('usage_type') or data.get('usageType') or '\u7efc\u5408\u5806\u573a',
        code=data.get('code') or None,
        capacity=int(data.get('capacity') or data.get('total_capacity') or data.get('totalCapacity') or 240),
        db_total_capacity=int(data.get('total_capacity') or data.get('totalCapacity') or data.get('capacity') or 240),
        db_available_capacity=int(data.get('available_capacity') or data.get('availableCapacity') or data.get('capacity') or 240),
        address=data.get('address'),
        manager=data.get('manager'),
        contact_phone=data.get('contact_phone') or data.get('contactPhone'),
        status=data.get('status') or 'active',
    )
    db.session.add(yard)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "\u5806\u573a\u540d\u79f0\u5df2\u5b58\u5728"}), 409

    return jsonify({"message": "\u65b0\u589e\u5806\u573a\u6210\u529f", "data": yard.to_dict()}), 201


@yard_bp.route('/<int:yard_id>', methods=['PUT'])
def update_yard(yard_id):
    """修改堆场基础信息；已有箱位不会被自动挪动。"""
    yard = Yard.query.get_or_404(yard_id)
    data = request.get_json() or {}

    yard.yard_name = data.get('yard_name') or data.get('yardName') or yard.yard_name
    yard.usage_type = data.get('usage_type') or data.get('usageType') or yard.usage_type
    if 'code' in data:
        yard.code = data.get('code') or None
    yard.capacity = int(data.get('capacity') or yard.capacity or 0)
    yard.db_total_capacity = int(data.get('total_capacity') or data.get('totalCapacity') or yard.db_total_capacity or yard.capacity or 240)
    yard.db_available_capacity = max(yard.db_total_capacity - yard.used_capacity(), 0)
    yard.address = data.get('address', yard.address)
    yard.manager = data.get('manager', yard.manager)
    yard.contact_phone = data.get('contact_phone') or data.get('contactPhone') or yard.contact_phone
    yard.status = data.get('status') or yard.status

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "\u5806\u573a\u540d\u79f0\u5df2\u5b58\u5728"}), 409

    return jsonify({"message": "\u4fee\u6539\u5806\u573a\u6210\u529f", "data": yard.to_dict()})


@yard_bp.route('/<int:yard_id>', methods=['DELETE'])
def delete_yard(yard_id):
    """删除空堆场；如果仍有未离港集装箱占用，则拒绝删除。"""
    yard = Yard.query.get_or_404(yard_id)
    if yard.used_capacity() > 0:
        return jsonify({"message": "\u5806\u573a\u4ecd\u6709\u96c6\u88c5\u7bb1\u5360\u7528\uff0c\u4e0d\u80fd\u5220\u9664"}), 400

    db.session.delete(yard)
    db.session.commit()
    return jsonify({"message": "\u5220\u9664\u5806\u573a\u6210\u529f"})


@yard_bp.route('/assign', methods=['POST'])
def assign_container():
    """
    将集装箱移入指定堆场位置。

    关键业务规则：
    1. 堆场必须存在且启用。
    2. 目标区、列、层必须落在堆场定义范围内。
    3. 同一堆场/区/列/层在同一时间只能放一个未离港集装箱。
    4. 分配成功后，集装箱状态自动变为“堆场存储”。
    """
    data = request.get_json() or {}
    container_id = data.get('container_id') or data.get('containerId')
    yard_name = data.get('yard') or data.get('yard_name') or data.get('yardName')
    area = data.get('area') or data.get('zone')
    column = data.get('column') if data.get('column') is not None else data.get('row')
    layer = data.get('layer') if data.get('layer') is not None else data.get('tier')

    if not all([container_id, yard_name, area, column, layer]):
        return jsonify({"message": "\u7f3a\u5c11\u7bb1ID\u6216\u76ee\u6807\u7bb1\u4f4d\u4fe1\u606f"}), 400

    container = Container.query.get_or_404(container_id)
    yard = Yard.query.filter_by(yard_name=yard_name).first()
    if yard is None:
        return jsonify({"message": "\u5806\u573a\u4e0d\u5b58\u5728"}), 404
    if yard.status not in ('\u542f\u7528', 'active'):
        return jsonify({"message": "\u5806\u573a\u672a\u542f\u7528"}), 400
    if container.is_dangerous and not is_dangerous_yard(yard):
        return jsonify({"message": "\u5371\u9669\u54c1\u96c6\u88c5\u7bb1\u5fc5\u987b\u5206\u914d\u5230\u5371\u9669\u54c1\u5806\u573a"}), 400
    if not container.is_dangerous and is_dangerous_yard(yard):
        return jsonify({"message": "\u5371\u9669\u54c1\u5806\u573a\u4ec5\u7528\u4e8e\u5b58\u653e\u5371\u9669\u54c1\u96c6\u88c5\u7bb1"}), 400

    column = int(column)
    layer = int(layer)
    error = _validate_slot(yard, area, column, layer)
    if error:
        return jsonify({"message": error}), 400

    occupied = _slot_occupied(yard_name, area, column, layer, container.id)
    if occupied:
        return jsonify({
            "message": "\u76ee\u6807\u7bb1\u4f4d\u5df2\u88ab\u5360\u7528",
            "container": occupied.to_dict()
        }), 409

    # 集装箱入库：只在所有校验通过后写入位置，避免堆场库存出现脏数据。
    container.yard = yard_name
    container.area = area
    container.column = column
    container.layer = layer
    container.status = '\u5806\u573a\u5b58\u50a8'
    db.session.commit()

    return jsonify({
        "message": "\u96c6\u88c5\u7bb1\u5206\u914d\u6210\u529f",
        "data": container.to_dict(),
        "yard": yard.to_dict()
    })


@yard_bp.route('/smart_assign_ship', methods=['POST'])
def smart_assign_ship():
    """
    按船舶批量智能分配堆场。

    规则：
    1. 只使用 yard 表中的正式堆场，不把历史脏数据中的“一号堆场/二号堆场”当作堆场。
    2. 危险品优先危险品堆场，冷藏箱优先冷藏堆场，重箱优先重箱堆场，空箱优先空箱堆场。
    3. 同一船舶的集装箱优先分配到同一堆场同一区域，便于后续整船作业。
    """
    data = request.get_json() or {}
    ship_id = data.get('ship_id') or data.get('shipId')
    if not ship_id:
        return jsonify({"message": "\u7f3a\u5c11\u8239\u8236ID"}), 400

    ship = Ship.query.get_or_404(ship_id)
    yards = Yard.query.order_by(Yard.id).all()
    if not yards:
        return jsonify({"message": "\u6682\u65e0\u53ef\u7528\u5806\u573a"}), 400

    official_names = {yard.yard_name for yard in yards}
    containers = Container.query.filter(
        Container.ship_id == ship.id,
        Container.status != '\u79bb\u6e2f'
    ).order_by(Container.id).all()
    if not containers:
        return jsonify({"message": "\u8be5\u8239\u6682\u65e0\u9700\u5206\u914d\u7684\u96c6\u88c5\u7bb1"}), 404

    occupied = {
        (c.yard, c.area, c.column, c.layer)
        for c in Container.query.filter(Container.status != '\u79bb\u6e2f').all()
        if c.yard in official_names and c.area and c.column and c.layer
    }
    ship_plan_counts = {}
    assignments = []
    skipped = []

    for container in containers:
        # 已在正式堆场且箱位有效的箱子不重复分配，只参与集中度计算。
        if container.yard in official_names and container.area and container.column and container.layer:
            key = (container.yard, container.area)
            ship_plan_counts[key] = ship_plan_counts.get(key, 0) + 1
            skipped.append({
                "container": container.to_dict(),
                "reason": "\u5df2\u5728\u6b63\u5f0f\u5806\u573a\u7bb1\u4f4d\u4e2d"
            })
            continue

        slot = _find_best_slot(container, yards, occupied, ship_plan_counts)
        if slot is None:
            skipped.append({
                "container": container.to_dict(),
                "reason": "\u672a\u627e\u5230\u53ef\u7528\u7bb1\u4f4d"
            })
            continue

        yard, area, column, layer = slot
        container.yard = yard.yard_name
        container.area = area
        container.column = column
        container.layer = layer
        container.status = '\u5806\u573a\u5b58\u50a8'
        occupied.add((yard.yard_name, area, column, layer))
        key = (yard.yard_name, area)
        ship_plan_counts[key] = ship_plan_counts.get(key, 0) + 1
        assignments.append({
            "container": container.to_dict(),
            "yard": yard.yard_name,
            "area": area,
            "column": column,
            "layer": layer,
            "reason": "\u6309\u8239\u8236\u6279\u91cf\u96c6\u4e2d\u5206\u914d"
        })

    db.session.commit()
    return jsonify({
        "message": f"{ship.name} \u667a\u80fd\u5206\u914d\u5b8c\u6210",
        "ship": ship.to_dict(),
        "assignedCount": len(assignments),
        "skippedCount": len(skipped),
        "assignments": assignments,
        "skipped": skipped,
        "yards": [yard.to_dict() for yard in yards]
    })
