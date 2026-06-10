from datetime import datetime

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from Container.models.container_model import BillingRecord, Container, PickupAppointment, db


finance_bp = Blueprint('finance_bp', __name__, url_prefix='/api/finance')


def _now():
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def _next_bill_no():
    return f'BILL-{datetime.now().strftime("%Y%m%d%H%M%S%f")[:-3]}'


def _resolve_container(data):
    container_id = data.get('containerId') or data.get('container_id')
    if container_id:
        return Container.query.get(container_id)
    container_no = (data.get('containerNo') or data.get('container_no') or '').strip()
    if container_no:
        return Container.query.filter_by(container_no=container_no).first()
    return None


def _customer_for_container(container):
    if not container:
        return ''
    appointment = PickupAppointment.query.filter_by(container_id=container.id).order_by(PickupAppointment.id.desc()).first()
    return appointment.customer if appointment and appointment.customer else '默认客户'


def _estimate_amount(container, charge_type):
    base = 260 if charge_type == '危险品附加费' else 120
    if not container:
        return base
    if container.container_type and '40' in container.container_type:
        base *= 1.6
    if container.is_refrigerated:
        base += 80
    if container.is_dangerous:
        base += 180
    return round(base, 2)


def ensure_departure_bill(container, remark='离港自动计费'):
    """Generate one automatic departure bill without touching manual bills."""
    if not container:
        return None, False

    existing = BillingRecord.query.filter(
        BillingRecord.container_id == container.id,
        BillingRecord.remark == remark,
    ).first()
    if existing:
        return existing, False

    charge_type = '危险品附加费' if container.is_dangerous else '堆存费'
    bill = BillingRecord(
        bill_no=_next_bill_no(),
        container_id=container.id,
        customer=_customer_for_container(container),
        charge_type=charge_type,
        amount=_estimate_amount(container, charge_type),
        status='未结算',
        generated_at=_now(),
        remark=remark,
    )
    db.session.add(bill)
    return bill, True


@finance_bp.route('/summary', methods=['GET'])
def summary():
    bills = BillingRecord.query.order_by(BillingRecord.id.desc()).all()
    total = sum(float(item.amount or 0) for item in bills)
    settled = sum(float(item.amount or 0) for item in bills if item.status == '已结算')
    pending = total - settled
    return jsonify({
        "totalAmount": round(total, 2),
        "settledAmount": round(settled, 2),
        "pendingAmount": round(pending, 2),
        "billCount": len(bills),
        "pendingCount": sum(1 for item in bills if item.status != '已结算'),
    })


@finance_bp.route('/bills', methods=['GET'])
def list_bills():
    bills = BillingRecord.query.order_by(BillingRecord.id.desc()).all()
    return jsonify([item.to_dict() for item in bills])


@finance_bp.route('/bills', methods=['POST'])
def create_bill():
    data = request.get_json(silent=True) or {}
    container = _resolve_container(data)
    charge_type = (data.get('chargeType') or data.get('charge_type') or '堆存费').strip()
    amount = data.get('amount')
    bill = BillingRecord(
        bill_no=(data.get('billNo') or data.get('bill_no') or _next_bill_no()).strip(),
        container_id=container.id if container else None,
        customer=(data.get('customer') or _customer_for_container(container)).strip(),
        charge_type=charge_type,
        amount=float(amount) if amount not in (None, '') else _estimate_amount(container, charge_type),
        status=(data.get('status') or '未结算').strip(),
        generated_at=_now(),
        remark=(data.get('remark') or '').strip(),
    )
    db.session.add(bill)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "账单号已存在"}), 409
    return jsonify({"message": "账单已生成", "data": bill.to_dict()}), 201


@finance_bp.route('/bills/<int:bill_id>/settle', methods=['PUT'])
def settle_bill(bill_id):
    bill = BillingRecord.query.get_or_404(bill_id)
    bill.status = '已结算'
    bill.settled_at = _now()
    db.session.commit()
    return jsonify({"message": "账单已结算", "data": bill.to_dict()})


@finance_bp.route('/generate/container/<int:container_id>', methods=['POST'])
def generate_for_container(container_id):
    container = Container.query.get_or_404(container_id)
    bill, created = ensure_departure_bill(container, remark='按集装箱状态自动计费')
    db.session.commit()
    status_code = 201 if created else 200
    message = "账单已生成" if created else "该集装箱已有自动账单"
    return jsonify({"message": message, "data": bill.to_dict()}), status_code
