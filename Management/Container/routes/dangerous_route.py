from flask import Blueprint, jsonify

from Container.models.container_model import Container, Yard, db
from Container.routes.yard_route import find_best_slot_for_container, is_dangerous_yard


dangerous_bp = Blueprint('dangerous_bp', __name__, url_prefix='/api/dangerous')


def _dangerous_yards():
    return [yard for yard in Yard.query.order_by(Yard.id).all() if is_dangerous_yard(yard)]


def _in_dangerous_yard(container):
    yard = Yard.query.filter_by(yard_name=container.yard).first() if container.yard else None
    return bool(yard and is_dangerous_yard(yard))


@dangerous_bp.route('/overview', methods=['GET'])
def overview():
    containers = Container.query.filter_by(is_dangerous=True).order_by(Container.id.desc()).all()
    violations = [item for item in containers if not _in_dangerous_yard(item)]
    yards = _dangerous_yards()
    return jsonify({
        "stats": {
            "dangerousCount": len(containers),
            "compliantCount": len(containers) - len(violations),
            "violationCount": len(violations),
            "dangerousYardCount": len(yards),
        },
        "containers": [item.to_dict() for item in containers],
        "violations": [item.to_dict() for item in violations],
        "dangerousYards": [yard.to_dict() for yard in yards],
    })


@dangerous_bp.route('/reassign', methods=['POST'])
def reassign_violations():
    yards = Yard.query.order_by(Yard.id).all()
    dangerous_yards = [yard for yard in yards if is_dangerous_yard(yard)]
    if not dangerous_yards:
        return jsonify({"message": "暂无危险品堆场，请先在堆场管理中创建危险品堆场"}), 400

    occupied = {
        (c.yard, c.area, c.column, c.layer)
        for c in Container.query.filter(Container.status != '离港').all()
        if c.yard and c.area and c.column and c.layer
    }
    ship_plan_counts = {}
    assigned = []
    skipped = []

    for container in Container.query.filter_by(is_dangerous=True).order_by(Container.id).all():
        if _in_dangerous_yard(container) and container.area and container.column and container.layer:
            continue
        slot = find_best_slot_for_container(container, dangerous_yards, occupied, ship_plan_counts)
        if not slot:
            skipped.append({"container": container.to_dict(), "reason": "危险品堆场无可用箱位"})
            continue
        yard, area, column, layer = slot
        container.yard = yard.yard_name
        container.area = area
        container.column = column
        container.layer = layer
        container.status = '堆场存储'
        occupied.add((yard.yard_name, area, column, layer))
        assigned.append(container.to_dict())

    db.session.commit()
    return jsonify({
        "message": f"危险品箱位校正完成，已调整 {len(assigned)} 个",
        "assignedCount": len(assigned),
        "skippedCount": len(skipped),
        "assigned": assigned,
        "skipped": skipped,
    })
