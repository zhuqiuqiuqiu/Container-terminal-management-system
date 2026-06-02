import math
import re
import threading
import time
from datetime import datetime
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from flask import Blueprint, current_app, jsonify, request
from sqlalchemy.exc import IntegrityError

from Container.models.container_model import Container, Equipment, Ship, Task, Yard, db


ship_bp = Blueprint('ship_bp', __name__, url_prefix='/ships')

STATUS_SCHEDULED = '\u8ba1\u5212\u4e2d'
STATUS_BERTHED = '\u5df2\u9760\u6cca'
STATUS_DEPARTED = '\u5df2\u79bb\u6e2f'
STATUS_ON_SHIP = '\u5728\u8239\u4e0a'
STATUS_UNLOADED = '\u5df2\u5378\u8239'
STATUS_TRANSFERRING = '\u8f6c\u8fd0\u4e2d'
STATUS_IN_YARD = '\u5806\u573a\u5b58\u50a8'
EQUIPMENT_IDLE = '\u7a7a\u95f2'
EQUIPMENT_WORKING = '\u5de5\u4f5c\u4e2d'
EQUIPMENT_FAULT = '\u6545\u969c'
TYPE_QUAY_CRANE = '\u5cb8\u6865'
TYPE_YARD_CRANE = '\u573a\u6865'
TYPE_AGV = 'AGV'

DEFAULT_BERTHS = [f'\u6cca\u4f4d{i}' for i in range(1, 7)]
EQUIPMENT_RATES = {
    'quayCrane': 30,
    'agv': 20,
    'yardCrane': 25,
}
BERTH_FRONT_CAPACITY = 2
YARD_TRANSFER_CAPACITY = 1
DEFAULT_SECONDS_PER_WORK_MINUTE = 1.0
WORKFLOW_RUNS = {}
WORKFLOW_LOCK = threading.Lock()


def _now():
    return datetime.now()


def _format_dt(value):
    return value.strftime('%Y-%m-%d %H:%M:%S')


def _normalize_payload(data):
    return {
        'name': (data.get('name') or data.get('shipName') or '').strip(),
        'voyage': (data.get('voyage') or '').strip(),
        'eta': data.get('eta') or data.get('ETA') or None,
        'etd': data.get('etd') or data.get('ETD') or None,
        'berth': (data.get('berth') or data.get('berthName') or '').strip() or None,
        'status': (data.get('status') or STATUS_SCHEDULED).strip(),
    }


@ship_bp.route('', methods=['GET'])
def list_ships():
    ships = Ship.query.order_by(Ship.id).all()
    return jsonify([ship.to_dict() for ship in ships])


@ship_bp.route('', methods=['POST'])
def create_ship():
    data = _normalize_payload(request.get_json(silent=True) or {})
    if not data['name'] or not data['voyage']:
        return jsonify({"message": "\u7f3a\u5c11\u8239\u540d\u6216\u822a\u6b21"}), 400

    ship = Ship(**data)
    db.session.add(ship)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "\u8239\u8236\u6570\u636e\u4fdd\u5b58\u5931\u8d25"}), 409

    return jsonify({"message": "\u65b0\u589e\u8239\u8236\u6210\u529f", "data": ship.to_dict()}), 201


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
    if data.get('status'):
        ship.status = data['status']

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"message": "\u8239\u8236\u6570\u636e\u4fdd\u5b58\u5931\u8d25"}), 409

    return jsonify({"message": "\u4fee\u6539\u8239\u8236\u6210\u529f", "data": ship.to_dict()})


@ship_bp.route('/<int:ship_id>', methods=['DELETE'])
def delete_ship(ship_id):
    ship = Ship.query.get_or_404(ship_id)
    db.session.delete(ship)
    db.session.commit()
    return jsonify({"message": "\u5220\u9664\u8239\u8236\u6210\u529f"})


def _safe_filename_ship_name(filename):
    name = Path(filename or '').stem.strip()
    return name or '\u672a\u547d\u540d\u8239\u8236'


def _column_index_from_ref(ref):
    match = re.match(r'([A-Z]+)', ref or '')
    if not match:
        return 0
    col = 0
    for char in match.group(1):
        col = col * 26 + (ord(char) - 64)
    return max(col - 1, 0)


def _read_cell_value(cell, shared_strings):
    cell_type = cell.attrib.get('t')
    if cell_type == 'inlineStr':
        text_node = cell.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}is/{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t')
        return (text_node.text or '').strip() if text_node is not None else ''

    value_node = cell.find('{http://schemas.openxmlformats.org/spreadsheetml/2006/main}v')
    value = value_node.text if value_node is not None else ''
    if cell_type == 's':
        try:
            return shared_strings[int(value)]
        except (ValueError, IndexError, TypeError):
            return ''
    if cell_type == 'b':
        return '1' if value == '1' else '0'
    return (value or '').strip()


def _read_xlsx_rows(file_storage):
    raw = file_storage.read()
    if not raw:
        raise ValueError('Excel \u6587\u4ef6\u4e3a\u7a7a')

    namespace = {
        'a': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main',
        'r': 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
    }
    rel_namespace = {'p': 'http://schemas.openxmlformats.org/package/2006/relationships'}
    shared_strings = []

    with ZipFile(BytesIO(raw)) as zf:
        if 'xl/sharedStrings.xml' in zf.namelist():
            shared_root = ET.fromstring(zf.read('xl/sharedStrings.xml'))
            for si in shared_root.findall('a:si', namespace):
                texts = [node.text or '' for node in si.findall('.//a:t', namespace)]
                shared_strings.append(''.join(texts))

        workbook_root = ET.fromstring(zf.read('xl/workbook.xml'))
        first_sheet = workbook_root.find('a:sheets/a:sheet', namespace)
        if first_sheet is None:
            raise ValueError('Excel \u4e2d\u672a\u627e\u5230\u5de5\u4f5c\u8868')
        rel_id = first_sheet.attrib.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id')

        rel_root = ET.fromstring(zf.read('xl/_rels/workbook.xml.rels'))
        sheet_target = None
        for rel in rel_root.findall('p:Relationship', rel_namespace):
            if rel.attrib.get('Id') == rel_id:
                sheet_target = rel.attrib.get('Target')
                break
        if not sheet_target:
            sheet_target = 'worksheets/sheet1.xml'
        sheet_path = sheet_target if sheet_target.startswith('xl/') else f'xl/{sheet_target.lstrip("/")}'
        sheet_root = ET.fromstring(zf.read(sheet_path))

        rows = []
        for row in sheet_root.findall('.//a:sheetData/a:row', namespace):
            values = []
            for cell in row.findall('a:c', namespace):
                idx = _column_index_from_ref(cell.attrib.get('r'))
                while len(values) <= idx:
                    values.append('')
                values[idx] = _read_cell_value(cell, shared_strings)
            if any((value or '').strip() for value in values):
                rows.append(values)
        return rows


def _normalize_header(header):
    return re.sub(r'[\s\u3000]+', '', str(header or '').strip())


def _parse_bool(text):
    value = str(text or '').strip().lower()
    return value in ('1', 'true', 'yes', 'y', '\u662f', '\u6709')


def _parse_slot(text):
    match = re.search(r'(?:\u5217)?\s*(\d+)\s*(?:\u5c42)?\s*(\d+)', str(text or ''))
    if not match:
        return None, None
    return int(match.group(1)), int(match.group(2))


def _get_or_create_ship(ship_name, voyage=None):
    ship = Ship.query.filter_by(name=ship_name).first()
    if ship:
        if voyage:
            ship.voyage = voyage
        if not ship.status:
            ship.status = STATUS_SCHEDULED
        return ship, False

    ship = Ship(
        name=ship_name,
        voyage=voyage or f'IMP-{datetime.now().strftime("%Y%m%d%H%M%S")}',
        status=STATUS_SCHEDULED,
    )
    db.session.add(ship)
    db.session.flush()
    return ship, True


def _upsert_manifest_row(ship, row_data):
    container_no = row_data.get('container_no')
    if not container_no:
        return None, None, '\u7f3a\u5c11\u7bb1\u53f7', False

    container = Container.query.filter_by(container_no=container_no).first()
    created = False
    if container is None:
        container = Container(container_no=container_no, container_type=row_data.get('container_type') or '20GP')
        created = True
        db.session.add(container)

    container.ship_id = ship.id
    container.container_type = row_data.get('container_type') or container.container_type or '20GP'
    container.is_full = row_data.get('is_full', container.is_full)
    container.is_dangerous = row_data.get('is_dangerous', container.is_dangerous)
    container.is_refrigerated = row_data.get('is_refrigerated', container.is_refrigerated)
    container.status = row_data.get('status') or STATUS_ON_SHIP
    container.yard = row_data.get('yard') or ship.name
    container.area = row_data.get('area')
    container.column = row_data.get('column')
    container.layer = row_data.get('layer')

    db.session.flush()

    task = _upsert_task(
        task_no=f'IMP-{ship.id}-{container_no}',
        task_type='\u5378\u8239\u4f5c\u4e1a',
        container_id=container.id,
        from_pos=ship.name,
        to_pos='\u5f85\u5206\u914d\u5806\u573a',
        remark=row_data.get('remark') or '',
        status='pending',
    )
    task.priority = 1 if '\u6025' in str(row_data.get('remark') or '') else 3

    return container, task, None, created


@ship_bp.route('/import_manifest', methods=['POST'])
def import_manifest():
    file = request.files.get('file')
    voyage = (request.form.get('voyage') or '').strip()
    auto_run = (request.form.get('autoRunWorkflow') or '').lower() in ('1', 'true', 'yes')
    if not file:
        return jsonify({"message": "\u8bf7\u9009\u62e9 Excel \u6587\u4ef6"}), 400
    if not file.filename.lower().endswith('.xlsx'):
        return jsonify({"message": "\u76ee\u524d\u4ec5\u652f\u6301 .xlsx \u6587\u4ef6"}), 400

    ship_name = _safe_filename_ship_name(file.filename)
    try:
        rows = _read_xlsx_rows(file)
    except Exception as exc:
        return jsonify({"message": f"Excel \u89e3\u6790\u5931\u8d25\uff1a{exc}"}), 400

    if not rows:
        return jsonify({"message": "Excel \u4e2d\u6ca1\u6709\u53ef\u5bfc\u5165\u7684\u6570\u636e"}), 400

    headers = [_normalize_header(item) for item in rows[0]]
    header_map = {
        '\u7bb1\u53f7': 'container_no',
        '\u96c6\u88c5\u7bb1\u53f7': 'container_no',
        '\u7bb1\u578b': 'container_type',
        '\u88c5\u8f7d': 'load_status',
        '\u72b6\u6001': 'status',
        '\u5806\u573a': 'yard',
        '\u533a': 'area',
        '\u533a\u57df': 'area',
        '\u5217\u5c42': 'slot',
        '\u5371\u9669\u54c1': 'dangerous',
        '\u51b7\u85cf': 'reefer',
        '\u64cd\u4f5c': 'operation',
    }
    index_map = {}
    for idx, header in enumerate(headers):
        key = header_map.get(header)
        if key:
            index_map[key] = idx

    if 'container_no' not in index_map:
        return jsonify({"message": "Excel \u7f3a\u5c11\u201c\u7bb1\u53f7\u201d\u5217"}), 400

    ship, created_ship = _get_or_create_ship(ship_name, voyage)
    imported = []
    updated = []
    skipped = []

    for raw_row in rows[1:]:
        def get(col_name):
            idx = index_map.get(col_name)
            if idx is None or idx >= len(raw_row):
                return ''
            return str(raw_row[idx]).strip()

        container_no = get('container_no')
        if not container_no:
            skipped.append({'reason': '\u7f3a\u5c11\u7bb1\u53f7'})
            continue

        column, layer = _parse_slot(get('slot'))
        row_data = {
            'container_no': container_no,
            'container_type': get('container_type') or '20GP',
            'is_full': get('load_status') in ('\u91cd\u7bb1', '\u5df2\u88c5\u8f7d', 'full', 'loaded'),
            'status': get('status') or STATUS_ON_SHIP,
            'yard': get('yard') or ship.name,
            'area': get('area') or None,
            'column': column,
            'layer': layer,
            'is_dangerous': _parse_bool(get('dangerous')),
            'is_refrigerated': _parse_bool(get('reefer')),
            'remark': get('operation'),
        }

        try:
            container, task, error, created = _upsert_manifest_row(ship, row_data)
            if error:
                skipped.append({'containerNo': container_no, 'reason': error})
                continue
            if container and task:
                if created:
                    imported.append(container.to_dict())
                else:
                    updated.append(container.to_dict())
        except Exception as exc:
            skipped.append({'containerNo': container_no, 'reason': str(exc)})

    workflow_result = None
    if auto_run:
        try:
            workflow_result = _start_async_workflow(ship.id, current_app._get_current_object())
        except ValueError as exc:
            db.session.rollback()
            return jsonify({"message": str(exc)}), 400
    else:
        db.session.commit()

    return jsonify({
        "message": f"\u8239\u8236\u4efb\u52a1\u5bfc\u5165\u5b8c\u6210\uff1a{ship.name}",
        "ship": ship.to_dict(),
        "createdShip": created_ship,
        "importedCount": len(imported),
        "updatedCount": len(updated),
        "skippedCount": len(skipped),
        "containers": imported + updated,
        "skipped": skipped,
        "workflow": workflow_result,
    })


def _yard_matches_container(yard, container):
    text = (yard.yard_name or '') + (yard.usage_type or '')
    if container.is_dangerous:
        return '\u5371\u9669' in text
    if container.is_refrigerated:
        return '\u51b7\u85cf' in text or '\u51b7' in text
    if container.is_full:
        return '\u91cd' in text or '\u8fdb\u53e3' in text or '\u7efc\u5408' in text
    return '\u7a7a' in text or '\u51fa\u53e3' in text or '\u7efc\u5408' in text


def _find_best_slot(container, yards, occupied, ship_plan_counts):
    candidates = []
    for yard in yards:
        if yard.status not in ('\u542f\u7528', 'active'):
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
                    candidates.append((score, yard, area, column, layer))
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1].id, item[2], item[3], item[4]))
    return candidates[0][1:]


def _assign_berth(ship, now):
    occupied = {
        item.berth
        for item in Ship.query.filter(Ship.id != ship.id, Ship.status == STATUS_BERTHED).all()
        if item.berth
    }
    known_berths = list(dict.fromkeys(DEFAULT_BERTHS + [item.berth for item in Ship.query.all() if item.berth]))
    if ship.berth and ship.berth not in occupied:
        ship.status = STATUS_BERTHED
        ship.eta = ship.eta or _format_dt(now)
        return ship.berth
    for berth in known_berths:
        if berth not in occupied:
            ship.berth = berth
            ship.status = STATUS_BERTHED
            ship.eta = ship.eta or _format_dt(now)
            return berth
    return None


def _upsert_task(task_no, task_type, container_id, from_pos, to_pos, remark, status='completed', estimated_time=None, start_time=None, end_time=None):
    task = Task.query.filter_by(task_no=task_no).first()
    if task is None:
        task = Task(task_no=task_no)
        db.session.add(task)
    timestamp = _format_dt(_now())
    task.task_type = task_type
    task.container_id = container_id
    task.from_pos = from_pos
    task.to_pos = to_pos
    task.remark = remark
    task.status = status
    task.priority = task.priority or 3
    task.estimated_time = estimated_time
    task.actual_time = estimated_time if status == 'completed' else task.actual_time
    task.start_time = start_time or task.start_time
    task.end_time = end_time or task.end_time
    task.created_at = task.created_at or timestamp
    task.updated_at = timestamp
    return task


def _stage_minutes(container_count):
    return {
        'quayCrane': math.ceil(container_count / EQUIPMENT_RATES['quayCrane'] * 60),
        'agv': math.ceil(container_count / EQUIPMENT_RATES['agv'] * 60),
        'yardCrane': math.ceil(container_count / EQUIPMENT_RATES['yardCrane'] * 60),
    }


def _sleep_seconds(stage_minutes, container_count, seconds_per_work_minute):
    if container_count <= 0:
        return 0
    return max(0.5, (stage_minutes / container_count) * seconds_per_work_minute)


def _workflow_snapshot(ship_id):
    with WORKFLOW_LOCK:
        state = WORKFLOW_RUNS.get(ship_id)
        return dict(state) if state else None


def _update_workflow_state(ship_id, **patch):
    patch['updatedAt'] = _format_dt(_now())
    with WORKFLOW_LOCK:
        state = WORKFLOW_RUNS.setdefault(ship_id, {"shipId": ship_id})
        state.update(patch)
        return dict(state)


def _build_slot_plan(containers, yards):
    official_names = {yard.yard_name for yard in yards}
    occupied = {
        (c.yard, c.area, c.column, c.layer)
        for c in Container.query.filter(Container.status != STATUS_DEPARTED).all()
        if c.yard in official_names and c.area and c.column and c.layer
    }
    ship_plan_counts = {}
    assignments = {}
    skipped = []

    for container in containers:
        if container.yard in official_names and container.area and container.column and container.layer:
            yard_name, area, column, layer = container.yard, container.area, container.column, container.layer
        else:
            slot = _find_best_slot(container, yards, occupied, ship_plan_counts)
            if slot is None:
                skipped.append({
                    "container": container.to_dict(),
                    "reason": "\u672a\u627e\u5230\u53ef\u7528\u7bb1\u4f4d",
                })
                continue
            yard, area, column, layer = slot
            yard_name = yard.yard_name
            occupied.add((yard_name, area, column, layer))

        key = (yard_name, area)
        ship_plan_counts[key] = ship_plan_counts.get(key, 0) + 1
        assignments[container.id] = {
            "yard": yard_name,
            "area": area,
            "column": column,
            "layer": layer,
            "transferPoint": f'{yard_name}\u8f6c\u8fd0\u70b9',
            "slotText": f'{yard_name}/{area}/\u5217{column}/\u5c42{layer}',
        }

    return assignments, skipped


def _complete_task(task_no):
    task = Task.query.filter_by(task_no=task_no).first()
    if task:
        _finish_task(task)


def _assign_equipment(task, equipment_type, location_hint=None):
    if not task or task.equipment_id:
        return None

    db.session.flush()

    query = Equipment.query.filter(
        Equipment.equipment_type == equipment_type,
        Equipment.status == EQUIPMENT_IDLE,
    )
    if location_hint:
        equipment = query.filter(Equipment.location.like(f'%{location_hint}%')).order_by(Equipment.id).first()
    else:
        equipment = None
    if equipment is None:
        equipment = query.order_by(Equipment.id).first()

    if equipment is None:
        query = Equipment.query.filter(
            Equipment.equipment_type == equipment_type,
            Equipment.status != EQUIPMENT_FAULT,
        )
        if location_hint:
            equipment = query.filter(Equipment.location.like(f'%{location_hint}%')).order_by(Equipment.id).first()
        else:
            equipment = None
        if equipment is None:
            equipment = query.order_by(Equipment.id).first()

    if equipment is None:
        return None

    task.equipment_id = equipment.id
    equipment.current_task_id = task.id
    equipment.status = EQUIPMENT_WORKING
    equipment.updated_at = _format_dt(_now())
    return equipment


def _berth_front_count(ship_id):
    return Container.query.filter(
        Container.ship_id == ship_id,
        Container.status == STATUS_UNLOADED,
    ).count()


def _transfer_point_count(ship_id, yard_name):
    return Container.query.filter(
        Container.ship_id == ship_id,
        Container.status == STATUS_TRANSFERRING,
        Container.yard == yard_name,
    ).count()


def _wait_for_buffer_capacity(ship_id, buffer_name, count_func, capacity, seconds_per_work_minute):
    wait_seconds = max(0.5, seconds_per_work_minute)
    while count_func() >= capacity:
        _update_workflow_state(
            ship_id,
            stage='\u7b49\u5f85\u7f13\u51b2\u533a',
            message=f'{buffer_name} \u5df2\u8fbe\u4e0a\u9650 {capacity} \u7bb1\uff0c\u7b49\u5f85\u4e0b\u9053\u5de5\u5e8f\u91ca\u653e\u4f4d\u7f6e',
        )
        time.sleep(wait_seconds)


def _release_task_equipment(task):
    if not task or not task.equipment_id:
        return
    equipment = Equipment.query.get(task.equipment_id)
    if equipment and equipment.current_task_id == task.id:
        equipment.current_task_id = None
        equipment.status = EQUIPMENT_IDLE
        equipment.updated_at = _format_dt(_now())


def _finish_task(task):
    finished_at = _format_dt(_now())
    task.status = 'completed'
    task.end_time = finished_at
    task.updated_at = finished_at
    task.actual_time = task.estimated_time
    _release_task_equipment(task)


def _run_workflow_worker(app, ship_id, seconds_per_work_minute):
    with app.app_context():
        try:
            ship = Ship.query.get(ship_id)
            if not ship:
                _update_workflow_state(ship_id, status='failed', stage='\u5f02\u5e38', message='\u8239\u8236\u4e0d\u5b58\u5728')
                return

            containers = Container.query.filter(
                Container.ship_id == ship.id,
                Container.status != STATUS_DEPARTED,
            ).order_by(Container.id).all()
            status_priority = {
                STATUS_TRANSFERRING: 0,
                STATUS_UNLOADED: 1,
                STATUS_ON_SHIP: 2,
                STATUS_IN_YARD: 3,
            }
            containers.sort(key=lambda item: (status_priority.get(item.status, 4), item.id))
            yards = Yard.query.order_by(Yard.id).all()
            if not containers:
                raise ValueError('\u8be5\u8239\u6682\u65e0\u9700\u5904\u7406\u7684\u96c6\u88c5\u7bb1')
            if not yards:
                raise ValueError('\u6682\u65e0\u53ef\u7528\u5806\u573a')

            stage_minutes = _stage_minutes(len(containers))
            now = _now()
            berth = _assign_berth(ship, now)
            if not berth:
                raise ValueError('\u5f53\u524d\u6ca1\u6709\u7a7a\u95f2\u6cca\u4f4d')

            ship.eta = ship.eta or _format_dt(now)
            ship.status = STATUS_BERTHED
            db.session.commit()

            _update_workflow_state(
                ship_id,
                status='running',
                stage='\u5cb8\u6865\u5378\u8239',
                message=f'{ship.name} \u5df2\u9760\u6cca {berth}\uff0c\u5cb8\u6865\u5f00\u59cb\u5378\u8239',
                releasedBerth=None,
                containerCount=len(containers),
                assignedCount=0,
                skippedCount=0,
                completedCount=0,
                equipmentRates=EQUIPMENT_RATES,
                stageMinutes=stage_minutes,
                totalMinutes=sum(stage_minutes.values()),
                progress=5,
            )

            assignments, skipped = _build_slot_plan(containers, yards)
            qc_sleep = _sleep_seconds(stage_minutes['quayCrane'], len(containers), seconds_per_work_minute)
            agv_sleep = _sleep_seconds(stage_minutes['agv'], max(len(assignments), 1), seconds_per_work_minute)
            yc_sleep = _sleep_seconds(stage_minutes['yardCrane'], max(len(assignments), 1), seconds_per_work_minute)
            total_operations = len(containers) + len(assignments) * 2
            finished_operations = 0
            assigned_count = 0

            _update_workflow_state(
                ship_id,
                stage='\u6d41\u6c34\u4f5c\u4e1a',
                message='\u5f00\u59cb\u6309\u5355\u7bb1\u6d41\u6c34\u7ebf\u63a8\u8fdb\uff1a\u5cb8\u6865\u5378\u8239 \u2192 AGV\u8f6c\u8fd0 \u2192 \u573a\u6865\u5165\u5806',
                skippedCount=len(skipped),
                progress=5,
            )

            for index, container in enumerate(containers, start=1):
                rec = assignments.get(container.id)

                start_text = _format_dt(_now())
                qc_task_no = f'QC-{ship.id}-{container.container_no}'
                qc_task = Task.query.filter_by(task_no=qc_task_no).first()
                if container.status == STATUS_ON_SHIP:
                    _wait_for_buffer_capacity(
                        ship_id,
                        '\u5cb8\u6865-AGV\u4ea4\u63a5\u70b9',
                        lambda: _berth_front_count(ship.id),
                        BERTH_FRONT_CAPACITY,
                        seconds_per_work_minute,
                    )
                    qc_task = _upsert_task(
                        task_no=qc_task_no,
                        task_type='\u5cb8\u6865\u5378\u8239',
                        container_id=container.id,
                        from_pos=f'{ship.name}/{berth}',
                        to_pos='\u6cca\u4f4d\u524d\u6cbf',
                        remark='\u5cb8\u6865\u6548\u7387 30 \u7bb1/h',
                        status='in-progress',
                        estimated_time=math.ceil(60 / EQUIPMENT_RATES['quayCrane']),
                        start_time=start_text,
                    )
                    qc_equipment = _assign_equipment(qc_task, TYPE_QUAY_CRANE)
                    if qc_equipment:
                        qc_task.to_pos = f'{qc_equipment.name}-AGV\u4ea4\u63a5\u70b9'
                    db.session.commit()
                    _update_workflow_state(
                        ship_id,
                        stage='\u5cb8\u6865\u5378\u8239',
                        message=f'\u5cb8\u6865\u6b63\u5728\u5378 {container.container_no}\uff08{index}/{len(containers)}\uff09',
                        completedCount=index - 1,
                        progress=5 + round(finished_operations / total_operations * 90),
                    )
                    time.sleep(qc_sleep)
                    container.status = STATUS_UNLOADED
                    _finish_task(qc_task)
                elif qc_task and qc_task.status != 'completed':
                    _finish_task(qc_task)
                finished_operations += 1
                db.session.commit()
                _update_workflow_state(
                    ship_id,
                    stage='\u5cb8\u6865\u5378\u8239',
                    message=f'\u5cb8\u6865\u5df2\u5378\u8239 {index}/{len(containers)} \u7bb1',
                    completedCount=index,
                    progress=5 + round(finished_operations / total_operations * 90),
                )
                qc_handoff_pos = qc_task.to_pos if qc_task else '\u6cca\u4f4d\u524d\u6cbf'

                if not rec:
                    _update_workflow_state(
                        ship_id,
                        stage='\u7b49\u5f85\u7bb1\u4f4d',
                        message=f'{container.container_no} \u672a\u627e\u5230\u53ef\u7528\u7bb1\u4f4d\uff0c\u5df2\u505c\u5728\u6cca\u4f4d\u524d\u6cbf\u7b49\u5f85\u8c03\u5ea6',
                        progress=5 + round(finished_operations / total_operations * 90),
                    )
                    continue

                agv_task_no = f'AGV-{ship.id}-{container.container_no}'
                agv_task = Task.query.filter_by(task_no=agv_task_no).first()
                agv_done = (
                    container.status in (STATUS_TRANSFERRING, STATUS_IN_YARD) or
                    (agv_task and agv_task.status == 'completed')
                )
                if not agv_done:
                    _wait_for_buffer_capacity(
                        ship_id,
                        f"{rec['transferPoint']}\uff08AGV-\u573a\u6865\u4ea4\u63a5\u70b9\uff09",
                        lambda yard_name=rec['yard']: _transfer_point_count(ship.id, yard_name),
                        YARD_TRANSFER_CAPACITY,
                        seconds_per_work_minute,
                    )
                    agv_task = _upsert_task(
                        task_no=agv_task_no,
                        task_type='AGV\u8f6c\u8fd0',
                        container_id=container.id,
                        from_pos=qc_handoff_pos or '\u6cca\u4f4d\u524d\u6cbf',
                        to_pos=rec['transferPoint'],
                        remark=f"\u6700\u7ec8\u7bb1\u4f4d {rec['slotText']}\uff1bAGV\u6548\u7387 20 \u7bb1/h",
                        status='in-progress',
                        estimated_time=math.ceil(60 / EQUIPMENT_RATES['agv']),
                        start_time=_format_dt(_now()),
                    )
                    _assign_equipment(agv_task, TYPE_AGV)
                    container.status = STATUS_TRANSFERRING
                    db.session.commit()
                    _update_workflow_state(
                        ship_id,
                        stage='AGV\u8f6c\u8fd0',
                        message=f"AGV \u6b63\u5728\u5c06 {container.container_no} \u9001\u5f80 {rec['transferPoint']}",
                        progress=5 + round(finished_operations / total_operations * 90),
                    )
                    time.sleep(agv_sleep)
                    _finish_task(agv_task)
                elif agv_task and agv_task.status != 'completed':
                    _finish_task(agv_task)
                finished_operations += 1
                db.session.commit()
                _update_workflow_state(
                    ship_id,
                    stage='AGV\u8f6c\u8fd0',
                    message=f"AGV \u5df2\u5c06 {container.container_no} \u9001\u8fbe {rec['transferPoint']}\uff0c\u573a\u6865\u53ef\u7acb\u5373\u63a5\u7ba1",
                    progress=5 + round(finished_operations / total_operations * 90),
                )

                yc_task_no = f'YC-{ship.id}-{container.container_no}'
                yc_task = Task.query.filter_by(task_no=yc_task_no).first()
                if container.status != STATUS_IN_YARD:
                    yc_task = _upsert_task(
                        task_no=yc_task_no,
                        task_type='\u573a\u6865\u5165\u5806',
                        container_id=container.id,
                        from_pos=rec['transferPoint'],
                        to_pos=rec['slotText'],
                        remark='\u573a\u6865\u6548\u7387 25 \u7bb1/h',
                        status='in-progress',
                        estimated_time=math.ceil(60 / EQUIPMENT_RATES['yardCrane']),
                        start_time=_format_dt(_now()),
                    )
                    _assign_equipment(yc_task, TYPE_YARD_CRANE)
                    db.session.commit()
                    _update_workflow_state(
                        ship_id,
                        stage='\u573a\u6865\u5165\u5806',
                        message=f"\u573a\u6865\u6b63\u5728\u4ece {rec['transferPoint']} \u6293\u53d6 {container.container_no} \u653e\u5165 {rec['slotText']}",
                        progress=5 + round(finished_operations / total_operations * 90),
                    )
                    time.sleep(yc_sleep)
                    container.yard = rec['yard']
                    container.area = rec['area']
                    container.column = rec['column']
                    container.layer = rec['layer']
                    container.status = STATUS_IN_YARD
                    _finish_task(yc_task)
                elif yc_task and yc_task.status != 'completed':
                    _finish_task(yc_task)
                finished_operations += 1
                assigned_count += 1
                db.session.commit()
                _update_workflow_state(
                    ship_id,
                    message=f'\u573a\u6865\u5df2\u5165\u5806 {assigned_count}/{len(assignments)} \u7bb1',
                    assignedCount=assigned_count,
                    progress=5 + round(finished_operations / total_operations * 90),
                )

            released_berth = ship.berth
            ship.etd = _format_dt(_now())
            ship.status = STATUS_DEPARTED
            ship.berth = None
            db.session.commit()
            _update_workflow_state(
                ship_id,
                status='completed',
                stage='\u5df2\u79bb\u6e2f',
                message=f'{ship.name} \u5378\u8239\u5165\u5806\u5b8c\u6210\uff0c\u5df2\u79bb\u6e2f\u5e76\u91ca\u653e {released_berth}',
                releasedBerth=released_berth,
                assignedCount=assigned_count,
                skippedCount=len(skipped),
                progress=100,
            )
        except Exception as exc:
            db.session.rollback()
            _update_workflow_state(
                ship_id,
                status='failed',
                stage='\u5f02\u5e38',
                message=f'\u540e\u53f0\u4f5c\u4e1a\u5931\u8d25\uff1a{exc}',
            )


def _start_async_workflow(ship_id, app, seconds_per_work_minute=None):
    ship = Ship.query.get_or_404(ship_id)
    containers = Container.query.filter(
        Container.ship_id == ship.id,
        Container.status != STATUS_DEPARTED,
    ).order_by(Container.id).all()
    if not containers:
        raise ValueError('\u8be5\u8239\u6682\u65e0\u9700\u5904\u7406\u7684\u96c6\u88c5\u7bb1')
    if not Yard.query.first():
        raise ValueError('\u6682\u65e0\u53ef\u7528\u5806\u573a')

    running = _workflow_snapshot(ship_id)
    if running and running.get('status') in ('queued', 'running'):
        return running

    seconds_per_work_minute = seconds_per_work_minute or DEFAULT_SECONDS_PER_WORK_MINUTE
    stage_minutes = _stage_minutes(len(containers))
    state = _update_workflow_state(
        ship_id,
        status='queued',
        stage='\u7b49\u5f85\u542f\u52a8',
        message=f'{ship.name} \u5df2\u52a0\u5165\u540e\u53f0\u81ea\u52a8\u4f5c\u4e1a\u961f\u5217',
        ship=ship.to_dict(),
        containerCount=len(containers),
        assignedCount=0,
        skippedCount=0,
        completedCount=0,
        releasedBerth=None,
        equipmentRates=EQUIPMENT_RATES,
        stageMinutes=stage_minutes,
        totalMinutes=sum(stage_minutes.values()),
        secondsPerWorkMinute=seconds_per_work_minute,
        progress=0,
        startedAt=_format_dt(_now()),
    )
    db.session.commit()

    worker = threading.Thread(
        target=_run_workflow_worker,
        args=(app, ship_id, seconds_per_work_minute),
        daemon=True,
    )
    worker.start()
    return state


@ship_bp.route('/<int:ship_id>/workflow', methods=['POST'])
def execute_ship_workflow(ship_id):
    data = request.get_json(silent=True) or {}
    seconds_per_work_minute = float(data.get('secondsPerWorkMinute') or DEFAULT_SECONDS_PER_WORK_MINUTE)
    try:
        result = _start_async_workflow(
            ship_id,
            current_app._get_current_object(),
            seconds_per_work_minute=seconds_per_work_minute,
        )
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"message": str(exc)}), 400
    except Exception as exc:
        db.session.rollback()
        return jsonify({"message": f"\u5de5\u4f5c\u6d41\u542f\u52a8\u5931\u8d25\uff1a{exc}"}), 500

    return jsonify({
        "message": result.get('message') or "\u540e\u53f0\u81ea\u52a8\u4f5c\u4e1a\u5df2\u542f\u52a8",
        **result,
    })


@ship_bp.route('/<int:ship_id>/workflow/status', methods=['GET'])
def get_ship_workflow_status(ship_id):
    state = _workflow_snapshot(ship_id)
    ship = Ship.query.get_or_404(ship_id)
    containers = Container.query.filter(Container.ship_id == ship.id).all()
    if not state:
        stage_minutes = _stage_minutes(len(containers)) if containers else {'quayCrane': 0, 'agv': 0, 'yardCrane': 0}
        state = {
            "shipId": ship.id,
            "ship": ship.to_dict(),
            "status": "idle",
            "stage": "\u672a\u542f\u52a8",
            "message": "\u5c1a\u672a\u542f\u52a8\u540e\u53f0\u81ea\u52a8\u4f5c\u4e1a",
            "containerCount": len(containers),
            "assignedCount": sum(1 for c in containers if c.status == STATUS_IN_YARD),
            "completedCount": 0,
            "skippedCount": 0,
            "releasedBerth": None,
            "equipmentRates": EQUIPMENT_RATES,
            "stageMinutes": stage_minutes,
            "totalMinutes": sum(stage_minutes.values()),
            "progress": 100 if ship.status == STATUS_DEPARTED else 0,
        }
    else:
        state["ship"] = ship.to_dict()
    return jsonify(state)
