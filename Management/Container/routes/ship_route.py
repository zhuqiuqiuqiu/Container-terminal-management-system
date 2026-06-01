from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from Container.models.container_model import Ship, db


ship_bp = Blueprint('ship_bp', __name__, url_prefix='/ships')


def _normalize_payload(data):
    return {
        'name': (data.get('name') or data.get('shipName') or '').strip(),
        'voyage': (data.get('voyage') or '').strip(),
        'eta': data.get('eta') or data.get('ETA') or None,
        'etd': data.get('etd') or data.get('ETD') or None,
        'berth': (data.get('berth') or data.get('berthName') or '').strip() or None,
        'status': (data.get('status') or '计划中').strip(),
    }


@ship_bp.route('', methods=['GET'])
def list_ships():
    ships = Ship.query.order_by(Ship.id).all()
    return jsonify([ship.to_dict() for ship in ships])


@ship_bp.route('', methods=['POST'])
def create_ship():
    data = _normalize_payload(request.get_json(silent=True) or {})
    if not data['name'] or not data['voyage']:
        return jsonify({"message": "缺少船名或航次"}), 400

    ship = Ship(**data)
    db.session.add(ship)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "船舶数据保存失败"}), 409

    return jsonify({"message": "新增船舶成功", "data": ship.to_dict()}), 201


@ship_bp.route('/<int:ship_id>', methods=['PUT'])
def update_ship(ship_id):
    ship = Ship.query.get_or_404(ship_id)
    data = _normalize_payload(request.get_json(silent=True) or {})

    if data['name']:
        ship.name = data['name']
    if data['voyage']:
        ship.voyage = data['voyage']
    if 'eta' in data:
        ship.eta = data['eta']
    if 'etd' in data:
        ship.etd = data['etd']
    if 'berth' in data:
        ship.berth = data['berth']
    if 'status' in data and data['status']:
        ship.status = data['status']

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "船舶数据保存失败"}), 409

    return jsonify({"message": "修改船舶成功", "data": ship.to_dict()})


@ship_bp.route('/<int:ship_id>', methods=['DELETE'])
def delete_ship(ship_id):
    ship = Ship.query.get_or_404(ship_id)
    db.session.delete(ship)
    db.session.commit()
    return jsonify({"message": "删除船舶成功"})
